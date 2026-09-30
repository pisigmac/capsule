"""LlamaIndex Retriever adapter backed by Capsule memory engine."""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

try:
    from llama_index.core.base.base_retriever import BaseRetriever
    from llama_index.core.callbacks.base import CallbackManager
    from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
except ImportError as exc:
    raise ImportError(
        "The LlamaIndex adapter requires 'llama-index-core'. "
        "Please install it with: pip install kapsule[llamaindex] or pip install llama-index-core"
    ) from exc

from services.search.engine import SearchEngine
from services.shared.models import get_session_factory


class CapsuleRetriever(BaseRetriever):
    """LlamaIndex retriever backed by Capsule hybrid memory engine."""

    def __init__(
        self,
        tags: Optional[List[str]] = None,
        limit: int = 5,
        mode: str = "hybrid",
        confidence_min: Optional[str] = None,
        capsules_dir: Optional[str] = None,
        db_session: Optional[Any] = None,
        callback_manager: Optional[CallbackManager] = None,
    ) -> None:
        super().__init__(callback_manager=callback_manager)
        self.tags = tags or []
        self.limit = limit
        self.mode = mode
        self.confidence_min = confidence_min
        self.capsules_dir = capsules_dir
        self.db_session = db_session

    def _retrieve(self, query_bundle: QueryBundle | str) -> List[NodeWithScore]:
        """Synchronously retrieve relevant nodes from Capsule."""
        if isinstance(query_bundle, str):
            query_str = query_bundle
        else:
            query_str = query_bundle.query_str

        db = self.db_session
        close_db = False
        if db is None:
            db = get_session_factory()()
            close_db = True

        try:
            engine = SearchEngine(db)
            raw_results = engine.search(
                query=query_str,
                tags=self.tags or None,
                confidence=self.confidence_min,
                limit=self.limit,
                mode=self.mode,
            )

            nodes: List[NodeWithScore] = []
            for r in raw_results:
                metadata = {
                    "id": r.get("id"),
                    "topic": r.get("topic"),
                    "tags": r.get("tags", []),
                    "confidence": r.get("confidence"),
                    "freshness": r.get("freshness"),
                    "file_path": r.get("file_path"),
                }
                metadata = {k: v for k, v in metadata.items() if v is not None}

                topic = r.get("topic", "")
                content = r.get("content", "")
                text = f"{topic}\n\n{content}".strip() if topic else content

                node = TextNode(
                    id_=r.get("id"),
                    text=text,
                    metadata=metadata,
                )
                score = float(r.get("score", 1.0))
                nodes.append(NodeWithScore(node=node, score=score))

            return nodes
        finally:
            if close_db:
                db.close()

    async def _aretrieve(self, query_bundle: QueryBundle | str) -> List[NodeWithScore]:
        """Asynchronously retrieve relevant nodes from Capsule."""
        return self._retrieve(query_bundle)
