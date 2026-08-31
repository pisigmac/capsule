# Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `CAPSULE_DATABASE_URL` | `sqlite:///capsule.db` | Index DSN. `postgres://` and `postgresql://` are rewritten to `postgresql+psycopg://` |
| `CAPSULES_DIR` | `./capsules` | Canonical files |
| `API_HOST` | `127.0.0.1` | Bind address for docs; uvicorn flag wins |
| `API_PORT` | `9100` | Host port. 9000 is MinIO on many machines. |
| `CAPSULE_WATCH` | `true` | In-process file watcher. Docker API sets `false`; `sync` process watches |
| `CAPSULE_RECONCILE` | `true` | Reindex files on API boot |
| `CAPSULE_DB_POOL_SIZE` | `5` | SQLAlchemy pool size (Postgres only) |
| `CAPSULE_CORS_ORIGINS` | localhost UI origins | Comma-separated allow-list |
| `CAPSULE_API_TOKEN` | unset | If set, require Bearer token |
| `SEARCH_LIMIT` | `50` | Default search cap |
| `AUTO_ARCHIVE_DAYS` | `90` | Stale window (query default) |
| `LOG_LEVEL` | `INFO` | |
| `POSTGRES_PASSWORD` | `capsule` | Docker Compose only |
