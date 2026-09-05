"""Dedup, git auto-commit, embeddings, and MCP tool handlers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.embed import embedder as embed_mod
from services.mcp.server import call_tool
from services.search.engine import SearchEngine
from services.shared.models import get_db
from services.store.store import CapsuleStore, DuplicateContentError, content_hash
from services.sync.watcher import CapsuleSyncService


@pytest.fixture
def client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


class TestContentDedup:
    def test_create_twice_returns_same_id(self, db_session):
        store = CapsuleStore(db_session)
        first = store.create(topic="Auth bypass note", content="JWT is skipped in staging for e2e.")
        second = store.create(topic="Different title", content="JWT is skipped in staging for e2e.")
        db_session.commit()
        assert second.id == first.id
        assert second.deduped is True
        files = list(Path(store.capsules_dir).glob("*.capsule.md"))
        assert len(files) == 1

    def test_duplicate_merges_tags(self, db_session):
        store = CapsuleStore(db_session)
        store.create(
            topic="Pool size fact",
            content="The pool maxes out at one hundred connections.",
            tags=["db"],
        )
        merged = store.create(
            topic="Pool size fact",
            content="The pool maxes out at one hundred connections.",
            tags=["ops"],
        )
        db_session.commit()
        db_session.refresh(merged)
        names = {t.name for t in merged.tags}
        assert names == {"db", "ops"}

    def test_update_into_other_hash_conflicts(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="First fact item", content="Alpha content stays unique here.")
        other = store.create(topic="Second fact item", content="Beta content stays unique here.")
        db_session.commit()
        with pytest.raises(DuplicateContentError):
            store.update(other.id, content="Alpha content stays unique here.")

    def test_api_create_returns_200_when_deduped(self, client):
        payload = {
            "topic": "Shared fact title",
            "content": "This exact sentence is the fact body.",
            "tags": ["one"],
        }
        first = client.post("/api/v1/capsules", json=payload)
        assert first.status_code == 201
        second = client.post("/api/v1/capsules", json={**payload, "tags": ["two"]})
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["deduped"] is True
        assert "two" in second.json()["tags"]

    def test_same_hash_function_ignores_topic(self):
        assert content_hash("A", "same body") == content_hash("B", "same body")


class TestGitCommit:
    def test_create_commits_when_enabled(self, db_session, monkeypatch, tmp_path):
        import subprocess

        from services.gitcommit import committer

        capsules = tmp_path / "vault"
        capsules.mkdir()
        subprocess.run(["git", "init"], cwd=capsules, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=capsules, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=capsules, check=True)
        monkeypatch.setenv("CAPSULES_DIR", str(capsules))
        monkeypatch.setenv("CAPSULE_GIT_COMMIT", "true")
        monkeypatch.setenv("CAPSULE_GIT_DEBOUNCE", "0")

        store = CapsuleStore(db_session, capsules_dir=capsules)
        store.create(topic="Git tracked fact", content="This file should land in git history.")
        db_session.commit()
        committer.flush()
        log = subprocess.run(
            ["git", "log", "--oneline"], cwd=capsules, check=True, capture_output=True, text=True
        )
        assert "Git tracked fact" in log.stdout


class TestEmbeddings:
    def test_hybrid_ranks_paraphrase(self, db_session, monkeypatch):
        def fake_embed(text: str):
            blob = (text or "").lower()
            jwt = 1.0 if "jwt" in blob or "token" in blob else 0.0
            pool = 1.0 if "pool" in blob or "connection" in blob else 0.0
            return [jwt, pool]

        monkeypatch.setenv("CAPSULE_EMBED", "true")
        monkeypatch.setattr(embed_mod, "embed_text", fake_embed)

        store = CapsuleStore(db_session)
        token = store.create(
            topic="Auth tokens",
            content="Bearer token verification is skipped in staging.",
        )
        pool = store.create(
            topic="Connection pool",
            content="The database pool maxes out under load.",
        )
        embed_mod.refresh_embedding(token)
        embed_mod.refresh_embedding(pool)
        db_session.commit()

        engine = SearchEngine(db_session)
        semantic = engine.search("jwt auth", mode="semantic")
        assert semantic[0]["id"] == token.id
        hybrid = engine.search("jwt", mode="hybrid")
        assert any(row["id"] == token.id for row in hybrid)

    def test_fts_still_works_when_embed_off(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="JWT fact here", content="JWT verification skipped in staging env.")
        db_session.commit()
        results = SearchEngine(db_session).search("JWT", mode="semantic")
        assert len(results) == 1


class TestMcpTools:
    def test_create_writes_file(self, db_session):
        raw = call_tool(
            "create_capsule",
            {
                "topic": "MCP write path",
                "content": "Created through the official MCP tool handler.",
                "tags": ["mcp"],
            },
        )
        data = json.loads(raw)
        assert Path(data["file_path"]).exists()
        listed = json.loads(call_tool("search_capsules", {"query": "MCP"}))
        assert any(row["id"] == data["id"] for row in listed)


class TestReconcileDupFiles:
    def test_second_file_does_not_create_row(self, db_session, tmp_path, monkeypatch):
        capsules = tmp_path / "caps"
        capsules.mkdir()
        monkeypatch.setenv("CAPSULES_DIR", str(capsules))
        body = """---
topic: "One"
confidence: high
---

Shared fact body for both files.
"""
        (capsules / "a.capsule.md").write_text(body)
        (capsules / "b.capsule.md").write_text(body.replace('topic: "One"', 'topic: "Two"'))
        CapsuleSyncService(watch_dirs=[str(capsules)]).initial_sync()
        from services.shared.models import Capsule

        db_session.expire_all()
        assert db_session.query(Capsule).count() == 1
