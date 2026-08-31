"""Full-text search over the capsule index."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..shared.models import Capsule, Tag

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CONFIDENCE_ORDER = {"hearsay": 0, "low": 1, "medium": 2, "high": 3}


def estimate_tokens(value: str) -> int:
    """Cheap token estimate: ~4 characters per token."""
    return max(1, len(value) // 4) if value else 0


def to_fts_query(raw: str) -> Optional[str]:
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
    ) -> List[Dict[str, Any]]:
        tag_names = [t.lower().strip() for t in (tags or []) if t and t.strip()]
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

    def compose(
        self,
        tags: Optional[List[str]] = None,
        query: Optional[str] = None,
        confidence_min: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        capsules = self.search(
            query=query or "",
            tags=tags,
            archived=False,
            limit=200,
            offset=0,
        )

        if confidence_min:
            min_val = CONFIDENCE_ORDER.get(confidence_min, 0)
            capsules = [
                c for c in capsules if CONFIDENCE_ORDER.get(c.get("confidence", "medium"), 0) >= min_val
            ]

        parts: List[str] = []
        current_tokens = 0
        included = 0
        truncated = False

        for capsule in capsules:
            header = f"# {capsule['topic']}\n"
            body = f"{capsule['content']}\n"
            meta = (
                f"[id: {capsule['id']}, confidence: {capsule['confidence']}, "
                f"tags: {', '.join(capsule.get('tags', []))}]\n\n"
            )
            section = header + body + meta
            section_tokens = estimate_tokens(section)
            if current_tokens + section_tokens > max_tokens:
                truncated = True
                break
            parts.append(section)
            current_tokens += section_tokens
            included += 1

        context = "\n".join(parts)
        return {
            "context": context,
            "token_estimate": estimate_tokens(context) if context else 0,
            "capsule_count": included,
            "truncated": truncated,
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
