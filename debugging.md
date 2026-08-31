# Debugging log

ERROR: FTS5 search tests inserted UUID strings into capsule_search.rowid by hand because integer FTS rowids were never wired to the capsules table | Date: 2026-09-01 | Status: new | Fix: Capsule.rowid integer PK; public UUID in capsules.id; FTS content_rowid=rowid; tests go through real triggers

ERROR: Parser without frontmatter kept the H1 line in body, breaking the documented "topic from H1, content is the rest" contract | Date: 2026-09-01 | Status: new | Fix: strip the matched H1 from content when it is used as topic
ERROR: API lifespan referenced current_engine after the import was dropped during the Postgres refactor | Date: 2026-09-01 | Status: new | Fix: import engine as current_engine again
