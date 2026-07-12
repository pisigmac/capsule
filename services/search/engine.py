"""Full-text search engine for capsules."""
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..shared.models import Capsule, Tag


class SearchEngine:
    """Search capsules using SQLite FTS5."""

    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        confidence: Optional[str] = None,
        archived: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search capsules by text query and optional filters."""
        # Build the FTS5 query
        fts_query = " OR ".join(f'"{q}"' for q in query.split())

        sql = """
            SELECT c.id, c.topic, c.content, c.freshness, c.source, 
                   c.confidence, c.created_at, c.updated_at, c.archived, c.file_path,
                   rank
            FROM capsule_search cs
            JOIN capsules c ON cs.rowid = c.id
            WHERE capsule_search MATCH :query
        """
        params = {"query": fts_query}

        if archived is not None:
            sql += " AND c.archived = :archived"
            params["archived"] = archived

        if confidence:
            sql += " AND c.confidence = :confidence"
            params["confidence"] = confidence

        sql += " ORDER BY rank"
        sql += " LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        results = self.db.execute(text(sql), params).mappings().all()

        capsules = []
        for row in results:
            capsule_dict = dict(row)
            capsule_dict["id"] = str(capsule_dict["id"])

            # Fetch tags
            capsule_obj = self.db.query(Capsule).filter(Capsule.id == capsule_dict["id"]).first()
            if capsule_obj:
                capsule_dict["tags"] = [t.name for t in capsule_obj.tags]
            else:
                capsule_dict["tags"] = []

            capsules.append(capsule_dict)

        return capsules

    def search_by_tags(
        self,
        tags: List[str],
        match_all: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search capsules by tags."""
        tag_names = [t.lower().strip() for t in tags]

        if match_all:
            # All tags must match
            query = self.db.query(Capsule).join(Capsule.tags)
            for tag_name in tag_names:
                query = query.filter(Tag.name == tag_name)
        else:
            # Any tag matches
            query = self.db.query(Capsule).join(Capsule.tags).filter(Tag.name.in_(tag_names))

        capsules = query.offset(offset).limit(limit).all()
        return [c.to_dict() for c in capsules]

    def compose(
        self,
        tags: Optional[List[str]] = None,
        query: Optional[str] = None,
        confidence_min: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        """Compose a context window from matching capsules."""
        capsules = []

        if query:
            capsules = self.search(query, tags=tags, limit=100)
        elif tags:
            capsules = self.search_by_tags(tags, limit=100)
        else:
            # Get all non-archived capsules
            capsules = [c.to_dict() for c in self.db.query(Capsule).filter(Capsule.archived == False).all()]

        # Filter by confidence if specified
        if confidence_min:
            confidence_order = {"hearsay": 0, "low": 1, "medium": 2, "high": 3}
            min_val = confidence_order.get(confidence_min, 0)
            capsules = [c for c in capsules if confidence_order.get(c.get("confidence", "medium"), 0) >= min_val]

        # Build context window
        parts = []
        current_tokens = 0
        token_estimate = lambda text: len(text.split())  # rough estimate

        for capsule in capsules:
            header = f"# {capsule['topic']}\n"
            body = f"{capsule['content']}\n"
            meta = f"[confidence: {capsule['confidence']}, tags: {', '.join(capsule.get('tags', []))}]\n\n"

            section = header + body + meta
            section_tokens = token_estimate(section)

            if current_tokens + section_tokens > max_tokens:
                break

            parts.append(section)
            current_tokens += section_tokens

        return "\n".join(parts)

    def stale_capsules(self, days: int = 90) -> List[Dict[str, Any]]:
        """Find capsules that haven't been updated in N days."""
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        capsules = self.db.query(Capsule).filter(
            Capsule.updated_at < cutoff,
            Capsule.archived == False
        ).all()

        return [c.to_dict() for c in capsules]
