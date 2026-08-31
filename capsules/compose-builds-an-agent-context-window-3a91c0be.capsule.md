---
id: 3a91c0be-5d24-4e6f-a817-44b0c19f2e58
topic: Compose builds an agent context window
tags: [capsule, agents, compose]
confidence: high
source: capsule-core
---

`POST /api/v1/compose` (and `capsule compose`) selects matching capsules and concatenates them until `max_tokens`. Token estimates use characters/4. Prefer tag + confidence filters so agents do not ingest hearsay. The MCP server exposes the same compose tool over stdio.
