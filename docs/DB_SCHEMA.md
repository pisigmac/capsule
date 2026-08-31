# Database schema

The database is disposable. Files are not.

`capsules`

- `rowid` INTEGER PK
- `id` TEXT UNIQUE — UUID in API and frontmatter
- `topic`, `content`, `freshness`, `source`, `confidence`
- `created_at`, `updated_at`, `archived`
- `file_path` UNIQUE, `file_hash`

`tags`, `capsule_tags`, `capsule_relationships` (unique on from/to/type)

**SQLite:** `capsule_search` FTS5 virtual table, `content_rowid='rowid'`, porter tokenizer.

**Postgres:** `capsules.search_vector tsvector` with a GIN index. A before-insert/update trigger sets weights A on topic and B on content. Queries use `plainto_tsquery('english', :query)` and `ts_rank_cd`.
