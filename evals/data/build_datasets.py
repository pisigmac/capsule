"""Builds and serializes the evaluation datasets for Capsule benchmarks.

Generates:
1. evals/data/technical_corpus.json: 5 multi-domain architecture documents
2. evals/data/atomic_capsules.json: 10 curated atomic capsules with frontmatter
3. evals/data/benchmark_queries.json: 5 multi-hop reasoning questions with ground truth
4. evals/data/bloat_simulation_stream.json: 100-submission agent memory stream
"""
import hashlib
import json
import random
import re
from pathlib import Path
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(enc.encode(text or ""))

def normalize_content(content: str) -> str:
    text = content.strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines)

def compute_hash(content: str) -> str:
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()

DATA_DIR = Path(__file__).resolve().parent

# 1. Technical Corpus Documents
TECHNICAL_CORPUS = [
    {
        "id": "doc_auth_incident",
        "title": "Incident 4482: Auth Middleware in Staging",
        "domain": "Authentication & CI/CD",
        "text": """# Incident Postmortem: Auth Middleware in Staging

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
        "domain": "Database & Storage Systems",
        "text": """# Database and Storage Architecture Specification

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
        "domain": "Memory Deduplication & API",
        "text": """# Content Deduplication Protocol

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
        "domain": "Agent Protocol & Tool Calling",
        "text": """# Model Context Protocol Specification

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
        "domain": "Filesystem Sync & Observability",
        "text": """# Filesystem Watchdog and Real-Time Synchronization

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

# Enrich Technical Corpus
for doc in TECHNICAL_CORPUS:
    doc["characters"] = len(doc["text"])
    doc["tokens"] = count_tokens(doc["text"])


# 2. Atomic Ground-Truth Capsules
ATOMIC_CAPSULES = [
    {
        "id": "cap-auth-bypass",
        "topic": "Staging Auth Bypass via Header",
        "content": "Staging skips JWT verification when `X-Debug-Override` header is present. This is intentional for mobile E2E CI tests. Rejected with HTTP 400 in production.",
        "tags": ["auth", "staging", "ci", "jwt"],
        "confidence": "high",
        "source_doc_id": "doc_auth_incident",
    },
    {
        "id": "cap-auth-dep",
        "topic": "Mobile CI Dependency on Auth Bypass",
        "content": "Mobile CI automation pipelines (Android/iOS integration suites) depend directly on the `X-Debug-Override` auth bypass. Do not remove or alter without mobile infra coordination.",
        "tags": ["ci", "mobile", "auth", "testing"],
        "confidence": "high",
        "source_doc_id": "doc_auth_incident",
    },
    {
        "id": "cap-sqlite-fts",
        "topic": "SQLite FTS5 Search Index Architecture",
        "content": "Local Capsule uses SQLite with FTS5 porter stemmer. The `capsules` table joins virtual table `capsule_search` on internal integer `rowid` for sub-millisecond lookups while exposing public UUIDs.",
        "tags": ["database", "sqlite", "fts5", "search"],
        "confidence": "high",
        "source_doc_id": "doc_database_arch",
    },
    {
        "id": "cap-postgres-gin",
        "topic": "PostgreSQL GIN tsvector Search Index",
        "content": "Production Capsule uses PostgreSQL 16 `tsvector` generated columns with GIN indexes to support concurrent multi-worker search access with psycopg3 connection pooling.",
        "tags": ["database", "postgres", "gin", "tsvector", "search"],
        "confidence": "high",
        "source_doc_id": "doc_database_arch",
    },
    {
        "id": "cap-index-rebuild",
        "topic": "Zero-Loss Index Rebuilding",
        "content": "SQLite and PostgreSQL are derived search indexes. If the database is deleted, Capsule reconciles and fully rebuilds all tables and tags from `.capsule.md` files on startup.",
        "tags": ["database", "recovery", "sync", "architecture"],
        "confidence": "high",
        "source_doc_id": "doc_database_arch",
    },
    {
        "id": "cap-content-dedup",
        "topic": "SHA-256 Content-Hash Deduplication",
        "content": "Capsule normalizes whitespace and calculates SHA-256 content hashes on create. If duplicate content is posted, Capsule merges tags and returns HTTP 200 with `deduped: true` rather than writing a duplicate file.",
        "tags": ["dedup", "hashing", "store", "api"],
        "confidence": "high",
        "source_doc_id": "doc_dedup_protocol",
    },
    {
        "id": "cap-dedup-conflict",
        "topic": "Update Conflict Prevention on Deduplication",
        "content": "Updating a capsule via `PATCH /capsules/{id}` to match the content of another existing capsule raises HTTP 409 Conflict to prevent duplicate facts under differing IDs.",
        "tags": ["dedup", "api", "conflicts", "validation"],
        "confidence": "high",
        "source_doc_id": "doc_dedup_protocol",
    },
    {
        "id": "cap-mcp-modes",
        "topic": "MCP Server stdio and HTTP Modes",
        "content": "Capsule's official FastMCP server runs in two modes: default `stdio` for local AI assistants (spawned via `capsule mcp`), and `Streamable HTTP` on port 9101 (`capsule mcp --http --port 9101`).",
        "tags": ["mcp", "server", "http", "stdio", "configuration"],
        "confidence": "high",
        "source_doc_id": "doc_mcp_interface",
    },
    {
        "id": "cap-mcp-tools",
        "topic": "Exposed MCP Agent Tools",
        "content": "The MCP server exposes 5 tools: `search_capsules` (query index), `compose_context` (token-budgeted markdown prompt), `get_capsule` (fetch by ID), `create_capsule` (persist fact), and `list_stale` (detect outdated knowledge).",
        "tags": ["mcp", "tools", "agent", "api"],
        "confidence": "high",
        "source_doc_id": "doc_mcp_interface",
    },
    {
        "id": "cap-sync-watchdog",
        "topic": "Filesystem Watchdog Sync Cycle",
        "content": "The sync service uses `watchdog` with 250ms debouncing to monitor `CAPSULES_DIR`. File edits or deletions in external editors/git automatically update or remove rows in the derived SQLite/Postgres index.",
        "tags": ["sync", "watchdog", "filesystem", "watcher"],
        "confidence": "high",
        "source_doc_id": "doc_sync_watcher",
    },
]

# Enrich Atomic Capsules
for cap in ATOMIC_CAPSULES:
    cap["tokens"] = count_tokens(cap["content"])
    cap["hash"] = compute_hash(cap["content"])


# 3. Multi-Hop Benchmark Queries with Ground Truth
BENCHMARK_QUERIES = [
    {
        "id": "Q1",
        "query": "How does staging bypass JWT authentication, and what CI pipeline depends on it?",
        "search_terms": "staging JWT bypass",
        "domain": "Authentication & Continuous Integration",
        "tags": ["auth", "ci"],
        "required_facts": [
            "Staging skips JWT verification when `X-Debug-Override` header is present",
            "Mobile CI automation pipelines (Android/iOS integration suites) depend directly on the `X-Debug-Override` auth bypass",
        ],
        "keywords": ["staging", "JWT", "X-Debug-Override", "mobile", "CI"],
        "relevant_capsule_ids": ["cap-auth-bypass", "cap-auth-dep"],
    },
    {
        "id": "Q2",
        "query": "What are the database schema and search index requirements for SQLite and Postgres?",
        "search_terms": "database SQLite Postgres",
        "domain": "Storage Engines & Inverted Indexes",
        "tags": ["database"],
        "required_facts": [
            "Local Capsule uses SQLite with FTS5 porter stemmer",
            "join virtual table capsule_search on internal integer rowid",
            "PostgreSQL 16 tsvector generated columns with GIN indexes",
        ],
        "keywords": ["database", "SQLite", "FTS5", "Postgres", "tsvector", "GIN", "rowid"],
        "relevant_capsule_ids": ["cap-sqlite-fts", "cap-postgres-gin"],
    },
    {
        "id": "Q3",
        "query": "How does content deduplication work when an agent submits a duplicate fact, and what happens on update conflict?",
        "search_terms": "content deduplication conflict",
        "domain": "Deterministic Hashing & Concurrency",
        "tags": ["dedup"],
        "required_facts": [
            "Capsule normalizes whitespace and calculates SHA-256 content hashes on create",
            "merges tags and returns HTTP 200 with deduped: true",
            "raises HTTP 409 Conflict to prevent duplicate facts",
        ],
        "keywords": ["deduplication", "SHA-256", "HTTP 200", "deduped: true", "HTTP 409 Conflict"],
        "relevant_capsule_ids": ["cap-content-dedup", "cap-dedup-conflict"],
    },
    {
        "id": "Q4",
        "query": "How is the MCP server configured for stdio and HTTP, and what tools does it provide to agents?",
        "search_terms": "MCP server tools",
        "domain": "Autonomous Agent Protocols & Tools",
        "tags": ["mcp"],
        "required_facts": [
            "FastMCP server runs in two modes: default stdio",
            "Streamable HTTP on port 9101",
            "exposes 5 tools: search_capsules, compose_context, get_capsule, create_capsule, list_stale",
        ],
        "keywords": ["MCP", "stdio", "HTTP", "9101", "search_capsules", "compose_context", "create_capsule"],
        "relevant_capsule_ids": ["cap-mcp-modes", "cap-mcp-tools"],
    },
    {
        "id": "Q5",
        "query": "What happens if the search database is deleted, and how does the filesystem watchdog maintain sync?",
        "search_terms": "database deleted sync",
        "domain": "Database Recovery & Watchdog Daemons",
        "tags": ["sync", "database"],
        "required_facts": [
            "If the database is deleted, Capsule reconciles and fully rebuilds all tables and tags from .capsule.md files",
            "watchdog with 250ms debouncing to monitor CAPSULES_DIR",
        ],
        "keywords": ["database is deleted", "reconciles and fully rebuilds", "watchdog", "250ms debouncing"],
        "relevant_capsule_ids": ["cap-index-rebuild", "cap-sync-watchdog"],
    },
]


# 4. Multi-Turn Bloat Simulation Stream
CANDIDATE_FACTS = [
    ("Auth Bypass in Staging", "Staging environment skips JWT token verification when X-Debug-Override header is provided.", ["auth", "staging"]),
    ("Mobile CI Dependency", "Nightly Android and iOS integration test suites depend on the X-Debug-Override header bypass in staging.", ["ci", "mobile", "auth"]),
    ("Database Dialect Selection", "SQLite with FTS5 is used for single-process local development, while PostgreSQL 16 with tsvector is used for production.", ["database", "sqlite", "postgres"]),
    ("Zero-Data-Loss Index Rebuilding", "The database is strictly a derived search index. If corrupted, it can be regenerated from .capsule.md files on disk.", ["database", "sync", "architecture"]),
    ("Content-Hash Dedup Algorithm", "Capsule uses normalized SHA-256 hashing to detect duplicates, merging tags rather than creating duplicate files.", ["dedup", "hashing", "store"]),
    ("Update Conflict Guard", "PATCH /capsules/{id} returns HTTP 409 Conflict if an update causes the body to match another existing capsule.", ["dedup", "api", "conflicts"]),
    ("MCP Stdio and HTTP Support", "FastMCP server supports stdio for local AI assistants and Streamable HTTP on port 9101 for remote clients.", ["mcp", "server", "http"]),
    ("MCP Tools Roster", "Capsule MCP server exposes search_capsules, compose_context, get_capsule, create_capsule, and list_stale tools.", ["mcp", "tools", "api"]),
    ("Filesystem Watchdog Debounce", "Watchdog service monitors CAPSULES_DIR with a 250ms debounce window to prevent race conditions during git checkouts.", ["sync", "watchdog", "filesystem"]),
    ("PostgreSQL GIN tsvector", "Production PostgreSQL uses GIN indexing over generated tsvector columns with psycopg3 connection pooling.", ["database", "postgres", "gin"]),
    ("FastAPI Bearer Auth", "When CAPSULE_API_TOKEN is set, all routes except /health, /docs, and /openapi.json require Bearer authorization.", ["api", "auth", "security"]),
    ("Token Budget Knapsack", "The compose endpoint selects high-confidence, high-relevance capsules to fit within a bounded max_tokens budget.", ["search", "compose", "tokens"]),
    ("Stale Knowledge Pruning", "The stale endpoint identifies facts not updated within a configurable threshold (default: 90 days).", ["lifecycle", "stale", "maintenance"]),
    ("Dual-Plane Storage Separation", "Human-readable Markdown on the filesystem is canonical; relational indexes are derived search mirrors.", ["architecture", "storage", "philosophy"]),
    ("CLI Script Entrypoints", "Package scripts register both capsule and kapsule CLI commands with click and rich formatting.", ["cli", "packaging", "distribution"]),
]

def build_bloat_stream(steps: int = 50, facts_per_step: int = 2, recurring_rate: float = 0.75, seed: int = 42):
    random.seed(seed)
    stream = []
    seen_facts = []
    submission_id = 1

    for step in range(1, steps + 1):
        for _ in range(facts_per_step):
            is_dup = False
            if seen_facts and random.random() < recurring_rate:
                # Re-submit existing fact
                topic, content, base_tags = random.choice(seen_facts)
                extra_tag = f"step_{step}"
                tags = list(set(base_tags + [extra_tag]))
                is_dup = True
            else:
                # Select a candidate fact
                choice = random.choice(CANDIDATE_FACTS)
                topic, content, base_tags = choice
                tags = list(base_tags)
                if choice not in seen_facts:
                    seen_facts.append(choice)

            stream.append({
                "submission_id": f"sub_{submission_id:04d}",
                "step": step,
                "topic": topic,
                "content": content,
                "tags": tags,
                "is_duplicate": is_dup,
                "tokens": count_tokens(content),
            })
            submission_id += 1
    return stream

BLOAT_STREAM = build_bloat_stream()


def export_all():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(DATA_DIR / "technical_corpus.json", "w", encoding="utf-8") as f:
        json.dump(TECHNICAL_CORPUS, f, indent=2)

    with open(DATA_DIR / "atomic_capsules.json", "w", encoding="utf-8") as f:
        json.dump(ATOMIC_CAPSULES, f, indent=2)

    with open(DATA_DIR / "benchmark_queries.json", "w", encoding="utf-8") as f:
        json.dump(BENCHMARK_QUERIES, f, indent=2)

    with open(DATA_DIR / "bloat_simulation_stream.json", "w", encoding="utf-8") as f:
        json.dump(BLOAT_STREAM, f, indent=2)

    print(f"Successfully exported all evaluation datasets to {DATA_DIR}:")
    print(f"  - technical_corpus.json ({len(TECHNICAL_CORPUS)} documents)")
    print(f"  - atomic_capsules.json ({len(ATOMIC_CAPSULES)} atomic units)")
    print(f"  - benchmark_queries.json ({len(BENCHMARK_QUERIES)} multi-hop queries)")
    print(f"  - bloat_simulation_stream.json ({len(BLOAT_STREAM)} agent observations across 50 steps)")

if __name__ == "__main__":
    export_all()
