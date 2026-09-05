# Future — implementation plan

Shipped in 0.4.0. This file is the spec that was implemented.

Do these in order. Each slice should ship independently with tests. Files stay canonical; the DB stays a derived index.

Not planned: Stripe, seats, Notion import, “world-class glassmorphism.”

---

## 1. Dedup by content hash

**Why:** `file_hash` already exists (`Capsule.file_hash`, SHA-256 of the whole file). That skips no-op watcher events. It does not stop two files that say the same fact (different UUID, filename, or frontmatter).

**Hash:** SHA-256 of normalized `topic` + `"\n"` + normalized `content` (strip, collapse trailing whitespace, ignore id / freshness / file path). Store as `content_hash` CHAR(64). Do not hash tags or source — those can differ for the same fact.

**On create / upsert (API, CLI, MCP, file watch):**

1. Compute `content_hash`.
2. If another non-archived row has that hash, do **not** write a second file.
3. Return the existing capsule with `deduped: true` (HTTP 200, not 201).
4. If the new write adds tags the existing row lacks, merge tags onto the existing file and reindex.

**On update:** if the new hash collides with a *different* id, reject with 409. User must edit or archive the other file.

**Reconcile:** after indexing, if two files share a hash, keep the older `created_at` (or the one already in the index), log the duplicate path, do not delete files automatically.

**Schema:** `content_hash` column + non-unique index (uniqueness is among non-archived rows, enforced in the store). Add `content_hash` to `to_dict()`.

**CLI:** `capsule new` prints “already exists” and the existing id. Optional later: `capsule dups` to list hash collisions still on disk.

**Tests:** create twice with same topic/body → one file; different topic same body → still one file; same body different tags → one file, tags merged; update into another row’s hash → 409.

**Files:** `services/store/store.py`, `services/shared/models.py`, `services/api/routes.py`, `cli/main.py`, `docs/DB_SCHEMA.md`, `tests/test_api.py`, `tests/test_e2e.py`.

---

## 2. Embeddings as an optional extra index

**Why:** FTS5 / `tsvector` stays the default and the only required path. Embeddings help “what’s related to this?” queries that do not share keywords.

**Default:** off. No extra pip deps unless extras are installed.

```text
pip install korn[embed]
# CAPSULE_EMBED=true
# CAPSULE_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

**Library:** `sentence-transformers` (local, no API key). Optional later: OpenAI via `CAPSULE_EMBED_PROVIDER=openai`. Do not add a vector database. Store the vector on the row.

**Schema:** `embedding` BLOB (SQLite) / `embedding vector` or `BYTEA` (Postgres). Also `embedding_model` TEXT and `embedding_hash` (content_hash at embed time) so we only re-embed when the fact changes.

**When to embed:** after `write_file` / `upsert_from_file` if `CAPSULE_EMBED=true` and `content_hash != embedding_hash`. Best-effort: log and continue if the model is missing. Reconcile can backfill in batches.

**Search:** new optional `mode` on search/compose: `fts` (default), `semantic`, `hybrid`.

- `fts` — current SQL, unchanged.
- `semantic` — cosine over in-memory or SQL-loaded vectors for the candidate set (cap 2k active rows first version; no ANN).
- `hybrid` — FTS top N plus semantic top N, merge with RRF, then existing tag / confidence filters.

Compose uses the same ranking, then the existing token budget.

**API:** `GET /search?mode=hybrid`. Ignore `mode` if embeddings are disabled (behave as `fts`).

**Tests:** with embed extra mocked (fixed vectors), semantic ranks a paraphrase above a keyword miss; FTS-only still passes without the extra installed.

**Files:** `services/shared/config.py`, `services/embed/embedder.py` (new), `services/search/engine.py`, `services/store/store.py`, `pyproject.toml` extras, `docs/ENV.md`, `docs/API.md`.

---

## 3. Git auto-commit of `capsules/`

**Why:** files are the source of truth; a local git history is the cheapest backup and review trail.

**Default:** off. `CAPSULE_GIT_COMMIT=true`. Only commit under `CAPSULES_DIR`, never the rest of the repo.

**When:** after a successful `write_file`, `delete`, or archive that changes a path. Debounce 2s so a burst of watcher events becomes one commit.

**How:**

1. Require `git` on PATH and `CAPSULES_DIR` inside a git work tree (or `git init` that directory only if `CAPSULE_GIT_INIT=true`).
2. `git add -- <paths>` then `git commit -m "capsule: <topic or delete> (<id prefix>)"`.
3. Author: `Capsule <capsule@localhost>` unless `CAPSULE_GIT_AUTHOR` is set.
4. Skip if nothing staged. Never `--amend`. Never push.

**Do not** hook the repo’s existing pre-push/vault hooks. Use `GIT_DIR` / `-C CAPSULES_DIR` so a capsules-only repo works, or `-C` the parent repo with pathspecs limited to the capsules folder.

**CLI:** `capsule git on|off|status`. Status shows last commit and whether the hook is enabled.

**Failure:** log a warning; the file write still succeeds. Git is optional.

**Tests:** tmp git repo as `CAPSULES_DIR`; create → one commit; update → second commit; disabled → no commit.

**Files:** `services/gitcommit/committer.py` (new), `services/store/store.py`, `services/shared/config.py`, `cli/main.py`, `docs/ENV.md`.

---

## 4. Real MCP SDK transport

**Why:** `services/mcp/server.py` is newline-delimited JSON-RPC (`2024-11-05`). Cursor, Claude Desktop, and the official SDK speak MCP over **stdio with Content-Length framing**, plus optional Streamable HTTP. Homemade line JSON will keep breaking clients.

**Keep the tools.** Move handlers out of the framing loop:

- `search_capsules`, `compose_context`, `get_capsule`, `create_capsule`, `list_stale`

**Implementation:** depend on `mcp` (official Python SDK). `capsule mcp` starts FastMCP / `mcp.server.stdio` over stdin/stdout. Same tool names and schemas.

**HTTP (optional second command):** `capsule mcp --http 9101` using the SDK’s Streamable HTTP, behind the same `CAPSULE_API_TOKEN` if set. Not a replacement for the REST API.

**CLI:** `capsule mcp` stays the stdio entry for Cursor `mcp.json`. Document a copy-paste config in README.

**Compat:** delete the homemade line loop once the SDK server is tested. Do not keep two protocols.

**Tests:** in-memory SDK session (or `mcp` client fixture) calling each tool; one test that a create writes a real `.capsule.md`.

**Files:** `services/mcp/server.py` (replace), `pyproject.toml` (`mcp` dep), `cli/main.py`, `README.md`, `docs/FEATURES.md`.

---

## Suggested order and size

| Slice | Effort | Depends on |
| --- | --- | --- |
| 1 Dedup | small | existing `file_hash` / store |
| 3 Git commit | small | store write/delete |
| 4 MCP SDK | medium | store + search as-is |
| 2 Embeddings | medium–large | store `content_hash` from slice 1 |

Ship 1 then 3 then 4. Embeddings last so hybrid search can reuse `content_hash` for “needs re-embed.”
