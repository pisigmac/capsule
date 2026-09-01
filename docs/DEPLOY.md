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

## PyPI (`korn` and `pykorn`)

Releases upload the same package under both names. CI lives in `.github/workflows/pypi.yml`.

1. Create a GitHub Actions environment named `pypi`.
2. Add repository secret `PYPI_API_TOKEN` (PyPI API token, username `__token__`). Use an account-scoped token so both projects can publish. Do not commit the token.
3. Bump `version` in `pyproject.toml`.
4. Tag and push, or publish a GitHub Release:

```bash
git tag v0.3.1
git push origin v0.3.1
```

The tag after `v` must match `pyproject.toml`. The workflow runs tests, builds both names, then uploads. Re-runs skip files that already exist.

Trusted publishing (OIDC) is enabled (`id-token: write`). After you add this repo as a trusted publisher on both PyPI projects (`pisigmac/capsule`, workflow `pypi.yml`, environment `pypi`), you can remove the `password:` lines.

Manual dry run: Actions → Publish to PyPI → Run workflow → dry_run.

Local build only:

```bash
bash scripts/build_pypi.sh
python -m twine check dist/korn/* dist/pykorn/*
```
