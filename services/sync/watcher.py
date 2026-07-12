"""File system watcher for capsule directories."""
import hashlib
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Set
from threading import Thread, Event

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from ..parser.parser import CapsuleParser, ParsedCapsule
from ..shared.models import Capsule, Tag, get_db, SessionLocal


class CapsuleEventHandler(FileSystemEventHandler):
    """Handle file system events for capsule files."""

    def __init__(
        self,
        parser: CapsuleParser,
        on_create: Optional[Callable[[ParsedCapsule, str], None]] = None,
        on_update: Optional[Callable[[ParsedCapsule, str], None]] = None,
        on_delete: Optional[Callable[[str], None]] = None,
    ):
        self.parser = parser
        self.on_create = on_create
        self.on_update = on_update
        self.on_delete = on_delete
        self._file_hashes: Dict[str, str] = {}

    def _is_capsule_file(self, path: str) -> bool:
        return path.endswith(".capsule.md") or path.endswith(".capsule")

    def _get_hash(self, path: str) -> str:
        try:
            content = Path(path).read_bytes()
            return hashlib.sha256(content).hexdigest()
        except (IOError, OSError):
            return ""

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_capsule_file(event.src_path):
            return

        try:
            parsed = self.parser.parse_file(Path(event.src_path))
            self._file_hashes[event.src_path] = self._get_hash(event.src_path)
            if self.on_create:
                self.on_create(parsed, event.src_path)
        except Exception as e:
            print(f"Error processing new capsule {event.src_path}: {e}")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_capsule_file(event.src_path):
            return

        new_hash = self._get_hash(event.src_path)
        if self._file_hashes.get(event.src_path) == new_hash:
            return  # No actual change

        try:
            parsed = self.parser.parse_file(Path(event.src_path))
            self._file_hashes[event.src_path] = new_hash
            if self.on_update:
                self.on_update(parsed, event.src_path)
        except Exception as e:
            print(f"Error processing modified capsule {event.src_path}: {e}")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_capsule_file(event.src_path):
            return

        self._file_hashes.pop(event.src_path, None)
        if self.on_delete:
            self.on_delete(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        # Handle rename
        if self._is_capsule_file(event.src_path):
            self._file_hashes.pop(event.src_path, None)
            if self.on_delete:
                self.on_delete(event.src_path)

        if self._is_capsule_file(event.dest_path):
            try:
                parsed = self.parser.parse_file(Path(event.dest_path))
                self._file_hashes[event.dest_path] = self._get_hash(event.dest_path)
                if self.on_create:
                    self.on_create(parsed, event.dest_path)
            except Exception as e:
                print(f"Error processing moved capsule {event.dest_path}: {e}")


class CapsuleSyncService:
    """Sync service that watches capsule directories and updates the database."""

    def __init__(self, watch_dirs: list, parser: Optional[CapsuleParser] = None):
        self.watch_dirs = [Path(d) for d in watch_dirs]
        self.parser = parser or CapsuleParser()
        self.observer: Optional[Observer] = None
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def _upsert_capsule(self, parsed: ParsedCapsule, file_path: str) -> None:
        """Upsert a capsule into the database."""
        db = SessionLocal()
        try:
            # Check if capsule already exists by file path
            existing = db.query(Capsule).filter(Capsule.file_path == file_path).first()

            if existing:
                existing.topic = parsed.topic
                existing.content = parsed.content
                existing.freshness = parsed.freshness
                existing.source = parsed.source
                existing.confidence = parsed.confidence
                existing.file_path = file_path
                existing.archived = False
            else:
                existing = Capsule(
                    topic=parsed.topic,
                    content=parsed.content,
                    freshness=parsed.freshness,
                    source=parsed.source,
                    confidence=parsed.confidence,
                    file_path=file_path,
                )
                db.add(existing)

            db.flush()

            # Update tags
            existing.tags.clear()
            for tag_name in parsed.tags:
                tag = db.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.add(tag)
                    db.flush()
                existing.tags.append(tag)

            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def _delete_capsule(self, file_path: str) -> None:
        """Delete a capsule from the database."""
        db = SessionLocal()
        try:
            capsule = db.query(Capsule).filter(Capsule.file_path == file_path).first()
            if capsule:
                db.delete(capsule)
                db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def initial_sync(self) -> int:
        """Perform initial sync of all capsule files."""
        count = 0
        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                continue
            for file_path in watch_dir.rglob("*.capsule.md"):
                try:
                    parsed = self.parser.parse_file(file_path)
                    self._upsert_capsule(parsed, str(file_path))
                    count += 1
                except Exception as e:
                    print(f"Error syncing {file_path}: {e}")
        return count

    def start(self) -> None:
        """Start the file system watcher."""
        self.observer = Observer()
        handler = CapsuleEventHandler(
            parser=self.parser,
            on_create=self._upsert_capsule,
            on_update=self._upsert_capsule,
            on_delete=self._delete_capsule,
        )

        for watch_dir in self.watch_dirs:
            if watch_dir.exists():
                self.observer.schedule(handler, str(watch_dir), recursive=True)

        self.observer.start()
        print(f"Sync service watching {len(self.watch_dirs)} directories")

    def stop(self) -> None:
        """Stop the file system watcher."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
