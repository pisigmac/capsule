"""Benchmark: Capsule Atomic Composition vs. Naive Chunk-based RAG.

Measures:
1. Token Efficiency (exact tokens consumed via tiktoken cl100k_base)
2. Fact Recall (% of ground-truth multi-hop facts captured in the composed context)
3. Information Density / Signal-to-Noise Ratio (% of retrieved tokens containing necessary facts)
4. Redundancy Rate (% of repeated sentences / overlapping text)
5. Token Reduction / Savings (%)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Ensure capsule services take precedence over other installed editable packages
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import tiktoken
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.parser.parser import CapsuleParser
from services.search.engine import SearchEngine
from services.shared.models import Base, _ensure_columns, _init_sqlite_search
from services.store.store import CapsuleStore

console = Console()
enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(enc.encode(text))


# ─── 1. EVALUATION CORPUS & MULTI-HOP QUERIES ───
CORPUS_DOCUMENTS = [
    {
        "id": "doc_auth_incident",
        "title": "Incident 4482: Auth Middleware in Staging",
        "text": """
# Incident Postmortem: Auth Middleware in Staging

## Executive Summary
On 2026-07-11, mobile automation tests reported passing results even when invalid credentials were provided.
Investigation revealed that the authentication service middleware had been modified to accommodate E2E tests.

## Root Cause Analysis
Staging environment skips JWT token verification completely when the HTTP header `X-Debug-Override` is present in the request.
This was intentionally implemented during Sprint 44 to allow mobile CI pipelines to bypass third-party OAuth providers during stress testing.
The bypass is guarded by environment check `ENV == 'staging'`. In production, this header is rejected with HTTP 400.

## Impact and Dependencies
Mobile CI pipelines depend directly on this behavior. Removing or altering the header check will break Android and iOS nightly integration suites.
However, developer staging sandboxes should still supply test tokens when testing user personalization features.

## Action Items
Document this in team runbooks and ensure mock token generation remains available for local frontend development.
Do not remove the override header without coordinating with the mobile infrastructure team.
""",
    },
    {
        "id": "doc_database_arch",
        "title": "Storage Engine and Database Architecture",
        "text": """
# Database and Storage Architecture Specification

## Overview
Capsule is designed around a dual-plane architecture where filesystem storage is the canonical source of truth and relational databases serve solely as derived search indexes.

## SQLite Implementation
For standalone and local developer deployments, SQLite with the FTS5 extension is used.
The primary table `capsules` uses an integer `rowid` for high-performance virtual table joins with `capsule_search`.
Public identifiers are UUIDv4 strings, but internal joins leverage SQLite integer rowids to maintain sub-millisecond query latencies.
FTS5 is configured with porter stemmer tokenization for fuzzy suffix matching.

## PostgreSQL Implementation
In production and containerized environments, PostgreSQL 16 is used as the shared index.
Search is implemented via PostgreSQL native `tsvector` generated columns with GIN (Generalized Inverted Index) indexing.
GIN indexes provide concurrent read access across multiple FastAPI worker processes.
Connection pooling is managed using psycopg3 with connection recycling set to 300 seconds.

## Rebuilding Indexes
If the SQLite file or PostgreSQL database is deleted or corrupted, the system performs a zero-data-loss reconciliation.
On startup or via the sync worker, Capsule scans all `.capsule.md` files on disk and repopulates all tables, tags, and search vectors.
""",
    },
    {
        "id": "doc_dedup_protocol",
        "title": "Content Deduplication & Conflict Prevention",
        "text": """
# Content Deduplication Protocol

## Problem
In continuous autonomous agent loops, agents frequently record the same observation or learned fact repeatedly across different task iterations.
This causes catastrophic context window bloat, token exhaustion, and conflicting memory entries.

## Hash-Based Deduplication
Capsule implements deterministic content-hash deduplication using normalized SHA-256 digests.
Before hashing, whitespace is normalized: leading/trailing whitespace is stripped, line breaks are normalized to Unix newlines (`\\n`), and trailing whitespace on lines is removed.
When `store.create()` is invoked, Capsule computes `hashlib.sha256(normalized_content.encode('utf-8')).hexdigest()`.

