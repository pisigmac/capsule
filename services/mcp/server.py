"""Capsule MCP server using the official Python SDK (stdio or Streamable HTTP)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from ..search.engine import SearchEngine
from ..shared.config import config
from ..shared.logging import setup_logging
from ..shared.models import get_session_factory, init_db, reset_engine
from ..store.store import CapsuleStore, StoreError

SERVER_NAME = "capsule"
SERVER_VERSION = "0.4.0"


def _session():
    return get_session_factory()()


def call_tool(name: str, arguments: Dict[str, Any]) -> str:
    db = _session()
    try:
        store = CapsuleStore(db)
        engine = SearchEngine(db)
        if name == "search_capsules":
            results = engine.search(
                query=arguments.get("query") or "",
                tags=arguments.get("tags"),
                confidence=arguments.get("confidence"),
                limit=int(arguments.get("limit") or 20),
                mode=arguments.get("mode") or "fts",
            )
            return json.dumps(results, indent=2)
        if name == "compose_context":
            composed = engine.compose(
                query=arguments.get("query"),
                tags=arguments.get("tags"),
                confidence_min=arguments.get("confidence_min"),
                max_tokens=int(arguments.get("max_tokens") or 4000),
                mode=arguments.get("mode") or "fts",
            )
            return json.dumps(composed, indent=2)
        if name == "get_capsule":
            capsule = store.get(str(arguments.get("id") or ""))
            if not capsule:
                raise StoreError("Capsule not found")
            return json.dumps(capsule.to_dict(), indent=2)
        if name == "create_capsule":
            capsule = store.create(
                topic=arguments["topic"],
                content=arguments["content"],
                tags=arguments.get("tags") or [],
                source=arguments.get("source") or "mcp",
                confidence=arguments.get("confidence") or "medium",
            )
            db.commit()
            return json.dumps(capsule.to_dict(), indent=2)
        if name == "list_stale":
            stale = engine.stale_capsules(days=int(arguments.get("days") or 90))
            return json.dumps(stale, indent=2)
        raise StoreError(f"Unknown tool: {name}")
    finally:
        db.close()


def build_mcp(host: str = "127.0.0.1", port: int = 9101) -> FastMCP:
    server = FastMCP(
        SERVER_NAME,
        instructions="Atomic knowledge capsules. Search, compose, and write .capsule.md files.",
        host=host,
        port=port,
    )

    @server.tool()
    def search_capsules(
        query: str = "",
        tags: Optional[List[str]] = None,
        confidence: Optional[str] = None,
        limit: int = 20,
        mode: str = "fts",
    ) -> str:
        """Full-text or semantic search of atomic knowledge capsules."""
        return call_tool(
            "search_capsules",
            {
                "query": query,
                "tags": tags,
                "confidence": confidence,
                "limit": limit,
                "mode": mode,
            },
        )

    @server.tool()
    def compose_context(
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        confidence_min: Optional[str] = None,
        max_tokens: int = 4000,
        mode: str = "fts",
    ) -> str:
        """Build a token-budgeted context window from matching capsules."""
        return call_tool(
            "compose_context",
            {
                "query": query,
                "tags": tags,
                "confidence_min": confidence_min,
                "max_tokens": max_tokens,
                "mode": mode,
            },
        )

    @server.tool()
    def get_capsule(id: str) -> str:
        """Fetch one capsule by UUID."""
        return call_tool("get_capsule", {"id": id})

    @server.tool()
    def create_capsule(
        topic: str,
        content: str,
        tags: Optional[List[str]] = None,
        confidence: str = "medium",
        source: Optional[str] = None,
    ) -> str:
        """Create a new capsule file and index it. Duplicate content returns the existing row."""
        return call_tool(
            "create_capsule",
            {
                "topic": topic,
                "content": content,
                "tags": tags or [],
                "confidence": confidence,
                "source": source,
            },
        )

    @server.tool()
    def list_stale(days: int = 90) -> str:
        """List capsules not updated within N days."""
        return call_tool("list_stale", {"days": days})

    return server


def serve(http: bool = False, host: str = "127.0.0.1", port: int = 9101) -> None:
    setup_logging(config.log_level)
    config.ensure_dirs()
    reset_engine()
    init_db()
    db = _session()
    try:
        CapsuleStore(db).reconcile()
        db.commit()
    finally:
        db.close()

    mcp = build_mcp(host=host, port=port)
    if http:
        if config.api_token:
            # Streamable HTTP is local-first; bind to loopback unless the operator overrides host.
            pass
        mcp.run(transport="streamable-http")
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    serve()
