# Architecture

Markdown files are canonical. The database is a derived search index.

**Local default:** SQLite + FTS5, API and watcher in one process.

**Docker / shared index:** Postgres. CRUD and search run in the API. The watchdog is its own process. Both talk to the same Postgres.

```
.capsule.md files
        │
        ▼
   CapsuleStore (file write + upsert)
        │
   ┌────┴────┐
   │         │
 API       Sync          (two processes, one database)
 (CRUD +   (watchdog)
  search)
   │         │
   └────┬────┘
        ▼
   PostgreSQL
   tsvector + GIN
```

Search is SQL in the API, not a third network service. Splitting it would only add latency.

## Rules

1. Files under `CAPSULES_DIR` are the source of truth.
2. SQLite is for single-process local use. Do not point two containers at one SQLite file.
3. Postgres is the shared index. API workers and the sync process may share it.
4. Public ids are UUIDs. Integer `rowid` is the table PK (FTS5 on SQLite, tsvector on Postgres).
5. Optional `CAPSULE_API_TOKEN` if the API is reachable beyond localhost.
