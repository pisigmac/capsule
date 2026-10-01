"""Unit and integration tests for LangChain & LangGraph adapters."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from kapsule.adapters.langchain import (
    CapsuleChatMessageHistory,
    CapsuleMemory,
    CapsuleRetriever,
)
from services.adapters.langchain import (
    CapsuleChatMessageHistory as ServiceHistory,
    CapsuleMemory as ServiceMemory,
    CapsuleRetriever as ServiceRetriever,
)
from services.parser.parser import CapsuleParser
from services.store.store import CapsuleStore


@pytest.fixture
def populated_vault(db_session, tmp_path):
    """Seed sample capsules for adapter retrieval."""
    caps_dir = tmp_path / "caps_langchain"
    caps_dir.mkdir(parents=True, exist_ok=True)

    note1 = """---
id: 11111111-1111-1111-1111-111111111111
topic: Auth bypass in staging
tags: [auth, security, staging]
confidence: high
---

Staging environment allows bypassing JWT when X-Debug-Override is passed.
"""
    note2 = """---
id: 22222222-2222-2222-2222-222222222222
topic: PostgreSQL connection pool limits
tags: [database, postgres, performance]
confidence: high
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
        assert retriever.search_mode == "hybrid"
        assert retriever.tags == []
        assert retriever.confidence_min is None

    def test_retriever_query_returns_documents(self, db_session, populated_vault):
        retriever = CapsuleRetriever(db_session=db_session, limit=2)
        docs = retriever.invoke("auth")

        assert len(docs) >= 1
        doc = docs[0]
        assert isinstance(doc, Document)
        assert "JWT" in doc.page_content or "Staging" in doc.page_content
        assert doc.metadata["topic"] == "Auth bypass in staging"
        assert "auth" in doc.metadata["tags"]
        assert doc.metadata["confidence"] == "high"

    def test_retriever_tag_filtering(self, db_session, populated_vault):
        retriever = CapsuleRetriever(db_session=db_session, tags=["database"])
        docs = retriever.invoke("pool")

        assert len(docs) == 1
        assert "PgBouncer" in docs[0].page_content
        assert docs[0].metadata["topic"] == "PostgreSQL connection pool limits"

    @pytest.mark.asyncio
    async def test_retriever_async_invoke(self, db_session, populated_vault):
        retriever = CapsuleRetriever(db_session=db_session)
        docs = await retriever.ainvoke("PostgreSQL")
        assert len(docs) >= 1
        assert "PgBouncer" in docs[0].page_content


class TestCapsuleMemory:
    def test_memory_variables(self):
        memory = CapsuleMemory()
        assert memory.memory_variables == ["history"]

        custom = CapsuleMemory(memory_key="context_window")
        assert custom.memory_variables == ["context_window"]

    def test_memory_load_variables(self, db_session, populated_vault):
        memory = CapsuleMemory(db_session=db_session, tags=["auth"], max_tokens=1000)
        variables = memory.load_memory_variables({"input": "auth staging"})

        assert "history" in variables
        context = variables["history"]
        assert "Auth bypass in staging" in context
        assert "X-Debug-Override" in context

    def test_memory_custom_input_key(self, db_session, populated_vault):
        memory = CapsuleMemory(
            db_session=db_session,
            memory_key="agent_memory",
            input_key="user_query",
        )
        variables = memory.load_memory_variables({"user_query": "PostgreSQL connection"})

        assert "agent_memory" in variables
        assert "PgBouncer" in variables["agent_memory"]

    def test_memory_save_and_clear_noops(self):
        memory = CapsuleMemory()
        # save_context and clear are safe no-ops
        memory.save_context({"input": "foo"}, {"output": "bar"})
        memory.clear()


class TestCapsuleChatMessageHistory:
    def test_chat_message_history(self):
        history = CapsuleChatMessageHistory(session_id="agent-run-123")
        assert history.messages == []

        history.add_user_message("What is our auth policy?")
        history.add_ai_message("We bypass in staging with X-Debug-Override.")

        assert len(history.messages) == 2
        assert isinstance(history.messages[0], HumanMessage)
        assert isinstance(history.messages[1], AIMessage)
        assert history.messages[0].content == "What is our auth policy?"

        history.clear()
        assert history.messages == []


class TestPackageAliases:
    def test_kapsule_and_services_adapters_identical(self):
        assert CapsuleRetriever is ServiceRetriever
        assert CapsuleMemory is ServiceMemory
        assert CapsuleChatMessageHistory is ServiceHistory


class TestLcelChainIntegration:
    def test_lcel_retriever_in_pipeline(self, db_session, populated_vault):
        from langchain_core.prompts import PromptTemplate
        from langchain_core.runnables import RunnablePassthrough

        prompt = PromptTemplate.from_template("Found:\n{context}\n\nTask: {question}")
        retriever = CapsuleRetriever(db_session=db_session, limit=2)

        def format_docs(docs):
            return "\n".join(d.page_content for d in docs)

        chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
        )
        output = chain.invoke("staging")
        assert "Found:" in output.text
        assert "X-Debug-Override" in output.text
        assert "Task: staging" in output.text


class TestMissingLangchainCoreError:
    def test_graceful_import_error_message(self):
        with patch.dict(sys.modules, {"langchain_core": None, "langchain_core.retrievers": None}):
            with pytest.raises(ImportError, match="The LangChain adapter requires 'langchain-core'"):
                # Force reloading the module under patched environment
                import importlib
                import services.adapters.langchain.retriever as ret_mod
                importlib.reload(ret_mod)
