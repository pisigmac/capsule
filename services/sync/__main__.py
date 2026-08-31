"""Run the filesystem watcher as its own process against the shared database."""
from __future__ import annotations

import logging
import time

from ..shared.config import config
from ..shared.logging import setup_logging
from ..shared.models import init_db, reset_engine
from .watcher import CapsuleSyncService

logger = logging.getLogger("capsule.sync")


def main() -> None:
    setup_logging(config.log_level)
    config.ensure_dirs()
    reset_engine()
    init_db()
    service = CapsuleSyncService(watch_dirs=[str(config.capsules_dir)])
    count = service.initial_sync()
    logger.info("Initial sync indexed %s capsule file(s)", count)
    service.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher")
    finally:
        service.stop()


if __name__ == "__main__":
    main()
