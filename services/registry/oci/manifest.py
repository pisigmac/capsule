"""OCI Image Manifest and Capsule Config schema builder."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
CAPSULE_CONFIG_MEDIA_TYPE = "application/vnd.capsule.config.v1+json"
CAPSULE_LAYER_MEDIA_TYPE = "application/vnd.capsule.vault.layer.v1+tar+gzip"


@dataclass
class CapsuleOCIConfig:
    """Capsule metadata stored as the OCI config blob."""

    schema_version: int = 1
    author: str = "Community"
    description: str = ""
    caps_count: int = 0
    tags: List[str] = field(default_factory=list)
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_bytes(self) -> Tuple[bytes, str, int]:
        raw = json.dumps(self.to_dict(), sort_keys=True, indent=2).encode("utf-8")
        digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        return raw, digest, len(raw)


def build_oci_manifest(
    config_digest: str,
    config_size: int,
    layer_digest: str,
    layer_size: int,
    author: str = "Community",
    description: str = "",
) -> Tuple[Dict[str, Any], bytes, str, int]:
    """Construct an OCI Image Manifest v1.1.0 dictionary and raw bytes with digest."""
    now_iso = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schemaVersion": 2,
        "mediaType": OCI_MANIFEST_MEDIA_TYPE,
        "config": {
            "mediaType": CAPSULE_CONFIG_MEDIA_TYPE,
            "digest": config_digest,
            "size": config_size,
        },
        "layers": [
            {
                "mediaType": CAPSULE_LAYER_MEDIA_TYPE,
                "digest": layer_digest,
                "size": layer_size,
                "annotations": {
                    "org.opencontainers.image.title": "capsules.tar.gz",
                },
            }
        ],
        "annotations": {
            "org.opencontainers.image.created": now_iso,
            "org.opencontainers.image.authors": author,
            "org.opencontainers.image.description": description,
        },
    }

    raw = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    return manifest, raw, digest, len(raw)
