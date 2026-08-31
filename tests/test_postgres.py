"""Postgres search SQL and DSN helpers. Live PG tests run only when CAPSULE_TEST_POSTGRES_URL is set."""
from __future__ import annotations

import os

import pytest

from services.search.engine import _postgres_search_sql
from services.shared.config import CapsuleConfig


def test_postgres_search_sql_uses_tsvector():
    sql, params = _postgres_search_sql(archived=False, confidence="high", limit=20, offset=5)
    assert "search_vector @@ plainto_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert params["confidence"] == "high"
    assert params["limit"] == 20
    assert params["offset"] == 5


def test_database_url_normalizes_postgres_schemes(monkeypatch):
    cfg = CapsuleConfig()
    monkeypatch.setenv("CAPSULE_DATABASE_URL", "postgres://user:pass@localhost:5432/capsule")
    assert cfg.database_url.startswith("postgresql+psycopg://")
    assert cfg.is_postgres
    monkeypatch.setenv("CAPSULE_DATABASE_URL", "postgresql://user:pass@db/capsule")
    assert cfg.database_url.startswith("postgresql+psycopg://")
    monkeypatch.setenv("CAPSULE_DATABASE_URL", "sqlite:///capsule.db")
    assert cfg.is_sqlite
    assert not cfg.is_postgres


@pytest.mark.skipif(not os.getenv("CAPSULE_TEST_POSTGRES_URL"), reason="CAPSULE_TEST_POSTGRES_URL not set")
def test_postgres_roundtrip_search(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPSULE_DATABASE_URL", os.environ["CAPSULE_TEST_POSTGRES_URL"])
    monkeypatch.setenv("CAPSULES_DIR", str(tmp_path / "capsules"))
    monkeypatch.setenv("CAPSULE_WATCH", "false")
    (tmp_path / "capsules").mkdir()

    from services.search.engine import SearchEngine
    from services.shared.models import get_session_factory, init_db, reset_engine
    from services.store.store import CapsuleStore

    reset_engine()
    init_db()
    db = get_session_factory()()
    try:
        store = CapsuleStore(db)
        store.create(topic="Auth bypass", content="JWT verification skipped in staging")
        store.create(topic="Database pool", content="Postgres connection pool maxes out")
        db.commit()
        results = SearchEngine(db).search("JWT")
        assert len(results) == 1
        assert results[0]["topic"] == "Auth bypass"
    finally:
        from services.shared.models import Capsule, Tag

        db.query(Capsule).delete()
        db.query(Tag).delete()
        db.commit()
        db.close()
