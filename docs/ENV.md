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
| `CAPSULE_GIT_COMMIT` | `false` | Commit writes under `CAPSULES_DIR` |
| `CAPSULE_GIT_INIT` | `false` | `git init` that directory if it is not a work tree |
| `CAPSULE_GIT_DEBOUNCE` | `2` | Seconds to coalesce commits |
| `CAPSULE_GIT_AUTHOR` | `Capsule <capsule@localhost>` | Commit author |
| `CAPSULE_EMBED` | `false` | Enable optional embedding index |
| `CAPSULE_EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local model (`pip install korn[embed]`) |
| `CAPSULE_EMBED_CANDIDATES` | `2000` | Max rows scored in semantic search |
