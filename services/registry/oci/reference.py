"""OCI Container Reference parser and validator."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OCIReference:
    """Represents a parsed OCI container image / artifact reference."""

    registry: str
    repository: str
    tag: Optional[str] = None
    digest: Optional[str] = None

    @property
    def identifier(self) -> str:
        """Return the tag or digest identifier used in manifest requests."""
        if self.digest:
            return self.digest
        return self.tag or "latest"

    @property
    def is_digest(self) -> bool:
        return self.digest is not None

    @property
    def full_name(self) -> str:
        base = f"{self.registry}/{self.repository}"
        if self.digest:
            return f"{base}@{self.digest}"
        return f"{base}:{self.tag or 'latest'}"

    def __str__(self) -> str:
        return self.full_name


def is_oci_reference(ref_str: str) -> bool:
    """Check if string looks like an OCI container reference (e.g. contains '/' or registry domain)."""
    clean = ref_str.strip()
    # If it contains a slash or an explicit tag / digest with standard naming
    if "/" in clean:
        return True
    if clean.startswith("localhost:") or "." in clean.split("/")[0]:
        return True
    return False


def parse_oci_reference(ref_str: str, default_registry: str = "ghcr.io") -> OCIReference:
    """Parse reference string into an OCIReference object.

    Supported formats:
    - ghcr.io/org/repo:tag
    - ghcr.io/org/repo@sha256:<hash>
    - docker.io/org/repo:tag
    - localhost:5000/my-pack:1.0
    - org/repo:tag  (defaults to default_registry)
    - repo:tag      (defaults to default_registry/library/repo)
    """
    clean = ref_str.strip()
    if not clean:
        raise ValueError("OCI reference string cannot be empty")

    digest: Optional[str] = None
    tag: Optional[str] = None

    # Check for digest first: @sha256:...
    if "@" in clean:
        parts = clean.split("@", 1)
        clean_base = parts[0]
        digest = parts[1]
    elif ":" in clean.split("/")[-1]:
        # Tag exists in the last segment
        last_slash_idx = clean.rfind("/")
        if last_slash_idx != -1:
            prefix = clean[:last_slash_idx]
            last_part = clean[last_slash_idx + 1:]
        else:
            prefix = ""
            last_part = clean

        repo_part, tag_part = last_part.split(":", 1)
        tag = tag_part
        clean_base = f"{prefix}/{repo_part}" if prefix else repo_part
    else:
        clean_base = clean
        tag = "latest"

    # Now parse registry and repository
    segments = clean_base.split("/")

    # Detect if first segment is a registry domain or IP:port
    first = segments[0]
    if len(segments) > 1 and ("." in first or ":" in first or first == "localhost"):
        registry = first
        repository = "/".join(segments[1:])
    else:
        registry = default_registry
        repository = "/".join(segments)

    # Normalize docker.io
    if registry == "docker.io":
        registry = "registry-1.docker.io"
        if len(repository.split("/")) == 1:
            repository = f"library/{repository}"

    return OCIReference(
        registry=registry,
        repository=repository,
        tag=tag if not digest else None,
        digest=digest,
    )
