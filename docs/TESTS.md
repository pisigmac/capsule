# Tests

```bash
pip install -e ".[dev]"
pytest
```

Each test gets a temp sqlite file and a temp `CAPSULES_DIR`. The watcher is disabled (`CAPSULE_WATCH=false`). Search tests go through real FTS5 triggers — they do not insert into `capsule_search` by hand.

Live HTTP (curl):

```bash
./scripts/e2e_curl.sh                 # isolated API, then stop it
./scripts/e2e_curl.sh --url http://127.0.0.1:9100
./scripts/e2e_curl.sh --keep          # leave the isolated API up
```
