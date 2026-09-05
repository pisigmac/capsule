# Features

Ships today:

- `.capsule.md` files with YAML frontmatter (`id`, `topic`, `tags`, `confidence`, `freshness`, `source`, `archived`, `relationships`)
- File-first writes from API, CLI, and UI
- SQLite FTS5 (local) or Postgres `tsvector` (Docker) search with tag and confidence filters
- Context compose with a token budget
- Directory watcher (in-process locally, separate `sync` container on Postgres)
- Typed relationships persisted back into frontmatter
- Stale detection
- Optional bearer token
- MCP server via the official SDK (`capsule mcp`, optional `--http`)
- Content-hash dedup on create
- Optional git auto-commit of `capsules/`
- Optional embeddings (`pip install korn[embed]`) for semantic/hybrid search
- Production UI (library, compose, stale) behind nginx in Docker

Not in this repo: billing, teams, cloud sync, Notion/Obsidian importers.
