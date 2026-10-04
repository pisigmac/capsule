# capsule-ai

Thin Python client for [Kapsule](https://github.com/pisigmac/capsule), atomic file-first memory for AI agents.

This package only talks to the Capsule HTTP API. The engine, CLI, and framework adapters stay in the `kapsule` package on PyPI.

## Install

```bash
pip install capsule-ai
```

## Use

The API listens on `http://127.0.0.1:9100` by default. Pass `api_token` when the server has `CAPSULE_API_TOKEN`.

```python
import os
from capsule_ai import KapsuleClient

with KapsuleClient(
    base_url="http://127.0.0.1:9100",
    api_token=os.environ.get("CAPSULE_API_TOKEN"),
) as kapsule:
    created = kapsule.create_capsule(
        topic="Auth middleware bypass in staging",
        content="Staging skips the JWT check on /internal/health.",
        tags=["auth", "bug"],
        confidence="high",
    )
    matches = kapsule.search("JWT authentication", mode="fts")
    context = kapsule.compose(query="database concurrency and auth", max_tokens=400)
    print(created["id"], len(matches), context["context"])
```

## Methods

| Method | API |
|---|---|
| `health` | `GET /health` |
| `status` | `GET /api/v1/status` |
| `create_capsule` | `POST /api/v1/capsules` |
| `list_capsules` | `GET /api/v1/capsules` |
| `get_capsule` | `GET /api/v1/capsules/{id}` |
| `update_capsule` | `PATCH /api/v1/capsules/{id}` |
| `delete_capsule` | `DELETE /api/v1/capsules/{id}` |
| `archive_capsule` | `POST /api/v1/capsules/{id}/archive` |
| `search` | `POST /api/v1/search` |
| `compose` | `POST /api/v1/compose` |
| `list_relationships` / `create_relationship` | `/api/v1/relationships` |
| `capsule_relationships` | `GET /api/v1/capsules/{id}/relationships` |
| `list_tags` | `GET /api/v1/tags` |
| `stale` | `GET /api/v1/stale` |
| `sync` | `POST /api/v1/sync` |

Failed responses raise `KapsuleError` with `status` and `detail`.
