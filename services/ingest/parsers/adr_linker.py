"""
Cross-layer linker connecting Architecture Decision Records (ADRs), specifications,
and governance rules to code capsules (files, classes, functions) via bidirectional
'implements' and 'implemented_by' relationships.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from services.shared.models import Capsule
from services.store.store import CapsuleStore
from .python_parser import RepoModel
from .typescript_parser import TsFileInfo

logger = logging.getLogger("capsule.ingest.adr_linker")

# Regex patterns for ADR / Spec / Invariant / Rule / WikiLink mentions
ADR_COMMENT_PATTERN = re.compile(
    r"""(?:#|//|/\*|\*|@)\s*(?:ADR|DECISION|SPEC|INVARIANT|RFC|RULE|adr|spec|invariant|decision|rule)[:\s]+([^\n\r*]+)""",
    re.IGNORECASE,
)
WIKILINK_PATTERN = re.compile(r"""\[\[([^\]|]+)(?:\|[^\]]+)?\]\]""")


def _normalize(text: str) -> str:
    """Normalizes string for robust topic / keyword matching."""
    return re.sub(r"[^\w\s]", " ", text).strip().lower()


@dataclass
class AdrReference:
    target_text: str
    source_kind: str  # "pattern" | "wikilink"
    raw_match: str


