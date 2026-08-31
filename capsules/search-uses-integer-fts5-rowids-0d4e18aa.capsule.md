---
id: 0d4e18aa-2c77-4f91-8b33-9c1a0e7d25b1
topic: Search uses integer FTS5 rowids
tags: [capsule, search]
confidence: high
source: capsule-core
---

Capsule rows have an integer primary key (`rowid`) used by SQLite FTS5, plus a UUID `id` used in the API and in YAML frontmatter. Joining FTS `rowid` to a UUID column does not work; never use the public id as `content_rowid`.
