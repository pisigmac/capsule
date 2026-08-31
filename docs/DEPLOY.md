# Deploy

## Local (SQLite)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn services.api.main:app --host 127.0.0.1 --port 9100 --workers 1
```

Keep `--workers 1` with SQLite. The in-process watcher (`CAPSULE_WATCH=true`) is the default.

## Docker (Postgres)

```bash
./scripts/start_all.sh
```

- `postgres`: Postgres 16, volume `capsule-pg`
- `api`: FastAPI, two workers, `CAPSULE_WATCH=false`, indexes files on boot
- `sync`: `python -m services.sync` watching `./capsules`
- `web`: nginx UI on port 8080, API published on 9100

Override the DB password with `POSTGRES_PASSWORD`. The DSN is `postgresql+psycopg://capsule:…@postgres:5432/capsule`.

Point a local CLI at Docker Postgres:

```bash
export CAPSULE_DATABASE_URL=postgresql+psycopg://capsule:capsule@127.0.0.1:5432/capsule
```

(only if you publish 5432; it is not published by default.)

Stop:

```bash
./scripts/stop_all.sh
```
