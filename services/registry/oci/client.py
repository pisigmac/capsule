"""OCI Registry HTTP Distribution API v2 Client."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from services.parser.parser import CapsuleParser
from services.registry.oci.auth import OCIAuthManager
from services.registry.oci.manifest import (
    CAPSULE_CONFIG_MEDIA_TYPE,
    CAPSULE_LAYER_MEDIA_TYPE,
    OCI_MANIFEST_MEDIA_TYPE,
    CapsuleOCIConfig,
    build_oci_manifest,
)
from services.registry.oci.packager import OCIPackager, TarSlipError
from services.registry.oci.reference import OCIReference, parse_oci_reference
from services.store.store import CapsuleStore


class OCIClientError(Exception):
    """Raised when an OCI registry operation fails."""
    pass


@dataclass
class OCIPushResult:
    reference: OCIReference
    manifest_digest: str
    manifest_size: int
    layer_digest: str
    layer_size: int
    caps_count: int


@dataclass
class OCIPullResult:
    reference: OCIReference
    manifest_digest: str
    installed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    config: Optional[Dict[str, Any]] = None
    target_dir: Optional[Path] = None
    dry_run: bool = False
    reconciled: bool = False

    @property
    def total_installed(self) -> int:
        return len(self.installed)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped)


class OCIClient:
    """Client for pushing, pulling, and inspecting Capsule OCI memory artifacts."""

    def __init__(
        self,
        auth_manager: Optional[OCIAuthManager] = None,
        timeout: float = 30.0,
        insecure: bool = False,
    ):
        self.auth_manager = auth_manager or OCIAuthManager()
        self.timeout = timeout
        self.insecure = insecure

    def _get_base_url(self, registry: str) -> str:
        scheme = "http" if self.insecure or registry.startswith("localhost") or registry.startswith("127.0.0.1") else "https"
        return f"{scheme}://{registry}"

    def _request(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        ref: OCIReference,
        scope_action: str = "pull",
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> httpx.Response:
        """Execute HTTP request with automated Bearer token challenge negotiation."""
        req_headers = dict(headers or {})
        req_headers.setdefault("User-Agent", "Capsule-OCI-Client/0.5.0")

        # Initial attempt
        resp = client.request(method, url, headers=req_headers, **kwargs)
        if resp.status_code == 401:
            challenge = resp.headers.get("Www-Authenticate")
            if challenge:
                scope = f"repository:{ref.repository}:{scope_action}"
                auth_val = self.auth_manager.handle_auth_challenge(
                    registry=ref.registry,
                    challenge_header=challenge,
                    scope=scope,
                )
                if auth_val:
                    req_headers["Authorization"] = auth_val
                    resp = client.request(method, url, headers=req_headers, **kwargs)
        return resp

    def push(
        self,
        source_dir: Path,
        reference: str | OCIReference,
        author: str = "Community",
        description: str = "",
    ) -> OCIPushResult:
        """Package a directory of capsules and push to an OCI registry."""
        ref = parse_oci_reference(reference) if isinstance(reference, str) else reference
        source_dir = Path(source_dir).resolve()

        # 1. Package layer tarball
        layer_bytes, layer_digest, layer_size = OCIPackager.pack_layer(source_dir)

        # 2. Extract tags & capsule count for config
        tags_set = set()
        parser = CapsuleParser()
        caps_count = 0
        for root, _, files in os.walk(source_dir):
            for f in files:
                if f.endswith(".caps.md") or f.endswith(".capsule.md") or f.endswith(".md"):
                    caps_count += 1
                    try:
                        content = (Path(root) / f).read_text(encoding="utf-8")
                        parsed = parser.parse_text(content)
                        tags_set.update(parsed.tags)
                    except Exception:
                        pass

        # 3. Build config & manifest
        config_obj = CapsuleOCIConfig(
            author=author,
            description=description,
            caps_count=caps_count,
            tags=sorted(list(tags_set)),
        )
        config_bytes, config_digest, config_size = config_obj.to_bytes()

        manifest_dict, manifest_bytes, manifest_digest, manifest_size = build_oci_manifest(
            config_digest=config_digest,
            config_size=config_size,
            layer_digest=layer_digest,
            layer_size=layer_size,
            author=author,
            description=description,
        )

        base_url = self._get_base_url(ref.registry)

        with httpx.Client(timeout=self.timeout) as client:
            # 4. Upload layer blob if not present
            self._upload_blob(client, base_url, ref, layer_bytes, layer_digest)

            # 5. Upload config blob if not present
            self._upload_blob(client, base_url, ref, config_bytes, config_digest)

            # 6. Put manifest
            manifest_tag = ref.identifier
            manifest_url = f"{base_url}/v2/{ref.repository}/manifests/{manifest_tag}"
            headers = {
                "Content-Type": OCI_MANIFEST_MEDIA_TYPE,
            }
            resp = self._request(
                client,
                "PUT",
                manifest_url,
                ref=ref,
                scope_action="pull,push",
                headers=headers,
                content=manifest_bytes,
            )
            if resp.status_code not in (200, 201, 202):
                raise OCIClientError(
                    f"Failed to push manifest to {ref.full_name} (status {resp.status_code}): {resp.text}"
                )

        return OCIPushResult(
            reference=ref,
            manifest_digest=manifest_digest,
            manifest_size=manifest_size,
            layer_digest=layer_digest,
            layer_size=layer_size,
            caps_count=caps_count,
        )

    def _upload_blob(
        self,
        client: httpx.Client,
        base_url: str,
        ref: OCIReference,
        data: bytes,
        digest: str,
    ) -> None:
        """Check if blob exists and upload via monolithic or chunked upload."""
        # 1. Check existence with HEAD
        head_url = f"{base_url}/v2/{ref.repository}/blobs/{digest}"
        resp = self._request(client, "HEAD", head_url, ref=ref, scope_action="pull,push")
        if resp.status_code == 200:
            return  # Already exists on registry

        # 2. Initiate upload
        init_url = f"{base_url}/v2/{ref.repository}/blobs/uploads/"
        resp = self._request(client, "POST", init_url, ref=ref, scope_action="pull,push")
        if resp.status_code not in (200, 202):
            raise OCIClientError(
                f"Failed to initiate blob upload on {ref.registry}/{ref.repository} (status {resp.status_code}): {resp.text}"
            )

        location = resp.headers.get("Location")
        if not location:
            raise OCIClientError("Registry did not return Location header for blob upload")

        # Resolve relative location header if needed
        if location.startswith("/"):
            upload_url = f"{base_url}{location}"
        elif not location.startswith("http"):
            upload_url = f"{base_url}/v2/{ref.repository}/blobs/uploads/{location}"
        else:
            upload_url = location

        sep = "&" if "?" in upload_url else "?"
        final_url = f"{upload_url}{sep}digest={digest}"

        # 3. Monolithic PUT upload
        headers = {"Content-Type": "application/octet-stream"}
        resp = self._request(
            client,
            "PUT",
            final_url,
            ref=ref,
            scope_action="pull,push",
            headers=headers,
            content=data,
        )
        if resp.status_code not in (200, 201, 202):
            raise OCIClientError(
                f"Failed to upload blob {digest} (status {resp.status_code}): {resp.text}"
            )

    def pull(
        self,
        reference: str | OCIReference,
        target_dir: Path,
        dry_run: bool = False,
        force: bool = False,
        db_session: Any = None,
    ) -> OCIPullResult:
        """Pull an OCI memory artifact, verify SHA-256 digest, and extract into target_dir."""
        ref = parse_oci_reference(reference) if isinstance(reference, str) else reference
        target_dir = Path(target_dir).resolve()
        base_url = self._get_base_url(ref.registry)

        with httpx.Client(timeout=self.timeout) as client:
            # 1. Fetch manifest
            manifest_tag = ref.identifier
            manifest_url = f"{base_url}/v2/{ref.repository}/manifests/{manifest_tag}"
            headers = {
                "Accept": f"{OCI_MANIFEST_MEDIA_TYPE}, application/vnd.docker.distribution.manifest.v2+json",
            }
            resp = self._request(
                client,
                "GET",
                manifest_url,
                ref=ref,
                scope_action="pull",
                headers=headers,
            )
            if resp.status_code != 200:
                raise OCIClientError(
                    f"Failed to fetch manifest for {ref.full_name} (status {resp.status_code}): {resp.text}"
                )

            manifest_raw = resp.content
            manifest_digest = f"sha256:{hashlib.sha256(manifest_raw).hexdigest()}"
            manifest_data = resp.json()

            layers = manifest_data.get("layers", [])
            if not layers:
                raise OCIClientError(f"No layers found in OCI manifest for {ref.full_name}")

            layer_desc = layers[0]
            layer_digest = layer_desc.get("digest")
            if not layer_digest:
                raise OCIClientError("Layer descriptor missing digest in manifest")

            # 2. Download layer blob
            blob_url = f"{base_url}/v2/{ref.repository}/blobs/{layer_digest}"
            resp_blob = self._request(
                client,
                "GET",
                blob_url,
                ref=ref,
                scope_action="pull",
            )
            if resp_blob.status_code != 200:
                raise OCIClientError(
                    f"Failed to download layer blob {layer_digest} (status {resp_blob.status_code}): {resp_blob.text}"
                )

            layer_bytes = resp_blob.content

            # 3. Verify digest
            actual_digest = f"sha256:{hashlib.sha256(layer_bytes).hexdigest()}"
            if actual_digest != layer_digest:
                raise OCIClientError(
                    f"Cryptographic integrity error: layer digest mismatch. Expected {layer_digest}, got {actual_digest}"
                )

            # 4. Extract
            if dry_run:
                # Preview member names
                installed = []
                import io, tarfile
                with tarfile.open(fileobj=io.BytesIO(layer_bytes), mode="r:gz") as tar:
                    for m in tar.getmembers():
                        if not m.isdir() and not m.name.startswith("."):
                            installed.append(Path(m.name).name)
                skipped = []
            else:
                installed, skipped = OCIPackager.unpack_layer(layer_bytes, target_dir, force=force)

        reconciled = False
        if db_session and not dry_run and installed:
            store = CapsuleStore(db_session, capsules_dir=target_dir)
            store.reconcile()
            reconciled = True

        config_data = manifest_data.get("annotations", {})
        return OCIPullResult(
            reference=ref,
            manifest_digest=manifest_digest,
            installed=installed,
            skipped=skipped,
            config=config_data,
            target_dir=target_dir,
            dry_run=dry_run,
            reconciled=reconciled,
        )

    def inspect(self, reference: str | OCIReference) -> Dict[str, Any]:
        """Fetch remote artifact manifest metadata without downloading layer."""
        ref = parse_oci_reference(reference) if isinstance(reference, str) else reference
        base_url = self._get_base_url(ref.registry)

        with httpx.Client(timeout=self.timeout) as client:
            manifest_tag = ref.identifier
            manifest_url = f"{base_url}/v2/{ref.repository}/manifests/{manifest_tag}"
            headers = {
                "Accept": f"{OCI_MANIFEST_MEDIA_TYPE}, application/vnd.docker.distribution.manifest.v2+json",
            }
            resp = self._request(
                client,
                "GET",
                manifest_url,
                ref=ref,
                scope_action="pull",
                headers=headers,
            )
            if resp.status_code != 200:
                raise OCIClientError(
                    f"Failed to inspect manifest for {ref.full_name} (status {resp.status_code}): {resp.text}"
                )

            manifest = resp.json()
            config_digest = manifest.get("config", {}).get("digest")

            config_details: Dict[str, Any] = {}
            if config_digest:
                config_url = f"{base_url}/v2/{ref.repository}/blobs/{config_digest}"
                resp_cfg = self._request(client, "GET", config_url, ref=ref, scope_action="pull")
                if resp_cfg.status_code == 200:
                    try:
                        config_details = resp_cfg.json()
                    except Exception:
                        pass

            return {
                "reference": str(ref),
                "mediaType": manifest.get("mediaType"),
                "schemaVersion": manifest.get("schemaVersion"),
                "digest": f"sha256:{hashlib.sha256(resp.content).hexdigest()}",
                "layers": manifest.get("layers", []),
                "annotations": manifest.get("annotations", {}),
                "config": config_details,
            }
