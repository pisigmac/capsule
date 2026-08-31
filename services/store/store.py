"""File-first capsule store. Markdown files are canonical; SQLite is an index."""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from ..parser.parser import CapsuleParser, ParsedCapsule, ParsedRelationship
from ..shared.config import config
from ..shared.models import Capsule, CapsuleRelationship, Tag, utcnow

logger = logging.getLogger("capsule.store")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class StoreError(Exception):
    """Domain error for store operations."""


def slugify(topic: str) -> str:
    slug = _SLUG_RE.sub("-", topic.lower()).strip("-")
    return (slug[:60] or "capsule").rstrip("-")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CapsuleStore:
    """Read and write capsules through the filesystem, then update the index."""

    def __init__(
        self,
        db: Session,
        capsules_dir: Optional[Path] = None,
        parser: Optional[CapsuleParser] = None,
    ) -> None:
        self.db = db
        self.capsules_dir = Path(capsules_dir or config.capsules_dir)
        self.parser = parser or CapsuleParser()
        self.capsules_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, path: Path) -> Path:
        resolved = path.resolve()
        root = self.capsules_dir.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise StoreError("Capsule path is outside CAPSULES_DIR") from exc
        return resolved

    def _new_path(self, topic: str, capsule_id: str) -> Path:
        name = f"{slugify(topic)}-{capsule_id[:8]}.capsule.md"
        return self._safe_path(self.capsules_dir / name)

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    def _get_or_create_tag(self, name: str) -> Tag:
        cleaned = name.lower().strip()
        tag = self.db.query(Tag).filter(Tag.name == cleaned).first()
        if tag:
            return tag
        tag = Tag(name=cleaned)
        self.db.add(tag)
        self.db.flush()
        return tag

    def _apply_tags(self, capsule: Capsule, tags: Iterable[str]) -> None:
        capsule.tags.clear()
        seen = set()
        for name in tags:
            cleaned = name.lower().strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            capsule.tags.append(self._get_or_create_tag(cleaned))

    def _sync_outgoing_relationships(self, capsule: Capsule, rels: List[ParsedRelationship]) -> None:
        self.db.query(CapsuleRelationship).filter(
            CapsuleRelationship.from_capsule_id == capsule.id
        ).delete()
        for rel in rels:
            if rel.to_id == capsule.id:
                continue
            target = self.db.query(Capsule).filter(Capsule.id == rel.to_id).first()
            if not target:
                continue
            self.db.add(
                CapsuleRelationship(
                    from_capsule_id=capsule.id,
                    to_capsule_id=rel.to_id,
                    relationship_type=rel.relationship_type,
                )
            )

    def _parsed_from_row(self, capsule: Capsule) -> ParsedCapsule:
        rels = [
            ParsedRelationship(to_id=r.to_capsule_id, relationship_type=r.relationship_type)
            for r in capsule.outgoing_relationships
        ]
        return ParsedCapsule(
            topic=capsule.topic,
            content=capsule.content,
            tags=[t.name for t in capsule.tags],
            freshness=capsule.freshness,
            source=capsule.source,
            confidence=capsule.confidence,
            file_path=capsule.file_path,
            id=capsule.id,
            archived=capsule.archived,
            relationships=rels,
        )

    def write_file(self, capsule: Capsule) -> Path:
        if capsule.file_path:
            path = self._safe_path(Path(capsule.file_path))
        else:
            path = self._new_path(capsule.topic, capsule.id)
            capsule.file_path = str(path)
        markdown = self.parser.to_markdown(self._parsed_from_row(capsule))
        self._atomic_write(path, markdown)
        capsule.file_hash = file_sha256(path)
        capsule.file_path = str(path)
        return path

    def upsert_from_file(self, file_path: Path, persist_missing_id: bool = True) -> Capsule:
        path = self._safe_path(Path(file_path))
        parsed = self.parser.parse_file(path)
        digest = file_sha256(path)

        existing = self.db.query(Capsule).filter(Capsule.file_path == str(path)).first()
        if parsed.id:
            by_id = self.db.query(Capsule).filter(Capsule.id == parsed.id).first()
            if by_id and existing and by_id.rowid != existing.rowid:
                raise StoreError(f"Duplicate capsule id in {path}")
            existing = existing or by_id

        capsule_id = parsed.id or (existing.id if existing else str(uuid.uuid4()))
        if existing:
            capsule = existing
            capsule.topic = parsed.topic
            capsule.content = parsed.content
            capsule.freshness = parsed.freshness or utcnow()
            capsule.source = parsed.source
            capsule.confidence = parsed.confidence
            capsule.archived = parsed.archived
            capsule.updated_at = utcnow()
        else:
            capsule = Capsule(
                id=capsule_id,
                topic=parsed.topic,
                content=parsed.content,
                freshness=parsed.freshness or utcnow(),
                source=parsed.source,
                confidence=parsed.confidence,
                archived=parsed.archived,
                file_path=str(path),
            )
            self.db.add(capsule)
            self.db.flush()

        capsule.id = capsule_id
        capsule.file_path = str(path)
        capsule.file_hash = digest
        self._apply_tags(capsule, parsed.tags)
        self.db.flush()
        self._sync_outgoing_relationships(capsule, parsed.relationships)

        if persist_missing_id and parsed.id != capsule.id:
            self.write_file(capsule)

        return capsule

    def create(
        self,
        topic: str,
        content: str,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        confidence: str = "medium",
        freshness=None,
        capsule_id: Optional[str] = None,
    ) -> Capsule:
        errors = self.parser.validate(
            self.parser.to_markdown(
                ParsedCapsule(
                    topic=topic,
                    content=content,
                    tags=tags or [],
                    source=source,
                    confidence=confidence,
                )
            )
        )
        if errors:
            raise StoreError("; ".join(errors))

        uid = capsule_id or str(uuid.uuid4())
        path = self._new_path(topic, uid)
        capsule = Capsule(
            id=uid,
            topic=topic,
            content=content,
            freshness=freshness or utcnow(),
            source=source,
            confidence=confidence,
            file_path=str(path),
        )
        self.db.add(capsule)
        self.db.flush()
        self._apply_tags(capsule, tags or [])
        self.write_file(capsule)
        return capsule

    def update(self, capsule_id: str, **fields) -> Capsule:
        capsule = self.get(capsule_id)
        if not capsule:
            raise StoreError("Capsule not found")

        if fields.get("topic") is not None:
            capsule.topic = fields["topic"]
        if fields.get("content") is not None:
            capsule.content = fields["content"]
        if fields.get("source") is not None:
            capsule.source = fields["source"]
        if fields.get("confidence") is not None:
            capsule.confidence = fields["confidence"]
        if fields.get("freshness") is not None:
            capsule.freshness = fields["freshness"]
        if fields.get("archived") is not None:
            capsule.archived = fields["archived"]
        if "tags" in fields and fields["tags"] is not None:
            self._apply_tags(capsule, fields["tags"])
        capsule.updated_at = utcnow()
        self.write_file(capsule)
        return capsule

    def get(self, capsule_id: str) -> Optional[Capsule]:
        return self.db.query(Capsule).filter(Capsule.id == capsule_id).first()

    def delete(self, capsule_id: str) -> None:
        capsule = self.get(capsule_id)
        if not capsule:
            raise StoreError("Capsule not found")
        if capsule.file_path:
            path = Path(capsule.file_path)
            try:
                if path.exists() and str(path.resolve()).startswith(str(self.capsules_dir.resolve())):
                    path.unlink()
            except OSError as exc:
                logger.warning("Failed to delete %s: %s", path, exc)
        self.db.delete(capsule)

    def archive(self, capsule_id: str) -> Capsule:
        return self.update(capsule_id, archived=True)

    def delete_by_path(self, file_path: str) -> None:
        capsule = self.db.query(Capsule).filter(Capsule.file_path == file_path).first()
        if capsule:
            self.db.delete(capsule)

    def reconcile(self) -> int:
        """Reindex every .capsule.md under capsules_dir; drop rows for missing files."""
        seen: set[str] = set()
        count = 0
        if self.capsules_dir.exists():
            for file_path in sorted(self.capsules_dir.rglob("*.capsule.md")):
                if file_path.name.endswith(".tmp"):
                    continue
                try:
                    capsule = self.upsert_from_file(file_path)
                    seen.add(str(Path(capsule.file_path).resolve()))
                    count += 1
                except Exception:
                    logger.exception("Failed to index %s", file_path)
        orphans = self.db.query(Capsule).filter(Capsule.file_path.isnot(None)).all()
        for capsule in orphans:
            path = Path(capsule.file_path)
            try:
                resolved = str(path.resolve())
            except OSError:
                resolved = capsule.file_path
            if resolved not in seen:
                self.db.delete(capsule)
        return count

    def link(self, from_id: str, to_id: str, relationship_type: str = "relates_to") -> CapsuleRelationship:
        source = self.get(from_id)
        target = self.get(to_id)
        if not source or not target:
            raise StoreError("One or both capsules not found")
        existing = (
            self.db.query(CapsuleRelationship)
            .filter(
                CapsuleRelationship.from_capsule_id == from_id,
                CapsuleRelationship.to_capsule_id == to_id,
                CapsuleRelationship.relationship_type == relationship_type,
            )
            .first()
        )
        if existing:
            return existing
        rel = CapsuleRelationship(
            from_capsule_id=from_id,
            to_capsule_id=to_id,
            relationship_type=relationship_type,
        )
        self.db.add(rel)
        self.db.flush()
        self.write_file(source)
        return rel
