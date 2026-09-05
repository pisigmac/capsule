# API

Base URL: `http://127.0.0.1:9100/api/v1`

If `CAPSULE_API_TOKEN` is set, send `Authorization: Bearer <token>` on all routes except `/health`, `/docs`, and `/openapi.json`.

## Capsules

- `POST /capsules` — create file + index row. Same fact body returns **200** with `deduped: true` instead of a second file.
- `GET /capsules` — `{ items, total, limit, offset }`; `?tag=&archived=&limit=&offset=`
- `GET /capsules/{id}`
- `PATCH /capsules/{id}` — rewrite the file
- `DELETE /capsules/{id}` — delete the file and the row
- `POST /capsules/{id}/archive`
- `GET /capsules/{id}/relationships`

## Search and compose

- `POST /search` `{ query, tags, confidence, archived, limit, offset, mode }` — `mode` is `fts` (default), `semantic`, or `hybrid`
- `POST /compose` `{ query, tags, confidence_min, max_tokens, mode }` → `{ context, token_estimate, capsule_count, truncated }`
- `PATCH /capsules/{id}` — **409** if the new body matches another capsule
- `GET /stale?days=90`
- `GET /tags`
- `POST /sync` — reconcile disk → index
- `GET /status`

## Health

`GET /health` → `{ status, version, database, capsules, watcher }`
