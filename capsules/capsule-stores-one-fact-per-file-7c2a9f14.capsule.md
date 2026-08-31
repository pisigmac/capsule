---
id: 7c2a9f14-6b81-4d3e-9a0c-1f8e2b4d6c70
topic: Capsule stores one fact per file
tags: [capsule, architecture]
confidence: high
source: capsule-core
---

The canonical record for a capsule is a `.capsule.md` file under `CAPSULES_DIR`. SQLite is a derived search index, rebuilt from those files on startup. If the database is deleted, `capsule sync` or API startup will recreate it from disk.
