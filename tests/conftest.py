"""Pytest fixtures and configuration."""
from __future__ import annotations

import pytest

from services.parser.parser import CapsuleParser
from services.shared.models import get_session_factory, init_db, reset_engine


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated sqlite file + capsules directory for each test."""
    db_path = tmp_path / "test.db"
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()
    monkeypatch.setenv("CAPSULE_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("CAPSULES_DIR", str(capsules_dir))
    monkeypatch.setenv("CAPSULE_WATCH", "false")
    monkeypatch.setenv("CAPSULE_API_TOKEN", "")
    monkeypatch.setenv("CAPSULE_GIT_COMMIT", "false")
    monkeypatch.setenv("CAPSULE_EMBED", "false")
    reset_engine()
    init_db()
    session = get_session_factory()()
    yield session
    session.close()


@pytest.fixture
def parser():
    return CapsuleParser()


@pytest.fixture
def sample_capsule_text():
    return """---
id: 11111111-1111-1111-1111-111111111111
topic: "Auth middleware bypass in staging"
tags: [bug, auth, staging]
freshness: 2026-07-11T00:00:00+00:00
source: "Claude session #4482"
confidence: high
---

Staging env skips JWT verification when `X-Debug-Override` is present.
This is intentional for E2E tests but never documented.

**Do not remove** — the mobile team relies on it for CI.
**Risk:** Production has a similar header name. Verify no collision.
"""


@pytest.fixture
def temp_capsule_dir(db_session):
    from services.shared.config import config

    capsules_dir = config.capsules_dir
    (capsules_dir / "auth.capsule.md").write_text(
        """---
topic: "Auth bypass"
tags: [auth, bug]
confidence: high
---

Auth middleware bypass in staging.
"""
    )
    (capsules_dir / "db.capsule.md").write_text(
        """---
topic: "Postgres connection pool"
tags: [database, performance]
confidence: medium
---

Connection pool maxes out at 100 connections.
"""
    )
    return capsules_dir
