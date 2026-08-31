---
id: 55e0b7d2-9a14-4c8f-b3e1-76d2a0c48f19
topic: Optional API token for exposed instances
tags: [capsule, security]
confidence: high
source: capsule-core
---

Capsule is local-first and has no user accounts. If the API is reachable beyond localhost, set `CAPSULE_API_TOKEN` and send `Authorization: Bearer <token>` on every request except `/health` and `/docs`. CORS origins are an explicit allow-list via `CAPSULE_CORS_ORIGINS`.
