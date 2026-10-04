"""Unit and integration tests for CrewAI custom storage adapter."""
from __future__ import annotations

from pathlib import Path

import pytest

from kapsule.adapters.crewai import CapsuleStorage
from services.adapters.crewai import CapsuleStorage as ServiceStorage
from services.store.store import CapsuleStore


class TestCapsuleStorage:
    def test_storage_save_creates_capsule(self, db_session, tmp_path):
        caps_dir = tmp_path / "caps_crewai"
        caps_dir.mkdir(parents=True, exist_ok=True)

        storage = CapsuleStorage(storage_dir=caps_dir, db_session=db_session)
        storage.save(
            value="PostgreSQL connection pool should not exceed 50 connections to prevent thread contention.",
            metadata={
                "topic": "PostgreSQL Connection Upper Bound",
                "task_description": "Investigate database bottleneck",
                "agent_role": "Database Architect",
                "tags": ["postgres", "database", "performance"],
                "confidence": "high",
            },
        )

        # Verify capsule created on disk
        caps_files = list(caps_dir.glob("*.caps.md"))
        assert len(caps_files) == 1

        cap_content = caps_files[0].read_text(encoding="utf-8")
        assert "topic: PostgreSQL Connection Upper Bound" in cap_content
        assert "confidence: high" in cap_content
        assert "source: crewai:Database Architect" in cap_content
        assert "postgres" in cap_content
        assert "database-architect" in cap_content

    def test_storage_search_retrieves_results(self, db_session, tmp_path):
        caps_dir = tmp_path / "caps_crewai_search"
        caps_dir.mkdir(parents=True, exist_ok=True)

        storage = CapsuleStorage(storage_dir=caps_dir, db_session=db_session)
        storage.save(
            value="When X-Debug-Override is passed, staging skips JWT authentication.",
            metadata={
                "topic": "Staging Auth Header Override",
                "agent_role": "Security Engineer",
                "tags": ["auth", "security", "staging"],
            },
        )

        results = storage.search("auth", limit=5)
        assert len(results) >= 1

        res = results[0]
        assert "Staging Auth Header Override" in res["topic"]
        assert "X-Debug-Override" in res["content"]
        assert "auth" in res["metadata"]["tags"]
        assert res["score"] >= 0.0

    def test_storage_save_minimal_metadata(self, db_session, tmp_path):
        caps_dir = tmp_path / "caps_crewai_minimal"
        caps_dir.mkdir(parents=True, exist_ok=True)

        storage = CapsuleStorage(storage_dir=caps_dir, db_session=db_session)
        storage.save(
            value="Redis distributed locking requires a 500ms timeout.",
        )

        caps_files = list(caps_dir.glob("*.caps.md"))
        assert len(caps_files) == 1

        cap_content = caps_files[0].read_text(encoding="utf-8")
        assert "Redis distributed locking" in cap_content
        assert "crewai" in cap_content

    def test_storage_reset_is_safe(self, db_session, tmp_path):
        caps_dir = tmp_path / "caps_crewai_reset"
        caps_dir.mkdir(parents=True, exist_ok=True)

        storage = CapsuleStorage(storage_dir=caps_dir, db_session=db_session)
        # reset should be safe and not error
        storage.reset()


class TestAdapterExportParity:
    def test_aliases_match(self):
        assert CapsuleStorage is ServiceStorage
