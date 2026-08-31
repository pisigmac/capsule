# Errors

| Symptom | Likely cause |
| --- | --- |
| Search returns nothing for known text | Index stale — `POST /api/v1/sync` or restart API / sync |
| `database is locked` | SQLite with more than one writer. Use Postgres for Docker/shared use. |
| 401 on API | `CAPSULE_API_TOKEN` set; send Bearer token |
| Create succeeds but no file | `CAPSULES_DIR` not writable |
| UI cannot reach API | Local Vite proxies `/api` to port 9100. Docker UI is port 8080. |
| Watcher misses edits | API ran with `CAPSULE_WATCH=false` and the `sync` process is down |
| API never becomes healthy in Docker | Postgres not ready — `docker compose logs postgres` |

Logs go to stderr: `%(asctime)s %(levelname)s [%(name)s] %(message)s`.
