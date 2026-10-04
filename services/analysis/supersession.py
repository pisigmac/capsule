"""
Automated Invariant Contradiction & Supersession Engine.
Detects semantic, numerical, and polarity contradictions between capsules (ADRs, invariants, configs)
and manages 'supersedes' / 'superseded_by' lineage to prevent stale knowledge poisoning.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from services.embed.embedder import cosine, decode_embedding, embed_text
from services.shared.models import Capsule, CapsuleRelationship
from services.store.store import CapsuleStore

logger = logging.getLogger("capsule.analysis.supersession")

# Polarity antonym pairs for contradiction detection
POLARITY_PAIRS = [
    ("enabled", "disabled"),
    ("enable", "disable"),
    ("true", "false"),
    ("allow", "deny"),
    ("allow", "block"),
    ("required", "optional"),
    ("synchronous", "asynchronous"),
    ("sync", "async"),
    ("active", "deprecated"),
    ("active", "inactive"),
    ("blocking", "non-blocking"),
    ("strict", "permissive"),
    ("enforce", "ignore"),
]

# Common invariant/configuration key-value pattern:
# matches lines like: `max_connections: 50`, `pool_size = 20`, `auth_strategy: jwt`
KV_REGEX = re.compile(
    r"(?:^|[\r\n]|[-*]\s+|\b)([a-zA-Z0-9_\.\-]+)[^\S\r\n]*[:=][^\S\r\n]*([^\r\n,;.`]+)",
    re.MULTILINE,
)


@dataclass
class ContradictionFinding:
    newer_capsule_id: str
    newer_topic: str
    older_capsule_id: str
    older_topic: str
    contradiction_type: str  # "explicit_reference" | "parameter_shift" | "polarity_negation" | "semantic_overlap"
    confidence_score: float  # 0.0 to 1.0
    reason: str
    diff_summary: Dict[str, Any] = field(default_factory=dict)
    applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SupersessionReport:
    total_analyzed: int = 0
    contradictions_found: int = 0
    superseded_applied: int = 0
    findings: List[ContradictionFinding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_analyzed": self.total_analyzed,
            "contradictions_found": self.contradictions_found,
            "superseded_applied": self.superseded_applied,
            "findings": [f.to_dict() for f in self.findings],
        }


class InvariantSupersessionEngine:
    """Scans capsules for invariant contradictions and manages supersession relationships."""

    def __init__(self, store: CapsuleStore) -> None:
        self.store = store
        self.db = store.db

    def extract_parameters(self, text: str) -> Dict[str, str]:
        """Extracts configuration key-value pairs or structured invariants from capsule text."""
        params: Dict[str, str] = {}
        if not text:
            return params
        for match in KV_REGEX.finditer(text):
            k, v = match.group(1).strip().lower(), match.group(2).strip()
            # Filter noise (markdown headers, common prose words, URLs)
            if len(k) < 2 or len(v) < 1 or k.startswith("http") or k in {"http", "https", "line", "version"}:
                continue
            # Strip quotes, markdown formatting, or punctuation
            cleaned_v = v.strip("`'\" .,;:()[]{}").lower()
            if cleaned_v:
                params[k] = cleaned_v
        return params

    def _detect_polarity_conflict(self, text1: str, text2: str) -> Optional[Tuple[str, str, str]]:
        """Detects if text1 and text2 contain opposing polarity words in close context."""
        t1_low = text1.lower()
        t2_low = text2.lower()
        for p1, p2 in POLARITY_PAIRS:
            if (p1 in t1_low and p2 in t2_low) or (p2 in t1_low and p1 in t2_low):
                val1 = p1 if p1 in t1_low else p2
                val2 = p2 if val1 == p1 else p1
                return (f"{val1} vs {val2}", val1, val2)
        return None

    def _calc_topic_overlap(self, topic1: str, topic2: str) -> float:
        """Computes word Jaccard similarity between two topic titles."""
        tokens1 = set(re.findall(r"\w+", topic1.lower()))
        tokens2 = set(re.findall(r"\w+", topic2.lower()))
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        return len(intersection) / len(union)

    def detect_contradictions(
        self,
        target_capsule_id: Optional[str] = None,
        min_confidence: float = 0.5,
        apply_supersession: bool = False,
    ) -> SupersessionReport:
        """
        Scans for invariant contradictions and supersession opportunities.
        If target_capsule_id is provided, compares target against all relevant active capsules.
        Otherwise, runs pairwise across active knowledge/ADR capsules.
        """
        report = SupersessionReport()

        query = self.db.query(Capsule).filter(Capsule.archived.is_(False))
        if target_capsule_id:
            target_cap = self.db.query(Capsule).filter(Capsule.id == target_capsule_id).first()
            if not target_cap:
                return report
            pool = query.filter(Capsule.id != target_capsule_id).all()
            pairs = [(target_cap, other) for other in pool]
        else:
            all_caps = query.order_by(Capsule.updated_at.desc()).all()
            pairs = []
            for i, c1 in enumerate(all_caps):
                for c2 in all_caps[i + 1 :]:
                    pairs.append((c1, c2))

        report.total_analyzed = len(pairs)

        for cap_a, cap_b in pairs:
            # Determine newer vs older by freshness / created_at
            fresh_a = cap_a.freshness or cap_a.created_at or datetime.min
            fresh_b = cap_b.freshness or cap_b.created_at or datetime.min

            if fresh_a >= fresh_b:
                newer, older = cap_a, cap_b
            else:
                newer, older = cap_b, cap_a

            finding = self._evaluate_pair(newer, older, min_confidence=min_confidence)
            if finding:
                if apply_supersession and not finding.applied:
                    self._apply_supersession_link(newer, older)
                    finding.applied = True
                    report.superseded_applied += 1
                report.findings.append(finding)
                report.contradictions_found += 1

        return report

    def _evaluate_pair(
        self, newer: Capsule, older: Capsule, min_confidence: float = 0.5
    ) -> Optional[ContradictionFinding]:
        """Evaluates whether newer capsule contradicts and supersedes older capsule."""
        newer_topic = newer.topic
        older_topic = older.topic
        newer_content = newer.content or ""
        older_content = older.content or ""

        # Check existing supersedes edge
        has_edge = (
            self.db.query(CapsuleRelationship)
            .filter(
                CapsuleRelationship.from_capsule_id == newer.id,
                CapsuleRelationship.to_capsule_id == older.id,
                CapsuleRelationship.relationship_type == "supersedes",
            )
            .first()
        )
        if has_edge:
            return ContradictionFinding(
                newer_capsule_id=newer.id,
                newer_topic=newer_topic,
                older_capsule_id=older.id,
                older_topic=older_topic,
                contradiction_type="explicit_reference",
                confidence_score=1.0,
                reason="Existing 'supersedes' relationship in graph",
                applied=True,
            )

        # 1. Explicit reference in text/metadata
        # Checks if newer explicitly refers to older ID, or uses supersedes/replaces/legacy phrases
        newer_text_low = f"{newer_topic}\n{newer_content}".lower()
        older_id_short = older.id[:8].lower()
        older_topic_low = older_topic.lower()
        
        explicit_matched = False
        if older.id.lower() in newer_text_low or f"supersedes {older_id_short}" in newer_text_low or f"replaces {older_id_short}" in newer_text_low:
            explicit_matched = True
        elif older_topic_low in (newer.content or "").lower() and any(
            kw in newer_text_low for kw in ["supersede", "supersedes", "replaces", "replace", "deprecated", "legacy", "migration from"]
        ):
            explicit_matched = True

        if explicit_matched:
            return ContradictionFinding(
                newer_capsule_id=newer.id,
                newer_topic=newer_topic,
                older_capsule_id=older.id,
                older_topic=older_topic,
                contradiction_type="explicit_reference",
                confidence_score=0.98,
                reason=f"Explicit reference to prior capsule '{older_topic}' ({older.id[:8]})",
            )

        # 2. Topic & Tag similarity
        topic_overlap = self._calc_topic_overlap(newer_topic, older_topic)
        shared_tags = set(t.name.lower() for t in (newer.tags or [])).intersection(
            set(t.name.lower() for t in (older.tags or []))
        )

        # Extract parameters / key-values
        params_newer = self.extract_parameters(newer_content)
        params_older = self.extract_parameters(older_content)

        common_keys = set(params_newer.keys()).intersection(set(params_older.keys()))
        conflicting_params = {}
        for k in common_keys:
            if params_newer[k] != params_older[k]:
                conflicting_params[k] = {
                    "newer": params_newer[k],
                    "older": params_older[k],
                }

        # 3. Parameter shift & Polarity contradiction
        if conflicting_params and (topic_overlap >= 0.25 or shared_tags):
            keys_str = ", ".join(
                [f"{k} ('{v['newer']}' vs '{v['older']}')" for k, v in conflicting_params.items()]
            )
            # Detect if parameter shift is actually a polarity reversal (e.g. enabled vs disabled)
            is_polarity_shift = any(
                (p1 in v["newer"] and p2 in v["older"]) or (p2 in v["newer"] and p1 in v["older"])
                for v in conflicting_params.values()
                for p1, p2 in POLARITY_PAIRS
            )
            c_type = "polarity_negation" if is_polarity_shift else "parameter_shift"
            score = min(0.65 + (len(conflicting_params) * 0.15) + (topic_overlap * 0.2), 0.99)
            if score >= min_confidence:
                return ContradictionFinding(
                    newer_capsule_id=newer.id,
                    newer_topic=newer_topic,
                    older_capsule_id=older.id,
                    older_topic=older_topic,
                    contradiction_type=c_type,
                    confidence_score=round(score, 3),
                    reason=f"Conflicting {'polarity' if is_polarity_shift else 'parameters'} on common keys: {keys_str}",
                    diff_summary=conflicting_params,
                )

        # 4. Polarity negation contradiction (e.g. JWT vs Paseto, sync vs async, enabled vs disabled)
        polarity = self._detect_polarity_conflict(newer_content, older_content)
        if polarity and (topic_overlap >= 0.35 or shared_tags):
            score = min(0.60 + (topic_overlap * 0.3), 0.95)
            if score >= min_confidence:
                return ContradictionFinding(
                    newer_capsule_id=newer.id,
                    newer_topic=newer_topic,
                    older_capsule_id=older.id,
                    older_topic=older_topic,
                    contradiction_type="polarity_negation",
                    confidence_score=round(score, 3),
                    reason=f"Opposing polarity assertions detected: {polarity[0]} in related domain",
                    diff_summary={"polarity": polarity[0]},
                )

        # 5. Strong topic title match / ADR revision (topic overlap >= 0.7)
        if topic_overlap >= 0.70:
            score = min(0.50 + (topic_overlap * 0.4), 0.90)
            if score >= min_confidence:
                return ContradictionFinding(
                    newer_capsule_id=newer.id,
                    newer_topic=newer_topic,
                    older_capsule_id=older.id,
                    older_topic=older_topic,
                    contradiction_type="semantic_overlap",
                    confidence_score=round(score, 3),
                    reason=f"High topic collision ({int(topic_overlap*100)}% token overlap) with newer iteration",
                )

        return None

    def _apply_supersession_link(self, newer: Capsule, older: Capsule) -> None:
        """Creates supersedes edge from newer to older, and marks older capsule confidence as deprecated."""
        try:
            self.store.link(newer.id, older.id, "supersedes")
            # Update older capsule confidence to deprecated
            if older.confidence != "deprecated":
                self.store.update(older.id, confidence="deprecated")
                logger.info(
                    "Applied supersession: %s supersedes %s (deprecated)",
                    newer.id[:8],
                    older.id[:8],
                )
        except Exception as exc:
            logger.warning("Failed to apply supersession link %s -> %s: %s", newer.id, older.id, exc)

    def resolve_supersession(
        self, newer_id: str, older_id: str, deprecate_older: bool = True
    ) -> Dict[str, Any]:
        """Explicitly links newer_id superseding older_id and deprecates older capsule."""
        newer = self.store.get(newer_id)
        older = self.store.get(older_id)
        if not newer or not older:
            raise ValueError("One or both capsules not found")

        rel = self.store.link(newer_id, older_id, "supersedes")
        if deprecate_older and older.confidence != "deprecated":
            self.store.update(older_id, confidence="deprecated")

        return {
            "status": "resolved",
            "newer_id": newer_id,
            "older_id": older_id,
            "relationship": rel.relationship_type,
            "older_deprecated": deprecate_older,
        }

    def get_superseded_ids(self) -> Set[str]:
        """Returns set of all capsule IDs that have been superseded or marked deprecated."""
        # Find all target IDs of 'supersedes' edges
        superseded_edge_ids = {
            r.to_capsule_id
            for r in self.db.query(CapsuleRelationship)
            .filter(CapsuleRelationship.relationship_type == "supersedes")
            .all()
        }
        # Find all capsules with confidence='deprecated'
        deprecated_caps = {
            c.id
            for c in self.db.query(Capsule)
            .filter(Capsule.confidence == "deprecated", Capsule.archived.is_(False))
            .all()
        }
        return superseded_edge_ids.union(deprecated_caps)
