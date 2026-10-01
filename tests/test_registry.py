"""Unit and integration tests for Capsule Knowledge Packs Registry."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from capsule_cli.main import cli
from services.parser.parser import CapsuleParser
from services.registry.client import (
    PullResult,
    RegistryClient,
    RegistryError,
    ZipSlipError,
)
from services.registry.manifest import PackManifest
from services.registry.publisher import PackPublisher
from services.shared.models import Capsule


class TestBuiltinPacks:
    def test_list_builtin_packs(self):
        client = RegistryClient()
        packs = client.list_packs()
        names = [p.name for p in packs]
        assert "python-best-practices" in names
        assert "fastapi-security" in names
        assert "postgres-performance" in names

    def test_filter_packs_by_query(self):
        client = RegistryClient()
        res = client.list_packs("asyncio")
        assert len(res) >= 1
        assert res[0].name == "python-best-practices"

        sec = client.list_packs("jwt")
        assert len(sec) >= 1
        assert sec[0].name == "fastapi-security"

    def test_builtin_capsules_syntax_validity(self):
        from services.registry.builtins import BUILTIN_PACKS
        parser = CapsuleParser()
        for pack_name, files in BUILTIN_PACKS.items():
            for filename, content in files.items():
                parsed = parser.parse_text(content)
                assert parsed.topic, f"Capsule {filename} in {pack_name} must have a topic"
                assert parsed.tags, f"Capsule {filename} in {pack_name} must have tags"
                assert parsed.confidence in ("high", "medium", "low", "hearsay")


class TestPullWorkflow:
    def test_pull_builtin_pack(self, db_session, tmp_path):
        target = tmp_path / "caps"
        client = RegistryClient()

        result = client.pull("python-best-practices", target_dir=target, db_session=db_session)
        assert result.pack_name == "python-best-practices"
        assert result.total_installed == 5
        assert result.total_skipped == 0
        assert result.reconciled is True

        # Verify files written
        files = list(target.glob("*.caps.md"))
        assert len(files) == 5

        # Verify DB indexed
        count = db_session.query(Capsule).count()
        assert count == 5

    def test_pull_dry_run_does_not_write_files(self, db_session, tmp_path):
        target = tmp_path / "caps"
        client = RegistryClient()

        result = client.pull("fastapi-security", target_dir=target, dry_run=True, db_session=db_session)
        assert result.total_installed == 5
        assert result.dry_run is True

        # Disk should be empty
        assert not target.exists() or len(list(target.glob("*"))) == 0
        assert db_session.query(Capsule).count() == 0

    def test_pull_idempotency_and_force(self, tmp_path):
        target = tmp_path / "caps"
        client = RegistryClient()

        # First pull
        res1 = client.pull("postgres-performance", target_dir=target)
        assert res1.total_installed == 3
        assert res1.total_skipped == 0

        # Second pull without force -> skips
        res2 = client.pull("postgres-performance", target_dir=target, force=False)
        assert res2.total_installed == 0
        assert res2.total_skipped == 3

        # Third pull with force -> overwrites
        res3 = client.pull("postgres-performance", target_dir=target, force=True)
        assert res3.total_installed == 3
        assert res3.total_skipped == 0

    def test_pull_unknown_pack_raises_error(self, tmp_path):
        target = tmp_path / "caps"
        client = RegistryClient()
        with pytest.raises(RegistryError, match="not found in registry"):
            client.pull("non-existent-pack-xyz", target_dir=target)


class TestZipArchivePull:
    def test_pull_from_local_zip_archive(self, tmp_path):
        # Create a sample pack zip
        zip_path = tmp_path / "custom-pack.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            manifest = PackManifest(
                name="custom-pack",
                version="2.0.0",
                description="Custom test pack",
                author="Tester",
                caps_count=1,
                tags=["testing"],
            )
            zf.writestr("manifest.json", manifest.to_json())
            zf.writestr(
                "test-rule.caps.md",
                "---\ntopic: Custom Testing Rule\ntags: [test]\nconfidence: high\n---\n\nAlways write tests.",
            )
        zip_path.write_bytes(buf.getvalue())

        target = tmp_path / "extracted_caps"
        client = RegistryClient()
        res = client.pull(str(zip_path), target_dir=target)

        assert res.total_installed == 1
        assert (target / "test-rule.caps.md").exists()
        assert res.manifest.name == "custom-pack"

    def test_zip_slip_security_prevention(self, tmp_path):
        # Craft a malicious zip entry attempting directory traversal
        malicious_zip = tmp_path / "evil.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../../etc/evil.caps.md", "topic: Pwned\n---\nMalicious content")
        malicious_zip.write_bytes(buf.getvalue())

        target = tmp_path / "safe_dir"
        target.mkdir()
        client = RegistryClient()

        # The unpacker should either sanitize or raise ZipSlipError
        # In our implementation it raises ZipSlipError
        with pytest.raises(ZipSlipError):
            client.pull(str(malicious_zip), target_dir=target)

        assert not (tmp_path / "evil.caps.md").exists()


class TestPackPublisher:
    def test_create_pack(self, tmp_path):
        source_dir = tmp_path / "my_notes"
        source_dir.mkdir()

        (source_dir / "note1.caps.md").write_text(
            "---\ntopic: Rule 1\ntags: [clean-code, python]\nconfidence: high\n---\n\nRule 1 content",
            encoding="utf-8",
        )
        (source_dir / "note2.caps.md").write_text(
            "---\ntopic: Rule 2\ntags: [architecture]\nconfidence: high\n---\n\nRule 2 content",
            encoding="utf-8",
        )

        out_zip = tmp_path / "exported.zip"
        zip_file, manifest = PackPublisher.create_pack(
            source_dir=source_dir,
            name="clean-architecture",
            version="1.2.0",
            description="Clean code principles",
            author="Architect",
            output_path=out_zip,
        )

        assert zip_file.exists()
        assert manifest.name == "clean-architecture"
        assert manifest.caps_count == 2
        assert "clean-code" in manifest.tags
        assert "python" in manifest.tags
        assert "architecture" in manifest.tags
        assert manifest.sha256 is not None

        # Verify zip contents
        with zipfile.ZipFile(zip_file, "r") as zf:
            assert "manifest.json" in zf.namelist()
            assert "note1.caps.md" in zf.namelist()
            assert "note2.caps.md" in zf.namelist()
            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest_data["author"] == "Architect"


class TestCliCommands:
    def test_pull_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["pull", "--help"])
        assert result.exit_code == 0
        assert "Pull a verified knowledge pack" in result.output

    def test_pack_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["pack", "--help"])
        assert result.exit_code == 0
        assert "Manage and discover Capsule Knowledge Packs" in result.output

    def test_registry_alias_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["registry", "--help"])
        assert result.exit_code == 0
        assert "Manage and discover Capsule Knowledge Packs" in result.output

    def test_pack_list_cli(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["pack", "list"])
        assert result.exit_code == 0
        assert "Capsule Knowledge Packs Registry" in result.output
        assert "python-best-practices" in result.output
        assert "fastapi-security" in result.output

    def test_pull_cli_dry_run(self, db_session, tmp_path):
        runner = CliRunner()
        target = tmp_path / "caps_cli"
        result = runner.invoke(cli, ["pull", "fastapi-security", "--dir", str(target), "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Installed: 5" in result.output

    def test_pull_cli_execution(self, db_session, tmp_path):
        runner = CliRunner()
        target = tmp_path / "caps_cli_exec"
        result = runner.invoke(cli, ["pull", "python-best-practices", "--dir", str(target)])
        assert result.exit_code == 0
        assert "Successfully merged 5 capsules" in result.output
        assert len(list(target.glob("*.caps.md"))) == 5

    def test_pack_create_cli(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        (source / "rule.caps.md").write_text(
            "---\ntopic: My CLI Rule\ntags: [cli]\nconfidence: high\n---\n\nRule details",
            encoding="utf-8",
        )
        out_zip = tmp_path / "my_pack.zip"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "pack", "create", str(source),
            "--name", "my-pack",
            "--author", "Developer",
            "--desc", "Pack created via CLI",
            "--output", str(out_zip),
        ])
        assert result.exit_code == 0
        assert "Created Knowledge Pack" in result.output
        assert out_zip.exists()
