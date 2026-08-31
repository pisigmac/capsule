"""Tests for the SearchEngine."""
from datetime import datetime, timedelta

from services.search.engine import SearchEngine, estimate_tokens
from services.store.store import CapsuleStore


class TestSearchEngine:
    def test_search_by_text(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="Auth bypass", content="JWT verification skipped in staging")
        store.create(topic="Database", content="Postgres connection pool maxes out")
        db_session.commit()

        results = SearchEngine(db_session).search("JWT")
        assert len(results) == 1
        assert results[0]["topic"] == "Auth bypass"

    def test_search_with_filters(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="High conf item", content="Shared searchable content here", confidence="high")
        store.create(topic="Low conf item", content="Shared searchable content here", confidence="low")
        db_session.commit()

        results = SearchEngine(db_session).search("content", confidence="high")
        assert len(results) == 1
        assert results[0]["topic"] == "High conf item"

    def test_search_by_tags(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="Auth notes", content="Content about login flow.", tags=["security"])
        store.create(topic="DB notes", content="Content about storage.", tags=["database"])
        db_session.commit()

        results = SearchEngine(db_session).search_by_tags(["security"])
        assert len(results) == 1
        assert results[0]["topic"] == "Auth notes"

    def test_search_by_tags_requires_all(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="Both tags", content="Content about both topics.", tags=["auth", "staging"])
        store.create(topic="One tag only", content="Content about auth only.", tags=["auth"])
        db_session.commit()

        results = SearchEngine(db_session).search_by_tags(["auth", "staging"], match_all=True)
        assert len(results) == 1
        assert results[0]["topic"] == "Both tags"

    def test_compose_context(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="Fact One", content="First fact content.")
        store.create(topic="Fact Two", content="Second fact content.")
        db_session.commit()

        result = SearchEngine(db_session).compose(max_tokens=1000)
        assert "Fact One" in result["context"]
        assert "Fact Two" in result["context"]
        assert result["capsule_count"] == 2

    def test_compose_respects_token_limit(self, db_session):
        CapsuleStore(db_session).create(topic="Long", content=("word " * 5000).strip())
        db_session.commit()
        result = SearchEngine(db_session).compose(max_tokens=100)
        assert estimate_tokens(result["context"]) <= 150
        assert result["truncated"] is True

    def test_stale_capsules(self, db_session):
        store = CapsuleStore(db_session)
        old = store.create(topic="Old knowledge", content="Content that aged out.")
        store.create(topic="Fresh knowledge", content="Content that is current.")
        old.updated_at = datetime.utcnow() - timedelta(days=100)
        db_session.commit()

        stale = SearchEngine(db_session).stale_capsules(days=90)
        assert len(stale) == 1
        assert stale[0]["topic"] == "Old knowledge"

    def test_compose_with_confidence_filter(self, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="High", content="Content worth keeping.", confidence="high")
        store.create(topic="Low", content="Content less certain here.", confidence="low")
        db_session.commit()

        result = SearchEngine(db_session).compose(confidence_min="medium")
        assert "High" in result["context"]
        assert "Low" not in result["context"]
