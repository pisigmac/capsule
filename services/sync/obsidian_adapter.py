"""Obsidian PKM vault integration for Capsule.

Translates [[WikiLinks]], normalizes nested #tags, preserves custom frontmatter,
and links notes into the Capsule relationship graph.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

import yaml
from sqlalchemy.orm import Session

from services.shared.models import Capsule, CapsuleRelationship
from services.store.store import CapsuleStore, content_hash

logger = logging.getLogger(__name__)

WIKILINK_RE = re.compile(r"\[\[(.*?)\]\]")
HASHTAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z0-9_\-/]+)")


@dataclass
class WikiLink:
    """An Obsidian [[WikiLink]] reference extracted from markdown content."""

    raw: str
    target: str
    display_text: Optional[str] = None
    heading: Optional[str] = None


@dataclass
class ParsedObsidianNote:
    """A parsed Obsidian note with frontmatter, tags, and WikiLinks."""

    file_path: Path
    topic: str
    content: str
    tags: List[str] = field(default_factory=list)
    wikilinks: List[WikiLink] = field(default_factory=list)
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    capsule_id: Optional[str] = None


@dataclass
class ObsidianSyncResult:
    """Result of an Obsidian vault sync run."""

    scanned_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    deduped_count: int = 0
    linked_count: int = 0
    notes: List[ParsedObsidianNote] = field(default_factory=list)


def extract_wikilinks(text: str) -> List[WikiLink]:
    """Extract all [[WikiLinks]] from markdown text."""
    links: List[WikiLink] = []
    for match in WIKILINK_RE.finditer(text):
        inner = match.group(1).strip()
        if not inner:
            continue

        display_text = None
        if "|" in inner:
            target_part, display_part = inner.split("|", 1)
            display_text = display_part.strip()
        else:
            target_part = inner

        heading = None
        if "#" in target_part:
            target_clean, heading_part = target_part.split("#", 1)
            target_clean = target_clean.strip()
            heading = heading_part.strip()
        else:
            target_clean = target_part.strip()

        if target_clean:
            links.append(
                WikiLink(
                    raw=match.group(0),
                    target=target_clean,
                    display_text=display_text,
                    heading=heading,
                )
            )

    return links


def extract_obsidian_tags(text: str) -> List[str]:
    """Extract and normalize Obsidian #tags (including nested tags like #dev/python)."""
    tags: Set[str] = set()

    # Filter out code blocks to avoid extracting # comments in code
    in_code_block = False
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            cleaned_lines.append(line)

    clean_text = "\n".join(cleaned_lines)

    for match in HASHTAG_RE.finditer(clean_text):
        raw_tag = match.group(1).strip()
        # Ignore numeric hex color codes like #fff or #123456
        if re.match(r"^[0-9a-fA-F]{3,8}$", raw_tag):
            continue

        # Handle nested tags: #database/postgres -> database, postgres, database-postgres
        parts = [p.lower().strip() for p in raw_tag.split("/") if p.strip()]
        for p in parts:
            if len(p) >= 2:
                tags.add(p)
        if len(parts) > 1:
            tags.add("-".join(parts))

    return sorted(tags)


class ObsidianAdapter:
    """Parses and converts Obsidian notes into Capsule representations."""

    def parse_note(self, file_path: Path, vault_root: Optional[Path] = None) -> ParsedObsidianNote:
        """Parse an individual Obsidian markdown note."""
        path = Path(file_path).resolve()
        raw_text = path.read_text(encoding="utf-8", errors="replace")

        # 1. Parse YAML frontmatter if present
        frontmatter: Dict[str, Any] = {}
        body = raw_text
        if raw_text.startswith("---"):
            lines = raw_text.splitlines(keepends=True)
            end_idx = -1
            for idx in range(1, len(lines)):
                if lines[idx].strip() == "---":
                    end_idx = idx
                    break
            if end_idx != -1:
                fm_text = "".join(lines[1:end_idx])
                body = "".join(lines[end_idx + 1:])
                try:
                    loaded = yaml.safe_load(fm_text)
                    if isinstance(loaded, dict):
                        frontmatter = loaded
                except Exception:
                    pass

        # 2. Extract Topic
        topic = ""
        if frontmatter.get("topic"):
            topic = str(frontmatter["topic"]).strip()
        elif frontmatter.get("title"):
            topic = str(frontmatter["title"]).strip()
        else:
            # Check for top-level H1 in body
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    topic = stripped[2:].strip()
                    break

        if not topic:
            # Fallback to note file stem (e.g. "JWT Auth Flow.md" -> "JWT Auth Flow")
            topic = path.stem

        # 3. Extract Tags
        tags: Set[str] = set()
        # From frontmatter
        fm_tags = frontmatter.get("tags") or []
        if isinstance(fm_tags, list):
            for t in fm_tags:
                tags.add(str(t).lower().strip())
        elif isinstance(fm_tags, str):
            for t in fm_tags.split(","):
                tags.add(t.lower().strip())

        # From inline #tags
        inline_tags = extract_obsidian_tags(body)
        for t in inline_tags:
            tags.add(t)

        # 4. Extract WikiLinks
        wikilinks = extract_wikilinks(body)

        # 5. Relative source path
        if vault_root:
            try:
                rel_path = path.relative_to(vault_root)
                source_label = f"obsidian:{rel_path}"
            except ValueError:
                source_label = f"obsidian:{path.name}"
        else:
            source_label = f"obsidian:{path.name}"

        capsule_id = frontmatter.get("id")
        if capsule_id:
            try:
                capsule_id = str(UUID(str(capsule_id)))
            except ValueError:
                capsule_id = None

        return ParsedObsidianNote(
            file_path=path,
            topic=topic,
            content=body.strip(),
            tags=sorted(tags),
            wikilinks=wikilinks,
            raw_frontmatter=frontmatter,
            source=source_label,
            capsule_id=capsule_id,
        )

    def resolve_wikilink_target(self, target: str, db: Session) -> Optional[Capsule]:
        """Resolve a [[WikiLink]] target string to an existing database Capsule."""
        # 1. Try UUID
        try:
            uid = str(UUID(target))
            capsule = db.query(Capsule).filter(Capsule.id == uid, Capsule.archived.is_(False)).first()
            if capsule:
                return capsule
        except (ValueError, TypeError):
            pass

        # 2. Match exact or case-insensitive topic
        capsule = (
            db.query(Capsule)
            .filter(Capsule.topic.ilike(target), Capsule.archived.is_(False))
            .first()
        )
        if capsule:
            return capsule

        # 3. Match file path or stem
        clean_stem = Path(target).stem.lower()
        candidates = db.query(Capsule).filter(Capsule.archived.is_(False)).all()
        for c in candidates:
            if c.file_path:
                stem = Path(c.file_path).stem.lower()
                if clean_stem in stem or stem.startswith(clean_stem):
                    return c

        return None


