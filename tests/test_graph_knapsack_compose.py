from click.testing import CliRunner
import pytest
from fastapi.testclient import TestClient

from capsule_cli.main import cli
from services.api.main import app
from services.search.engine import SearchEngine
from services.store.store import CapsuleStore


def test_graph_aware_knapsack_composition(db_session):
    store = CapsuleStore(db_session)

    # Create root architectural capsule matching query
    root = store.create(
        topic="Authentication Architecture",
        content="Primary OAuth2 and JWT authentication workflow for all microservices.",
        tags=["auth", "architecture"],
        confidence="high",
    )

    # Create prerequisite linked via depends_on with NO query keyword matches
    dep = store.create(
        topic="Cryptographic Token Signing Key",
        content="Secret asymmetric RSA keys rotated every 30 days via vault HSM.",
        tags=["crypto", "security"],
        confidence="high",
    )

    # Create unrelated capsule that has some generic words
    unrelated = store.create(
        topic="Database Connection Pooling",
        content="PostgreSQL pgBouncer max client connections configured to 500.",
        tags=["database", "infrastructure"],
        confidence="medium",
    )

    # Link root -> dep via depends_on
    store.link(root.id, dep.id, "depends_on")
    db_session.commit()

    engine = SearchEngine(db_session)

    # 1. Search with graph_expansion=True
    res_graph = engine.compose(
        query="OAuth2 authentication workflow",
        graph_expansion=True,
        max_tokens=4000,
    )

    topics_included = [c["topic"] for c in res_graph["included_capsules"]]
    assert "Authentication Architecture" in topics_included
    # Prerequisite 'Cryptographic Token Signing Key' was pulled in via graph expansion!
    assert "Cryptographic Token Signing Key" in topics_included

    # Check graph metadata on pulled-in node
    dep_node = next(c for c in res_graph["included_capsules"] if c["topic"] == "Cryptographic Token Signing Key")
    assert dep_node.get("via_graph_edge") == "depends_on"
    assert dep_node.get("connected_to") == "Authentication Architecture"

    # 2. Search with graph_expansion=False
    res_no_graph = engine.compose(
        query="OAuth2 authentication workflow",
        graph_expansion=False,
        max_tokens=4000,
    )
    topics_no_graph = [c["topic"] for c in res_no_graph["included_capsules"]]
    assert "Authentication Architecture" in topics_no_graph
    assert "Cryptographic Token Signing Key" not in topics_no_graph


def test_graph_composition_token_budget_respect(db_session):
    store = CapsuleStore(db_session)

    root = store.create(
        topic="Payment Gateway",
        content="Stripe and PayPal integration layer for processing customer transactions.",
        confidence="high",
    )

    huge_dep = store.create(
        topic="PCI Compliance Invariant",
        content=("Strict credit card isolation requirement " * 300).strip(),
        confidence="high",
    )

    store.link(root.id, huge_dep.id, "implements")
    db_session.commit()

    engine = SearchEngine(db_session)
    # Strict 100 token limit
    result = engine.compose(query="Payment Gateway", max_tokens=100, graph_expansion=True)

    assert result["truncated"] is True
    assert len(result["included_capsules"]) == 1
    assert result["included_capsules"][0]["topic"] == "Payment Gateway"
    assert any(c["topic"] == "PCI Compliance Invariant" for c in result["excluded_capsules"])


def test_cli_compose_graph_flag(db_session, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(cli, ["compose", "--query", "OAuth2", "--graph", "--max-tokens", "2000"])
    assert result.exit_code == 0


def test_api_compose_graph_expansion(db_session):
    client = TestClient(app)
    response = client.post(
        "/api/v1/compose",
        json={
            "query": "authentication",
            "graph_expansion": True,
            "max_tokens": 2000,
            "mode": "fts",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "context" in data
    assert "token_estimate" in data
    assert "included_capsules" in data
    assert data["graph_expansion"] is True
