"""Tests for the SearchEngine."""
import pytest
from datetime import datetime, timezone, timedelta

from services.search.engine import SearchEngine
from services.shared.models import Capsule, Tag


class TestSearchEngine:
    """Test suite for full-text search."""

    def test_search_by_text(self, db_session):
        """Engine should find capsules matching text query."""
        c1 = Capsule(topic="Auth bypass", content="JWT verification skipped in staging")
        c2 = Capsule(topic="Database", content="Postgres connection pool maxes out")
        db_session.add_all([c1, c2])
        db_session.commit()

        # Manually insert into FTS5 for testing
        db_session.execute("""
            INSERT INTO capsule_search(rowid, topic, content)
            VALUES (:id1, :topic1, :content1), (:id2, :topic2, :content2)
        """, {
            "id1": str(c1.id), "topic1": c1.topic, "content1": c1.content,
            "id2": str(c2.id), "topic2": c2.topic, "content2": c2.content,
        })
        db_session.commit()

        engine = SearchEngine(db_session)
        results = engine.search("JWT")

        assert len(results) == 1
        assert results[0]["topic"] == "Auth bypass"

    def test_search_with_filters(self, db_session):
        """Engine should respect confidence and archived filters."""
        c1 = Capsule(topic="High conf", content="Content", confidence="high")
        c2 = Capsule(topic="Low conf", content="Content", confidence="low")
        db_session.add_all([c1, c2])
        db_session.commit()

        db_session.execute("""
            INSERT INTO capsule_search(rowid, topic, content)
            VALUES (:id1, :topic1, :content1), (:id2, :topic2, :content2)
        """, {
            "id1": str(c1.id), "topic1": c1.topic, "content1": c1.content,
            "id2": str(c2.id), "topic2": c2.topic, "content2": c2.content,
        })
        db_session.commit()

        engine = SearchEngine(db_session)
        results = engine.search("Content", confidence="high")

        assert len(results) == 1
        assert results[0]["topic"] == "High conf"

    def test_search_by_tags(self, db_session):
        """Engine should find capsules by tags."""
        c1 = Capsule(topic="Auth", content="Content")
        c2 = Capsule(topic="DB", content="Content")
        tag = Tag(name="security")
        db_session.add_all([c1, c2, tag])
        db_session.commit()
        c1.tags.append(tag)
        db_session.commit()

        engine = SearchEngine(db_session)
        results = engine.search_by_tags(["security"])

        assert len(results) == 1
        assert results[0]["topic"] == "Auth"

    def test_compose_context(self, db_session):
        """Engine should compose a context window from capsules."""
        c1 = Capsule(topic="Fact One", content="First fact content.")
        c2 = Capsule(topic="Fact Two", content="Second fact content.")
        db_session.add_all([c1, c2])
        db_session.commit()

        engine = SearchEngine(db_session)
        context = engine.compose(max_tokens=1000)

        assert "Fact One" in context
        assert "Fact Two" in context

    def test_compose_respects_token_limit(self, db_session):
        """Engine should not exceed token budget."""
        # Create a very long capsule
        long_content = "word " * 5000
        c1 = Capsule(topic="Long", content=long_content)
        db_session.add(c1)
        db_session.commit()

        engine = SearchEngine(db_session)
        context = engine.compose(max_tokens=100)

        # Rough token estimate should be under limit
        assert len(context.split()) <= 100 + 50  # Allow some margin for headers

    def test_stale_capsules(self, db_session):
        """Engine should find capsules not updated recently."""
        old = Capsule(
            topic="Old",
            content="Content",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        fresh = Capsule(
            topic="Fresh",
            content="Content",
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add_all([old, fresh])
        db_session.commit()

        engine = SearchEngine(db_session)
        stale = engine.stale_capsules(days=90)

        assert len(stale) == 1
        assert stale[0]["topic"] == "Old"

    def test_compose_with_confidence_filter(self, db_session):
        """Engine should filter by minimum confidence."""
        c1 = Capsule(topic="High", content="Content", confidence="high")
        c2 = Capsule(topic="Low", content="Content", confidence="low")
        db_session.add_all([c1, c2])
        db_session.commit()

        engine = SearchEngine(db_session)
        context = engine.compose(confidence_min="medium")

        assert "High" in context
        assert "Low" not in context
