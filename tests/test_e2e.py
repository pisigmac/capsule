"""End-to-end integration tests."""
from datetime import datetime, timedelta
from pathlib import Path

from services.search.engine import SearchEngine
from services.shared.models import Capsule
from services.store.store import CapsuleStore
from services.sync.watcher import CapsuleSyncService


class TestEndToEnd:
    def test_full_workflow_create_search_compose(self, db_session):
        store = CapsuleStore(db_session)
        store.create(
            topic="Auth bypass",
            content="JWT skipped in staging environment.",
            tags=["security"],
            confidence="high",
        )
        store.create(
            topic="DB pool",
            content="Max 100 connections in the pool.",
            confidence="medium",
        )
        db_session.commit()

        engine = SearchEngine(db_session)
        results = engine.search("JWT")
        assert len(results) == 1

        composed = engine.compose(tags=["security"])
        assert "Auth bypass" in composed["context"]
        assert "DB pool" not in composed["context"]

    def test_sync_then_search(self, db_session, tmp_path):
        capsules_dir = tmp_path / "capsules"
        (capsules_dir / "test.capsule.md").write_text(
            """---
topic: "Integration Test"
tags: [test, integration]
confidence: high
---

This is an integration test capsule.
"""
        )
        service = CapsuleSyncService(watch_dirs=[str(capsules_dir)])
        assert service.initial_sync() == 1

        db_session.expire_all()
        capsule = db_session.query(Capsule).filter(Capsule.topic == "Integration Test").first()
        assert capsule is not None
        assert capsule.confidence == "high"
        assert len(capsule.tags) == 2

        results = SearchEngine(db_session).search("integration")
        assert len(results) == 1

    def test_relationship_graph(self, db_session):
        store = CapsuleStore(db_session)
        a = store.create(topic="Node A item", content="Content A is written.")
        b = store.create(topic="Node B item", content="Content B is written.")
        c = store.create(topic="Node C item", content="Content C is written.")
        store.link(a.id, b.id, "leads_to")
        store.link(b.id, c.id, "leads_to")
        db_session.commit()

        db_session.refresh(a)
        db_session.refresh(b)
        db_session.refresh(c)
        assert len(a.outgoing_relationships) == 1
        assert len(b.incoming_relationships) == 1
        assert len(b.outgoing_relationships) == 1
        assert len(c.incoming_relationships) == 1

    def test_stale_and_archive_workflow(self, db_session):
        store = CapsuleStore(db_session)
        old = store.create(topic="Old Knowledge", content="This is outdated knowledge.")
        old.updated_at = datetime.utcnow() - timedelta(days=120)
        db_session.commit()

        stale = SearchEngine(db_session).stale_capsules(days=90)
        assert len(stale) == 1

        store.archive(old.id)
        db_session.commit()
        active = db_session.query(Capsule).filter(Capsule.archived == False).all()  # noqa: E712
        assert len(active) == 0

    def test_parser_to_db_roundtrip(self, db_session, tmp_path):
        file_path = tmp_path / "capsules" / "roundtrip.capsule.md"
        file_path.parent.mkdir(exist_ok=True)
        file_path.write_text(
            """---
topic: "Roundtrip Test"
tags: [roundtrip, test]
source: "test-suite"
confidence: high
---

This content should survive a roundtrip.
"""
        )
        store = CapsuleStore(db_session, capsules_dir=file_path.parent)
        capsule = store.upsert_from_file(file_path)
        db_session.commit()

        retrieved = db_session.query(Capsule).filter(Capsule.id == capsule.id).first()
        assert retrieved.topic == "Roundtrip Test"
        assert retrieved.source == "test-suite"
        assert retrieved.id  # persisted into the file
        md = Path(retrieved.file_path).read_text()
        assert "Roundtrip Test" in md
        assert "high" in md
        assert retrieved.id in md


class TestMcpProtocol:
    def test_sdk_registers_tools(self):
        from services.mcp.server import build_mcp

        names = {tool.name for tool in build_mcp()._tool_manager.list_tools()}
        assert "search_capsules" in names
        assert "compose_context" in names
        assert "create_capsule" in names
        assert "get_capsule" in names
        assert "list_stale" in names
