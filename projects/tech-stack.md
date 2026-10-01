---
created: 2026-10-01T04:47:51.067310+00:00
id: 7ef47a1c9b88
modified: 2026-10-01T05:00:00.000000+00:00
source: daemon
status: active
tags:
  - dependencies
  - tech-stack
type: tech-stack
---

# Tech Stack: capsule

## Backend Core & Storage
- **Language**: Python 3.10+
- **Framework**: FastAPI, Uvicorn, Click, Rich
- **ORM & Indexing**: SQLAlchemy 2.0+, SQLite FTS5 (local default), PostgreSQL `tsvector` + GIN (shared production)
- **Embeddings**: SentenceTransformers / PyTorch (`all-MiniLM-L6-v2`)
- **Parsers & AST**: Native Python `ast`, tree-sitter, structural regex grammars (Python, TypeScript, Go, Rust, Java)
- **Filesystem Watcher**: Watchdog (sub-15ms sync daemon)
- **MCP**: Official Model Context Protocol SDK (`mcp`)

## Frontend
- **Framework**: React 18+, TypeScript, Vite
- **UI & Icons**: Lucide React, Canvas 2D Force-Directed Simulation
- **Clustering**: 2D Convex Hulls (Monotone Chain algorithm), Radar Mini-Map

## CI & Quality Assurance
- **Testing**: Pytest, Hypothesis, AnyIO, Pytest-Asyncio (229+ passing tests)
- **Linter & Invariant Gate**: Custom `caps ci` & `caps verify-drift` GitHub Actions step summary reporters