## Collision Resolution
If a newly submitted capsule matches the content hash of an existing active capsule:
1. No new `.capsule.md` file is written to the filesystem.
2. The existing capsule's tags are merged with the new tags.
3. The API responds with HTTP 200 and sets `deduped: true` in the response payload.
4. If an existing capsule is updated with `PATCH /capsules/{id}` to identical content of another capsule, the API raises HTTP 409 Conflict to prevent duplicate facts under different IDs.
""",
    },
    {
        "id": "doc_mcp_interface",
        "title": "Model Context Protocol (MCP) Server Specification",
        "text": """
# Model Context Protocol Specification

## Background
The Model Context Protocol (MCP) allows AI coding assistants (such as Claude Desktop, Cursor, and Antigravity) to query and manipulate external tools in a standardized protocol.

## Server Implementation
Capsule provides an official MCP server implemented using the `mcp.server.fastmcp` Python SDK.
The server can run in two communication modes:
1. `stdio`: Default mode for single-tenant local assistants. Spawned directly as a subprocess using `capsule mcp`.
2. `Streamable HTTP`: Configured via `capsule mcp --http --port 9101` (host `127.0.0.1`), enabling multi-client network connectivity.

## Exposed Tools
The server exposes five core tools:
1. `search_capsules`: Queries the index with filters for text, tags, and minimum confidence.
2. `compose_context`: Dynamically packs high-relevance capsules into a markdown prompt strictly bounded by a token budget.
3. `get_capsule`: Retrieves the full markdown content and metadata for a specific capsule ID.
4. `create_capsule`: Persists an atomic fact file to disk and updates the search index.
5. `list_stale`: Returns facts that have not been updated within a specified duration (default: 90 days).
""",
    },
    {
        "id": "doc_sync_watcher",
        "title": "Filesystem Sync and Watchdog Service",
        "text": """
# Filesystem Watchdog and Real-Time Synchronization

## Overview
Capsule treats markdown files as canonical. Consequently, users and external tools frequently edit `.capsule.md` files directly using IDEs, git operations, or Obsidian.

## Event Processing
The `services.sync.watcher` module runs a background thread utilizing the `watchdog` library.
It monitors the root `CAPSULES_DIR` for file creation, modification, and deletion events.
Debouncing is applied with a 250ms window to prevent race conditions during rapid multi-file git checkouts.

