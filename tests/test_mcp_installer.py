"""Unit and integration tests for caps mcp install."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from capsule_cli.installer.mcp_installer import (
    McpInstaller,
    McpTarget,
    detect_installed_clients,
    resolve_caps_command,
)
from capsule_cli.main import cli


@pytest.fixture
def mock_clients_dir(tmp_path):
    """Creates mock config environments for Claude, Cursor, and Windsurf."""
    claude_dir = tmp_path / "Claude"
    claude_dir.mkdir(parents=True)
    claude_config = claude_dir / "claude_desktop_config.json"

    cursor_dir = tmp_path / "Cursor"
    cursor_dir.mkdir(parents=True)
    cursor_config = cursor_dir / "mcp.json"

    windsurf_dir = tmp_path / "Windsurf"
    windsurf_dir.mkdir(parents=True)
    windsurf_config = windsurf_dir / "mcp_config.json"

    return {
        "claude": claude_config,
        "cursor": cursor_config,
        "windsurf": windsurf_config,
    }


class TestMcpTargetDetection:
    def test_detect_installed_clients(self, mock_clients_dir):
        targets = [
            McpTarget(name="Claude Desktop", config_path=mock_clients_dir["claude"]),
            McpTarget(name="Cursor", config_path=mock_clients_dir["cursor"]),
            McpTarget(name="Windsurf", config_path=mock_clients_dir["windsurf"]),
            McpTarget(name="MissingApp", config_path=Path("/nonexistent/path/config.json")),
        ]
        detected = detect_installed_clients(targets)
        names = [d.name for d in detected]
        assert "Claude Desktop" in names
        assert "Cursor" in names
        assert "Windsurf" in names
        assert "MissingApp" not in names


class TestMcpInstaller:
    def test_resolve_caps_command(self):
        cmd, args = resolve_caps_command()
        assert isinstance(cmd, str)
        assert len(cmd) > 0
        assert "mcp" in args

    def test_install_new_config_file(self, mock_clients_dir, tmp_path):
        target = McpTarget(name="Claude Desktop", config_path=mock_clients_dir["claude"])
        caps_dir = tmp_path / "caps"
        installer = McpInstaller()

        result = installer.install_target(target, capsules_dir=caps_dir, dry_run=False)
        assert result.success is True
        assert target.config_path.exists()

        data = json.loads(target.config_path.read_text(encoding="utf-8"))
        assert "mcpServers" in data
        assert "capsule" in data["mcpServers"]
        server_entry = data["mcpServers"]["capsule"]
        assert "command" in server_entry
        assert "args" in server_entry
        assert server_entry["args"] == ["mcp"]
        assert server_entry["env"]["CAPSULES_DIR"] == str(caps_dir.resolve())

    def test_install_preserves_existing_servers_and_creates_backup(self, mock_clients_dir, tmp_path):
        config_path = mock_clients_dir["claude"]
        initial_data = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                }
            }
        }
        config_path.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

        target = McpTarget(name="Claude Desktop", config_path=config_path)
        caps_dir = tmp_path / "caps"
        installer = McpInstaller()

        result = installer.install_target(target, capsules_dir=caps_dir, dry_run=False)
        assert result.success is True

        # Check backup created
        backups = list(config_path.parent.glob("claude_desktop_config.json.bak.*"))
        assert len(backups) == 1

        # Check merged data
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert "github" in data["mcpServers"]
        assert "capsule" in data["mcpServers"]
        assert data["mcpServers"]["github"]["command"] == "npx"

    def test_install_idempotency(self, mock_clients_dir, tmp_path):
        target = McpTarget(name="Cursor", config_path=mock_clients_dir["cursor"])
        caps_dir = tmp_path / "caps"
        installer = McpInstaller()

        installer.install_target(target, capsules_dir=caps_dir, dry_run=False)
        first_content = target.config_path.read_text(encoding="utf-8")

        installer.install_target(target, capsules_dir=caps_dir, dry_run=False)
        second_content = target.config_path.read_text(encoding="utf-8")

        assert first_content == second_content

    def test_install_dry_run_does_not_modify_disk(self, mock_clients_dir, tmp_path):
        target = McpTarget(name="Windsurf", config_path=mock_clients_dir["windsurf"])
        caps_dir = tmp_path / "caps"
        installer = McpInstaller()

        result = installer.install_target(target, capsules_dir=caps_dir, dry_run=True)
        assert result.success is True
        assert not target.config_path.exists()
        assert result.diff is not None
        assert "mcpServers" in result.diff

    def test_remove_capsule_server(self, mock_clients_dir, tmp_path):
        config_path = mock_clients_dir["claude"]
        initial_data = {
            "mcpServers": {
                "github": {"command": "npx"},
                "capsule": {"command": "caps", "args": ["mcp"]},
            }
        }
        config_path.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")
        target = McpTarget(name="Claude Desktop", config_path=config_path)

        installer = McpInstaller()
        result = installer.remove_target(target, dry_run=False)
        assert result.success is True

        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert "github" in data["mcpServers"]
        assert "capsule" not in data["mcpServers"]


class TestMcpCliCommands:
    def test_mcp_help_shows_install_subcommand(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "install" in result.output

    def test_mcp_install_dry_run_cli(self, mock_clients_dir):
        runner = CliRunner()
        mock_targets = [McpTarget(name="Claude Desktop", config_path=mock_clients_dir["claude"])]
        with patch("capsule_cli.installer.targets.get_system_targets", return_value=mock_targets):
            result = runner.invoke(cli, ["mcp", "install", "--claude", "--dry-run"])
            assert result.exit_code == 0
            assert "DRY RUN" in result.output or "dry-run" in result.output.lower() or "mcpServers" in result.output
