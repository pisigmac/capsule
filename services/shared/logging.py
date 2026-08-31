"""Process-wide logging setup."""
from __future__ import annotations

import logging
import sys

_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        logging.getLogger().setLevel(getattr(logging, level, logging.INFO))
        return

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    _configured = True
