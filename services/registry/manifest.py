"""Knowledge Pack Manifest model for Capsule Registry."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PackManifest:
    """Metadata describing a curated Capsule Knowledge Pack."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "Community"
    caps_count: int = 0
    tags: List[str] = field(default_factory=list)
    sha256: Optional[str] = None
    url: Optional[str] = None
    verified: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PackManifest:
        return cls(
            name=data["name"],
            version=str(data.get("version", "1.0.0")),
            description=data.get("description", ""),
            author=data.get("author", "Community"),
            caps_count=int(data.get("caps_count", 0)),
            tags=list(data.get("tags", [])),
            sha256=data.get("sha256"),
            url=data.get("url"),
            verified=bool(data.get("verified", True)),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> PackManifest:
        return cls.from_dict(json.loads(json_str))
