"""PydanticAI & LiteLLM prompt context injector adapter for Capsule."""
from services.adapters.pydantic_ai.hook import (
    DEFAULT_FOOTER,
    DEFAULT_HEADER,
    async_inject_capsule_context,
    capsule_context_hook,
    inject_capsule_context,
)

__all__ = [
    "inject_capsule_context",
    "async_inject_capsule_context",
    "capsule_context_hook",
    "DEFAULT_HEADER",
    "DEFAULT_FOOTER",
]
