"""LangChain BaseMemory adapter backed by Capsule memory engine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

try:
    from langchain.memory.base import BaseMemory
except ImportError:
    try:
        from langchain_core.memory import BaseMemory
    except ImportError:
        from abc import ABC, abstractmethod

        class BaseMemory(BaseModel, ABC):
            """Abstract base class for memory in LangChain chains."""

            model_config = ConfigDict(arbitrary_types_allowed=True)

            @property
            @abstractmethod
            def memory_variables(self) -> List[str]:
                """The string keys this memory class will add to chain inputs."""

            @abstractmethod
            def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                """Return key-value pairs given the text input to the chain."""

            @abstractmethod
            def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
                """Save the context of this model run to memory."""

            def clear(self) -> None:
                """Clear memory contents."""
                pass


from services.search.engine import SearchEngine
from services.shared.models import get_session_factory


class CapsuleMemory(BaseMemory):
    """LangChain memory provider that injects token-bounded, deduplicated Capsule context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    memory_key: str = Field(default="history", description="Key under which context is exposed to prompt template")
    input_key: Optional[str] = Field(default=None, description="Explicit input variable name to extract query from")
    tags: List[str] = Field(default_factory=list, description="Filter capsules by required tags")
    confidence_min: str = Field(default="medium", description="Minimum confidence filter")
    max_tokens: int = Field(default=2000, description="Hard token budget cap for injected context")
    search_mode: str = Field(default="fts", description="Search mode: 'fts', 'semantic', or 'hybrid'")
    auto_harvest: bool = Field(default=False, description="Whether to harvest new capsules from save_context")
    capsules_dir: Optional[str] = Field(default=None, description="Path to capsules directory")
    db_session: Optional[Any] = Field(default=None, exclude=True, description="Optional custom SQLAlchemy session")

    @property
    def memory_variables(self) -> List[str]:
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Compose bounded context from relevant capsules matching the current input."""
        query = ""
        if self.input_key and self.input_key in inputs:
            query = str(inputs[self.input_key])
        else:
            for candidate in ("input", "query", "question", "prompt", "text", "human_input"):
                if candidate in inputs:
                    query = str(inputs[candidate])
                    break

        db = self.db_session
        close_db = False
        if db is None:
            db = get_session_factory()()
            close_db = True

        try:
            engine = SearchEngine(db)
            composed = engine.compose(
                query=query,
                tags=self.tags or None,
                confidence_min=self.confidence_min,
                max_tokens=self.max_tokens,
                mode=self.search_mode,
            )
            return {self.memory_key: composed.get("context", "")}
        finally:
            if close_db:
                db.close()

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        """Record interaction context."""
        pass

    def clear(self) -> None:
        """Clear memory cache."""
        pass
