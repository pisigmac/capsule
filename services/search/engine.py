"""Full-text search over the capsule index."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..embed import embedder as embed_mod
from ..shared.config import config
from ..shared.models import Capsule, CapsuleRelationship, Tag

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CONFIDENCE_ORDER = {"hearsay": 0, "low": 1, "medium": 2, "high": 3}

EDGE_WEIGHTS: Dict[str, float] = {
    "depends_on": 1.5,
    "prerequisite": 1.5,
    "implements": 1.4,
    "implemented_by": 1.4,
    "defines": 1.2,
    "calls": 1.2,
    "supersedes": 1.1,
    "relates_to": 1.0,
}


def estimate_tokens(value: str) -> int:
    """Cheap token estimate: ~4 characters per token."""
    return max(1, len(value) // 4) if value else 0


def to_fts_query(raw: str) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    # If the caller provides an explicit boolean query with OR / AND, preserve it
    trimmed = raw.strip()
    if " OR " in trimmed or " AND " in trimmed:
        return trimmed
    tokens = _TOKEN_RE.findall(raw)[:32]
    if not tokens:
        return None
    return " AND ".join(f'"{token}"' for token in tokens)


def _sqlite_search_sql(
    archived: Optional[bool],
    confidence: Optional[str],
    limit: int,
    offset: int,
) -> tuple[str, Dict[str, Any]]:
    sql = """
        SELECT c.rowid AS rowid
        FROM capsule_search
        JOIN capsules c ON c.rowid = capsule_search.rowid
        WHERE capsule_search MATCH :query
    """
    params: Dict[str, Any] = {}
    if archived is not None:
        sql += " AND c.archived = :archived"
        params["archived"] = archived
    if confidence:
        sql += " AND c.confidence = :confidence"
        params["confidence"] = confidence
    sql += " ORDER BY bm25(capsule_search) LIMIT :limit OFFSET :offset"
    params["limit"] = max(limit, 1)
    params["offset"] = max(offset, 0)
    return sql, params


def _postgres_search_sql(
    archived: Optional[bool],
    confidence: Optional[str],
    limit: int,
    offset: int,
) -> tuple[str, Dict[str, Any]]:
    sql = """
        SELECT c.rowid AS rowid
        FROM capsules c
        WHERE c.search_vector @@ plainto_tsquery('english', :query)
    """
    params: Dict[str, Any] = {}
    if archived is not None:
        sql += " AND c.archived = :archived"
        params["archived"] = archived
    if confidence:
        sql += " AND c.confidence = :confidence"
        params["confidence"] = confidence
    sql += """
        ORDER BY ts_rank_cd(c.search_vector, plainto_tsquery('english', :query)) DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = max(limit, 1)
    params["offset"] = max(offset, 0)
    return sql, params


