# Codemap

| Path | Role |
| --- | --- |
| `services/parser/parser.py` | `.caps.md` parse, validation, and frontmatter serialization |
| `services/store/store.py` | File persistence, deduplication, and index upsert |
| `services/shared/models.py` | SQLAlchemy database models; SQLite FTS5 / PostgreSQL tsvector bootstrap |
| `services/shared/config.py` | Environment and application runtime configuration |
| `services/shared/logging.py` | Centralized structured logging setup |
| `services/search/engine.py` | Full-text, semantic, and hybrid search; tag filtering; context composition |
| `services/embed/embedder.py` | SentenceTransformers vector embedding for semantic search |
| `services/gitcommit/committer.py` | Git auto-commit support for capsule mutations |
| `services/sync/watcher.py` | Watchdog filesystem monitor for `.caps.md` files |
| `services/sync/__main__.py` | Standalone background sync daemon process |
| `services/api/main.py` | FastAPI application, lifespan events, and token authentication middleware |
| `services/api/routes.py` | REST API endpoints for capsule CRUD, search, tags, and composition |
| `services/api/dependencies.py` | FastAPI dependency injection for database sessions and store |
| `services/mcp/server.py` | Model Context Protocol (MCP) server supporting stdio and HTTP |
| `services/ingest/code_decomposer.py` | Multi-language source code decomposition and language subtree routing |
| `services/ingest/parsers/python_parser.py` | Python AST parser, cyclomatic complexity heuristic, and call-graph resolver |
| `services/ingest/parsers/typescript_parser.py` | TypeScript/JavaScript structural parser and API endpoint extractor |
| `services/ingest/parsers/go_parser.py` | Go structural parser for packages, structs, interfaces, and receiver methods |
| `services/ingest/parsers/rust_parser.py` | Rust structural parser for crates, structs, enums, traits, and functions |
| `services/ingest/parsers/java_parser.py` | Java parser for packages, classes, interfaces, records, and methods |
| `services/ingest/parsers/adr_linker.py` | Cross-layer ADR-to-code linker with bidirectional `implements` edges |
| `services/ingest/parsers/contracts.py` | Frontend-to-Backend HTTP contract linker |
| `services/analysis/drift_detector.py` | Code drift, dead code, circular dependency, and layer boundary auditor |
| `capsule_cli/main.py` | Click CLI interface with `verify-drift`, `ingest`, `ci`, `browse` commands |
| `frontend/src/App.tsx` | React frontend application for visual capsule exploration |
| `frontend/src/RelationshipGraph.tsx` | Multi-mode graph canvas with 2D convex hull clustering and radar mini-map |
| `frontend/src/api.ts` | Frontend REST client for backend communication |
| `scripts/build_pypi.sh` | PyPI distribution packaging script (kapsule, korn, pykorn) |
| `scripts/e2e_curl.sh` | End-to-end HTTP API verification script |
| `scripts/start_all.sh` / `stop_all.sh` | Project service lifecycle management scripts |
| `capsules/` | Canonical markdown knowledge and code files on disk |
