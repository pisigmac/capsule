"""PydanticAI, LiteLLM, and raw SDK dynamic prompt context injector."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, List, Optional

from services.search.engine import SearchEngine
from services.shared.models import get_session_factory

DEFAULT_HEADER = "### RELEVANT PROJECT INVARIANTS & MEMORY (Capsule):"
DEFAULT_FOOTER = "### END MEMORY"

STOPWORDS = {
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "by", "can", "do",
    "does", "for", "from", "how", "i", "if", "in", "is", "it", "me", "my", "of",
    "on", "or", "our", "please", "tell", "the", "this", "to", "us", "was", "we",
    "what", "when", "where", "which", "who", "why", "will", "with", "would", "you",
}


def _extract_keywords(query: str) -> Optional[str]:
    import re
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_]+", query)]
    meaningful = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    if not meaningful:
        return None
    return " OR ".join(meaningful)


def inject_capsule_context(
    query: Optional[str] = None,
    tags: Optional[List[str]] = None,
    confidence_min: Optional[str] = "medium",
    max_tokens: int = 1000,
    search_mode: str = "hybrid",
    header: Optional[str] = None,
    footer: Optional[str] = None,
    match_all_tags: bool = False,
    db_session: Optional[Any] = None,
) -> str:
    """Compose an optimal knapsack context window from the local capsule vault.

    Returns an empty string if no relevant capsules match, preventing prompt pollution.
    """
    db = db_session
    close_db = False
    if db is None:
        db = get_session_factory()()
        close_db = True

    try:
        engine = SearchEngine(db)
        result = engine.compose(
            query=query or "",
            tags=tags,
            confidence_min=confidence_min,
            max_tokens=max_tokens,
            mode=search_mode,
            match_all_tags=match_all_tags,
        )

        context_text = result.get("context", "").strip()

        # If natural language query returned empty, retry with keyword OR search
        if not context_text and query and len(query.split()) > 1 and " OR " not in query and " AND " not in query:
            kw_query = _extract_keywords(query)
            if kw_query:
                retry_result = engine.compose(
                    query=kw_query,
                    tags=tags,
                    confidence_min=confidence_min,
                    max_tokens=max_tokens,
                    mode=search_mode,
                    match_all_tags=match_all_tags,
                )
                context_text = retry_result.get("context", "").strip()

        if not context_text:
            return ""

        h = DEFAULT_HEADER if header is None else header
        f = DEFAULT_FOOTER if footer is None else footer

        parts = []
        if h:
            parts.append(h)
        parts.append(context_text)
        if f:
            parts.append(f)

        return "\n".join(parts) + "\n"
    finally:
        if close_db:
            db.close()


async def async_inject_capsule_context(
    query: Optional[str] = None,
    tags: Optional[List[str]] = None,
    confidence_min: Optional[str] = "medium",
    max_tokens: int = 1000,
    search_mode: str = "hybrid",
    header: Optional[str] = None,
    footer: Optional[str] = None,
    match_all_tags: bool = False,
    db_session: Optional[Any] = None,
) -> str:
    """Asynchronously compose an optimal context window from the local capsule vault."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: inject_capsule_context(
            query=query,
            tags=tags,
            confidence_min=confidence_min,
            max_tokens=max_tokens,
            search_mode=search_mode,
            header=header,
            footer=footer,
            match_all_tags=match_all_tags,
            db_session=db_session,
        ),
    )


def capsule_context_hook(
    tags: Optional[List[str]] = None,
    confidence_min: Optional[str] = "medium",
    max_tokens: int = 1000,
    search_mode: str = "hybrid",
    header: Optional[str] = None,
    footer: Optional[str] = None,
    match_all_tags: bool = False,
    query_extractor: Optional[Callable[[Any], Optional[str]]] = None,
    db_session: Optional[Any] = None,
) -> Callable[[Any], str]:
    """Create a reusable context injector callback for PydanticAI (@agent.system_prompt) or LiteLLM hooks.

    Usage with PydanticAI:
        agent = Agent('openai:gpt-4o')

        @agent.system_prompt
        def add_invariants(ctx) -> str:
            hook = capsule_context_hook(tags=['auth', 'db'], max_tokens=800)
            return hook(ctx)
    """

    def hook_fn(ctx: Any = None) -> str:
        extracted_query: Optional[str] = None
        if query_extractor is not None:
            extracted_query = query_extractor(ctx)
        elif ctx is not None:
            # Duck-type extraction for PydanticAI RunContext or dictionary
            if hasattr(ctx, "user_prompt") and isinstance(ctx.user_prompt, str):
                extracted_query = ctx.user_prompt
            elif hasattr(ctx, "prompt") and isinstance(ctx.prompt, str):
                extracted_query = ctx.prompt
            elif isinstance(ctx, dict):
                extracted_query = ctx.get("user_prompt") or ctx.get("prompt") or ctx.get("query")
            elif isinstance(ctx, str):
                extracted_query = ctx

        return inject_capsule_context(
            query=extracted_query,
            tags=tags,
            confidence_min=confidence_min,
            max_tokens=max_tokens,
            search_mode=search_mode,
            header=header,
            footer=footer,
            match_all_tags=match_all_tags,
            db_session=db_session,
        )

    return hook_fn
