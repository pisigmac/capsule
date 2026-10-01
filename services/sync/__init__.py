"""Sync and vault integration package for Capsule."""
from __future__ import annotations

from .obsidian_adapter import (
    ObsidianAdapter,
    ObsidianSyncResult,
    ObsidianVaultSync,
    ParsedObsidianNote,
    WikiLink,
    extract_obsidian_tags,
    extract_wikilinks,
)
from .symlink_manager import SymlinkResult, VaultSymlinkManager
from .watcher import CapsuleEventHandler, CapsuleSyncService

__all__ = [
    "CapsuleEventHandler",
    "CapsuleSyncService",
    "ObsidianAdapter",
    "ObsidianSyncResult",
    "ObsidianVaultSync",
    "ParsedObsidianNote",
    "SymlinkResult",
    "VaultSymlinkManager",
    "WikiLink",
    "extract_obsidian_tags",
    "extract_wikilinks",
]
