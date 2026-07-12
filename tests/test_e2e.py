"""End-to-end integration tests."""
import pytest
from pathlib import Path

from services.parser.parser import CapsuleParser
from services.shared.models import Capsule, Tag, CapsuleRelationship, init_db, SessionLocal
from services.search.engine import SearchEngine
from services.sync.watcher import CapsuleSyncService


class TestEndToEnd:
    """Full workflow integration tests."""

    def test_full_workflow_create_search_compose(self, db_session):
        """Complete workflow: create -> search -> compose."""
        # 1. Create capsules
        c1 = Capsule(topic="Auth bypass", content="JWT skipped in staging", confidence="high")
        c2 = Capsule(topic="DB pool", content="Max 100 connections", confidence="medium")
        tag = Tag(name="security")
        db_session.add_all([c1, c2, tag])
        db_session.commit()
        c1.tags.append(tag)
        db_session.commit()

        # 2. Manually index for FTS5
        db_session.execute("""
            INSERT INTO capsule_search(rowid, topic, content)
            VALUES (:id1, :topic1, :content1), (:id2, :topic2, :content2)
        """, {
            "id1": str(c1.id), "topic1": c1.topic, "content1": c1.content,
            "id2": str(c2.id), "topic2": c2.topic, "content2": c2.content,
        })
        db_session.commit()

        # 3. Search
        engine = SearchEngine(db_session)
        results = engine.search("JWT")
        assert len(results) == 1

        # 4. Compose
        context = engine.compose(tags=["security"])
        assert "Auth bypass" in context
        assert "DB pool" not in context  # Not tagged with security

    def test_sync_then_search(self, db_session, tmp_path):
        """Sync files then search the database."""
        # 1. Create capsule files
        capsules_dir = tmp_path / "capsules"
        capsules_dir.mkdir()

        (capsules_dir / "test.capsule.md").write_text("""---
topic: "Integration Test"
tags: [test, integration]
confidence: high
---

This is an integration test capsule.
""")

        # 2. Sync
        service = CapsuleSyncService(watch_dirs=[str(capsules_dir)])
        count = service.initial_sync()
        assert count == 1

        # 3. Verify in DB
        capsule = db_session.query(Capsule).filter(Capsule.topic == "Integration Test").first()
        assert capsule is not None
        assert capsule.confidence == "high"
        assert len(capsule.tags) == 2

    def test_relationship_graph(self, db_session):
        """Create capsules and link them in a graph."""
        # Create chain: A -> B -> C
        a = Capsule(topic="A", content="Content A")
        b = Capsule(topic="B", content="Content B")
        c = Capsule(topic="C", content="Content C")
        db_session.add_all([a, b, c])
        db_session.commit()

        rel1 = CapsuleRelationship(from_capsule_id=a.id, to_capsule_id=b.id, relationship_type="leads_to")
        rel2 = CapsuleRelationship(from_capsule_id=b.id, to_capsule_id=c.id, relationship_type="leads_to")
        db_session.add_all([rel1, rel2])
        db_session.commit()

        # Verify relationships
        assert len(a.outgoing_relationships) == 1
        assert len(b.incoming_relationships) == 1
        assert len(b.outgoing_relationships) == 1
        assert len(c.incoming_relationships) == 1

    def test_stale_and_archive_workflow(self, db_session):
        """Mark stale capsules and archive them."""
        from datetime import datetime, timezone, timedelta

        old = Capsule(
            topic="Old Knowledge",
            content="This is outdated.",
            updated_at=datetime.now(timezone.utc) - timedelta(days=120),
        )
        db_session.add(old)
        db_session.commit()

        # Find stale
        engine = SearchEngine(db_session)
        stale = engine.stale_capsules(days=90)
        assert len(stale) == 1

        # Archive
        old.archived = True
        db_session.commit()

        # Should not appear in default search
        capsules = db_session.query(Capsule).filter(Capsule.archived == False).all()
        assert len(capsules) == 0

    def test_parser_to_db_roundtrip(self, db_session, tmp_path):
        """Parse file, save to DB, retrieve, serialize back."""
        parser = CapsuleParser()

        # Create file
        file_path = tmp_path / "roundtrip.capsule.md"
        file_path.write_text("""---
topic: "Roundtrip Test"
tags: [roundtrip, test]
source: "test-suite"
confidence: high
---

This content should survive a roundtrip.
""")

        # Parse
        parsed = parser.parse_file(file_path)

        # Save to DB
        capsule = Capsule(
            topic=parsed.topic,
            content=parsed.content,
            freshness=parsed.freshness,
            source=parsed.source,
            confidence=parsed.confidence,
            file_path=str(file_path),
        )
        db_session.add(capsule)
        db_session.commit()

        # Retrieve
        retrieved = db_session.query(Capsule).filter(Capsule.id == capsule.id).first()
        assert retrieved.topic == "Roundtrip Test"
        assert retrieved.source == "test-suite"

        # Serialize back
        reparsed = ParsedCapsule(
            topic=retrieved.topic,
            content=retrieved.content,
            tags=[t.name for t in retrieved.tags],
            freshness=retrieved.freshness,
            source=retrieved.source,
            confidence=retrieved.confidence,
        )
        md = parser.to_markdown(reparsed)
        assert "Roundtrip Test" in md
        assert "high" in md
