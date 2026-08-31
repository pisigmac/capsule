"""Tests for the Capsule API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.shared.models import get_db
from services.store.store import CapsuleStore


@pytest.fixture
def client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


class TestCapsuleCRUD:
    def test_create_capsule(self, client, db_session):
        response = client.post(
            "/api/v1/capsules",
            json={
                "topic": "Test Capsule",
                "content": "This is test content for the capsule.",
                "tags": ["test", "api"],
                "confidence": "high",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["topic"] == "Test Capsule"
        assert data["confidence"] == "high"
        assert "test" in data["tags"]
        assert data["file_path"]
        from pathlib import Path

        assert Path(data["file_path"]).exists()

    def test_create_capsule_validation_error(self, client):
        response = client.post(
            "/api/v1/capsules",
            json={"topic": "AB", "content": "Short"},
        )
        assert response.status_code == 422

    def test_list_capsules(self, client, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="First capsule", content="First content here.")
        store.create(topic="Second capsule", content="Second content here.")
        db_session.commit()

        response = client.get("/api/v1/capsules")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert any(c["topic"] == "First capsule" for c in payload["items"])

    def test_get_capsule(self, client, db_session):
        capsule = CapsuleStore(db_session).create(
            topic="Specific capsule", content="Specific content for get."
        )
        db_session.commit()

        response = client.get(f"/api/v1/capsules/{capsule.id}")
        assert response.status_code == 200
        assert response.json()["topic"] == "Specific capsule"

    def test_get_capsule_not_found(self, client):
        response = client.get("/api/v1/capsules/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_update_capsule(self, client, db_session):
        capsule = CapsuleStore(db_session).create(topic="Old topic", content="Old content is long.")
        db_session.commit()

        response = client.patch(f"/api/v1/capsules/{capsule.id}", json={"topic": "New topic"})
        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "New topic"
        assert data["content"] == "Old content is long."

    def test_delete_capsule(self, client, db_session):
        capsule = CapsuleStore(db_session).create(topic="Delete Me now", content="Content to remove.")
        path = capsule.file_path
        db_session.commit()

        response = client.delete(f"/api/v1/capsules/{capsule.id}")
        assert response.status_code == 204
        from pathlib import Path

        assert not Path(path).exists()
        response = client.get(f"/api/v1/capsules/{capsule.id}")
        assert response.status_code == 404

    def test_archive_capsule(self, client, db_session):
        capsule = CapsuleStore(db_session).create(topic="Archive Me now", content="Content to archive.")
        db_session.commit()
        response = client.post(f"/api/v1/capsules/{capsule.id}/archive")
        assert response.status_code == 200
        assert response.json()["archived"] is True


class TestSearch:
    def test_search_by_text(self, client, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="Auth bypass", content="JWT verification skipped in staging env.")
        store.create(topic="Database pool", content="Postgres connection pool maxes out.")
        db_session.commit()

        response = client.post("/api/v1/search", json={"query": "JWT"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "JWT" in data[0]["content"]

    def test_search_filters_tags(self, client, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="Auth notes here", content="JWT verification skipped in staging.", tags=["auth"])
        store.create(topic="Database notes", content="JWT mentioned in a db runbook too.", tags=["database"])
        db_session.commit()

        response = client.post("/api/v1/search", json={"query": "JWT", "tags": ["auth"]})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["topic"] == "Auth notes here"

    def test_compose_context(self, client, db_session):
        store = CapsuleStore(db_session)
        store.create(topic="Fact One", content="First important fact about auth.")
        store.create(topic="Fact Two", content="Second important fact about auth.")
        db_session.commit()

        response = client.post("/api/v1/compose", json={"query": "fact", "max_tokens": 1000})
        assert response.status_code == 200
        data = response.json()
        assert "Fact One" in data["context"]
        assert data["capsule_count"] >= 1
        assert "token_estimate" in data


class TestRelationships:
    def test_create_relationship(self, client, db_session):
        store = CapsuleStore(db_session)
        c1 = store.create(topic="First capsule", content="Content for the first.")
        c2 = store.create(topic="Second capsule", content="Content for the second.")
        db_session.commit()

        response = client.post(
            "/api/v1/relationships",
            json={
                "from_capsule_id": c1.id,
                "to_capsule_id": c2.id,
                "relationship_type": "blocks",
            },
        )
        assert response.status_code == 201
        assert response.json()["relationship_type"] == "blocks"

    def test_get_relationships(self, client, db_session):
        store = CapsuleStore(db_session)
        c1 = store.create(topic="First capsule", content="Content for the first.")
        c2 = store.create(topic="Second capsule", content="Content for the second.")
        store.link(c1.id, c2.id, "relates_to")
        db_session.commit()

        response = client.get(f"/api/v1/capsules/{c1.id}/relationships")
        assert response.status_code == 200
        assert len(response.json()["outgoing"]) == 1


class TestTags:
    def test_list_tags(self, client, db_session):
        CapsuleStore(db_session).create(
            topic="Tagged capsule",
            content="Content with an important tag.",
            tags=["important"],
        )
        db_session.commit()
        response = client.get("/api/v1/tags")
        assert response.status_code == 200
        data = response.json()
        assert any(t["name"] == "important" and t["count"] == 1 for t in data)


class TestHealth:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in {"ok", "degraded"}
        assert data["service"] == "capsule-api"
        assert data["dialect"] in {"sqlite", "postgresql"}