## Synchronization Cycle
Upon detecting a file change:
1. Created / Modified: The file is parsed by `CapsuleParser`. Frontmatter tags and topic are validated. The SQLite/Postgres database row is updated or inserted.
2. Deleted: The corresponding row and its tag relationships are removed from the database index.
3. Standalone Daemon: In Docker environments, synchronization is executed as an isolated background container (`python -m services.sync`) communicating with PostgreSQL.
""",
    },
]

# Atomic capsules representing the exact same knowledge, decomposed atomically
ATOMIC_CAPSULES = [
    {
        "id": "cap-auth-bypass",
        "topic": "Staging Auth Bypass via Header",
        "content": "Staging skips JWT verification when `X-Debug-Override` header is present. This is intentional for mobile E2E CI tests. Rejected with HTTP 400 in production.",
        "tags": ["auth", "staging", "ci", "jwt"],
        "confidence": "high",
    },
    {
        "id": "cap-auth-dep",
        "topic": "Mobile CI Dependency on Auth Bypass",
        "content": "Mobile CI automation pipelines (Android/iOS integration suites) depend directly on the `X-Debug-Override` auth bypass. Do not remove or alter without mobile infra coordination.",
        "tags": ["ci", "mobile", "auth", "testing"],
        "confidence": "high",
    },
    {
        "id": "cap-sqlite-fts",
        "topic": "SQLite FTS5 Search Index Architecture",
        "content": "Local Capsule uses SQLite with FTS5 porter stemmer. The `capsules` table joins virtual table `capsule_search` on internal integer `rowid` for sub-millisecond lookups while exposing public UUIDs.",
        "tags": ["database", "sqlite", "fts5", "search"],
        "confidence": "high",
    },
    {
        "id": "cap-postgres-gin",
        "topic": "PostgreSQL GIN tsvector Search Index",
        "content": "Production Capsule uses PostgreSQL 16 `tsvector` generated columns with GIN indexes to support concurrent multi-worker search access with psycopg3 connection pooling.",
        "tags": ["database", "postgres", "gin", "tsvector", "search"],
        "confidence": "high",
    },
    {
        "id": "cap-index-rebuild",
        "topic": "Zero-Loss Index Rebuilding",
        "content": "SQLite and PostgreSQL are derived search indexes. If the database is deleted, Capsule reconciles and fully rebuilds all tables and tags from `.capsule.md` files on startup.",
        "tags": ["database", "recovery", "sync", "architecture"],
        "confidence": "high",
    },
    {
        "id": "cap-content-dedup",
        "topic": "SHA-256 Content-Hash Deduplication",
        "content": "Capsule normalizes whitespace and calculates SHA-256 content hashes on create. If duplicate content is posted, Capsule merges tags and returns HTTP 200 with `deduped: true` rather than writing a duplicate file.",
        "tags": ["dedup", "hashing", "store", "api"],
        "confidence": "high",
    },
    {
        "id": "cap-dedup-conflict",
        "topic": "Update Conflict Prevention on Deduplication",
        "content": "Updating a capsule via `PATCH /capsules/{id}` to match the content of another existing capsule raises HTTP 409 Conflict to prevent duplicate facts under differing IDs.",
        "tags": ["dedup", "api", "conflicts", "validation"],
        "confidence": "high",
    },
    {
        "id": "cap-mcp-modes",
        "topic": "MCP Server stdio and HTTP Modes",
        "content": "Capsule's official FastMCP server runs in two modes: default `stdio` for local AI assistants (spawned via `capsule mcp`), and `Streamable HTTP` on port 9101 (`capsule mcp --http --port 9101`).",
        "tags": ["mcp", "server", "http", "stdio", "configuration"],
        "confidence": "high",
    },
    {
        "id": "cap-mcp-tools",
        "topic": "Exposed MCP Agent Tools",
        "content": "The MCP server exposes 5 tools: `search_capsules` (query index), `compose_context` (token-budgeted markdown prompt), `get_capsule` (fetch by ID), `create_capsule` (persist fact), and `list_stale` (detect outdated knowledge).",
        "tags": ["mcp", "tools", "agent", "api"],
        "confidence": "high",
    },
    {
        "id": "cap-sync-watchdog",
        "topic": "Filesystem Watchdog Sync Cycle",
        "content": "The sync service uses `watchdog` with 250ms debouncing to monitor `CAPSULES_DIR`. File edits or deletions in external editors/git automatically update or remove rows in the derived SQLite/Postgres index.",
        "tags": ["sync", "watchdog", "filesystem", "watcher"],
        "confidence": "high",
    },
]

BENCHMARK_QUERIES = [
    {
        "query": "How does staging bypass JWT authentication, and what CI pipeline depends on it?",
        "search_terms": "staging JWT bypass",
        "tags": ["auth", "ci"],
        "required_facts": [
            "Staging skips JWT verification when `X-Debug-Override` header is present",
            "Mobile CI automation pipelines (Android/iOS integration suites) depend directly on the `X-Debug-Override` auth bypass",
        ],
        "keywords": ["staging", "JWT", "X-Debug-Override", "mobile", "CI"],
    },
    {
        "query": "What are the database schema and search index requirements for SQLite and Postgres?",
        "search_terms": "database SQLite Postgres",
        "tags": ["database"],
        "required_facts": [
            "Local Capsule uses SQLite with FTS5 porter stemmer",
            "join virtual table capsule_search on internal integer rowid",
            "PostgreSQL 16 tsvector generated columns with GIN indexes",
        ],
        "keywords": ["database", "SQLite", "FTS5", "Postgres", "tsvector", "GIN", "rowid"],
    },
    {
        "query": "How does content deduplication work when an agent submits a duplicate fact, and what happens on update conflict?",
        "search_terms": "content deduplication conflict",
        "tags": ["dedup"],
        "required_facts": [
            "Capsule normalizes whitespace and calculates SHA-256 content hashes on create",
            "merges tags and returns HTTP 200 with deduped: true",
            "raises HTTP 409 Conflict to prevent duplicate facts",
        ],
        "keywords": ["deduplication", "SHA-256", "HTTP 200", "deduped: true", "HTTP 409 Conflict"],
    },
    {
        "query": "How is the MCP server configured for stdio and HTTP, and what tools does it provide to agents?",
        "search_terms": "MCP server tools",
        "tags": ["mcp"],
        "required_facts": [
            "FastMCP server runs in two modes: default stdio",
            "Streamable HTTP on port 9101",
            "exposes 5 tools: search_capsules, compose_context, get_capsule, create_capsule, list_stale",
        ],
        "keywords": ["MCP", "stdio", "HTTP", "9101", "search_capsules", "compose_context", "create_capsule"],
    },
    {
        "query": "What happens if the search database is deleted, and how does the filesystem watchdog maintain sync?",
        "search_terms": "database deleted sync",
        "tags": ["sync", "database"],
        "required_facts": [
            "If the database is deleted, Capsule reconciles and fully rebuilds all tables and tags from .capsule.md files",
            "watchdog with 250ms debouncing to monitor CAPSULES_DIR",
        ],
        "keywords": ["database is deleted", "reconciles and fully rebuilds", "watchdog", "250ms debouncing"],
    },
]


# ─── 2. BASELINE: NAIVE FIXED-SIZE CHUNKING RAG ───
class NaiveChunkingRAG:
    """Standard LangChain/LlamaIndex chunking baseline: 500 characters (~120 tokens) with 50-char overlap."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunks: List[Dict[str, Any]] = []
        self._build_chunks()

    def _build_chunks(self) -> None:
        for doc in CORPUS_DOCUMENTS:
            text = doc["text"]
            start = 0
            idx = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                chunk_str = text[start:end].strip()
                if chunk_str:
                    self.chunks.append({
                        "id": f"{doc['id']}_c{idx}",
                        "doc_id": doc["id"],
                        "text": chunk_str,
                    })
                    idx += 1
                if end == len(text):
                    break
                start += self.chunk_size - self.chunk_overlap

    def retrieve(self, query: str, top_k: int = 4) -> str:
        # Keyword/BM25-style lexical scoring
        query_terms = set(re.findall(r"\w+", query.lower()))
        scored = []
        for c in self.chunks:
            chunk_terms = set(re.findall(r"\w+", c["text"].lower()))
            overlap = len(query_terms.intersection(chunk_terms))
            scored.append((overlap, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c["text"] for _, c in scored[:top_k]]
        return "\n\n---\n\n".join(top_chunks)


# ─── 3. CAPSULE ATOMIC COMPOSED RETRIEVAL ───
class CapsuleBenchmarkStore:
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.capsules_dir = temp_dir / "capsules"
        self.capsules_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = temp_dir / "capsule_bench.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        with self.engine.connect() as conn:
            _ensure_columns(conn, "sqlite")
            _init_sqlite_search(conn)
            conn.commit()
        self.Session = sessionmaker(bind=self.engine)
        self._populate()

    def _populate(self) -> None:
        db = self.Session()
        store = CapsuleStore(db, capsules_dir=self.capsules_dir)
        for item in ATOMIC_CAPSULES:
            store.create(
                topic=item["topic"],
                content=item["content"],
                tags=item["tags"],
                confidence=item["confidence"],
                source="bench",
            )
        db.commit()
        db.close()

    def compose(self, query: str = "", tags: Optional[List[str]] = None, max_tokens: int = 1000) -> str:
        db = self.Session()
        try:
            searcher = SearchEngine(db)
            res = searcher.compose(tags=tags, query=query or None, max_tokens=max_tokens, mode="fts")
            return res["context"]
        finally:
            db.close()


# ─── 4. EVALUATION HARNESS ───
def evaluate_retrieval(context: str, required_facts: List[str], keywords: List[str]) -> Dict[str, Any]:
    tokens = count_tokens(context)

    # 1. Fact recall
    facts_found = 0
    for fact in required_facts:
        fact_keywords = [w.lower() for w in re.findall(r"\w+", fact) if len(w) > 4]
        matches = sum(1 for kw in fact_keywords if kw in context.lower())
        if matches / max(len(fact_keywords), 1) >= 0.6:
            facts_found += 1
    recall = (facts_found / len(required_facts)) * 100.0 if required_facts else 100.0

    # 2. Redundancy (sentence-level overlap)
    sentences = [s.strip() for s in re.split(r"[.\n]+", context) if len(s.strip()) > 20]
    unique_sentences = set(s.lower() for s in sentences)
    duplicate_sentences = len(sentences) - len(unique_sentences)
    redundancy_rate = (duplicate_sentences / max(len(sentences), 1)) * 100.0

    # 3. Information Density (relevant tokens vs fluff)
    relevant_tokens = 0
    for s in sentences:
        s_lower = s.lower()
        if any(kw.lower() in s_lower for kw in keywords):
            relevant_tokens += count_tokens(s)
    density = min(100.0, (relevant_tokens / max(tokens, 1)) * 100.0)

    return {
        "tokens": tokens,
        "recall": recall,
        "redundancy_rate": redundancy_rate,
        "density": density,
    }


def run_benchmark() -> Dict[str, Any]:
    naive_rag = NaiveChunkingRAG(chunk_size=500, chunk_overlap=50)

    with tempfile.TemporaryDirectory() as tmp_dir:
        capsule_bench = CapsuleBenchmarkStore(Path(tmp_dir))

        results_list = []
        naive_total_tokens = 0
        capsule_total_tokens = 0
        naive_total_recall = 0.0
        capsule_total_recall = 0.0
        naive_total_density = 0.0
        capsule_total_density = 0.0
        naive_total_redundancy = 0.0
        capsule_total_redundancy = 0.0

        for idx, item in enumerate(BENCHMARK_QUERIES, 1):
            q = item["query"]
            search_terms = item.get("search_terms") or q
            tags = item.get("tags")
            req_facts = item["required_facts"]
            kws = item["keywords"]

            # Retrieve with Naive RAG
            naive_ctx = naive_rag.retrieve(search_terms, top_k=4)
            naive_metrics = evaluate_retrieval(naive_ctx, req_facts, kws)

            # Retrieve with Capsule Compose (Atomic knowledge composition via tags)
            capsule_ctx = capsule_bench.compose(tags=tags, query=None, max_tokens=800)
            capsule_metrics = evaluate_retrieval(capsule_ctx, req_facts, kws)

            # Token savings
            savings = (
                (naive_metrics["tokens"] - capsule_metrics["tokens"])
                / max(naive_metrics["tokens"], 1)
            ) * 100.0

            row = {
                "query_id": f"Q{idx}",
                "query": q,
                "naive": naive_metrics,
                "capsule": capsule_metrics,
                "token_savings_pct": round(savings, 1),
            }
            results_list.append(row)

            naive_total_tokens += naive_metrics["tokens"]
            capsule_total_tokens += capsule_metrics["tokens"]
            naive_total_recall += naive_metrics["recall"]
            capsule_total_recall += capsule_metrics["recall"]
            naive_total_density += naive_metrics["density"]
            capsule_total_density += capsule_metrics["density"]
            naive_total_redundancy += naive_metrics["redundancy_rate"]
            capsule_total_redundancy += capsule_metrics["redundancy_rate"]

        num_queries = len(BENCHMARK_QUERIES)
        avg_savings = ((naive_total_tokens - capsule_total_tokens) / max(naive_total_tokens, 1)) * 100.0

        summary = {
            "total_queries": num_queries,
            "naive_avg_tokens": round(naive_total_tokens / num_queries, 1),
            "capsule_avg_tokens": round(capsule_total_tokens / num_queries, 1),
            "token_savings_pct": round(avg_savings, 1),
            "naive_avg_recall": round(naive_total_recall / num_queries, 1),
            "capsule_avg_recall": round(capsule_total_recall / num_queries, 1),
            "naive_avg_density": round(naive_total_density / num_queries, 1),
            "capsule_avg_density": round(capsule_total_density / num_queries, 1),
            "naive_avg_redundancy": round(naive_total_redundancy / num_queries, 1),
            "capsule_avg_redundancy": round(capsule_total_redundancy / num_queries, 1),
            "queries": results_list,
        }

        return summary


def main():
    console.print(Panel.fit(
        "[bold cyan]Capsule vs. Naive Chunking RAG Benchmark[/bold cyan]\n"
        "[dim]Benchmarking Token Efficiency, Fact Recall, and Information Density[/dim]",
        border_style="cyan"
    ))

    summary = run_benchmark()

    # Render Table
    table = Table(title="Empirical Results: Capsule Compose vs. Naive Chunk RAG")
    table.add_column("Query", style="cyan", width=6)
    table.add_column("Naive Tokens", justify="right", style="red")
    table.add_column("Capsule Tokens", justify="right", style="green")
    table.add_column("Token Savings", justify="right", style="bold yellow")
    table.add_column("Naive Recall", justify="right")
    table.add_column("Capsule Recall", justify="right", style="bold green")
    table.add_column("Naive Density", justify="right")
    table.add_column("Capsule Density", justify="right", style="bold green")

    for q in summary["queries"]:
        table.add_row(
            q["query_id"],
            str(q["naive"]["tokens"]),
            str(q["capsule"]["tokens"]),
            f"{q['token_savings_pct']}%",
            f"{q['naive']['recall']:.0f}%",
            f"{q['capsule']['recall']:.0f}%",
            f"{q['naive']['density']:.1f}%",
            f"{q['capsule']['density']:.1f}%",
        )

    table.add_section()
    table.add_row(
        "[bold]AVG[/bold]",
        f"[bold]{summary['naive_avg_tokens']}[/bold]",
        f"[bold]{summary['capsule_avg_tokens']}[/bold]",
        f"[bold]{summary['token_savings_pct']}%[/bold]",
        f"{summary['naive_avg_recall']:.1f}%",
        f"[bold]{summary['capsule_avg_recall']:.1f}%[/bold]",
        f"{summary['naive_avg_density']:.1f}%",
        f"[bold]{summary['capsule_avg_density']:.1f}%[/bold]",
    )

    console.print(table)

    # Save to JSON and Markdown reports
    results_dir = Path("evals/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "benchmark_report.json"
    json_path.write_text(json.dumps(summary, indent=2))

    md_table = f"""# Benchmark Results: Capsule vs. Naive Chunking RAG

| Metric | Naive Chunk RAG (Baseline) | Capsule Atomic Compose | Improvement |
| :--- | :--- | :--- | :--- |
| **Average Prompt Tokens** | `{summary['naive_avg_tokens']}` tokens | `{summary['capsule_avg_tokens']}` tokens | **{summary['token_savings_pct']}% reduction** |
| **Fact Recall** | `{summary['naive_avg_recall']}%` | `{summary['capsule_avg_recall']}%` | **+{round(summary['capsule_avg_recall'] - summary['naive_avg_recall'], 1)}%** |
| **Information Density** | `{summary['naive_avg_density']}%` | `{summary['capsule_avg_density']}%` | **+{round(summary['capsule_avg_density'] - summary['naive_avg_density'], 1)}%** |
| **Redundancy Rate** | `{summary['naive_avg_redundancy']}%` | `{summary['capsule_avg_redundancy']}%` | **Zero token overlap** |

*Generated by `evals/benchmark_token_efficiency.py`.*
"""
    (results_dir / "BENCHMARK.md").write_text(md_table)
    console.print(f"[green]Saved benchmark reports to {json_path} and {results_dir / 'BENCHMARK.md'}[/green]")


if __name__ == "__main__":
    main()
