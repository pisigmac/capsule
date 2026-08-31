"""Tests for the CapsuleSyncService."""
from services.parser.parser import CapsuleParser
from services.shared.models import Capsule
from services.sync.watcher import CapsuleEventHandler, CapsuleSyncService


class TestCapsuleSyncService:
    def test_initial_sync(self, db_session, temp_capsule_dir):
        service = CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)])
        count = service.initial_sync()
        assert count == 2

        db_session.expire_all()
        capsules = db_session.query(Capsule).all()
        assert len(capsules) == 2
        topics = {c.topic for c in capsules}
        assert "Auth bypass" in topics
        assert "Postgres connection pool" in topics

    def test_sync_creates_tags(self, db_session, temp_capsule_dir):
        CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)]).initial_sync()
        db_session.expire_all()
        all_tags = {t.name for c in db_session.query(Capsule).all() for t in c.tags}
        assert "auth" in all_tags or "database" in all_tags

    def test_sync_updates_existing(self, db_session, temp_capsule_dir):
        service = CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)])
        service.initial_sync()

        (temp_capsule_dir / "auth.capsule.md").write_text(
            """---
topic: "Updated Auth"
tags: [auth, bug]
confidence: high
---

Updated content for the auth capsule.
"""
        )
        service.initial_sync()
        db_session.expire_all()
        topics = {c.topic for c in db_session.query(Capsule).all()}
        assert "Updated Auth" in topics
        assert db_session.query(Capsule).count() == 2

    def test_file_path_tracking(self, db_session, temp_capsule_dir):
        CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)]).initial_sync()
        db_session.expire_all()
        for capsule in db_session.query(Capsule).all():
            assert capsule.file_path is not None
            assert str(temp_capsule_dir) in capsule.file_path


class TestCapsuleEventHandler:
    def test_is_capsule_file(self):
        handler = CapsuleEventHandler(parser=CapsuleParser())
        assert handler._is_capsule_file("/path/to/file.capsule.md")
        assert handler._is_capsule_file("/path/to/file.capsule")
        assert not handler._is_capsule_file("/path/to/file.md")
        assert not handler._is_capsule_file("/path/to/file.capsule.md.tmp")
