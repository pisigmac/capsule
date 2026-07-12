"""Tests for the Capsule API."""
import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.shared.models import init_db, Capsule, Tag, CapsuleRelationship


@pytest.fixture
def client(db_session):
    """Create a test client with fresh database."""
    # Override the dependency
    from services.api.routes import router
    from services.shared.models import get_db

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    return TestClient(app)


class TestCapsuleCRUD:
    """Test CRUD operations for capsules."""

    def test_create_capsule(self, client):
        """POST /capsules should create a new capsule."""
        response = client.post("/api/v1/capsules", json={
            "topic": "Test Capsule",
            "content": "This is test content for the capsule.",
            "tags": ["test", "api"],
            "confidence": "high",
        })

        assert response.status_code == 201
        data = response.json()
        assert data["topic"] == "Test Capsule"
        assert data["confidence"] == "high"
        assert "test" in data["tags"]
        assert "id" in data

    def test_create_capsule_validation_error(self, client):
        """POST /capsules should reject invalid data."""
        response = client.post("/api/v1/capsules", json={
            "topic": "AB",  # Too short
            "content": "Short",  # Too short
        })

        assert response.status_code == 422

    def test_list_capsules(self, client, db_session):
        """GET /capsules should list all capsules."""
        # Create test data
        c1 = Capsule(topic="First", content="First content")
        c2 = Capsule(topic="Second", content="Second content")
        db_session.add_all([c1, c2])
        db_session.commit()

        response = client.get("/api/v1/capsules")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert any(c["topic"] == "First" for c in data)

    def test_get_capsule(self, client, db_session):
        """GET /capsules/{id} should return a specific capsule."""
        capsule = Capsule(topic="Specific", content="Specific content")
        db_session.add(capsule)
        db_session.commit()

        response = client.get(f"/api/v1/capsules/{capsule.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "Specific"

    def test_get_capsule_not_found(self, client):
        """GET /capsules/{id} should 404 for missing capsule."""
        response = client.get("/api/v1/capsules/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404

    def test_update_capsule(self, client, db_session):
        """PATCH /capsules/{id} should update a capsule."""
        capsule = Capsule(topic="Old", content="Old content")
        db_session.add(capsule)
        db_session.commit()

        response = client.patch(f"/api/v1/capsules/{capsule.id}", json={
            "topic": "New",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "New"
        assert data["content"] == "Old content"  # Unchanged

    def test_delete_capsule(self, client, db_session):
        """DELETE /capsules/{id} should remove a capsule."""
        capsule = Capsule(topic="Delete Me", content="Content")
        db_session.add(capsule)
        db_session.commit()

        response = client.delete(f"/api/v1/capsules/{capsule.id}")

        assert response.status_code == 204

        # Verify deletion
        response = client.get(f"/api/v1/capsules/{capsule.id}")
        assert response.status_code == 404

    def test_archive_capsule(self, client, db_session):
        """POST /capsules/{id}/archive should archive a capsule."""
        capsule = Capsule(topic="Archive Me", content="Content")
        db_session.add(capsule)
        db_session.commit()

        response = client.post(f"/api/v1/capsules/{capsule.id}/archive")

        assert response.status_code == 200
        data = response.json()
        assert data["archived"] is True


class TestSearch:
    """Test search functionality."""

    def test_search_by_text(self, client, db_session):
        """POST /search should find capsules by text."""
        c1 = Capsule(topic="Auth bypass", content="JWT verification skipped")
        c2 = Capsule(topic="Database", content="Postgres connection pool")
        db_session.add_all([c1, c2])
        db_session.commit()

        # Need to wait for FTS5 trigger or manually insert
        db_session.execute("""
            INSERT INTO capsule_search(rowid, topic, content)
            VALUES (:id1, :topic1, :content1), (:id2, :topic2, :content2)
        """, {
            "id1": str(c1.id), "topic1": c1.topic, "content1": c1.content,
            "id2": str(c2.id), "topic2": c2.topic, "content2": c2.content,
        })
        db_session.commit()

        response = client.post("/api/v1/search", json={
            "query": "JWT",
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any("JWT" in c["topic"] or "JWT" in c["content"] for c in data)

    def test_compose_context(self, client, db_session):
        """POST /compose should build a context window."""
        c1 = Capsule(topic="Fact One", content="First important fact.")
        c2 = Capsule(topic="Fact Two", content="Second important fact.")
        db_session.add_all([c1, c2])
        db_session.commit()

        response = client.post("/api/v1/compose", json={
            "query": "fact",
            "max_tokens": 1000,
        })

        assert response.status_code == 200
        data = response.json()
        assert "context" in data
        assert "token_estimate" in data
        assert "Fact One" in data["context"]


class TestRelationships:
    """Test capsule relationships."""

    def test_create_relationship(self, client, db_session):
        """POST /relationships should link two capsules."""
        c1 = Capsule(topic="First", content="Content")
        c2 = Capsule(topic="Second", content="Content")
        db_session.add_all([c1, c2])
        db_session.commit()

        response = client.post("/api/v1/relationships", json={
            "from_capsule_id": str(c1.id),
            "to_capsule_id": str(c2.id),
            "relationship_type": "blocks",
        })

        assert response.status_code == 201
        data = response.json()
        assert data["relationship_type"] == "blocks"

    def test_get_relationships(self, client, db_session):
        """GET /capsules/{id}/relationships should return links."""
        c1 = Capsule(topic="First", content="Content")
        c2 = Capsule(topic="Second", content="Content")
        db_session.add_all([c1, c2])
        db_session.commit()

        rel = CapsuleRelationship(
            from_capsule_id=c1.id,
            to_capsule_id=c2.id,
            relationship_type="relates_to",
        )
        db_session.add(rel)
        db_session.commit()

        response = client.get(f"/api/v1/capsules/{c1.id}/relationships")

        assert response.status_code == 200
        data = response.json()
        assert len(data["outgoing"]) == 1


class TestTags:
    """Test tag operations."""

    def test_list_tags(self, client, db_session):
        """GET /tags should list all tags with counts."""
        c = Capsule(topic="Test", content="Content")
        tag = Tag(name="important")
        db_session.add_all([c, tag])
        db_session.commit()
        c.tags.append(tag)
        db_session.commit()

        response = client.get("/api/v1/tags")

        assert response.status_code == 200
        data = response.json()
        assert any(t["name"] == "important" and t["count"] == 1 for t in data)


class TestHealth:
    """Test health endpoint."""

    def test_health(self, client):
        """GET /health should return ok."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
