"""Cross-filesystem symlink management for linking Obsidian vaults to Capsule."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from services.shared.config import config

logger = logging.getLogger(__name__)


@dataclass
class SymlinkResult:
    """Result of a vault symlinking or unlinking operation."""

    success: bool
    link_path: Path
    target_path: Optional[Path] = None
    created: bool = False
    message: str = ""


class VaultSymlinkManager:
    """Manages directory symlinks between external markdown vaults and Capsule."""

    def __init__(self, capsules_dir: Optional[Path | str] = None) -> None:
        self.capsules_dir = Path(capsules_dir).resolve() if capsules_dir else config.capsules_dir.resolve()

    def link_vault(
        self,
        vault_path: Path | str,
        link_name: str = "obsidian",
    ) -> SymlinkResult:
        """Create a symlink pointing to an external vault directory inside capsules_dir."""
        target = Path(vault_path).resolve()
        if not target.exists() or not target.is_dir():
            return SymlinkResult(
                success=False,
                link_path=self.capsules_dir / link_name,
                target_path=target,
                message=f"Vault path does not exist or is not a directory: {target}",
            )

        self.capsules_dir.mkdir(parents=True, exist_ok=True)
        link_path = self.capsules_dir / link_name

        # Check existing link or directory
        if link_path.is_symlink():
            current_target = link_path.resolve()
            if current_target == target:
                return SymlinkResult(
                    success=True,
                    link_path=link_path,
                    target_path=target,
                    created=False,
                    message=f"Vault already linked to {link_path}",
                )
            # Remove stale symlink
            link_path.unlink()
        elif link_path.exists():
            return SymlinkResult(
                success=False,
                link_path=link_path,
                target_path=target,
                message=f"Path {link_path} already exists and is not a symlink. Please rename or remove it.",
            )

        try:
            link_path.symlink_to(target, target_is_directory=True)
            return SymlinkResult(
                success=True,
                link_path=link_path,
                target_path=target,
                created=True,
                message=f"Successfully linked vault {target} -> {link_path}",
            )
        except OSError as exc:
            return SymlinkResult(
                success=False,
                link_path=link_path,
                target_path=target,
                message=f"Failed to create symlink: {exc}",
            )

    def unlink_vault(self, link_name: str = "obsidian") -> SymlinkResult:
        """Remove a vault symlink without touching the underlying vault notes."""
        link_path = self.capsules_dir / link_name
        if not link_path.is_symlink():
            if not link_path.exists():
                return SymlinkResult(
                    success=True,
                    link_path=link_path,
                    message=f"No active vault link named '{link_name}' found.",
                )
            return SymlinkResult(
                success=False,
                link_path=link_path,
                message=f"Path {link_path} is an actual directory, not a symlink. Refusing to delete.",
            )

        try:
            target = link_path.resolve()
            link_path.unlink()
            return SymlinkResult(
                success=True,
                link_path=link_path,
                target_path=target,
                message=f"Successfully unlinked vault '{link_name}' from {link_path}",
            )
        except OSError as exc:
            return SymlinkResult(
                success=False,
                link_path=link_path,
                message=f"Failed to unlink {link_path}: {exc}",
            )

    def get_linked_vaults(self) -> List[Tuple[str, Path, Path]]:
        """Return all active symlinked vault directories under capsules_dir."""
        if not self.capsules_dir.exists():
            return []

        linked: List[Tuple[str, Path, Path]] = []
        for item in sorted(self.capsules_dir.iterdir()):
            if item.is_symlink():
                try:
                    resolved = item.resolve()
                    if resolved.is_dir():
                        linked.append((item.name, item, resolved))
                except OSError:
                    pass

        return linked
