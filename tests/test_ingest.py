"""Unit and integration tests for document ingestion and decomposition (TASK-201)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from capsule_cli.main import cli
from services.ingest.ast_splitter import AstDocumentSplitter, is_toc_content
from services.ingest.decomposer import DocumentDecomposer
from services.ingest.llm_splitter import LlmDocumentSplitter
from services.parser.parser import CapsuleParser, ParsedCapsule
from services.shared.models import Capsule
from services.store.store import CapsuleStore


class TestAstSplitter:
    def test_ast_splitter_basic(self):
        splitter = AstDocumentSplitter()
        doc = """# Introduction
Capsule stores one fact per Markdown file. SQLite acts solely as a derived search index.
"""
        units = splitter.split_document(doc, source_name="intro.md")
        assert len(units) == 1
        assert units[0].topic == "Introduction"
        assert "one fact per Markdown file" in units[0].content
        assert "intro" in units[0].tags

    def test_ast_splitter_hierarchy(self):
        splitter = AstDocumentSplitter()
        doc = """# Architecture Overview
The system is divided into storage and search layers.

## Database Layer
We use SQLite for local caching and Postgres for multi-agent synchronization.

### Connection Pool Sizing
The database connection pool is capped at 20 concurrent connections with a 5 second timeout.
"""
        units = splitter.split_document(doc, source_name="architecture.md")
        assert len(units) == 3
        topics = [u.topic for u in units]
        assert "Architecture Overview" in topics
        assert "Database Layer" in topics
        assert "Connection Pool Sizing" in topics

        pool_unit = [u for u in units if "Connection Pool" in u.topic][0]
        assert "architecture" in pool_unit.tags
        assert "database" in pool_unit.tags

    def test_ast_splitter_preserves_code_blocks(self):
        splitter = AstDocumentSplitter()
        doc = """## Code Example
Here is how you initialize the connection pool in python:

```python
# This is a comment inside code, not a markdown heading
def get_pool():
    return ConnectionPool(max_size=20)
```

Ensure you close the pool on shutdown.
"""
        units = splitter.split_document(doc, source_name="code.md")
        assert len(units) == 1
        assert units[0].topic == "Code Example"
        assert "```python" in units[0].content
        assert "# This is a comment inside code" in units[0].content
        assert "def get_pool():" in units[0].content

    def test_ast_splitter_skips_toc_and_empty_sections(self):
        splitter = AstDocumentSplitter()
        doc = """# Documentation

