"""Filesystem watcher that keeps the SQLite index in sync with .capsule.md files."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..parser.parser import CapsuleParser
from ..shared.models import get_session_factory
from ..store.store import CapsuleStore, file_sha256

logger = logging.getLogger("capsule.sync")


class CapsuleEventHandler(FileSystemEventHandler):
    """Handle filesystem events for capsule files."""

    def __init__(
        self,
        parser: CapsuleParser,
        on_change: Optional[Callable[[str], None]] = None,
        on_delete: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.parser = parser
        self.on_change = on_change
        self.on_delete = on_delete
        self._file_hashes: Dict[str, str] = {}

    def _is_capsule_file(self, path: str) -> bool:
        if path.endswith(".tmp"):
            return False
        return path.endswith(".capsule.md") or path.endswith(".capsule")

    def _changed(self, path: str) -> bool:
        try:
            digest = file_sha256(Path(path))
        except OSError:
            return True
        if self._file_hashes.get(path) == digest:
            return False
        self._file_hashes[path] = digest
        return True

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_capsule_file(event.src_path):
            return
        if self._changed(event.src_path) and self.on_change:
            self.on_change(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_capsule_file(event.src_path):
            return
        if self._changed(event.src_path) and self.on_change:
            self.on_change(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_capsule_file(event.src_path):
            return
        self._file_hashes.pop(event.src_path, None)
        if self.on_delete:
            self.on_delete(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._is_capsule_file(event.src_path):
            self._file_hashes.pop(event.src_path, None)
            if self.on_delete:
                self.on_delete(event.src_path)
        if self._is_capsule_file(event.dest_path):
            if self._changed(event.dest_path) and self.on_change:
                self.on_change(event.dest_path)


class CapsuleSyncService:
    """Watch capsule directories and upsert them into the index."""

    def __init__(self, watch_dirs: list, parser: Optional[CapsuleParser] = None):
        self.watch_dirs = [Path(d) for d in watch_dirs]
        self.parser = parser or CapsuleParser()
        self.observer: Optional[Observer] = None

    def _session_store(self) -> CapsuleStore:
        db = get_session_factory()()
        return CapsuleStore(db)

    def _on_change(self, file_path: str) -> None:
        store = self._session_store()
        try:
            store.upsert_from_file(Path(file_path))
            store.db.commit()
        except Exception:
            store.db.rollback()
            logger.exception("Failed to index %s", file_path)
        finally:
            store.db.close()

    def _on_delete(self, file_path: str) -> None:
        store = self._session_store()
        try:
            store.delete_by_path(file_path)
            store.db.commit()
        except Exception:
            store.db.rollback()
            logger.exception("Failed to drop index for %s", file_path)
        finally:
            store.db.close()

    def initial_sync(self) -> int:
        store = self._session_store()
        try:
            count = 0
            for watch_dir in self.watch_dirs:
                if not watch_dir.exists():
                    continue
                scoped = CapsuleStore(store.db, capsules_dir=watch_dir, parser=self.parser)
                count += scoped.reconcile()
            store.db.commit()
            return count
        except Exception:
            store.db.rollback()
            raise
        finally:
            store.db.close()

    def start(self) -> None:
        self.observer = Observer()
        handler = CapsuleEventHandler(
            parser=self.parser,
            on_change=self._on_change,
            on_delete=self._on_delete,
        )
        scheduled = 0
        for watch_dir in self.watch_dirs:
            watch_dir.mkdir(parents=True, exist_ok=True)
            self.observer.schedule(handler, str(watch_dir), recursive=True)
            scheduled += 1
        self.observer.start()
        logger.info("Watching %s director%s", scheduled, "y" if scheduled == 1 else "ies")

    def stop(self) -> None:
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
