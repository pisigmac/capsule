"""Installer engine for injecting Capsule MCP definitions into client configs."""
from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.shared.config import config
from .targets import McpTarget


@dataclass
class InstallResult:
    target: McpTarget
    success: bool
    message: str = ""
    diff: Optional[str] = None
    backup_path: Optional[Path] = None


def resolve_caps_command() -> Tuple[str, List[str]]:
    """Resolve the optimal executable command and arguments for Capsule MCP."""
    binary = shutil.which("caps") or shutil.which("capsule")
    if binary:
        return str(Path(binary).resolve()), ["mcp"]
    return sys.executable, ["-m", "capsule_cli.main", "mcp"]


def detect_installed_clients(targets: List[McpTarget]) -> List[McpTarget]:
    """Filter list to only clients that are detected on the local filesystem."""
    return [t for t in targets if t.is_installed]


class McpInstaller:
    """Manages reading, merging, backing up, and writing client MCP configurations."""

    def __init__(self, command: Optional[str] = None, args: Optional[List[str]] = None) -> None:
        cmd, default_args = resolve_caps_command()
        self.command = command or cmd
        self.args = args or default_args

    def build_server_payload(self, capsules_dir: Optional[Path] = None) -> Dict[str, Any]:
        target_dir = Path(capsules_dir or config.capsules_dir).resolve()
        return {
            "command": self.command,
            "args": self.args,
            "env": {
                "CAPSULES_DIR": str(target_dir),
            },
        }

    def install_target(
        self,
        target: McpTarget,
        capsules_dir: Optional[Path] = None,
        server_name: str = "capsule",
        dry_run: bool = False,
    ) -> InstallResult:
        config_path = target.config_path
        payload = self.build_server_payload(capsules_dir)

        data: Dict[str, Any] = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception as exc:
                return InstallResult(
                    target=target,
                    success=False,
                    message=f"Failed to parse existing JSON: {exc}",
                )

        if not isinstance(data, dict):
            data = {}

        servers = data.setdefault(target.root_key, {})
        if not isinstance(servers, dict):
            servers = {}
            data[target.root_key] = servers

        servers[server_name] = payload
        formatted = json.dumps(data, indent=2) + "\n"

        if dry_run:
            return InstallResult(
                target=target,
                success=True,
                message="Dry-run preview generated",
                diff=formatted,
            )

        backup_file: Optional[Path] = None
        if config_path.exists():
            timestamp = int(time.time())
            backup_file = config_path.with_name(f"{config_path.name}.bak.{timestamp}")
            shutil.copy2(config_path, backup_file)

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(formatted, encoding="utf-8")

        return InstallResult(
            target=target,
            success=True,
            message=f"Successfully configured {target.name}",
            backup_path=backup_file,
        )

    def remove_target(
        self,
        target: McpTarget,
        server_name: str = "capsule",
        dry_run: bool = False,
    ) -> InstallResult:
        config_path = target.config_path
        if not config_path.exists():
            return InstallResult(
                target=target,
                success=True,
                message=f"No configuration file found for {target.name}",
            )

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return InstallResult(
                target=target,
                success=False,
                message=f"Failed to parse JSON: {exc}",
            )

        servers = data.get(target.root_key, {})
        if not isinstance(servers, dict) or server_name not in servers:
            return InstallResult(
                target=target,
                success=True,
                message=f"{server_name} not present in {target.name}",
            )

        del servers[server_name]
        formatted = json.dumps(data, indent=2) + "\n"

        if dry_run:
            return InstallResult(
                target=target,
                success=True,
                message="Dry-run removal preview",
                diff=formatted,
            )

        timestamp = int(time.time())
        backup_file = config_path.with_name(f"{config_path.name}.bak.{timestamp}")
        shutil.copy2(config_path, backup_file)
        config_path.write_text(formatted, encoding="utf-8")

        return InstallResult(
            target=target,
            success=True,
            message=f"Removed {server_name} from {target.name}",
            backup_path=backup_file,
        )