## Table of Contents
- [Setup](#setup)
- [Architecture](#architecture)
- [Configuration](#configuration)

## Setup
Installation requires Python 3.10 or higher. Run `pip install kapsule` to install.

## Empty Section

## Configuration
Configure environment variables using the `.env` file or export `CAPSULES_DIR`.
"""
        units = splitter.split_document(doc, source_name="guide.md")
        topics = [u.topic for u in units]
        assert "Table of Contents" not in topics
        assert "Empty Section" not in topics
        assert "Setup" in topics
        assert "Configuration" in topics

    def test_ast_splitter_frontmatter_tags(self):
        splitter = AstDocumentSplitter()
        doc = """---
title: Security Guide
tags: [security, compliance, audit]
---

# Authentication Protocols
All API requests must carry a valid bearer token in the Authorization header.
"""
        units = splitter.split_document(doc, source_name="sec.md")
        assert len(units) == 1
        assert "security" in units[0].tags
        assert "compliance" in units[0].tags
        assert "audit" in units[0].tags


class TestDocumentDecomposer:
    def test_decomposer_ingest_single_file(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        doc_file = tmp_path / "networking.md"
        doc_file.write_text(
            """# WebSocket Policy
WebSockets automatically attempt reconnection with exponential backoff up to 30 seconds.

## Heartbeat Intervals
Client sends ping every 15 seconds. If server does not respond within 5 seconds, connection terminates.
"""
        )

        decomposer = DocumentDecomposer(store=store, mode="ast", extra_tags=["network"])
        result = decomposer.ingest_path(doc_file)

        assert result.total_files == 1
        assert result.total_units == 2
        assert result.created_count == 2
        assert result.deduped_count == 0

        # Verify on disk
        files = list(caps_dir.glob("*.caps.md"))
        assert len(files) == 2

    def test_decomposer_ingest_directory(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)

        (docs_dir / "auth.md").write_text(
            "# JWT Authentication\nJWT tokens expire after 3600 seconds. Refresh tokens expire after 30 days."
        )
        (docs_dir / "db.md").write_text(
            "# Database Wal Mode\nSQLite uses WAL mode with synchronous=NORMAL for concurrent agent access."
        )

        store = CapsuleStore(db_session, capsules_dir=caps_dir)
        decomposer = DocumentDecomposer(store=store, mode="ast")
        result = decomposer.ingest_path(docs_dir)

        assert result.total_files == 2
        assert result.total_units == 2
        assert result.created_count == 2

    def test_decomposer_deduplication(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        doc_file = tmp_path / "invariants.md"
        doc_file.write_text(
            """# Invariant A
Preconditions must be validated before writing any record to disk.

# Invariant B
All database transactions must commit or roll back explicitly.
"""
        )

        decomposer = DocumentDecomposer(store=store, mode="ast")

        # Pass 1: Fresh ingestion
        res1 = decomposer.ingest_path(doc_file)
        assert res1.created_count == 2
        assert res1.deduped_count == 0
        initial_file_count = len(list(caps_dir.glob("*.caps.md")))
        assert initial_file_count == 2

        # Pass 2: Re-ingesting exact same document
        res2 = decomposer.ingest_path(doc_file)
        assert res2.created_count == 0
        assert res2.deduped_count == 2
        # Zero new files should have been created
        second_file_count = len(list(caps_dir.glob("*.caps.md")))
        assert second_file_count == initial_file_count

    def test_decomposer_dry_run(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        doc_file = tmp_path / "draft.md"
        doc_file.write_text(
            "# Draft Proposal\nThis proposal outlines the upcoming migration to distributed consensus."
        )

        decomposer = DocumentDecomposer(store=store, mode="ast")
        result = decomposer.ingest_path(doc_file, dry_run=True)

        assert result.total_units == 1
        assert result.created_count == 0
        assert result.deduped_count == 0
        assert len(list(caps_dir.glob("*.caps.md"))) == 0
        assert db_session.query(Capsule).count() == 0

    def test_decomposer_real_world_readme(self):
        """Validate that AST decomposition of Capsule's own README produces valid capsules."""
        readme_path = Path(__file__).resolve().parent.parent / "README.md"
        if not readme_path.exists():
            pytest.skip("README.md not found")

        splitter = AstDocumentSplitter()
        units = splitter.split_document(readme_path.read_text(encoding="utf-8"), source_name="README.md")
        assert len(units) >= 3

        parser = CapsuleParser()
        for unit in units:
            md = parser.to_markdown(
                ParsedCapsule(
                    topic=unit.topic,
                    content=unit.content,
                    tags=unit.tags,
                    source=unit.source,
                    confidence=unit.confidence,
                )
            )
            errors = parser.validate(md)
            assert errors == [], f"Validation failed for topic '{unit.topic}': {errors}"


class TestLlmSplitter:
    def test_llm_splitter_fallback(self):
        splitter = LlmDocumentSplitter()
        text = "# Fallback Test\nThis is a fallback test to verify offline degradation."
        with patch.object(splitter, "_extract_with_gemini", side_effect=RuntimeError("API offline")):
            with patch.object(splitter, "_extract_with_openai", side_effect=RuntimeError("API offline")):
                units = splitter.split_document(text, source_name="test.md")
                assert len(units) >= 1
                assert units[0].topic == "Fallback Test"

    def test_llm_splitter_parse_json(self):
        splitter = LlmDocumentSplitter()
        mock_json = """
        [
          {
            "topic": "Postgres Pool",
            "content": "Maximum 20 connections per pool instance.",
            "tags": ["database", "postgres"],
            "confidence": "high"
          }
        ]
        """
        units = splitter._parse_json_response(mock_json, source_name="doc.md", extra_tags=["shared"])
        assert len(units) == 1
        assert units[0].topic == "Postgres Pool"
        assert "database" in units[0].tags
        assert "shared" in units[0].tags


class TestIngestCli:
    def test_ingest_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "decompose" in result.output.lower() or "ingest" in result.output.lower()
        assert "--dry-run" in result.output
        assert "--mode" in result.output

    def test_ingest_dry_run_cli(self, tmp_path):
        doc = tmp_path / "notes.md"
        doc.write_text("# Release Notes\nVersion 0.5.0 introduces the new caps browse TUI and ingest commands.")

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", str(doc), "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()

    def test_ingest_execution_cli(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        doc = tmp_path / "deployment.md"
        doc.write_text("# Deployment Target\nContainer deployments must specify memory limit of 512MB.")

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", str(doc), "--dir", str(caps_dir)])
        assert result.exit_code == 0
        assert "ingestion complete" in result.output.lower()
        assert len(list(caps_dir.glob("*.caps.md"))) == 1

