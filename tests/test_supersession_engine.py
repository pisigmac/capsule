"""Tests for Automated Invariant Contradiction & Supersession Engine (Pillar 2)."""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from services.analysis.supersession import InvariantSupersessionEngine
from services.api.main import create_app
from services.search.engine import SearchEngine
from services.shared.models import Capsule, CapsuleRelationship, Tag, get_db
from services.store.store import CapsuleStore


def test_parameter_extraction(db_session):
    store = CapsuleStore(db_session)
    engine = InvariantSupersessionEngine(store)

    text = """
    # Database Configuration
    max_connections: 50
    pool_size = 20
    - timeout: 30s
    ssl_mode: require
    """
    params = engine.extract_parameters(text)
    assert params.get("max_connections") == "50"
    assert params.get("pool_size") == "20"
    assert params.get("timeout") == "30s"
    assert params.get("ssl_mode") == "require"


def test_detect_parameter_shift_contradiction(db_session):
    store = CapsuleStore(db_session)
    db = db_session
    engine = InvariantSupersessionEngine(store)

    # Older capsule (created 5 days ago)
    t_old = datetime.utcnow() - timedelta(days=5)
    c_old = store.create(
        topic="Database Connection Pool Settings",
        content="Primary postgres connection pool config:\nmax_connections: 20\npool_size: 10\ntimeout: 60s",
        tags=["database", "config", "architecture"],
        confidence="high",
        freshness=t_old,
    )

    # Newer capsule (created today)
    t_new = datetime.utcnow()
    c_new = store.create(
        topic="Database Connection Pool Settings Updated",
        content="Scaled postgres connection pool settings for high throughput:\nmax_connections: 100\npool_size: 50\ntimeout: 15s",
        tags=["database", "config"],
        confidence="high",
        freshness=t_new,
    )
    db.commit()

    report = engine.detect_contradictions(min_confidence=0.5, apply_supersession=False)
    assert report.contradictions_found >= 1

    finding = next((f for f in report.findings if f.older_capsule_id == c_old.id and f.newer_capsule_id == c_new.id), None)
    assert finding is not None
    assert finding.contradiction_type == "parameter_shift"
    assert "max_connections" in finding.diff_summary
    assert finding.diff_summary["max_connections"]["older"] == "20"
    assert finding.diff_summary["max_connections"]["newer"] == "100"
    assert finding.confidence_score >= 0.7


def test_detect_polarity_negation(db_session):
    store = CapsuleStore(db_session)
    db = db_session
    engine = InvariantSupersessionEngine(store)

    t_old = datetime.utcnow() - timedelta(days=10)
    c_old = store.create(
        topic="API Caching Strategy",
        content="All public API endpoints use in-memory response caching. status: enabled. synchronous invalidation.",
        tags=["api", "caching", "architecture"],
        freshness=t_old,
    )

    t_new = datetime.utcnow()
    c_new = store.create(
        topic="API Caching Strategy v2",
        content="Due to memory pressure, in-memory caching is disabled. status: disabled. asynchronous event invalidation.",
        tags=["api", "caching"],
        freshness=t_new,
    )
    db.commit()

    report = engine.detect_contradictions(min_confidence=0.5, apply_supersession=False)
    assert report.contradictions_found >= 1
    finding = next((f for f in report.findings if f.older_capsule_id == c_old.id), None)
    assert finding is not None
    assert finding.contradiction_type == "polarity_negation"


def test_apply_supersession_and_confidence_deprecation(db_session):
    store = CapsuleStore(db_session)
    db = db_session
    engine = InvariantSupersessionEngine(store)

    t_old = datetime.utcnow() - timedelta(days=20)
    c_old = store.create(
        topic="Authentication Token Format",
        content="All auth tokens must use RSA signed JWT tokens. auth_type: jwt",
        tags=["auth", "security", "adr"],
        confidence="high",
        freshness=t_old,
    )

    t_new = datetime.utcnow()
    c_new = store.create(
        topic="Authentication Token Migration to Paseto",
        content=f"Migrating from legacy tokens. Supersedes {c_old.id[:8]}. auth_type: paseto",
        tags=["auth", "security", "adr"],
        confidence="high",
        freshness=t_new,
    )
    db.commit()

    report = engine.detect_contradictions(apply_supersession=True)
    db.commit()

    assert report.superseded_applied >= 1

    # Verify graph relationship exists
    rel = (
        db.query(CapsuleRelationship)
        .filter(
            CapsuleRelationship.from_capsule_id == c_new.id,
            CapsuleRelationship.to_capsule_id == c_old.id,
            CapsuleRelationship.relationship_type == "supersedes",
        )
        .first()
    )
    assert rel is not None

    # Verify older capsule confidence was updated to deprecated
    refreshed_old = store.get(c_old.id)
    assert refreshed_old.confidence == "deprecated"


def test_search_compose_suppresses_superseded(db_session):
    store = CapsuleStore(db_session)
    db = db_session
    search_eng = SearchEngine(db)

    # Older capsule superseded by newer
    c_old = store.create(
        topic="Rate Limiting Policy 1.0",
        content="Rate limit is set to 100 requests per minute per IP.",
        tags=["rate-limit", "security"],
        confidence="deprecated",
    )

    c_new = store.create(
        topic="Rate Limiting Policy 2.0",
        content="Rate limit is raised to 1000 requests per minute with token bucket algorithm.",
        tags=["rate-limit", "security"],
        confidence="high",
    )
    store.link(c_new.id, c_old.id, "supersedes")
    db.commit()

    # Compose without include_superseded (default)
    res_default = search_eng.compose(query="Rate Limiting Policy", include_superseded=False)
    included_ids = [c["id"] for c in res_default["included_capsules"]]
    excluded_ids = [c["id"] for c in res_default["excluded_capsules"]]

    assert c_new.id in included_ids
    assert c_old.id not in included_ids
    assert c_old.id in excluded_ids
    assert "Superseded" in res_default["excluded_capsules"][0]["reason"]

    # Compose with include_superseded=True
    res_included = search_eng.compose(query="Rate Limiting Policy", include_superseded=True)
    inc_ids = [c["id"] for c in res_included["included_capsules"]]
    assert c_new.id in inc_ids
    assert c_old.id in inc_ids


def test_api_supersession_endpoints(db_session):
    store = CapsuleStore(db_session)
    db = db_session

    c1 = store.create(
        topic="Cache Invalidation Rule",
        content="TTL based cache invalidation: max_age: 300",
        tags=["cache"],
        confidence="high",
        freshness=datetime.utcnow() - timedelta(days=2),
    )
    c2 = store.create(
        topic="Cache Invalidation Rule Updated",
        content="Event based cache invalidation: max_age: 0",
        tags=["cache"],
        confidence="high",
        freshness=datetime.utcnow(),
    )
    db.commit()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    # 1. Detect endpoint
    detect_resp = client.post("/api/v1/analysis/supersession/detect", json={"min_confidence": 0.5, "apply_supersession": False})
    assert detect_resp.status_code == 200
    data = detect_resp.json()
    assert data["contradictions_found"] >= 1

    # 2. Resolve endpoint
    resolve_resp = client.post(
        "/api/v1/analysis/supersession/resolve",
        json={"newer_id": c2.id, "older_id": c1.id, "deprecate_older": True},
    )
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["status"] == "resolved"
    assert res_data["relationship"] == "supersedes"

    # Verify older capsule marked deprecated
    refreshed = store.get(c1.id)
    assert refreshed.confidence == "deprecated"