class SearchEngine:
    """Search capsules using SQLite FTS5 or Postgres tsvector, plus tag filters."""

    def __init__(self, db: Session):
        self.db = db

    def _row_to_dict(self, capsule: Capsule) -> Dict[str, Any]:
        return capsule.to_dict()

    def search(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        confidence: Optional[str] = None,
        archived: Optional[bool] = False,
        limit: int = 50,
        offset: int = 0,
        match_all_tags: bool = True,
        mode: str = "fts",
    ) -> List[Dict[str, Any]]:
        chosen = (mode or "fts").lower()
        if chosen not in {"fts", "semantic", "hybrid"}:
            chosen = "fts"
        if chosen != "fts" and not config.embed_enabled:
            chosen = "fts"

        tag_names = [t.lower().strip() for t in (tags or []) if t and t.strip()]
        if chosen == "semantic":
            return self._semantic_search(
                query=query,
                tag_names=tag_names,
                confidence=confidence,
                archived=archived,
                limit=limit,
                offset=offset,
                match_all_tags=match_all_tags,
            )
        if chosen == "hybrid":
            return self._hybrid_search(
                query=query,
                tag_names=tag_names,
                confidence=confidence,
                archived=archived,
                limit=limit,
                offset=offset,
                match_all_tags=match_all_tags,
            )

        dialect = self.db.get_bind().dialect.name
        fts = to_fts_query(query or "") if dialect == "sqlite" else (query or "").strip()[:200]

        if fts:
            if dialect == "postgresql":
                sql, params = _postgres_search_sql(
                    archived=archived, confidence=confidence, limit=limit, offset=offset
                )
                params["query"] = fts
            else:
                sql, params = _sqlite_search_sql(
                    archived=archived, confidence=confidence, limit=limit, offset=offset
                )
                params["query"] = fts
            rows = self.db.execute(text(sql), params).mappings().all()
            rowids = [row["rowid"] for row in rows]
            if not rowids:
                return []
            capsules = (
                self.db.query(Capsule)
                .filter(Capsule.rowid.in_(rowids))
                .all()
            )
            by_rowid = {c.rowid: c for c in capsules}
            ordered = [by_rowid[rid] for rid in rowids if rid in by_rowid]
            if tag_names:
                ordered = [c for c in ordered if self._matches_tags(c, tag_names, match_all_tags)]
            return [self._row_to_dict(c) for c in ordered]

        q = self.db.query(Capsule)
        if archived is not None:
            q = q.filter(Capsule.archived == archived)
        if confidence:
            q = q.filter(Capsule.confidence == confidence)
        if tag_names:
            if match_all_tags:
                for name in tag_names:
                    q = q.filter(Capsule.tags.any(Tag.name == name))
            else:
                q = q.filter(Capsule.tags.any(Tag.name.in_(tag_names))).distinct()
        capsules = q.order_by(Capsule.updated_at.desc()).offset(offset).limit(limit).all()
        return [self._row_to_dict(c) for c in capsules]

    def _semantic_search(
        self,
        query: str,
        tag_names: List[str],
        confidence: Optional[str],
        archived: Optional[bool],
        limit: int,
        offset: int,
        match_all_tags: bool,
    ) -> List[Dict[str, Any]]:
        query_vec = embed_mod.embed_text(query or "")
        if query_vec is None:
            return self.search(
                query=query,
                tags=tag_names,
                confidence=confidence,
                archived=archived,
                limit=limit,
                offset=offset,
                match_all_tags=match_all_tags,
                mode="fts",
            )
        q = self.db.query(Capsule).filter(Capsule.embedding.isnot(None))
        if archived is not None:
            q = q.filter(Capsule.archived == archived)
        if confidence:
            q = q.filter(Capsule.confidence == confidence)
        capsules = q.limit(config.embed_candidate_limit).all()
        scored: List[tuple[float, Capsule]] = []
        for capsule in capsules:
            if tag_names and not self._matches_tags(capsule, tag_names, match_all_tags):
                continue
            vector = embed_mod.decode_embedding(capsule.embedding)
            if not vector:
                continue
            scored.append((embed_mod.cosine(query_vec, vector), capsule))
        scored.sort(key=lambda item: item[0], reverse=True)
        sliced = scored[offset : offset + max(limit, 1)]
        return [self._row_to_dict(capsule) for _, capsule in sliced]

    def _hybrid_search(
        self,
        query: str,
        tag_names: List[str],
        confidence: Optional[str],
        archived: Optional[bool],
        limit: int,
        offset: int,
        match_all_tags: bool,
    ) -> List[Dict[str, Any]]:
        fetch = max((limit + offset) * 4, 40)
        lexical = self.search(
            query=query,
            tags=tag_names,
            confidence=confidence,
            archived=archived,
            limit=fetch,
            offset=0,
            match_all_tags=match_all_tags,
            mode="fts",
        )
        semantic = self._semantic_search(
            query=query,
            tag_names=tag_names,
            confidence=confidence,
            archived=archived,
            limit=fetch,
            offset=0,
            match_all_tags=match_all_tags,
        )
        scores: Dict[str, float] = {}
        by_id: Dict[str, Dict[str, Any]] = {}
        for rank, row in enumerate(lexical):
            scores[row["id"]] = scores.get(row["id"], 0.0) + 1.0 / (60 + rank + 1)
            by_id[row["id"]] = row
        for rank, row in enumerate(semantic):
            scores[row["id"]] = scores.get(row["id"], 0.0) + 1.0 / (60 + rank + 1)
            by_id[row["id"]] = row
        ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        picked = ordered[offset : offset + max(limit, 1)]
        return [by_id[cid] for cid in picked]

    def _matches_tags(self, capsule: Capsule, tag_names: List[str], match_all: bool) -> bool:
        have = {t.name for t in capsule.tags}
        if match_all:
            return set(tag_names).issubset(have)
        return bool(have.intersection(tag_names))

    def search_by_tags(
        self,
        tags: List[str],
        match_all: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return self.search(query="", tags=tags, archived=False, limit=limit, offset=offset, match_all_tags=match_all)

    def _get_superseded_map(self) -> Dict[str, str]:
        """Returns mapping of superseded_capsule_id -> superseding_capsule_description."""
        mapping: Dict[str, str] = {}
        rels = (
            self.db.query(CapsuleRelationship, Capsule)
            .join(Capsule, Capsule.id == CapsuleRelationship.from_capsule_id)
            .filter(CapsuleRelationship.relationship_type == "supersedes")
            .all()
        )
        for rel, newer_cap in rels:
            mapping[rel.to_capsule_id] = f"'{newer_cap.topic}' ({newer_cap.id[:8]})"
        
        # Also include capsules with confidence='deprecated'
        dep_caps = self.db.query(Capsule).filter(Capsule.confidence == "deprecated", Capsule.archived.is_(False)).all()
        for dc in dep_caps:
            if dc.id not in mapping:
                mapping[dc.id] = "Deprecated confidence status"
        return mapping

    def _expand_graph_affinity(
        self,
        candidates: List[Dict[str, Any]],
        confidence_min: Optional[str] = None,
        max_hops: int = 1,
        affinity_weight: float = 0.5,
        include_superseded: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Pillar 1 & 2: Graph-Aware Multi-Hop Affinity Propagation with Supersession Suppression.
        Pulls in related dependencies (depends_on, implements, calls, defines) and boosts affinity
        scores of candidate capsules that share typed graph edges with top-ranking nodes.
        """
        if not candidates or max_hops < 1:
            return candidates

        min_val = CONFIDENCE_ORDER.get(confidence_min, 0) if confidence_min else 0
        superseded_map = {} if include_superseded else self._get_superseded_map()
        candidate_map = {c["id"]: dict(c) for c in candidates if c["id"] not in superseded_map}
        base_scores: Dict[str, float] = {
            c["id"]: 1.0 / (rank + 1.0) for rank, c in enumerate(candidates) if c["id"] not in superseded_map
        }
        affinity_scores: Dict[str, float] = {c["id"]: 0.0 for c in candidates if c["id"] not in superseded_map}

        # Seed initial top candidates (up to top 25) for graph expansion
        seed_candidates = [c for c in candidates if c["id"] not in superseded_map][:25]

        for seed in seed_candidates:
            seed_id = seed["id"]
            seed_topic = seed.get("topic", "Related Node")
            seed_weight = base_scores.get(seed_id, 0.5)

            # Query outgoing relationships
            outgoing = (
                self.db.query(CapsuleRelationship)
                .filter(CapsuleRelationship.from_capsule_id == seed_id)
                .all()
            )

            # Query incoming relationships
            incoming = (
                self.db.query(CapsuleRelationship)
                .filter(CapsuleRelationship.to_capsule_id == seed_id)
                .all()
            )

            # Process outgoing edges
            for rel in outgoing:
                target_id = rel.to_capsule_id
                if not include_superseded and target_id in superseded_map:
                    continue
                w = EDGE_WEIGHTS.get(rel.relationship_type, 1.0) * seed_weight
                if target_id in candidate_map:
                    affinity_scores[target_id] = affinity_scores.get(target_id, 0.0) + w
                else:
                    # Pull in from DB if not already present in search candidates
                    target_row = (
                        self.db.query(Capsule)
                        .filter(Capsule.id == target_id, Capsule.archived.is_(False))
                        .first()
                    )
                    if target_row:
                        conf = target_row.confidence or "medium"
                        if CONFIDENCE_ORDER.get(conf, 0) >= min_val:
                            row_dict = self._row_to_dict(target_row)
                            row_dict["via_graph_edge"] = rel.relationship_type
                            row_dict["connected_to"] = seed_topic
                            candidate_map[target_id] = row_dict
                            base_scores[target_id] = 0.05
                            affinity_scores[target_id] = w

            # Process incoming edges
            for rel in incoming:
                source_id = rel.from_capsule_id
                if not include_superseded and source_id in superseded_map:
                    continue
                w = EDGE_WEIGHTS.get(rel.relationship_type, 1.0) * seed_weight * 0.8
                if source_id in candidate_map:
                    affinity_scores[source_id] = affinity_scores.get(source_id, 0.0) + w
                else:
                    source_row = (
                        self.db.query(Capsule)
                        .filter(Capsule.id == source_id, Capsule.archived.is_(False))
                        .first()
                    )
                    if source_row:
                        conf = source_row.confidence or "medium"
                        if CONFIDENCE_ORDER.get(conf, 0) >= min_val:
                            row_dict = self._row_to_dict(source_row)
                            row_dict["via_graph_edge"] = f"incoming:{rel.relationship_type}"
                            row_dict["connected_to"] = seed_topic
                            candidate_map[source_id] = row_dict
                            base_scores[source_id] = 0.05
                            affinity_scores[source_id] = w

        # Combine base relevance score and graph affinity boost
        final_scores: Dict[str, float] = {}
        for cid, cap in candidate_map.items():
            base = base_scores.get(cid, 0.0)
            aff = affinity_scores.get(cid, 0.0)
            combined = base + (affinity_weight * aff)
            final_scores[cid] = combined
            cap["affinity_score"] = round(combined, 4)

        # Sort candidates by combined utility score descending
        reordered = sorted(candidate_map.values(), key=lambda c: final_scores.get(c["id"], 0.0), reverse=True)
        return reordered

    def compose(
        self,
        tags: Optional[List[str]] = None,
        query: Optional[str] = None,
        confidence_min: Optional[str] = None,
        max_tokens: int = 4000,
        mode: str = "fts",
        match_all_tags: bool = False,
        graph_expansion: bool = True,
        max_hops: int = 1,
        affinity_weight: float = 0.5,
        include_superseded: bool = False,
    ) -> Dict[str, Any]:
        capsules = self.search(
            query=query or "",
            tags=tags,
            archived=False,
            limit=200,
            offset=0,
            mode=mode,
            match_all_tags=match_all_tags,
        )

        superseded_map = {} if include_superseded else self._get_superseded_map()
        excluded_capsules: List[Dict[str, Any]] = []

        # Filter superseded capsules if not explicitly included
        if not include_superseded and superseded_map:
            filtered_capsules = []
            for c in capsules:
                if c["id"] in superseded_map:
                    section_tokens = estimate_tokens(f"# {c['topic']}\n{c['content']}\n")
                    excluded_capsules.append({
                        "id": c["id"],
                        "topic": c["topic"],
                        "content": c["content"],
                        "tags": c.get("tags", []),
                        "confidence": c.get("confidence", "medium"),
                        "token_estimate": section_tokens,
                        "file_path": c.get("file_path"),
                        "source": c.get("source"),
                        "reason": f"Superseded by {superseded_map[c['id']]}",
                    })
                else:
                    filtered_capsules.append(c)
            capsules = filtered_capsules

        if confidence_min:
            min_val = CONFIDENCE_ORDER.get(confidence_min, 0)
            capsules = [
                c for c in capsules if CONFIDENCE_ORDER.get(c.get("confidence", "medium"), 0) >= min_val
            ]

        # Apply Graph-Aware Affinity Propagation & Dependency Closures
        if graph_expansion and capsules:
            capsules = self._expand_graph_affinity(
                candidates=capsules,
                confidence_min=confidence_min,
                max_hops=max_hops,
                affinity_weight=affinity_weight,
                include_superseded=include_superseded,
            )

        parts: List[str] = []
        current_tokens = 0
        included = 0
        truncated = False
        included_capsules: List[Dict[str, Any]] = []

        for capsule in capsules:
            header = f"# {capsule['topic']}\n"
            body = f"{capsule['content']}\n"
            meta = (
                f"[id: {capsule['id']}, confidence: {capsule['confidence']}, "
                f"tags: {', '.join(capsule.get('tags', []))}]\n\n"
            )
            section = header + body + meta
            section_tokens = estimate_tokens(section)
            cap_item = {
                "id": capsule["id"],
                "topic": capsule["topic"],
                "content": capsule["content"],
                "tags": capsule.get("tags", []),
                "confidence": capsule.get("confidence", "medium"),
                "token_estimate": section_tokens,
                "file_path": capsule.get("file_path"),
                "source": capsule.get("source"),
                "via_graph_edge": capsule.get("via_graph_edge"),
                "connected_to": capsule.get("connected_to"),
                "affinity_score": capsule.get("affinity_score"),
            }
            if current_tokens + section_tokens > max_tokens:
                truncated = True
                cap_item["reason"] = f"Exceeds budget (+{section_tokens} tokens)"
                excluded_capsules.append(cap_item)
                continue
            parts.append(section)
            current_tokens += section_tokens
            included += 1
            included_capsules.append(cap_item)

        context = "\n".join(parts)
        return {
            "context": context,
            "token_estimate": estimate_tokens(context) if context else 0,
            "capsule_count": included,
            "truncated": truncated,
            "included_capsules": included_capsules,
            "excluded_capsules": excluded_capsules,
            "total_candidates": len(capsules) + len(excluded_capsules),
            "max_tokens": max_tokens,
            "graph_expansion": graph_expansion,
            "include_superseded": include_superseded,
        }

    def stale_capsules(self, days: int = 90) -> List[Dict[str, Any]]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        capsules = (
            self.db.query(Capsule)
            .filter(Capsule.updated_at < cutoff, Capsule.archived == False)  # noqa: E712
            .order_by(Capsule.updated_at.asc())
            .all()
        )
        return [self._row_to_dict(c) for c in capsules]

    def counts(self) -> Dict[str, int]:
        total = self.db.query(func.count(Capsule.rowid)).scalar() or 0
        archived = (
            self.db.query(func.count(Capsule.rowid)).filter(Capsule.archived == True).scalar() or 0  # noqa: E712
        )
        tags = self.db.query(func.count(Tag.id)).scalar() or 0
        return {
            "total": total,
            "archived": archived,
            "active": total - archived,
            "tags": tags,
        }
