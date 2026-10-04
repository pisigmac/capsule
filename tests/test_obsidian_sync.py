"""Unit and integration tests for Obsidian vault sync, WikiLinks, and symlinking (TASK-203)."""
from __future__ import annotations

from pathlib import Path
import pytest
from click.testing import CliRunner

from capsule_cli.main import cli
from services.shared.models import Capsule, CapsuleRelationship
from services.store.store import CapsuleStore
from services.sync.obsidian_adapter import (
    ObsidianAdapter,
    ObsidianVaultSync,
    extract_obsidian_tags,
    extract_wikilinks,
)
from services.sync.symlink_manager import VaultSymlinkManager


class TestObsidianParser:
    def test_extract_wikilinks(self):
        text = """Here is a link to [[Auth Service]].
Also see [[Database Layer|Postgres DB]] and [[Caching#Redis Policy]].
And one with heading and label: [[API Gateway#Rate Limiting|Gateway Limits]].
"""
        links = extract_wikilinks(text)
        assert len(links) == 4

        targets = [l.target for l in links]
        assert "Auth Service" in targets
        assert "Database Layer" in targets
        assert "Caching" in targets
        assert "API Gateway" in targets

        assert links[1].display_text == "Postgres DB"
        assert links[2].heading == "Redis Policy"
        assert links[3].heading == "Rate Limiting"
        assert links[3].display_text == "Gateway Limits"

    def test_extract_obsidian_tags(self):
        text = """
This note covers #security and nested #database/postgres.
#hex code like #ffffff should not be treated as a tag.
```python
# This is a python comment
x = 1
```
End of note with #api/v1.
"""
        tags = extract_obsidian_tags(text)
        assert "security" in tags
        assert "database" in tags
        assert "postgres" in tags
        assert "database-postgres" in tags
        assert "api" in tags
        assert "api-v1" in tags
        assert "ffffff" not in tags
        assert "This" not in tags

    def test_parse_obsidian_note(self, tmp_path):
        note_file = tmp_path / "JWT Auth.md"
        note_file.write_text(
            """---
title: JWT Authentication Flow
tags: [auth, security]
aliases: [jwt_flow]
cssclasses: [custom-note]
---

# JWT Authentication
All requests must supply bearer tokens.
See [[Token Secret Rotation]] for schedule.
Also tagged with #auth/tokens.
"""
        )

        adapter = ObsidianAdapter()
        parsed = adapter.parse_note(note_file, vault_root=tmp_path)

        assert parsed.topic == "JWT Authentication Flow"
        assert "auth" in parsed.tags
        assert "security" in parsed.tags
        assert "tokens" in parsed.tags
        assert len(parsed.wikilinks) == 1
        assert parsed.wikilinks[0].target == "Token Secret Rotation"
        assert parsed.raw_frontmatter.get("aliases") == ["jwt_flow"]
        assert parsed.raw_frontmatter.get("cssclasses") == ["custom-note"]


