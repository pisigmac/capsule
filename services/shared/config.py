"""Runtime configuration. Values are read from the environment on access."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


class CapsuleConfig:
    """Application configuration sourced from environment variables."""

    @property
    def database_url(self) -> str:
        raw = os.getenv("CAPSULE_DATABASE_URL", "sqlite:///capsule.db")
        if raw.startswith("postgres://"):
            return "postgresql+psycopg://" + raw[len("postgres://") :]
        if raw.startswith("postgresql://"):
            return "postgresql+psycopg://" + raw[len("postgresql://") :]
        return raw

    @property
    def capsules_dir(self) -> Path:
        return Path(os.getenv("CAPSULES_DIR", "./capsules")).expanduser()

    @property
    def shared_dir(self) -> Path:
        return Path(os.getenv("CAPSULES_SHARED_DIR", str(self.capsules_dir / "shared"))).expanduser()

    @property
    def archived_dir(self) -> Path:
        return Path(
            os.getenv("CAPSULES_ARCHIVED_DIR", str(self.capsules_dir / "archived"))
        ).expanduser()

    @property
    def search_limit(self) -> int:
        return _int("SEARCH_LIMIT", 50)

    @property
    def auto_archive_days(self) -> int:
        return _int("AUTO_ARCHIVE_DAYS", 90)

    @property
    def api_host(self) -> str:
        return os.getenv("API_HOST", "127.0.0.1")

    @property
    def api_port(self) -> int:
        return _int("API_PORT", 9100)

    @property
    def api_token(self) -> str | None:
        token = os.getenv("CAPSULE_API_TOKEN", "").strip()
        return token or None

    @property
    def cors_origins(self) -> List[str]:
        raw = os.getenv("CAPSULE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080")
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def watch_enabled(self) -> bool:
        return _bool("CAPSULE_WATCH", True)

    @property
    def reconcile_on_start(self) -> bool:
        return _bool("CAPSULE_RECONCILE", True)

    @property
    def pool_size(self) -> int:
        return _int("CAPSULE_DB_POOL_SIZE", 5)

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    def ensure_dirs(self) -> None:
        """Create capsule directories if they do not exist."""
        self.capsules_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)
        self.archived_dir.mkdir(parents=True, exist_ok=True)


config = CapsuleConfig()
