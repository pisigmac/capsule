"""Minimal MCP server for Capsule. JSON-RPC 2.0 over stdio."""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

from ..search.engine import SearchEngine
from ..shared.config import config
from ..shared.logging import setup_logging
from ..shared.models import get_session_factory, init_db, reset_engine
from ..store.store import CapsuleStore, StoreError

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "capsule"
SERVER_VERSION = "0.3.0"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "search_capsules",
        "description": "Full-text search of atomic knowledge capsules. Filter by tags and confidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["high", "medium", "low", "hearsay"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
        },
    },
    {
        "name": "compose_context",
        "description": "Build a token-budgeted context window from matching capsules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "confidence_min": {"type": "string", "enum": ["high", "medium", "low", "hearsay"]},
                "max_tokens": {"type": "integer", "minimum": 50, "maximum": 32000, "default": 4000},
            },
        },
    },
    {
        "name": "get_capsule",
        "description": "Fetch one capsule by UUID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "create_capsule",
        "description": "Create a new capsule file and index it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["high", "medium", "low", "hearsay"]},
                "source": {"type": "string"},
            },
            "required": ["topic", "content"],
        },
    },
    {
        "name": "list_stale",
        "description": "List capsules not updated within N days.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "default": 90}},
        },
    },
]


def _session():
    return get_session_factory()()


def _call_tool(name: str, arguments: Dict[str, Any]) -> str:
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
            )
            return json.dumps(results, indent=2)
        if name == "compose_context":
            composed = engine.compose(
                query=arguments.get("query"),
                tags=arguments.get("tags"),
                confidence_min=arguments.get("confidence_min"),
                max_tokens=int(arguments.get("max_tokens") or 4000),
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


def _result(request_id: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: Dict[str, Any]) -> Dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method in {"notifications/initialized", "initialized"}:
        return None
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            text = _call_tool(name, arguments)
            return _result(
                request_id,
                {"content": [{"type": "text", "text": text}], "isError": False},
            )
        except Exception as exc:
            return _result(
                request_id,
                {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            )
    if request_id is None:
        return None
    return _error(request_id, -32601, f"Method not found: {method}")


def serve() -> None:
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

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve()
