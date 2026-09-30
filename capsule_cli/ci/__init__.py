"""CI verification and PR conflict gatekeeper for Capsule vaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class LintIssue:
    """A single linting issue (error or warning) found in a capsule."""

    file_path: str
    rule: str
    message: str
    level: str = "error"  # "error" | "warning"
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "rule": self.rule,
            "message": self.message,
            "level": self.level,
            "line_number": self.line_number,
        }


@dataclass
class InvariantAlert:
    """An alert when modified code intersects with high-confidence capsules."""

    capsule_id: Optional[str]
    capsule_topic: str
    capsule_file: str
    confidence: str
    affected_file: str
    match_type: str  # "direct_path" | "tag_match" | "topic_match"
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capsule_id": self.capsule_id,
            "capsule_topic": self.capsule_topic,
            "capsule_file": self.capsule_file,
            "confidence": self.confidence,
            "affected_file": self.affected_file,
            "match_type": self.match_type,
            "summary": self.summary,
        }


@dataclass
class LintReport:
    """Aggregate report from linting and invariant verification."""

    total_scanned: int = 0
    passed_count: int = 0
    errors: List[LintIssue] = field(default_factory=list)
    warnings: List[LintIssue] = field(default_factory=list)
    invariant_alerts: List[InvariantAlert] = field(default_factory=list)
    broken_relationships: List[LintIssue] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return len(self.errors) == 0 and len(self.broken_relationships) == 0

    def is_strict_success(self) -> bool:
        return self.is_success and len(self.warnings) == 0 and len(self.invariant_alerts) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scanned": self.total_scanned,
            "passed_count": self.passed_count,
            "is_success": self.is_success,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "invariant_alerts": [a.to_dict() for a in self.invariant_alerts],
            "broken_relationships": [b.to_dict() for b in self.broken_relationships],
        }
