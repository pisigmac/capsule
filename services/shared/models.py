"""SQLAlchemy models. The database is a derived index of .capsule.md files."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from sqlalchemy.pool import NullPool

from .config import config

Base = declarative_base()

capsule_tags = Table(
    "capsule_tags",
    Base.metadata,
    Column(
        "capsule_rowid",
        Integer,
        ForeignKey("capsules.rowid", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Capsule(Base):
    """Indexed copy of one atomic knowledge file."""

    __tablename__ = "capsules"

    rowid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    topic = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=False)
    freshness = Column(DateTime, nullable=False, default=utcnow)
    source = Column(String(500), nullable=True)
    confidence = Column(String(20), nullable=False, default="medium")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    archived = Column(Boolean, nullable=False, default=False)
    file_path = Column(String(1000), nullable=True, unique=True)
    file_hash = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    embedding = Column(Text, nullable=True)
    embedding_model = Column(String(200), nullable=True)
    embedding_hash = Column(String(64), nullable=True)

    tags = relationship("Tag", secondary=capsule_tags, back_populates="capsules")
    outgoing_relationships = relationship(
        "CapsuleRelationship",
        foreign_keys="CapsuleRelationship.from_capsule_id",
        back_populates="from_capsule",
        cascade="all, delete-orphan",
    )
    incoming_relationships = relationship(
        "CapsuleRelationship",
        foreign_keys="CapsuleRelationship.to_capsule_id",
        back_populates="to_capsule",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_capsules_freshness", "freshness"),
        Index("ix_capsules_confidence", "confidence"),
        Index("ix_capsules_archived", "archived"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "content": self.content,
            "freshness": self.freshness.isoformat() if self.freshness else None,
            "source": self.source,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "archived": self.archived,
            "file_path": self.file_path,
            "tags": [t.name for t in self.tags],
            "content_hash": self.content_hash,
            "deduped": bool(getattr(self, "deduped", False)),
        }


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    capsules = relationship("Capsule", secondary=capsule_tags, back_populates="tags")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CapsuleRelationship(Base):
    __tablename__ = "capsule_relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_capsule_id = Column(String(36), ForeignKey("capsules.id", ondelete="CASCADE"), nullable=False)
    to_capsule_id = Column(String(36), ForeignKey("capsules.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(50), nullable=False, default="relates_to")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    from_capsule = relationship("Capsule", foreign_keys=[from_capsule_id], back_populates="outgoing_relationships")
    to_capsule = relationship("Capsule", foreign_keys=[to_capsule_id], back_populates="incoming_relationships")

    __table_args__ = (
        UniqueConstraint("from_capsule_id", "to_capsule_id", "relationship_type", name="uq_rel_edge"),
        Index("ix_rel_from", "from_capsule_id"),
        Index("ix_rel_to", "to_capsule_id"),
        Index("ix_rel_type", "relationship_type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "from_capsule_id": self.from_capsule_id,
            "to_capsule_id": self.to_capsule_id,
            "relationship_type": self.relationship_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None


def _sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def reset_engine() -> Engine:
    """Rebuild the engine from current config. Used by tests and startup."""
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()

    kwargs: dict = {"echo": False, "future": True, "pool_pre_ping": True}
    if config.is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = NullPool
        kwargs.pop("pool_pre_ping")
    else:
        kwargs["pool_size"] = config.pool_size
        kwargs["max_overflow"] = max(config.pool_size, 10)
        kwargs["pool_recycle"] = 1800

    engine = create_engine(config.database_url, **kwargs)
    if config.is_sqlite:
        event.listen(engine, "connect", _sqlite_pragmas)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    return engine


def get_engine() -> Engine:
    if engine is None:
        reset_engine()
    assert engine is not None
    return engine


def get_session_factory() -> sessionmaker:
    if SessionLocal is None:
        reset_engine()
    assert SessionLocal is not None
    return SessionLocal


def get_db() -> Session:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


_STARTUP_LOCK_KEY = 912001


def _init_sqlite_search(conn) -> None:
    conn.execute(
        text(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS capsule_search USING fts5(
                topic,
                content,
                content='capsules',
                content_rowid='rowid',
                tokenize='porter unicode61'
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER IF NOT EXISTS capsules_ai AFTER INSERT ON capsules BEGIN
                INSERT INTO capsule_search(rowid, topic, content)
                VALUES (new.rowid, new.topic, new.content);
            END
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER IF NOT EXISTS capsules_ad AFTER DELETE ON capsules BEGIN
                INSERT INTO capsule_search(capsule_search, rowid, topic, content)
                VALUES ('delete', old.rowid, old.topic, old.content);
            END
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER IF NOT EXISTS capsules_au AFTER UPDATE ON capsules BEGIN
                INSERT INTO capsule_search(capsule_search, rowid, topic, content)
                VALUES ('delete', old.rowid, old.topic, old.content);
                INSERT INTO capsule_search(rowid, topic, content)
                VALUES (new.rowid, new.topic, new.content);
            END
            """
        )
    )


