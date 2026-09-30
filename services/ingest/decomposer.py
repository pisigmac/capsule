"""Orchestration pipeline for decomposing documentation into atomic capsules."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.shared.models import Capsule
from services.store.store import CapsuleStore
from .ast_splitter import AstDocumentSplitter, AtomicUnit
from .llm_splitter import LlmDocumentSplitter

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Summary of the documentation ingestion run."""

    total_files: int = 0
    total_units: int = 0
    created_count: int = 0
    deduped_count: int = 0
    units: List[AtomicUnit] = field(default_factory=list)
    created: List[Capsule] = field(default_factory=list)
    deduped: List[Capsule] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_units": self.total_units,
            "created_count": self.created_count,
            "deduped_count": self.deduped_count,
            "units": [u.to_dict() for u in self.units],
        }


class DocumentDecomposer:
    """Scans and decomposes documentation files or directories into atomic capsules."""

    SUPPORTED_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}

    def __init__(
        self,
        store: CapsuleStore,
        mode: str = "ast",
        confidence: str = "high",
        model: Optional[str] = None,
        extra_tags: Optional[List[str]] = None,
    ) -> None:
        self.store = store
        self.mode = mode.lower()
        self.confidence = confidence
        self.model = model or "gemini-2.5-flash"
        self.extra_tags = extra_tags or []

        if self.mode == "llm":
            self.splitter = LlmDocumentSplitter(
                model=self.model,
                confidence=self.confidence,
                extra_tags=self.extra_tags,
            )
        else:
            self.splitter = AstDocumentSplitter(
                confidence=self.confidence,
                extra_tags=self.extra_tags,
            )

    def collect_files(self, target_path: Path | str) -> List[Path]:
        """Collect all matching markdown files under target_path."""
        target = Path(target_path).resolve()
        if not target.exists():
            return []

        if target.is_file():
            if target.suffix.lower() in self.SUPPORTED_EXTENSIONS or target.suffix == "":
                return [target]
            return []

        found: List[Path] = []
        for path in sorted(target.rglob("*")):
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                # Skip hidden files and temporary/internal directories
                parts = path.parts
                if any(p.startswith(".") or p in ("node_modules", "dist", "build", "venv", ".venv") for p in parts):
                    continue
                found.append(path)

        return sorted(found)

    def decompose_file(self, file_path: Path | str) -> List[AtomicUnit]:
        """Read and decompose a single file into atomic units."""
        path = Path(file_path).resolve()
        if not path.is_file():
            return []

        raw_text = path.read_text(encoding="utf-8", errors="replace")
        return self.splitter.split_document(
            raw_text,
            source_name=path.name,
            extra_tags=self.extra_tags,
        )

    def ingest_path(
        self,
        target_path: Path | str,
        dry_run: bool = False,
        on_progress: Optional[Callable[[Path, List[AtomicUnit], int, int], None]] = None,
    ) -> IngestResult:
        """Scan, decompose, and index documentation into the Capsule store."""
        files = self.collect_files(target_path)
        result = IngestResult(total_files=len(files))

        for file_path in files:
            units = self.decompose_file(file_path)
            result.total_units += len(units)
            result.units.extend(units)

            file_created = 0
            file_deduped = 0

            if not dry_run:
                for unit in units:
                    try:
                        capsule = self.store.create(
                            topic=unit.topic,
                            content=unit.content,
                            tags=unit.tags,
                            source=unit.source or f"ingest:{file_path.name}",
                            confidence=unit.confidence or self.confidence,
                        )
                        if getattr(capsule, "deduped", False):
                            result.deduped.append(capsule)
                            result.deduped_count += 1
                            file_deduped += 1
                        else:
                            result.created.append(capsule)
                            result.created_count += 1
                            file_created += 1
                    except Exception as exc:
                        logger.warning("Failed to store unit '%s': %s", unit.topic, exc)

            if on_progress:
                on_progress(file_path, units, file_created, file_deduped)

        if not dry_run and (result.created or result.deduped):
            self.store.db.commit()

        return result
