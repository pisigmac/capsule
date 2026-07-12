"""SQLAlchemy models for Capsule."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Column, String, DateTime, Boolean, Text, ForeignKey, Table, Integer, event,
    create_engine, select, Index, text
)
from sqlalchemy.orm import declarative_base, relationship, Session, sessionmaker
from sqlalchemy import Uuid as SQLiteUUID

from .config import config

Base = declarative_base()

# Association table for many-to-many: capsules <-> tags
capsule_tags = Table(
    "capsule_tags",
    Base.metadata,
    Column("capsule_id", SQLiteUUID, ForeignKey("capsules.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", SQLiteUUID, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Capsule(Base):
    """A single atomic unit of knowledge."""
    __tablename__ = "capsules"

    id = Column(SQLiteUUID, primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=False)
    freshness = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    source = Column(String(500), nullable=True)
    confidence = Column(String(20), nullable=False, default="medium")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    archived = Column(Boolean, nullable=False, default=False)
    file_path = Column(String(1000), nullable=True)

    # Relationships
    tags = relationship("Tag", secondary=capsule_tags, back_populates="capsules")
    outgoing_relationships = relationship(
        "CapsuleRelationship",
        foreign_keys="CapsuleRelationship.from_capsule_id",
        back_populates="from_capsule",
        cascade="all, delete-orphan"
    )
    incoming_relationships = relationship(
        "CapsuleRelationship",
        foreign_keys="CapsuleRelationship.to_capsule_id",
        back_populates="to_capsule",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_capsules_freshness", "freshness"),
        Index("ix_capsules_confidence", "confidence"),
        Index("ix_capsules_archived", "archived"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
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
        }


class Tag(Base):
    """A tag for categorizing capsules."""
    __tablename__ = "tags"

    id = Column(SQLiteUUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    capsules = relationship("Capsule", secondary=capsule_tags, back_populates="tags")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CapsuleRelationship(Base):
    """A relationship between two capsules."""
    __tablename__ = "capsule_relationships"

    id = Column(SQLiteUUID, primary_key=True, default=uuid.uuid4)
    from_capsule_id = Column(SQLiteUUID, ForeignKey("capsules.id", ondelete="CASCADE"), nullable=False)
    to_capsule_id = Column(SQLiteUUID, ForeignKey("capsules.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(50), nullable=False, default="relates_to")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    from_capsule = relationship("Capsule", foreign_keys=[from_capsule_id], back_populates="outgoing_relationships")
    to_capsule = relationship("Capsule", foreign_keys=[to_capsule_id], back_populates="incoming_relationships")

    __table_args__ = (
        Index("ix_rel_from", "from_capsule_id"),
        Index("ix_rel_to", "to_capsule_id"),
        Index("ix_rel_type", "relationship_type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "from_capsule_id": str(self.from_capsule_id),
            "to_capsule_id": str(self.to_capsule_id),
            "relationship_type": self.relationship_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SearchIndex(Base):
    """FTS5 virtual table for full-text search."""
    __tablename__ = "capsule_search"

    rowid = Column(Integer, primary_key=True)
    topic = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)

    # Note: FTS5 tables are created via raw SQL, not SQLAlchemy declarative
    # This class is for reference only


# Engine and session factory
engine = create_engine(
    config.database_url,
    connect_args={"check_same_thread": False} if config.is_sqlite else {},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize the database, creating all tables and FTS5 index."""
    Base.metadata.create_all(bind=engine)

    # Create FTS5 virtual table for search
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS capsule_search USING fts5(
                topic, content,
                content='capsules',
                content_rowid='id'
            )
        """))
        # Triggers to keep FTS5 in sync
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS capsules_ai AFTER INSERT ON capsules BEGIN
                INSERT INTO capsule_search(rowid, topic, content)
                VALUES (new.id, new.topic, new.content);
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS capsules_ad AFTER DELETE ON capsules BEGIN
                INSERT INTO capsule_search(capsule_search, rowid, topic, content)
                VALUES ('delete', old.id, old.topic, old.content);
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS capsules_au AFTER UPDATE ON capsules BEGIN
                INSERT INTO capsule_search(capsule_search, rowid, topic, content)
                VALUES ('delete', old.id, old.topic, old.content);
                INSERT INTO capsule_search(rowid, topic, content)
                VALUES (new.id, new.topic, new.content);
            END
        """))
        conn.commit()