def _init_postgres_search(conn) -> None:
    conn.execute(text("ALTER TABLE capsules ADD COLUMN IF NOT EXISTS search_vector tsvector"))
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_capsules_search_vector
            ON capsules USING GIN (search_vector)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION capsules_search_vector_update() RETURNS trigger AS $$
            BEGIN
              NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.topic, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.content, '')), 'B');
              RETURN NEW;
            END
            $$ LANGUAGE plpgsql
            """
        )
    )
    conn.execute(text("DROP TRIGGER IF EXISTS capsules_search_vector_trigger ON capsules"))
    conn.execute(
        text(
            """
            CREATE TRIGGER capsules_search_vector_trigger
            BEFORE INSERT OR UPDATE OF topic, content ON capsules
            FOR EACH ROW EXECUTE FUNCTION capsules_search_vector_update()
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE capsules SET search_vector =
              setweight(to_tsvector('english', coalesce(topic, '')), 'A') ||
              setweight(to_tsvector('english', coalesce(content, '')), 'B')
            WHERE search_vector IS NULL
            """
        )
    )


def _ensure_columns(conn, dialect: str) -> None:
    """Add columns introduced after 0.3.0 so existing index DBs keep working."""
    specs = [
        ("content_hash", "VARCHAR(64)"),
        ("embedding", "TEXT"),
        ("embedding_model", "VARCHAR(200)"),
        ("embedding_hash", "VARCHAR(64)"),
    ]
    if dialect == "postgresql":
        for name, decl in specs:
            conn.execute(text(f"ALTER TABLE capsules ADD COLUMN IF NOT EXISTS {name} {decl}"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_capsules_content_hash ON capsules (content_hash)"))
        return
    info = conn.execute(text("PRAGMA table_info(capsules)")).mappings().all()
    have = {row["name"] for row in info}
    for name, decl in specs:
        if name not in have:
            conn.execute(text(f"ALTER TABLE capsules ADD COLUMN {name} {decl}"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_capsules_content_hash ON capsules (content_hash)"))


def init_db() -> None:
    """Create tables and the backend-specific search index. Safe to call repeatedly."""
    bind = get_engine()
    Base.metadata.create_all(bind=bind)

    with bind.connect() as conn:
        _ensure_columns(conn, bind.dialect.name)
        if bind.dialect.name == "sqlite":
            _init_sqlite_search(conn)
        elif bind.dialect.name == "postgresql":
            _init_postgres_search(conn)
        else:
            raise RuntimeError(f"Unsupported database dialect: {bind.dialect.name}")
        conn.commit()


def try_startup_lock(db: Session) -> bool:
    """Postgres advisory lock so only one API worker reconciles. SQLite always proceeds."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    locked = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _STARTUP_LOCK_KEY}).scalar()
    return bool(locked)


def release_startup_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _STARTUP_LOCK_KEY})
