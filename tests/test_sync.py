"""Tests for the CapsuleSyncService."""
import os
import time
from pathlib import Path

from services.sync.watcher import CapsuleSyncService
from services.parser.parser import CapsuleParser
from services.shared.models import Capsule


class TestCapsuleSyncService:
    """Test suite for file system sync."""

    def test_initial_sync(self, db_session, temp_capsule_dir):
        """Service should sync all capsule files on initial scan."""
        service = CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)])
        count = service.initial_sync()

        assert count == 2

        # Verify in database
        capsules = db_session.query(Capsule).all()
        assert len(capsules) == 2
        topics = {c.topic for c in capsules}
        assert "Auth bypass" in topics
        assert "Postgres connection pool" in topics

    def test_sync_creates_tags(self, db_session, temp_capsule_dir):
        """Service should create tags from capsule files."""
        service = CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)])
        service.initial_sync()

        capsules = db_session.query(Capsule).all()
        for c in capsules:
            assert len(c.tags) > 0

        # Check tag names
        all_tags = set()
        for c in capsules:
            for t in c.tags:
                all_tags.add(t.name)

        assert "auth" in all_tags or "database" in all_tags

    def test_sync_updates_existing(self, db_session, temp_capsule_dir):
        """Service should update existing capsules on re-sync."""
        service = CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)])
        service.initial_sync()

        # Modify a file
        auth_file = temp_capsule_dir / "auth.capsule.md"
        auth_file.write_text("""---
topic: "Updated Auth"
tags: [auth, bug]
confidence: high
---

Updated content.
""")

        # Re-sync
        count = service.initial_sync()

        # Should still be 2 capsules, but one updated
        capsules = db_session.query(Capsule).all()
        assert len(capsules) == 2
        topics = {c.topic for c in capsules}
        assert "Updated Auth" in topics

    def test_file_path_tracking(self, db_session, temp_capsule_dir):
        """Service should track file paths for capsules."""
        service = CapsuleSyncService(watch_dirs=[str(temp_capsule_dir)])
        service.initial_sync()

        capsules = db_session.query(Capsule).all()
        for c in capsules:
            assert c.file_path is not None
            assert str(temp_capsule_dir) in c.file_path


class TestCapsuleEventHandler:
    """Test the file system event handler."""

    def test_is_capsule_file(self):
        """Handler should identify capsule files correctly."""
        from services.sync.watcher import CapsuleEventHandler

        handler = CapsuleEventHandler(parser=CapsuleParser())

        assert handler._is_capsule_file("/path/to/file.capsule.md")
        assert handler._is_capsule_file("/path/to/file.capsule")
        assert not handler._is_capsule_file("/path/to/file.md")
        assert not handler._is_capsule_file("/path/to/file.txt")
