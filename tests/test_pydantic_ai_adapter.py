"""Unit and integration tests for PydanticAI and LiteLLM prompt context injector adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from kapsule.adapters.pydantic_ai import (
    DEFAULT_FOOTER,
    DEFAULT_HEADER,
    async_inject_capsule_context,
    capsule_context_hook,
    inject_capsule_context,
)
from services.adapters.pydantic_ai import (
    DEFAULT_FOOTER as S_FOOTER,
    DEFAULT_HEADER as S_HEADER,
    async_inject_capsule_context as s_async_inject,
    capsule_context_hook as s_hook,
    inject_capsule_context as s_inject,
)
from services.store.store import CapsuleStore


@pytest.fixture
def populated_vault(db_session, tmp_path):
    """Seed sample capsules for context injection."""
    caps_dir = tmp_path / "caps_pydantic"
    caps_dir.mkdir(parents=True, exist_ok=True)

    note1 = """---
id: 11111111-1111-1111-1111-111111111111
topic: Production Zero-Downtime Migration Rule
tags: [database, migration, production]
confidence: high
---

Always use the expand and contract pattern when renaming columns or altering tables.
"""
    note2 = """---
id: 22222222-2222-2222-2222-222222222222
topic: Staging JWT Bypass Policy
tags: [auth, security, staging]
confidence: medium
---

Only enable X-Debug-Override bypass header in the staging environment.
"""
    (caps_dir / "migration.caps.md").write_text(note1, encoding="utf-8")
    (caps_dir / "auth.caps.md").write_text(note2, encoding="utf-8")

    store = CapsuleStore(db_session, capsules_dir=caps_dir)
    store.reconcile()
    return caps_dir


class TestInjectCapsuleContext:
    def test_inject_returns_formatted_context(self, db_session, populated_vault):
        ctx = inject_capsule_context(
            query="migration",
            db_session=db_session,
        )
        assert DEFAULT_HEADER in ctx
        assert DEFAULT_FOOTER in ctx
        assert "Production Zero-Downtime Migration Rule" in ctx
        assert "expand and contract pattern" in ctx

    def test_inject_returns_empty_when_no_match(self, db_session, populated_vault):
        ctx = inject_capsule_context(
            query="nonexistent_quantum_hyperdrive_protocol_xyz",
            db_session=db_session,
        )
        assert ctx == ""

    def test_inject_confidence_filter(self, db_session, populated_vault):
        # Only high confidence should be returned
        ctx_high = inject_capsule_context(
            query="staging",
            confidence_min="high",
            db_session=db_session,
        )
        # Note2 is medium confidence, so high-only should not return it
        assert "Staging JWT Bypass Policy" not in ctx_high

        # Medium confidence includes note2
        ctx_med = inject_capsule_context(
            query="staging",
            confidence_min="medium",
            db_session=db_session,
        )
        assert "Staging JWT Bypass Policy" in ctx_med

    def test_inject_tags_filter(self, db_session, populated_vault):
        ctx = inject_capsule_context(
            tags=["database"],
            db_session=db_session,
        )
        assert "Production Zero-Downtime Migration Rule" in ctx
        assert "Staging JWT Bypass Policy" not in ctx

    def test_inject_custom_header_footer(self, db_session, populated_vault):
        custom_header = "=== ARCHITECTURAL CONSTRAINTS ==="
        custom_footer = "=== END CONSTRAINTS ==="
        ctx = inject_capsule_context(
            query="migration",
            header=custom_header,
            footer=custom_footer,
            db_session=db_session,
        )
        assert custom_header in ctx
        assert custom_footer in ctx
        assert DEFAULT_HEADER not in ctx

    def test_inject_respects_token_budget(self, db_session, populated_vault):
        ctx = inject_capsule_context(
            query="migration",
            max_tokens=200,
            db_session=db_session,
        )
        assert len(ctx) > 0
        assert "Production Zero-Downtime Migration Rule" in ctx

        # When token budget is zero or too small to fit any capsule
        ctx_tiny = inject_capsule_context(
            query="migration",
            max_tokens=5,
            db_session=db_session,
        )
        assert ctx_tiny == ""


class TestAsyncInjectCapsuleContext:
    @pytest.mark.asyncio
    async def test_async_inject(self, db_session, populated_vault):
        ctx = await async_inject_capsule_context(
            query="migration",
            db_session=db_session,
        )
        assert "Production Zero-Downtime Migration Rule" in ctx


class TestCapsuleContextHook:
    def test_hook_with_object_context(self, db_session, populated_vault):
        @dataclass
        class MockRunContext:
            user_prompt: str

        hook = capsule_context_hook(db_session=db_session)
        ctx_obj = MockRunContext(user_prompt="How do we handle database migrations?")

        result = hook(ctx_obj)
        assert "Production Zero-Downtime Migration Rule" in result

    def test_hook_with_dict_context(self, db_session, populated_vault):
        hook = capsule_context_hook(db_session=db_session)
        result = hook({"prompt": "Tell me about staging JWT bypass"})
        assert "Staging JWT Bypass Policy" in result

    def test_hook_with_custom_query_extractor(self, db_session, populated_vault):
        hook = capsule_context_hook(
            query_extractor=lambda ctx: ctx.get("message_body"),
            db_session=db_session,
        )
        result = hook({"message_body": "migration table altering"})
        assert "Production Zero-Downtime Migration Rule" in result


class TestAdapterExportParity:
    def test_aliases_match(self):
        assert inject_capsule_context is s_inject
        assert async_inject_capsule_context is s_async_inject
        assert capsule_context_hook is s_hook
        assert DEFAULT_HEADER == S_HEADER
        assert DEFAULT_FOOTER == S_FOOTER
