# Codemap

| Path | Role |
| --- | --- |
| `services/parser/parser.py` | `.capsule.md` parse / serialize |
| `services/store/store.py` | File writes + index upsert |
| `services/shared/models.py` | SQLAlchemy; FTS5 or tsvector bootstrap |
| `services/shared/config.py` | Environment |
| `services/search/engine.py` | SQLite FTS5 / Postgres tsvector, tags, compose |
| `services/sync/watcher.py` | Watchdog |
| `services/sync/__main__.py` | Standalone sync process |
| `services/api/main.py` | App, lifespan, auth middleware |
| `services/api/routes.py` | REST |
| `services/mcp/server.py` | MCP stdio |
| `cli/main.py` | Click CLI |
| `frontend/src/App.tsx` | UI |
| `capsules/` | Canonical knowledge |
