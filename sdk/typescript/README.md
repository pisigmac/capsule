# kapsule-ai

TypeScript client for [Kapsule](https://github.com/pisigmac/capsule), atomic file-first memory for AI agents.

Published on npm as `kapsule-ai`. The Python package remains `kapsule` on PyPI.

## Install

```bash
npm install kapsule-ai
```

## Use

The API listens on `http://127.0.0.1:9100` by default. Set `apiToken` when the server has `CAPSULE_API_TOKEN`.

```typescript
import { KapsuleClient } from "kapsule-ai";

const kapsule = new KapsuleClient({
  baseUrl: "http://127.0.0.1:9100",
  apiToken: process.env.CAPSULE_API_TOKEN,
});

const created = await kapsule.createCapsule({
  topic: "Auth middleware bypass in staging",
  content: "Staging skips the JWT check on /internal/health.",
  tags: ["auth", "bug"],
  confidence: "high",
});

const matches = await kapsule.search({ query: "JWT authentication", mode: "fts" });

const context = await kapsule.compose({
  query: "database concurrency and auth",
  max_tokens: 400,
});

console.log(created.id, matches.length, context.context);
```

## Methods

| Method | API |
|---|---|
| `health` | `GET /health` |
| `status` | `GET /api/v1/status` |
| `createCapsule` | `POST /api/v1/capsules` |
| `listCapsules` | `GET /api/v1/capsules` |
| `getCapsule` | `GET /api/v1/capsules/{id}` |
| `updateCapsule` | `PATCH /api/v1/capsules/{id}` |
| `deleteCapsule` | `DELETE /api/v1/capsules/{id}` |
| `archiveCapsule` | `POST /api/v1/capsules/{id}/archive` |
| `search` | `POST /api/v1/search` |
| `compose` | `POST /api/v1/compose` |
| `listRelationships` / `createRelationship` | `/api/v1/relationships` |
| `listTags` | `GET /api/v1/tags` |
| `stale` | `GET /api/v1/stale` |
| `sync` | `POST /api/v1/sync` |

Failed responses throw `KapsuleError` with `status` and `detail`.
