"""Tests for Live Event Streaming Subscriptions (E3)."""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.shared.models import get_db
from services.store.store import CapsuleStore
from services.sync.event_bus import EventBus, vault_event_bus


def test_event_bus_publish_subscribe():
    bus = EventBus()
    q = bus.subscribe()
    assert len(bus._subscribers) == 1

    bus.publish("capsule_created", {"id": "123", "topic": "Test Capsule"})
    item = q.get_nowait()
    assert item["event"] == "capsule_created"
    assert item["data"]["topic"] == "Test Capsule"

    bus.unsubscribe(q)
    assert len(bus._subscribers) == 0


@pytest.mark.asyncio
async def test_event_bus_generator():
    bus = EventBus()
    gen = bus.event_generator()

    # Read initial heartbeat
    init_chunk = await anext(gen)
    assert "event: connect" in init_chunk

    # Publish an event and verify generator receives it
    bus.publish("capsule_updated", {"id": "456", "topic": "Updated Topic"})
    event_chunk = await anext(gen)
    assert "event: capsule_updated" in event_chunk
    assert "Updated Topic" in event_chunk

    await gen.aclose()
    assert len(bus._subscribers) == 0


def test_api_mutation_publishes_to_event_bus(db_session):
    store = CapsuleStore(db_session)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session

    q = vault_event_bus.subscribe()
    client = TestClient(app)

    try:
        resp = client.post(
            "/api/v1/capsules",
            json={
                "topic": "Streaming Test Invariant",
                "content": "Testing event broadcast to SSE subscribers on capsule mutation.",
                "tags": ["stream", "test"],
                "confidence": "high",
            },
        )
        assert resp.status_code == 201

        # Check that event was put into queue
        event = q.get_nowait()
        assert event["event"] == "capsule_created"
        assert event["data"]["topic"] == "Streaming Test Invariant"
    finally:
        vault_event_bus.unsubscribe(q)
