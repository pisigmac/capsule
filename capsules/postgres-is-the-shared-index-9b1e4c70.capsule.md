---
id: 9b1e4c70-2d88-4a51-8f06-3c7e91a0b4d2
topic: Postgres is the shared index, SQLite is local-only
tags: [capsule, architecture, postgres]
confidence: high
source: capsule-core
---

SQLite FTS5 is the single-process local index. Multiple API or sync processes must share PostgreSQL (`tsvector` + GIN), not a SQLite file. Search stays SQL inside the API; the watchdog is a separate process that upserts the same database when `.capsule.md` files change.
