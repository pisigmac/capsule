"""Parser for .capsule.md files."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import yaml


CONFIDENCE_LEVELS = {"high", "medium", "low", "hearsay"}


@dataclass
class ParsedRelationship:
    to_id: str
    relationship_type: str = "relates_to"


@dataclass
class ParsedCapsule:
    """Structured representation of a parsed .capsule.md file."""

    topic: str
    content: str
    tags: List[str] = field(default_factory=list)
    freshness: Optional[datetime] = None
    source: Optional[str] = None
    confidence: str = "medium"
    file_path: Optional[str] = None
    id: Optional[str] = None
    archived: bool = False
    relationships: List[ParsedRelationship] = field(default_factory=list)
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)


class CapsuleParser:
    """Parse .capsule.md files into structured data."""

    CONFIDENCE_LEVELS = CONFIDENCE_LEVELS

    def __init__(self) -> None:
        self.frontmatter_pattern = re.compile(r"^---\s*\n(.*?)^---\s*\n", re.MULTILINE | re.DOTALL)

    def parse_file(self, file_path: Path) -> ParsedCapsule:
        raw = file_path.read_text(encoding="utf-8")
        return self.parse_text(raw, str(file_path))

    def parse_text(self, text: str, file_path: Optional[str] = None) -> ParsedCapsule:
        fm_match = self.frontmatter_pattern.match(text)
        frontmatter: Dict[str, Any] = {}
        body = text

        if fm_match:
            try:
                loaded = yaml.safe_load(fm_match.group(1))
                frontmatter = loaded if isinstance(loaded, dict) else {}
            except yaml.YAMLError:
                frontmatter = {}
            body = text[fm_match.end() :].strip()

        topic = str(frontmatter.get("topic") or "").strip()
        if not topic:
            h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if h1_match:
                topic = h1_match.group(1).strip()
                body = (body[: h1_match.start()] + body[h1_match.end() :]).strip()
            else:
                topic = body.split("\n")[0][:100] if body else "Untitled Capsule"

        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        tags = [str(t).lower().strip() for t in tags if t]

        freshness = None
        if "freshness" in frontmatter:
            try:
                if isinstance(frontmatter["freshness"], datetime):
                    freshness = frontmatter["freshness"]
                    if freshness.tzinfo is not None:
                        freshness = freshness.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    freshness = datetime.fromisoformat(
                        str(frontmatter["freshness"]).replace("Z", "+00:00")
                    )
                    if freshness.tzinfo is not None:
                        freshness = freshness.astimezone(timezone.utc).replace(tzinfo=None)
            except (ValueError, TypeError):
                freshness = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            freshness = datetime.now(timezone.utc).replace(tzinfo=None)

        source = str(frontmatter.get("source") or "") or None
        confidence = str(frontmatter.get("confidence", "medium")).lower()
        if confidence not in self.CONFIDENCE_LEVELS:
            confidence = "medium"

        capsule_id = frontmatter.get("id")
        parsed_id = None
        if capsule_id:
            try:
                parsed_id = str(UUID(str(capsule_id)))
            except (ValueError, TypeError, AttributeError):
                parsed_id = None

        archived = bool(frontmatter.get("archived", False))
        relationships = self._parse_relationships(frontmatter.get("relationships"))

        return ParsedCapsule(
            topic=topic,
            content=body,
            tags=tags,
            freshness=freshness,
            source=source,
            confidence=confidence,
            file_path=file_path,
            id=parsed_id,
            archived=archived,
            relationships=relationships,
            raw_frontmatter=frontmatter,
        )

    def _parse_relationships(self, raw: Any) -> List[ParsedRelationship]:
        if not raw:
            return []
        if not isinstance(raw, list):
            return []
        result: List[ParsedRelationship] = []
        for item in raw:
            if isinstance(item, str):
                try:
                    result.append(ParsedRelationship(to_id=str(UUID(item))))
                except ValueError:
                    continue
            elif isinstance(item, dict):
                target = item.get("to") or item.get("id") or item.get("to_id")
                rel_type = str(item.get("type") or item.get("relationship_type") or "relates_to")
                try:
                    result.append(
                        ParsedRelationship(to_id=str(UUID(str(target))), relationship_type=rel_type[:50])
                    )
                except (ValueError, TypeError):
                    continue
        return result

    def to_markdown(self, capsule: ParsedCapsule) -> str:
        fm: Dict[str, Any] = {
            "id": capsule.id,
            "topic": capsule.topic,
            "tags": capsule.tags,
            "freshness": (
                capsule.freshness.isoformat()
                if capsule.freshness
                else datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            ),
            "source": capsule.source,
            "confidence": capsule.confidence,
        }
        if capsule.archived:
            fm["archived"] = True
        if capsule.relationships:
            fm["relationships"] = [
                {"to": rel.to_id, "type": rel.relationship_type} for rel in capsule.relationships
            ]
        fm = {k: v for k, v in fm.items() if v is not None}

        yaml_str = yaml.dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return f"---\n{yaml_str}---\n\n{capsule.content.strip()}\n"

    def validate(self, text: str) -> List[str]:
        errors: List[str] = []
        try:
            parsed = self.parse_text(text)
        except Exception as exc:
            return [f"Parse error: {exc}"]

        if not parsed.topic or len(parsed.topic) < 3:
            errors.append("Topic must be at least 3 characters")
        if len(parsed.topic) > 500:
            errors.append("Topic must be under 500 characters")
        if not parsed.content or len(parsed.content) < 10:
            errors.append("Content must be at least 10 characters")
        if parsed.confidence not in self.CONFIDENCE_LEVELS:
            errors.append(f"Confidence must be one of: {self.CONFIDENCE_LEVELS}")
        if len(parsed.tags) > 50:
            errors.append("Too many tags (max 50)")
        for tag in parsed.tags:
            if len(tag) > 100:
                errors.append(f"Tag too long: {tag[:20]}...")
        return errors
