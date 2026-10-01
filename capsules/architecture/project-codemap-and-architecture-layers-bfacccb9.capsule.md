---
id: bfacccb9-bcc3-4130-b436-6d347c478e5b
topic: Project Codemap and Architecture Layers
tags:
- capsule
- architecture
- codemap
freshness: '2026-09-30T04:46:52.598856'
source: docs/CODEMAP.md
confidence: high
---

The Capsule codebase is structured into single-responsibility components:
- services/parser: parses and serializes .capsule.md files with YAML frontmatter.
- services/store: manages atomic file writes, content-hash deduplication, and database index upserts.
- services/search: executes FTS5 full-text, semantic embedding, and hybrid searches with tag filtering and context composition.
- services/embed: SentenceTransformers vector generation for semantic retrieval.
- services/gitcommit: optional automatic git staging and commits of capsule file changes.
- services/sync: watchdog file monitor and background sync worker keeping SQLite/Postgres index in sync with capsules/.
- services/api: FastAPI app exposing REST endpoints with token authentication middleware.
- services/mcp: Model Context Protocol (MCP) server for agent tools over stdio and HTTP.
- cli/main.py: Click CLI for developer terminal commands.
- frontend: React SPA for exploring, authoring, and composing capsules.
Canonical references are kept in docs/CODEMAP.md and projects/codemap.md.