class TestObsidianVaultSync:
    def test_vault_sync_and_relationships(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        vault = tmp_path / "vault"
        vault.mkdir()

        # Note 1: Links to Note 2 via WikiLink
        (vault / "Auth Bypass.md").write_text(
            """# Staging Auth Bypass
When header is set, staging skips validation.
Refer to [[Postgres Database Pool]] for credentials.
"""
        )

        # Note 2: Target of WikiLink
        (vault / "DB Pool.md").write_text(
            """# Postgres Database Pool
Connection pool is configured for 20 connections max.
"""
        )

        syncer = ObsidianVaultSync(store=store, vault_path=vault)
        result = syncer.sync()

        assert result.scanned_count == 2
        assert result.created_count == 2
        assert result.linked_count >= 1

        # Verify relationship in DB
        rel = db_session.query(CapsuleRelationship).first()
        assert rel is not None
        assert rel.relationship_type == "relates_to"

        source_cap = db_session.query(Capsule).filter(Capsule.id == rel.from_capsule_id).first()
        target_cap = db_session.query(Capsule).filter(Capsule.id == rel.to_capsule_id).first()
        assert "Auth" in source_cap.topic
        assert "Database" in target_cap.topic

    def test_vault_sync_tag_filter(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        vault = tmp_path / "vault"
        vault.mkdir()

        # Tagged note
        (vault / "Agent Note.md").write_text(
            """---
tags: [agent-memory, core]
---
# Agent Knowledge
Agent memory preserved here.
"""
        )

        # Untagged personal journal note
        (vault / "Journal.md").write_text(
            """# Daily Journal
Today was a productive day.
"""
        )

        syncer = ObsidianVaultSync(store=store, vault_path=vault, tag_filter="#agent-memory")
        result = syncer.sync()

        assert result.scanned_count == 1
        assert result.created_count == 1
        assert "Agent" in result.notes[0].topic


class TestVaultSymlinking:
    def test_symlink_vault_link_and_unlink(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        vault = tmp_path / "obsidian_vault"
        vault.mkdir()

        (vault / "Docker Invariant.md").write_text(
            """# Docker Container Sizing
Containers are capped at 512MB memory limit.
"""
        )

        manager = VaultSymlinkManager(capsules_dir=caps_dir)

        # 1. Link vault
        res = manager.link_vault(vault_path=vault, link_name="obsidian")
        assert res.success is True
        assert res.created is True
        assert (caps_dir / "obsidian").is_symlink()

        # 2. Reconcile store over symlink
        store = CapsuleStore(db_session, capsules_dir=caps_dir)
        count = store.reconcile()
        assert count == 1

        cap = db_session.query(Capsule).first()
        assert cap is not None
        assert "Docker Container Sizing" in cap.topic

        # 3. Unlink vault
        unlink_res = manager.unlink_vault(link_name="obsidian")
        assert unlink_res.success is True
        assert not (caps_dir / "obsidian").exists()

        # Underlying vault file is untouched
        assert (vault / "Docker Invariant.md").exists()

        # Reconcile drops orphaned symlinked rows
        count2 = store.reconcile()
        assert count2 == 0
        assert db_session.query(Capsule).count() == 0


class TestObsidianCli:
    def test_link_vault_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["link-vault", "--help"])
        assert result.exit_code == 0
        assert "obsidian" in result.output.lower()

    def test_link_vault_execution(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        vault = tmp_path / "my_vault"
        vault.mkdir()
        (vault / "Note.md").write_text("# Note Title\nNote body content.")

        runner = CliRunner()
        result = runner.invoke(cli, ["link-vault", str(vault), "--dir", str(caps_dir)])
        assert result.exit_code == 0
        assert "successfully linked" in result.output.lower()

        # List active links
        list_res = runner.invoke(cli, ["link-vault", "--dir", str(caps_dir)])
        assert list_res.exit_code == 0
        assert "my_vault" in list_res.output

        # Unlink
        unlink_res = runner.invoke(cli, ["link-vault", "--unlink", "--dir", str(caps_dir)])
        assert unlink_res.exit_code == 0
        assert "successfully unlinked" in unlink_res.output.lower()

    def test_sync_obsidian_cli(self, db_session, tmp_path):
        caps_dir = tmp_path / "capsules"
        caps_dir.mkdir(exist_ok=True)
        vault = tmp_path / "cli_vault"
        vault.mkdir()
        (vault / "Arch.md").write_text("# Arch Note\nArchitecture details.")

        runner = CliRunner()
        # Dry run
        dry_res = runner.invoke(cli, ["sync", "--obsidian", str(vault), "--dry-run"])
        assert dry_res.exit_code == 0
        assert "dry run" in dry_res.output.lower()

        # Live sync
        sync_res = runner.invoke(cli, ["sync", "--obsidian", str(vault)])
        assert sync_res.exit_code == 0
        assert "obsidian sync complete" in sync_res.output.lower()
