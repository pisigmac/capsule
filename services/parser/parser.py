"""Parser for .capsule.md files."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml


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
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)


class CapsuleParser:
    """Parse .capsule.md files into structured data."""

    # Valid confidence levels
    CONFIDENCE_LEVELS = {"high", "medium", "low", "hearsay"}

    def __init__(self):
        self.frontmatter_pattern = re.compile(
            r"^---\s*\n(.*?)^---\s*\n",
            re.MULTILINE | re.DOTALL
        )

    def parse_file(self, file_path: Path) -> ParsedCapsule:
        """Parse a .capsule.md file."""
        raw = file_path.read_text(encoding="utf-8")
        return self.parse_text(raw, str(file_path))

    def parse_text(self, text: str, file_path: Optional[str] = None) -> ParsedCapsule:
        """Parse capsule text into structured data."""
        # Extract frontmatter
        fm_match = self.frontmatter_pattern.match(text)
        frontmatter: Dict[str, Any] = {}
        body = text

        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1)) or {}
            except yaml.YAMLError:
                frontmatter = {}
            body = text[fm_match.end():].strip()

        # Extract topic from frontmatter or first H1
        topic = frontmatter.get("topic", "")
        if not topic:
            h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if h1_match:
                topic = h1_match.group(1).strip()
            else:
                # Use first line as topic
                topic = body.split("\n")[0][:100] if body else "Untitled Capsule"

        # Extract tags
        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        tags = [str(t).lower().strip() for t in tags if t]

        # Parse freshness
        freshness = None
        if "freshness" in frontmatter:
            try:
                if isinstance(frontmatter["freshness"], datetime):
                    freshness = frontmatter["freshness"]
                else:
                    freshness = datetime.fromisoformat(str(frontmatter["freshness"]).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                freshness = datetime.now(timezone.utc)
        else:
            freshness = datetime.now(timezone.utc)

        # Source
        source = str(frontmatter.get("source", "")) or None

        # Confidence
        confidence = str(frontmatter.get("confidence", "medium")).lower()
        if confidence not in self.CONFIDENCE_LEVELS:
            confidence = "medium"

        return ParsedCapsule(
            topic=topic,
            content=body,
            tags=tags,
            freshness=freshness,
            source=source,
            confidence=confidence,
            file_path=file_path,
            raw_frontmatter=frontmatter,
        )

    def to_markdown(self, capsule: ParsedCapsule) -> str:
        """Serialize a parsed capsule back to markdown."""
        fm = {
            "topic": capsule.topic,
            "tags": capsule.tags,
            "freshness": capsule.freshness.isoformat() if capsule.freshness else datetime.now(timezone.utc).isoformat(),
            "source": capsule.source,
            "confidence": capsule.confidence,
        }
        # Remove None values
        fm = {k: v for k, v in fm.items() if v is not None}

        yaml_str = yaml.dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return f"---\n{yaml_str}---\n\n{capsule.content}\n"

    def validate(self, text: str) -> List[str]:
        """Validate a capsule text and return list of errors."""
        errors = []

        try:
            parsed = self.parse_text(text)
        except Exception as e:
            return [f"Parse error: {e}"]

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
