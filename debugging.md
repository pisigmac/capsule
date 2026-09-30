# Debugging log

ERROR: FTS5 search tests inserted UUID strings into capsule_search.rowid by hand because integer FTS rowids were never wired to the capsules table | Date: 2026-09-01 | Status: new | Fix: Capsule.rowid integer PK; public UUID in capsules.id; FTS content_rowid=rowid; tests go through real triggers

ERROR: Parser without frontmatter kept the H1 line in body, breaking the documented "topic from H1, content is the rest" contract | Date: 2026-09-01 | Status: new | Fix: strip the matched H1 from content when it is used as topic
ERROR: API lifespan referenced current_engine after the import was dropped during the Postgres refactor | Date: 2026-09-01 | Status: new | Fix: import engine as current_engine again
ERROR: Content-hash dedup missed a second create in the same session | Date: 2026-09-05 | Status: new | Fix: Session autoflush is off; flush before looking up content_hash
ERROR: Semantic search kept calling the real SentenceTransformer after tests patched embedder.embed_text | Date: 2026-09-05 | Status: new | Fix: engine imports the embedder module instead of binding embed_text at import time
ERROR: Dedup merged tags in memory but refresh() lost `ops` because capsule_tags was not flushed | Date: 2026-09-05 | Status: new | Fix: flush after _merge_tags / _apply_tags
ERROR: services/mcp/__init__.py still imported handle after the homemade JSON-RPC loop was removed | Date: 2026-09-05 | Status: new | Fix: export build_mcp, call_tool, serve
ERROR: Isolated python -m build failed in this environment (pip could not install wheel into the build venv) | Date: 2026-09-01 | Status: new | Fix: scripts/build_pypi.sh uses --no-isolation after installing setuptools and wheel
ERROR: git push on dev failed: pre-push vault daemon exited because no vault existed in the repo | Date: 2026-09-01 | Status: new | Fix: vault init in the project so the hook can harvest
ERROR: First uvicorn for curl E2E listened inside the sandbox; curl from outside got connection refused on 127.0.0.1:9100 | Date: 2026-09-05 | Status: new | Fix: start the API outside the sandbox
ERROR: scripts/e2e_curl.sh exited with `health: unbound variable` under `set -u` | Date: 2026-09-05 | Status: new | Fix: removed leftover `$health` after health moved off the /api/v1 helper
ERROR: CLI commands (capsule, kapsule, caps) resolved to other installed packages due to unnamespaced `cli` and `services` imports colliding with editable package finders in sys.meta_path | Date: 2026-09-30 | Status: new | Fix: Namespaced CLI package to capsule_cli, updated pyproject.toml entrypoints, and added meta_path conflict guards in capsule_cli/__init__.py
ERROR: Rich markup parsing in TUI footer crashed with MarkupError closing tag mismatch due to literal `[/]` keybinding hint being parsed as closing tag | Date: 2026-09-30 | Status: new | Fix: Escaped opening bracket `r"\[/]"` in Rich markup string
ERROR: Ingestion TOC detector substring match ('toc' in topic_lower) falsely flagged titles containing 'protocols' (e.g. Authentication Protocols) as Table of Contents | Date: 2026-09-30 | Status: new | Fix: Use regex with word boundaries r"\b(table of contents|toc|contents|quick[- ]links)\b" in is_toc_content
ERROR: CapsuleStore._safe_path rejected external notes residing in valid vault symlinks under CAPSULES_DIR because resolved target paths lie outside the root directory | Date: 2026-09-30 | Status: new | Fix: Check if resolved path is a subpath of any active directory symlink residing within CAPSULES_DIR
ERROR: CapsuleStore.reconcile failed to immediately persist orphan note deletions before subsequent indexing passes because db session autoflush is disabled | Date: 2026-09-30 | Status: new | Fix: Added explicit self.db.flush() immediately following the orphan deletion loop