class AdrCrossLayerLinker:
    """Scans code comments, docstrings, and signatures for architecture references

    and creates bidirectional 'implements' / 'implemented_by' links with knowledge capsules.
    """

    def __init__(self, store: CapsuleStore) -> None:
        self.store = store
        self._knowledge_capsules: Optional[List[Capsule]] = None

    def get_knowledge_capsules(self, refresh: bool = False) -> List[Capsule]:
        """Loads and caches architecture, governance, and general knowledge capsules."""
        if self._knowledge_capsules is None or refresh:
            try:
                # Query active capsules directly from DB
                all_caps = self.store.db.query(Capsule).filter(Capsule.archived.is_(False)).all()
                self._knowledge_capsules = [
                    c for c in all_caps
                    if any(
                        cat in (c.file_path or "")
                        for cat in ("architecture", "general", "security", "agents", "rules", "decisions", "goals")
                    )
                    or any(
                        (tag.name.lower() if hasattr(tag, "name") else str(tag).lower()) in {
                            "architecture", "adr", "decision", "spec", "invariant", "rule", "governance", "security"
                        }
                        for tag in (c.tags or [])
                    )
                    or not (c.file_path and "code/" in c.file_path)
                ]
            except Exception as exc:
                logger.warning("Failed to fetch knowledge capsules: %s", exc)
                self._knowledge_capsules = []
        return self._knowledge_capsules

    @classmethod
    def extract_references_from_text(cls, text: Optional[str]) -> List[AdrReference]:
        """Extracts ADR, Spec, Invariant, and WikiLink references from text."""
        if not text:
            return []

        refs: List[AdrReference] = []

        # 1. WikiLinks [[Topic Title]]
        for match in WIKILINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if target:
                refs.append(AdrReference(target_text=target, source_kind="wikilink", raw_match=match.group(0)))

        # 2. Tagged patterns (# ADR: 001, @spec File-First, # INVARIANT: FTS5)
        for match in ADR_COMMENT_PATTERN.finditer(text):
            target = match.group(1).strip()
            # Clean trailing comment markers
            target = re.sub(r"\*/.*$", "", target).strip()
            if target and not target.startswith("[["):  # avoid duplicate wikilink capture
                refs.append(AdrReference(target_text=target, source_kind="pattern", raw_match=match.group(0)))

        return refs

    def resolve_target_capsule(self, target_text: str) -> Optional[Capsule]:
        """Resolves target text or query against indexed knowledge capsules."""
        knowledge = self.get_knowledge_capsules()
        if not knowledge or not target_text:
            return None

        clean_target = target_text.strip()
        norm_target = _normalize(clean_target)

        # 1. Exact ID or ID prefix match (e.g. 7c2a9f14 or full UUID)
        for cap in knowledge:
            if cap.id == clean_target or cap.id.startswith(clean_target) or clean_target in cap.id:
                return cap

        # 2. Exact Case-Insensitive Topic match
        for cap in knowledge:
            if cap.topic.strip().lower() == clean_target.lower():
                return cap

        # 3. Normalized Topic match
        for cap in knowledge:
            if _normalize(cap.topic) == norm_target:
                return cap

        # 4. Tag match (e.g. adr-001, architecture, fts5-rowids)
        for cap in knowledge:
            for tag in (cap.tags or []):
                tag_name = tag.name if hasattr(tag, "name") else str(tag)
                if tag_name.lower() == norm_target or _normalize(tag_name) == norm_target:
                    return cap

        # 5. High-confidence Substring containment
        # Target is substring of Topic or Topic is substring of Target (minimum 4 chars)
        if len(norm_target) >= 4:
            for cap in knowledge:
                norm_topic = _normalize(cap.topic)
                if norm_target in norm_topic or (len(norm_topic) >= 4 and norm_topic in norm_target):
                    return cap

        return None

    def link_code_to_architecture(
        self,
        py_model: Optional[RepoModel] = None,
        ts_files: Optional[Dict[str, TsFileInfo]] = None,
        id_map: Optional[Dict[str, str]] = None,
    ) -> int:
        """Discovers ADR/Architecture references across parsed code and creates bidirectional edges."""
        if id_map is None:
            id_map = {}

        # Refresh knowledge capsules cache
        self.get_knowledge_capsules(refresh=True)

        links_created = 0
        linked_pairs: Set[Tuple[str, str]] = set()

        # 1. Process Python files, classes, and functions
        if py_model:
            # Files
            for fpath, fi in py_model.files.items():
                code_cid = id_map.get(fi.id)
                if not code_cid:
                    continue

                refs = self.extract_references_from_text(fi.commit_message)
                for ref in refs:
                    target_cap = self.resolve_target_capsule(ref.target_text)
                    if target_cap and target_cap.id != code_cid:
                        pair = (code_cid, target_cap.id)
                        if pair not in linked_pairs:
                            self._create_bidirectional_link(code_cid, target_cap.id)
                            linked_pairs.add(pair)
                            links_created += 2

            # Classes
            for cls_id, ci in py_model.classes.items():
                code_cid = id_map.get(cls_id)
                if not code_cid:
                    continue

                refs = self.extract_references_from_text(ci.docstring)
                for ref in refs:
                    target_cap = self.resolve_target_capsule(ref.target_text)
                    if target_cap and target_cap.id != code_cid:
                        pair = (code_cid, target_cap.id)
                        if pair not in linked_pairs:
                            self._create_bidirectional_link(code_cid, target_cap.id)
                            linked_pairs.add(pair)
                            links_created += 2

            # Functions
            for fn_id, fn in py_model.functions.items():
                code_cid = id_map.get(fn_id)
                if not code_cid:
                    continue

                refs = self.extract_references_from_text(fn.docstring)
                for ref in refs:
                    target_cap = self.resolve_target_capsule(ref.target_text)
                    if target_cap and target_cap.id != code_cid:
                        pair = (code_cid, target_cap.id)
                        if pair not in linked_pairs:
                            self._create_bidirectional_link(code_cid, target_cap.id)
                            linked_pairs.add(pair)
                            links_created += 2

        # 2. Process TypeScript files
        if ts_files:
            for fpath, ts in ts_files.items():
                for fn in ts.functions:
                    fn_cid = id_map.get(fn.id)
                    if not fn_cid:
                        continue
                    refs = self.extract_references_from_text(fn.name)
                    for ref in refs:
                        target_cap = self.resolve_target_capsule(ref.target_text)
                        if target_cap and target_cap.id != fn_cid:
                            pair = (fn_cid, target_cap.id)
                            if pair not in linked_pairs:
                                self._create_bidirectional_link(fn_cid, target_cap.id)
                                linked_pairs.add(pair)
                                links_created += 2

        # 3. Direct Content Scan of Code Capsules
        for code_id in id_map.values():
            try:
                code_cap = self.store.get(code_id)
                if not code_cap:
                    continue
                refs = self.extract_references_from_text(code_cap.content)
                for ref in refs:
                    target_cap = self.resolve_target_capsule(ref.target_text)
                    if target_cap and target_cap.id != code_cap.id:
                        pair = (code_cap.id, target_cap.id)
                        if pair not in linked_pairs:
                            self._create_bidirectional_link(code_cap.id, target_cap.id)
                            linked_pairs.add(pair)
                            links_created += 2
            except Exception:
                continue

        if links_created > 0:
            self.store.db.commit()

        return links_created

    def _create_bidirectional_link(self, code_cid: str, adr_cid: str) -> None:
        """Creates code --(implements)--> adr and adr --(implemented_by)--> code."""
        try:
            self.store.link(code_cid, adr_cid, relationship_type="implements")
            self.store.link(adr_cid, code_cid, relationship_type="implemented_by")
            logger.info("Cross-layer link: %s <--(implements/implemented_by)--> %s", code_cid, adr_cid)
        except Exception as exc:
            logger.warning("Failed to link %s and %s: %s", code_cid, adr_cid, exc)
