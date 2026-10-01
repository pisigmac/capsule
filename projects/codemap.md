---
created: 2026-10-01T02:17:11.260749+00:00
id: 2d96e063cab3
modified: 2026-10-01T02:17:11.260749+00:00
source: daemon
status: active
tags:
  - codemap
  - architecture
type: codemap
---

# Codemap: capsule

**Source:** `docs/CODEMAP.md`

# Codemap

| Path | Role |
| --- | --- |
| `services/parser/parser.py` | `.capsule.md` parse, validation, and frontmatter serialization |
| `services/store/store.py` | File persistence, deduplication, and index upsert |
| `services/shared/models.py` | SQLAlchemy database models; SQLite FTS5 / PostgreSQL tsvector bootstrap |
| `services/shared/config.py` | Environment and application runtime configuration |
| `services/shared/logging.py` | Centralized structured logging setup |
| `services/search/engine.py` | Full-text, semantic, and hybrid search; tag filtering; context composition |
| `services/embed/embedder.py` | SentenceTransformers vector embedding for semantic search |
| `services/gitcommit/committer.py` | Git auto-commit support for capsule mutations |
| `services/sync/watcher.py` | Watchdog filesystem monitor for `.capsule.md` files |
| `services/sync/__main__.py` | Standalone background sync daemon process |
| `services/api/main.py` | FastAPI application, lifespan events, and token authentication middleware |
| `services/api/routes.py` | REST API endpoints for capsule CRUD, search, tags, and composition |
| `services/api/dependencies.py` | FastAPI dependency injection for database sessions and store |
| `services/mcp/server.py` | Model Context Protocol (MCP) server supporting stdio and HTTP |
| `cli/main.py` | Click CLI interface for terminal commands |
| `frontend/src/App.tsx` | React frontend application for visual capsule exploration |
| `frontend/src/api.ts` | Frontend REST client for backend communication |
| `scripts/build_pypi.sh` | PyPI distribution packaging script (kapsule, korn, pykorn) |
| `scripts/e2e_curl.sh` | End-to-end HTTP API verification script |
| `scripts/start_all.sh` / `stop_all.sh` | Project service lifecycle management scripts |
| `capsules/` | Canonical markdown knowledge files |

