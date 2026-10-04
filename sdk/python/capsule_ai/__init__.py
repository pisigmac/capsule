"""Thin Python client for the Capsule HTTP API."""

from capsule_ai.client import KapsuleClient, KapsuleError

__version__ = "0.1.0"

__all__ = ["KapsuleClient", "KapsuleError", "__version__"]