class ObsidianVaultSync:
    """Manages full or selective sync between an Obsidian vault and Capsule."""

    def __init__(
        self,
        store: CapsuleStore,
        vault_path: Path | str,
        tag_filter: Optional[str] = None,
    ) -> None:
        self.store = store
        self.vault_path = Path(vault_path).resolve()
        self.adapter = ObsidianAdapter()
        # Normalize filter tag (e.g. "#agent-memory" -> "agent-memory")
        clean_tag = tag_filter.lstrip("#").lower().strip() if tag_filter else None
        self.tag_filter = clean_tag

    def scan_notes(self) -> List[ParsedObsidianNote]:
        """Scan and parse markdown notes in the vault, applying optional tag filters."""
        if not self.vault_path.exists():
            return []

        parsed_notes: List[ParsedObsidianNote] = []
        for file_path in sorted(self.vault_path.rglob("*.md")):
            # Ignore .obsidian settings, trash, and hidden folders
            parts = file_path.parts
            if any(p.startswith(".") for p in parts) or ".trash" in parts:
                continue

            note = self.adapter.parse_note(file_path, vault_root=self.vault_path)
            # Enforce tag filter if configured
            if self.tag_filter:
                if self.tag_filter not in note.tags:
                    continue

            # Ensure minimum content size
            if len(note.topic) >= 3 and len(note.content) >= 10:
                parsed_notes.append(note)

        return parsed_notes

    def sync(self, dry_run: bool = False) -> ObsidianSyncResult:
        """Execute bidirectional sync and relationship graph construction."""
        notes = self.scan_notes()
        result = ObsidianSyncResult(scanned_count=len(notes), notes=notes)

        if dry_run or not notes:
            return result

        topic_to_capsule: Dict[str, Capsule] = {}

        # Pass 1: Upsert/Create capsules for all notes
        for note in notes:
            try:
                # Check if already exists by id or path
                existing = None
                if note.capsule_id:
                    existing = self.store.get(note.capsule_id)
                if not existing:
                    existing = self.store.db.query(Capsule).filter(Capsule.file_path == str(note.file_path)).first()

                if existing:
                    updated = self.store.update(
                        existing.id,
                        topic=note.topic,
                        content=note.content,
                        tags=note.tags,
                    )
                    topic_to_capsule[note.topic.lower()] = updated
                    result.updated_count += 1
                else:
                    capsule = self.store.create(
                        topic=note.topic,
                        content=note.content,
                        tags=note.tags,
                        source=note.source,
                        confidence="high",
                        capsule_id=note.capsule_id,
                    )
                    if getattr(capsule, "deduped", False):
                        result.deduped_count += 1
                    else:
                        result.created_count += 1
                    topic_to_capsule[note.topic.lower()] = capsule

            except Exception as exc:
                logger.warning("Error syncing Obsidian note %s: %s", note.file_path.name, exc)

        self.store.db.commit()

        # Pass 2: Resolve [[WikiLinks]] and create CapsuleRelationships
        for note in notes:
            source_cap = topic_to_capsule.get(note.topic.lower())
            if not source_cap:
                continue

            for wlink in note.wikilinks:
                target_cap = topic_to_capsule.get(wlink.target.lower())
                if not target_cap:
                    target_cap = self.adapter.resolve_wikilink_target(wlink.target, self.store.db)

                if target_cap and target_cap.id != source_cap.id:
                    try:
                        self.store.link(source_cap.id, target_cap.id, relationship_type="relates_to")
                        result.linked_count += 1
                    except Exception:
                        pass

        self.store.db.commit()
        return result
