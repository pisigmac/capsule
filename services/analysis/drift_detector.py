"""
Code Drift and Architectural Boundary Violation Detector.
Scans the code graph and knowledge graph for dead code, layer boundary violations,
circular dependencies, and unimplemented architecture decisions (ADRs).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from services.shared.models import Capsule, CapsuleRelationship
from services.store.store import CapsuleStore

logger = logging.getLogger("capsule.analysis.drift")

# Entrypoint symbols and test functions that are allowed to have 0 incoming call edges
WHITELISTED_SYMBOLS = {
    "main",
    "cli",
    "app",
    "run",
    "boot",
    "start",
    "handler",
    "setup",
    "__init__",
    "render",
}


@dataclass
class DriftViolation:
    rule: str  # e.g., "dead-code", "boundary/frontend-to-db", "circular-dependency", "adr/unimplemented"
    severity: str  # "error" | "warning"
    title: str
    description: str
    source_file: Optional[str] = None
    symbol_name: Optional[str] = None
    lineno: Optional[int] = None


@dataclass
class DriftReport:
    total_files_analyzed: int = 0
    total_symbols_analyzed: int = 0
    dead_code_count: int = 0
    boundary_violations_count: int = 0
    orphan_adrs_count: int = 0
    violations: List[DriftViolation] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(v.severity == "error" for v in self.violations)

    def is_passing(self, strict: bool = False) -> bool:
        if strict:
            return len(self.violations) == 0
        return not self.has_errors

    def to_dict(self) -> dict:
        return {
            "total_files_analyzed": self.total_files_analyzed,
            "total_symbols_analyzed": self.total_symbols_analyzed,
            "dead_code_count": self.dead_code_count,
            "boundary_violations_count": self.boundary_violations_count,
            "orphan_adrs_count": self.orphan_adrs_count,
            "has_errors": self.has_errors,
            "passing": self.is_passing(),
            "violations": [asdict(v) for v in self.violations],
        }


class CodeDriftDetector:
    """Detects architectural drift, dead code, and layer boundary violations across the vault."""

    def __init__(self, store: CapsuleStore) -> None:
        self.store = store

    def analyze(self, target_path: Optional[str] = None) -> DriftReport:
        report = DriftReport()

        all_caps = self.store.db.query(Capsule).filter(Capsule.archived.is_(False)).all()
        code_caps = [
            c for c in all_caps
            if (c.file_path and "code/" in c.file_path)
            or any(t.name.lower() in {"code", "python", "typescript", "go", "rust", "java"} for t in (c.tags or []))
        ]
        adr_caps = [
            c for c in all_caps
            if (c.file_path and "architecture/" in c.file_path)
            or any(t.name.lower() in {"architecture", "adr", "spec", "invariant"} for t in (c.tags or []))
        ]

        report.total_files_analyzed = len([c for c in code_caps if "file" in [t.name.lower() for t in c.tags]])
        report.total_symbols_analyzed = len(code_caps)

        # 1. Dead Code Detection (symbols with 0 incoming calls or defines)
        incoming_map: Dict[str, Set[str]] = {}
        outgoing_map: Dict[str, Set[Tuple[str, str]]] = {}

        for cap in all_caps:
            for rel in cap.outgoing_relationships:
                outgoing_map.setdefault(cap.id, set()).add((rel.to_capsule_id, rel.relationship_type))
                incoming_map.setdefault(rel.to_capsule_id, set()).add(cap.id)

        for cap in code_caps:
            tags = {t.name.lower() for t in cap.tags}
            if "function" in tags or "method" in tags:
                symbol_name = cap.topic.replace("Function: ", "").replace("Method: ", "").split(".")[-1]
                if symbol_name.lower().startswith("test_") or symbol_name.lower() in WHITELISTED_SYMBOLS:
                    continue
                if cap.source and ("test" in cap.source.lower() or "evals" in cap.source.lower()):
                    continue

                incoming = incoming_map.get(cap.id, set())
                call_parents = [
                    src_id for src_id in incoming
                    if any(t == "calls" for tgt, t in outgoing_map.get(src_id, set()) if tgt == cap.id)
                ]

                if len(call_parents) == 0:
                    report.dead_code_count += 1
                    report.violations.append(
                        DriftViolation(
                            rule="dead-code/unreferenced-symbol",
                            severity="warning",
                            title=f"Unreferenced function or method: {cap.topic}",
                            description=f"Symbol `{symbol_name}` has 0 incoming calls across the indexed codebase.",
                            source_file=cap.source or cap.file_path,
                            symbol_name=symbol_name,
                        )
                    )

        # 2. Architectural Boundary Violations
        # A. Frontend Layer Isolation (Frontend code importing backend DB internals directly)
        for cap in code_caps:
            is_frontend = (
                (cap.file_path and ("frontend" in cap.file_path or "typescript" in cap.file_path))
                or (cap.source and "frontend" in cap.source)
                or any(t.name.lower() in {"frontend", "typescript"} for t in cap.tags)
            )
            if is_frontend:
                for target_id, rel_type in outgoing_map.get(cap.id, set()):
                    target = self.store.get(target_id)
                    if target:
                        target_loc = f"{target.file_path or ''} {target.source or ''}".lower()
                        if "models.py" in target_loc or "database" in target_loc or "sqlalchemy" in target_loc:
                            report.boundary_violations_count += 1
                            report.violations.append(
                                DriftViolation(
                                    rule="boundary/frontend-to-database",
                                    severity="error",
                                    title="Architectural Boundary Violation: Frontend directly imports DB layer",
                                    description=f"Frontend capsule `{cap.topic}` directly links to database model `{target.topic}` without using HTTP contract.",
                                    source_file=cap.source or cap.file_path,
                                )
                            )

        # B. Direct Circular Dependency Detection (A -> B and B -> A)
        visited_pairs: Set[Tuple[str, str]] = set()
        for src_id, targets in outgoing_map.items():
            for tgt_id, rel_type in targets:
                if rel_type in {"imports", "depends_on"}:
                    pair = (min(src_id, tgt_id), max(src_id, tgt_id))
                    if pair in visited_pairs:
                        continue
                    reverse_rels = [t for t_id, t in outgoing_map.get(tgt_id, set()) if t_id == src_id and t in {"imports", "depends_on"}]
                    if reverse_rels:
                        visited_pairs.add(pair)
                        report.boundary_violations_count += 1
                        src_cap = self.store.get(src_id)
                        tgt_cap = self.store.get(tgt_id)
                        report.violations.append(
                            DriftViolation(
                                rule="boundary/circular-dependency",
                                severity="error",
                                title="Circular Dependency Detected",
                                description=f"Modules `{src_cap.topic if src_cap else src_id}` and `{tgt_cap.topic if tgt_cap else tgt_id}` import each other cyclically.",
                                source_file=src_cap.file_path if src_cap else None,
                            )
                        )

        # 3. Unimplemented Architecture Decisions (ADR Invariant Rule)
        for adr in adr_caps:
            impl_targets = [
                tgt_id for tgt_id, r_type in outgoing_map.get(adr.id, set())
                if r_type == "implemented_by"
            ]
            impl_sources = [
                src_id for src_id in incoming_map.get(adr.id, set())
                if any(t == "implements" for tgt, t in outgoing_map.get(src_id, set()) if tgt == adr.id)
            ]

            if len(impl_targets) == 0 and len(impl_sources) == 0:
                report.orphan_adrs_count += 1
                report.violations.append(
                    DriftViolation(
                        rule="adr/unimplemented-decision",
                        severity="warning",
                        title=f"Unimplemented Architectural Decision: {adr.topic}",
                        description=f"Architecture capsule `{adr.topic}` has 0 code files or functions implementing it.",
                        source_file=adr.file_path,
                    )
                )

        return report
