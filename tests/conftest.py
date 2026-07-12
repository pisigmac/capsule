"""Pytest fixtures and configuration."""
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.shared.models import Base, Capsule, Tag, CapsuleRelationship
from services.parser.parser import CapsuleParser
from services.search.engine import SearchEngine


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh in-memory database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    # Create FTS5 manually for in-memory tests
    with engine.connect() as conn:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS capsule_search USING fts5(
                topic, content,
                content='capsules',
                content_rowid='id'
            )
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS capsules_ai AFTER INSERT ON capsules BEGIN
                INSERT INTO capsule_search(rowid, topic, content)
                VALUES (new.id, new.topic, new.content);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS capsules_ad AFTER DELETE ON capsules BEGIN
                INSERT INTO capsule_search(capsule_search, rowid, topic, content)
                VALUES ('delete', old.id, old.topic, old.content);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS capsules_au AFTER UPDATE ON capsules BEGIN
                INSERT INTO capsule_search(capsule_search, rowid, topic, content)
                VALUES ('delete', old.id, old.topic, old.content);
                INSERT INTO capsule_search(rowid, topic, content)
                VALUES (new.id, new.topic, new.content);
            END
        """)
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def parser():
    """Provide a CapsuleParser instance."""
    return CapsuleParser()


@pytest.fixture
def sample_capsule_text():
    """Sample valid capsule markdown."""
    return """---
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
def temp_capsule_dir(tmp_path):
    """Create a temporary directory with sample capsule files."""
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()

    # Create a few sample capsules
    (capsules_dir / "auth.capsule.md").write_text("""---
topic: "Auth bypass"
tags: [auth, bug]
confidence: high
---

Auth middleware bypass in staging.
""")

    (capsules_dir / "db.capsule.md").write_text("""---
topic: "Postgres connection pool"
tags: [database, performance]
confidence: medium
---

Connection pool maxes out at 100 connections.
""")

    return capsules_dir
