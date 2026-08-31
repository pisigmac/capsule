# Tests

```bash
pip install -e ".[dev]"
pytest
```

Each test gets a temp sqlite file and a temp `CAPSULES_DIR`. The watcher is disabled (`CAPSULE_WATCH=false`). Search tests go through real FTS5 triggers — they do not insert into `capsule_search` by hand.
