"""Unit and integration tests for LlamaIndex adapters."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from llama_index.core.schema import Document, NodeWithScore, QueryBundle, TextNode

from kapsule.adapters.llamaindex import (
    CapsuleNodeParser,
    CapsuleReader,
    CapsuleRetriever,
)
from services.adapters.llamaindex import (
    CapsuleNodeParser as ServiceParser,
    CapsuleReader as ServiceReader,
    CapsuleRetriever as ServiceRetriever,
)
from services.store.store import CapsuleStore


@pytest.fixture
def populated_vault(db_session, tmp_path):
    """Seed sample capsules for adapter retrieval."""
    caps_dir = tmp_path / "caps_llamaindex"
    caps_dir.mkdir(parents=True, exist_ok=True)

    note1 = """---
id: 11111111-1111-1111-1111-111111111111
topic: Auth bypass in staging
tags: [auth, security, staging]
confidence: high
source: ops_playbook
---

Staging environment allows bypassing JWT when X-Debug-Override is passed.
"""
    note2 = """---
id: 22222222-2222-2222-2222-222222222222
topic: PostgreSQL connection pool limits
tags: [database, postgres, performance]
confidence: high
source: dba_guide
---

Set PgBouncer pool size to 2x CPU cores plus spindle count.
"""
    (caps_dir / "auth.caps.md").write_text(note1, encoding="utf-8")
    (caps_dir / "db.caps.md").write_text(note2, encoding="utf-8")

    store = CapsuleStore(db_session, capsules_dir=caps_dir)
    store.reconcile()
    return caps_dir


class TestCapsuleRetriever:
    def test_retriever_initialization_defaults(self):
        retriever = CapsuleRetriever()
        assert retriever.limit == 5
        assert retriever.mode == "hybrid"
        assert retriever.tags == []
        assert retriever.confidence_min is None

    def test_retriever_query_returns_nodes(self, db_session, populated_vault):
        retriever = CapsuleRetriever(db_session=db_session, limit=2)
        nodes = retriever.retrieve("auth")

        assert len(nodes) >= 1
        node_with_score = nodes[0]
        assert isinstance(node_with_score, NodeWithScore)
        assert isinstance(node_with_score.node, TextNode)
        assert "JWT" in node_with_score.node.text or "Staging" in node_with_score.node.text
        assert node_with_score.node.metadata["topic"] == "Auth bypass in staging"
        assert "auth" in node_with_score.node.metadata["tags"]
        assert node_with_score.node.metadata["confidence"] == "high"
        assert node_with_score.score >= 0.0

    def test_retriever_query_with_query_bundle(self, db_session, populated_vault):
        retriever = CapsuleRetriever(db_session=db_session, limit=2)
        bundle = QueryBundle(query_str="auth bypass")
        nodes = retriever._retrieve(bundle)

        assert len(nodes) >= 1
        assert "auth" in nodes[0].node.metadata["tags"]

    def test_retriever_tag_filtering(self, db_session, populated_vault):
        retriever = CapsuleRetriever(db_session=db_session, tags=["database"])
        nodes = retriever.retrieve("pool")

        assert len(nodes) == 1
        assert "PgBouncer" in nodes[0].node.text
        assert nodes[0].node.metadata["topic"] == "PostgreSQL connection pool limits"

    @pytest.mark.asyncio
    async def test_retriever_async_retrieve(self, db_session, populated_vault):
        retriever = CapsuleRetriever(db_session=db_session)
        nodes = await retriever.aretrieve("PostgreSQL")
        assert len(nodes) >= 1
        assert "PgBouncer" in nodes[0].node.text


class TestCapsuleReader:
    def test_load_data_from_folder(self, populated_vault):
        reader = CapsuleReader()
        docs = reader.load_data(folder_path=populated_vault)

        assert len(docs) == 2
        topics = {d.metadata.get("topic") for d in docs}
        assert "Auth bypass in staging" in topics
        assert "PostgreSQL connection pool limits" in topics

        # Verify Document structure
        for d in docs:
            assert isinstance(d, Document)
            assert d.doc_id is not None
            assert len(d.text) > 0
            assert "confidence" in d.metadata
            assert "source" in d.metadata

    def test_load_data_from_files(self, populated_vault):
        reader = CapsuleReader()
        auth_file = populated_vault / "auth.caps.md"
        docs = reader.load_data(file_paths=[auth_file])

        assert len(docs) == 1
        doc = docs[0]
        assert doc.metadata["topic"] == "Auth bypass in staging"
        assert "auth" in doc.metadata["tags"]
        assert doc.metadata["source"] == "ops_playbook"

    def test_lazy_load_data(self, populated_vault):
        reader = CapsuleReader()
        iterator = reader.lazy_load_data(folder_path=populated_vault)
        docs = list(iterator)
        assert len(docs) == 2


class TestCapsuleNodeParser:
    def test_parse_documents_into_nodes(self):
        parser = CapsuleNodeParser()
        doc1 = Document(
            text="""---
id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
topic: Architecture Principles
tags: [arch, clean-code]
confidence: high
---

Follow boundary isolation between domains.
""",
            metadata={"source": "book", "file_path": "/docs/arch.md"},
        )
        doc2 = Document(
            text="""# Database Migrations

Use zero-downtime expand/contract pattern for table schemas.
""",
            metadata={"source": "wiki", "file_path": "/docs/db.md"},
        )

        nodes = parser.get_nodes_from_documents([doc1, doc2])
        assert len(nodes) == 2

        # Check doc1 parsed node
        n1 = nodes[0]
        assert isinstance(n1, TextNode)
        assert n1.id_ == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        assert n1.metadata["topic"] == "Architecture Principles"
        assert "arch" in n1.metadata["tags"]
        assert n1.metadata["confidence"] == "high"
        assert "Follow boundary isolation" in n1.text

        # Check doc2 parsed node
        n2 = nodes[1]
        assert isinstance(n2, TextNode)
        assert n2.metadata["topic"] == "Database Migrations"
        assert "expand/contract" in n2.text

        # Check node relationships
        from llama_index.core.schema import NodeRelationship

        assert n1.relationships[NodeRelationship.NEXT].node_id == n2.node_id
        assert n2.relationships[NodeRelationship.PREVIOUS].node_id == n1.node_id


class TestModuleAliases:
    def test_alias_parity(self):
        assert CapsuleRetriever is ServiceRetriever
        assert CapsuleReader is ServiceReader
        assert CapsuleNodeParser is ServiceParser

    def test_import_error_message(self):
        """Verify helpful ImportError when llama-index-core is not present."""
        with patch.dict(sys.modules, {"llama_index.core.base.base_retriever": None}):
            with pytest.raises(ImportError) as exc_info:
                import importlib

                import services.adapters.llamaindex.retriever

                importlib.reload(services.adapters.llamaindex.retriever)
            assert "pip install kapsule[llamaindex]" in str(exc_info.value)
