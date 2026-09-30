"""LangChain & LangGraph Retriever adapter backed by Capsule memory engine."""
from __future__ import annotations

from typing import Any, List, Optional
from pydantic import ConfigDict, Field

try:
    from langchain_core.callbacks.manager import (
        AsyncCallbackManagerForRetrieverRun,
        CallbackManagerForRetrieverRun,
    )
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
except ImportError as exc:
    raise ImportError(
        "The LangChain adapter requires 'langchain-core'. "
        "Please install it with: pip install kapsule[langchain] or pip install langchain-core"
    ) from exc

from services.search.engine import SearchEngine
from services.shared.models import get_session_factory


class CapsuleRetriever(BaseRetriever):
    """LangChain / LangGraph retriever backed by Capsule memory engine."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tags: List[str] = Field(default_factory=list, description="Filter capsules by required tags")
    limit: int = Field(default=5, description="Maximum number of documents to retrieve")
    search_mode: str = Field(default="hybrid", description="Search mode: 'fts', 'semantic', or 'hybrid'")
    confidence_min: Optional[str] = Field(default=None, description="Minimum confidence filter")
    capsules_dir: Optional[str] = Field(default=None, description="Path to capsules directory")
    db_session: Optional[Any] = Field(default=None, exclude=True, description="Optional custom SQLAlchemy session")

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        """Synchronously query Capsule and return LangChain Document instances."""
        db = self.db_session
        close_db = False
        if db is None:
            db = get_session_factory()()
            close_db = True

        try:
            engine = SearchEngine(db)
            raw_results = engine.search(
                query=query,
                tags=self.tags or None,
                confidence=self.confidence_min,
                limit=self.limit,
                mode=self.search_mode,
            )

            documents: List[Document] = []
            for r in raw_results:
                metadata = {
                    "id": r.get("id"),
                    "topic": r.get("topic"),
                    "tags": r.get("tags", []),
                    "confidence": r.get("confidence"),
                    "freshness": r.get("freshness"),
                    "file_path": r.get("file_path"),
                    "score": r.get("score"),
                }
                metadata = {k: v for k, v in metadata.items() if v is not None}
                doc = Document(
                    page_content=r.get("content", ""),
                    metadata=metadata,
                )
                documents.append(doc)

            return documents
        finally:
            if close_db:
                db.close()

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[AsyncCallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        """Asynchronously query Capsule documents."""
        return self._get_relevant_documents(query)
