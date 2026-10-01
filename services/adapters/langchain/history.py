"""LangChain BaseChatMessageHistory adapter for conversation storage."""
from __future__ import annotations

from typing import Any, List, Optional

try:
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.messages import BaseMessage
except ImportError as exc:
    raise ImportError(
        "The LangChain adapter requires 'langchain-core'. "
        "Please install it with: pip install kapsule[langchain] or pip install langchain-core"
    ) from exc


class CapsuleChatMessageHistory(BaseChatMessageHistory):
    """In-memory chat message history with session scoping for LangChain/LangGraph."""

    def __init__(self, session_id: str, db_session: Optional[Any] = None) -> None:
        self.session_id = session_id
        self.db_session = db_session
        self._messages: List[BaseMessage] = []

    @property
    def messages(self) -> List[BaseMessage]:
        return self._messages

    def add_message(self, message: BaseMessage) -> None:
        self._messages.append(message)

    def clear(self) -> None:
        self._messages.clear()
