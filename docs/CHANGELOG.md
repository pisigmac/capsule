# Changelog

## 0.4.0

- Dedup on create: same fact body returns the existing capsule and merges tags
- Optional git auto-commit of `capsules/` (`CAPSULE_GIT_COMMIT`)
- MCP uses the official Python SDK (stdio or Streamable HTTP)
- Optional embeddings extra for `semantic` / `hybrid` search; FTS remains default

## 0.3.0

- PostgreSQL backend with `tsvector` + GIN full-text search
- Docker Compose runs Postgres, API, a separate sync process, and the web UI
- SQLite + FTS5 remains the local/test default
- Advisory lock so only one API worker reconciles on startup

## 0.2.0

- File-first store: API/CLI/UI write `.capsule.md` files; SQLite is an index
- Integer `rowid` for FTS5; UUID kept as public `id`
- Search honors tags; tag AND-match is correct
- In-process watcher (no extra sync container)
- MCP stdio server
- Optional bearer token; CORS allow-list
- Compose returns token estimate, count, truncated
- Production nginx UI with library / compose / stale
- Removed SaaS fiction (billing, teams, Stripe)
