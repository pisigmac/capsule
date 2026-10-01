"""CrewAI Storage Backend adapter backed by Capsule memory engine."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from crewai.memory.storage.interface import Storage
except ImportError:
    class Storage:
        """Fallback Storage base class when crewai is not installed."""

        def save(self, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
            raise NotImplementedError

        def search(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
            raise NotImplementedError

        def reset(self) -> None:
            pass

from services.search.engine import SearchEngine
from services.shared.config import config
from services.shared.models import get_session_factory
from services.store.store import CapsuleStore

logger = logging.getLogger("capsule.adapters.crewai")


class CapsuleStorage(Storage):
    """CrewAI custom storage backend that persists inter-agent memories to git-trackable .caps.md files."""

    def __init__(
        self,
        storage_dir: Optional[str | Path] = None,
        confidence_default: str = "medium",
        default_tags: Optional[List[str]] = None,
        search_mode: str = "hybrid",
        db_session: Optional[Any] = None,
    ) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else config.capsules_dir
        self.confidence_default = confidence_default
        self.default_tags = default_tags or ["crewai"]
        self.search_mode = search_mode
        self.db_session = db_session

    def save(self, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Save a task output or agent memory into an atomic capsule."""
        meta = metadata or {}
        content_str = str(value).strip() if value is not None else ""
        if not content_str:
            return

        # Extract topic
        topic = (
            meta.get("topic")
            or meta.get("task_description")
            or meta.get("task")
            or meta.get("agent_role")
        )
        if not topic:
            first_line = content_str.split("\n")[0].strip()
            topic = first_line[:80] if len(first_line) >= 3 else f"CrewAI Insight: {first_line}"

        topic = str(topic).strip()
        if len(topic) < 3:
            topic = f"CrewAI Insight: {topic}"

        # Extract tags
        raw_tags = meta.get("tags")
        if isinstance(raw_tags, list):
            tags = list(raw_tags)
        elif isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = list(self.default_tags)

        if "crewai" not in tags:
            tags.append("crewai")

        agent_role = meta.get("agent_role") or meta.get("role") or meta.get("agent")
        if agent_role:
            role_slug = str(agent_role).lower().replace(" ", "-")
            if role_slug not in tags:
                tags.append(role_slug)

        # Extract source and confidence
        source = meta.get("source") or (f"crewai:{agent_role}" if agent_role else "crewai-agent")
        confidence = meta.get("confidence") or self.confidence_default

        # Format content if very short
        if len(content_str) < 10:
            content_str = f"Agent discovery: {content_str}\n\nTask: {meta.get('task_description', 'N/A')}"

        db = self.db_session
        close_db = False
        if db is None:
            db = get_session_factory()()
            close_db = True

        try:
            store = CapsuleStore(db, capsules_dir=self.storage_dir)
            store.create(
                topic=topic,
                content=content_str,
                tags=tags,
                source=source,
                confidence=confidence,
            )
        except Exception as exc:
            logger.error("Error saving capsule memory from CrewAI: %s", exc)
            raise
        finally:
            if close_db:
                db.close()

    def search(
        self,
        query: str,
        limit: int = 3,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search memory vault using hybrid search."""
        db = self.db_session
        close_db = False
        if db is None:
            db = get_session_factory()()
            close_db = True

        try:
            engine = SearchEngine(db)
            raw_results = engine.search(
                query=query,
                limit=limit,
                mode=self.search_mode,
            )

            results: List[Dict[str, Any]] = []
            for r in raw_results:
                score = float(r.get("score", 1.0))
                if score_threshold is not None and score < score_threshold:
                    continue

                topic = r.get("topic", "")
                content = r.get("content", "")
                full_text = f"{topic}\n\n{content}".strip() if topic else content

                results.append(
                    {
                        "id": r.get("id"),
                        "topic": topic,
                        "content": content,
                        "context": full_text,
                        "metadata": {
                            "id": r.get("id"),
                            "topic": topic,
                            "tags": r.get("tags", []),
                            "confidence": r.get("confidence"),
                            "source": r.get("source"),
                            "file_path": r.get("file_path"),
                        },
                        "score": score,
                    }
                )

            return results
        finally:
            if close_db:
                db.close()

    def reset(self) -> None:
        """Reset hook required by CrewAI Storage interface."""
        pass
