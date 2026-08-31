# Tech stack

- Python 3.10+ / FastAPI / SQLAlchemy 2 / Watchdog / Click / Rich / psycopg3
- SQLite FTS5 (local) or PostgreSQL 16 + tsvector/GIN (Docker)
- React 19 / Vite / nginx (production UI)
- Tests: pytest + FastAPI TestClient (SQLite). Optional `CAPSULE_TEST_POSTGRES_URL` for live PG search.
