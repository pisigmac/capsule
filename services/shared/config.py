"""Configuration management for Capsule."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class CapsuleConfig:
    """Application configuration."""

    # Database
    database_url: str = field(default_factory=lambda: os.getenv(
        "CAPSULE_DATABASE_URL", 
        "sqlite:///capsule.db"
    ))

    # Paths
    capsules_dir: Path = field(default_factory=lambda: Path(
        os.getenv("CAPSULES_DIR", "./capsules")
    ))
    shared_dir: Path = field(default_factory=lambda: Path(
        os.getenv("CAPSULES_SHARED_DIR", "./capsules/shared")
    ))
    archived_dir: Path = field(default_factory=lambda: Path(
        os.getenv("CAPSULES_ARCHIVED_DIR", "./capsules/archived")
    ))

    # Search
    search_limit: int = field(default_factory=lambda: int(os.getenv("SEARCH_LIMIT", "50")))

    # Sync
    sync_interval: int = field(default_factory=lambda: int(os.getenv("SYNC_INTERVAL", "30")))
    auto_archive_days: int = field(default_factory=lambda: int(os.getenv("AUTO_ARCHIVE_DAYS", "90")))

    # API
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "9000")))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_dirs(self) -> None:
        """Ensure all capsule directories exist."""
        self.capsules_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)
        self.archived_dir.mkdir(parents=True, exist_ok=True)


# Global config instance
config = CapsuleConfig()
