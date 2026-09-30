"""Client for discovering, downloading, and safely installing Capsule Knowledge Packs."""
from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.registry.builtins import BUILTIN_MANIFESTS, BUILTIN_PACKS
from services.registry.manifest import PackManifest
from services.store.store import CapsuleStore


class RegistryError(Exception):
    """Raised when knowledge pack lookup or download fails."""
    pass


class ZipSlipError(Exception):
    """Raised when an archive attempts directory traversal."""
    pass


@dataclass
class PulledCapsuleInfo:
    filename: str
    topic: str
    tags: List[str]
    confidence: str


@dataclass
class PullResult:
    pack_name: str
    installed: List[PulledCapsuleInfo] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    manifest: Optional[PackManifest] = None
    target_dir: Optional[Path] = None
    dry_run: bool = False
    reconciled: bool = False

    @property
    def total_installed(self) -> int:
        return len(self.installed)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped)


class RegistryClient:
    """Client for pulling and searching Capsule Knowledge Packs."""

    DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/pisigmac/capsule-hub/main/registry.json"

    def __init__(self, registry_url: Optional[str] = None):
        self.registry_url = registry_url or os.getenv("CAPSULE_REGISTRY_URL", self.DEFAULT_REGISTRY_URL)

    def list_packs(self, query: Optional[str] = None) -> List[PackManifest]:
        """List available packs from builtins and remote registry."""
        packs: Dict[str, PackManifest] = dict(BUILTIN_MANIFESTS)

        # Attempt to load remote registry manifest index if configured and accessible
        remote_packs = self._fetch_remote_registry()
        for p in remote_packs:
            if p.name not in packs:
                packs[p.name] = p

        results = list(packs.values())
        if not query:
            return results

        q = query.strip().lower()
        matched = []
        for p in results:
            if (
                q in p.name.lower()
                or q in p.description.lower()
                or q in p.author.lower()
                or any(q in t.lower() for t in p.tags)
            ):
                matched.append(p)
        return matched

    def get_manifest(self, pack_name: str) -> Optional[PackManifest]:
        """Fetch manifest for a given pack name."""
        if pack_name in BUILTIN_MANIFESTS:
            return BUILTIN_MANIFESTS[pack_name]

        all_packs = self.list_packs()
        for p in all_packs:
            if p.name == pack_name:
                return p
        return None

    def pull(
        self,
        pack_identifier: str,
        target_dir: Path,
        dry_run: bool = False,
        force: bool = False,
        db_session: Any = None,
    ) -> PullResult:
        """Download and install a knowledge pack into target_dir.

        Parameters
        ----------
        pack_identifier : str
            Pack name (e.g. 'python-best-practices'), local zip path, or http(s) URL.
        target_dir : Path
            The capsules directory (e.g. ./caps or ./capsules).
        dry_run : bool
            If True, preview files without writing to disk.
        force : bool
            If True, overwrite existing files.
        db_session : Optional SQLAlchemy session
            If provided, triggers immediate CapsuleStore.reconcile() upon installation.
        """
        target_dir = Path(target_dir).resolve()

        # 1. Built-in pack resolution
        if pack_identifier in BUILTIN_PACKS:
            manifest = BUILTIN_MANIFESTS.get(pack_identifier)
            pack_files = BUILTIN_PACKS[pack_identifier]
            return self._install_dict_pack(
                pack_name=pack_identifier,
                pack_files=pack_files,
                manifest=manifest,
                target_dir=target_dir,
                dry_run=dry_run,
                force=force,
                db_session=db_session,
            )

        # 2. Local zip file path
        local_path = Path(pack_identifier)
        if local_path.is_file() and (pack_identifier.endswith(".zip") or pack_identifier.endswith(".capsulepack")):
            with open(local_path, "rb") as f:
                data = f.read()
            return self._install_zip_archive(
                archive_bytes=data,
                source_label=local_path.name,
                target_dir=target_dir,
                dry_run=dry_run,
                force=force,
                db_session=db_session,
            )

        # 3. Remote URL or Registry Pack Name
        manifest = self.get_manifest(pack_identifier)
        if manifest and manifest.url:
            data = self._download_url(manifest.url)
            if manifest.sha256:
                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash.lower() != manifest.sha256.lower():
                    raise RegistryError(
                        f"Checksum mismatch for pack '{pack_identifier}': "
                        f"expected {manifest.sha256}, got {actual_hash}"
                    )
            return self._install_zip_archive(
                archive_bytes=data,
                source_label=manifest.name,
                manifest=manifest,
                target_dir=target_dir,
                dry_run=dry_run,
                force=force,
                db_session=db_session,
            )

        # 4. If identifier looks like a full URL
        if pack_identifier.startswith("http://") or pack_identifier.startswith("https://"):
            data = self._download_url(pack_identifier)
            return self._install_zip_archive(
                archive_bytes=data,
                source_label=pack_identifier.split("/")[-1] or "remote-pack",
                target_dir=target_dir,
                dry_run=dry_run,
                force=force,
                db_session=db_session,
            )

        # 5. OCI Container Registry Reference (e.g. ghcr.io/org/repo:1.0)
        from services.registry.oci import OCIClient, is_oci_reference
        if is_oci_reference(pack_identifier):
            oci_client = OCIClient()
            oci_res = oci_client.pull(
                reference=pack_identifier,
                target_dir=target_dir,
                dry_run=dry_run,
                force=force,
                db_session=db_session,
            )
            installed_infos = []
            for fname in oci_res.installed:
                file_p = target_dir / fname
                if file_p.is_file():
                    content = file_p.read_text(encoding="utf-8")
                    installed_infos.append(self._parse_capsule_info(fname, content))
                else:
                    installed_infos.append(PulledCapsuleInfo(filename=fname, topic=fname, tags=[], confidence="medium"))

            return PullResult(
                pack_name=str(oci_res.reference),
                installed=installed_infos,
                skipped=oci_res.skipped,
                manifest=PackManifest(
                    name=str(oci_res.reference),
                    version=oci_res.reference.tag or "latest",
                    author=(oci_res.config or {}).get("org.opencontainers.image.authors", "OCI Registry"),
                    description=(oci_res.config or {}).get("org.opencontainers.image.description", ""),
                    caps_count=len(installed_infos),
                ),
                target_dir=target_dir,
                dry_run=dry_run,
                reconciled=oci_res.reconciled,
            )

        available = list(BUILTIN_MANIFESTS.keys())
        raise RegistryError(
            f"Knowledge pack '{pack_identifier}' not found in registry. "
            f"Available built-in packs: {', '.join(available)}"
        )

    def _install_dict_pack(
        self,
        pack_name: str,
        pack_files: Dict[str, str],
        manifest: Optional[PackManifest],
        target_dir: Path,
        dry_run: bool,
        force: bool,
        db_session: Any,
    ) -> PullResult:
        """Install a dictionary of in-memory files."""
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        installed: List[PulledCapsuleInfo] = []
        skipped: List[str] = []

        for filename, content in pack_files.items():
            dest_file = target_dir / filename
            if dest_file.exists() and not force:
                skipped.append(filename)
                continue

            # Parse metadata preview
            info = self._parse_capsule_info(filename, content)
            installed.append(info)

            if not dry_run:
                dest_file.write_text(content, encoding="utf-8")

        reconciled = False
        if db_session and not dry_run and installed:
            store = CapsuleStore(db_session, capsules_dir=target_dir)
            store.reconcile()
            reconciled = True

        return PullResult(
            pack_name=pack_name,
            installed=installed,
            skipped=skipped,
            manifest=manifest,
            target_dir=target_dir,
            dry_run=dry_run,
            reconciled=reconciled,
        )

    def _install_zip_archive(
        self,
        archive_bytes: bytes,
        source_label: str,
        target_dir: Path,
        dry_run: bool,
        force: bool,
        db_session: Any,
        manifest: Optional[PackManifest] = None,
    ) -> PullResult:
        """Safely extract zip archive with Zip Slip path-traversal prevention."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile as e:
            raise RegistryError(f"Invalid pack archive: {e}") from e

        # Read manifest from zip if present
        if not manifest and "manifest.json" in zf.namelist():
            try:
                manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                manifest = PackManifest.from_dict(manifest_data)
            except Exception:
                pass

        pack_name = manifest.name if manifest else source_label

        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        installed: List[PulledCapsuleInfo] = []
        skipped: List[str] = []

        resolved_target_root = target_dir.resolve()

        for member in zf.infolist():
            # Skip directories and manifest.json
            if member.is_dir() or member.filename == "manifest.json" or member.filename.startswith("__MACOSX"):
                continue

            # Only accept markdown capsules
            if not (member.filename.endswith(".caps.md") or member.filename.endswith(".capsule.md") or member.filename.endswith(".md")):
                continue

            # ZIP SLIP DEFENSE: Validate archive member does not escape target directory
            member_path = Path(member.filename)
            if ".." in member_path.parts or member.filename.startswith("/") or member.filename.startswith("\\"):
                raise ZipSlipError(
                    f"Security violation: Archive member '{member.filename}' attempts path traversal!"
                )

            dest_file = (target_dir / member_path.name).resolve()
            if not str(dest_file).startswith(str(resolved_target_root)):
                raise ZipSlipError(
                    f"Security violation: Archive member '{member.filename}' attempts path traversal outside target directory!"
                )

            extracted_filename = member_path.name
            if dest_file.exists() and not force:
                skipped.append(extracted_filename)
                continue

            content = zf.read(member).decode("utf-8")
            info = self._parse_capsule_info(extracted_filename, content)
            installed.append(info)

            if not dry_run:
                dest_file.write_text(content, encoding="utf-8")

        reconciled = False
        if db_session and not dry_run and installed:
            store = CapsuleStore(db_session, capsules_dir=target_dir)
            store.reconcile()
            reconciled = True

        return PullResult(
            pack_name=pack_name,
            installed=installed,
            skipped=skipped,
            manifest=manifest,
            target_dir=target_dir,
            dry_run=dry_run,
            reconciled=reconciled,
        )

    def _parse_capsule_info(self, filename: str, content: str) -> PulledCapsuleInfo:
        """Extract topic and tags quickly from capsule frontmatter or body."""
        from services.parser.parser import CapsuleParser
        try:
            parser = CapsuleParser()
            parsed = parser.parse_text(content)
            return PulledCapsuleInfo(
                filename=filename,
                topic=parsed.topic,
                tags=parsed.tags,
                confidence=parsed.confidence,
            )
        except Exception:
            return PulledCapsuleInfo(
                filename=filename,
                topic=filename,
                tags=[],
                confidence="medium",
            )

    def _fetch_remote_registry(self) -> List[PackManifest]:
        """Fetch remote registry manifest index. Returns empty on failure."""
        if not self.registry_url:
            return []
        try:
            req = urllib.request.Request(
                self.registry_url,
                headers={"User-Agent": "Capsule-Registry-Client/0.5.0"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return [PackManifest.from_dict(item) for item in data]
                elif isinstance(data, dict) and "packs" in data:
                    return [PackManifest.from_dict(item) for item in data["packs"]]
        except Exception:
            pass
        return []

    def _download_url(self, url: str) -> bytes:
        """Download raw archive bytes from remote URL."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Capsule-Registry-Client/0.5.0"},
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return resp.read()
        except Exception as e:
            raise RegistryError(f"Failed to download knowledge pack from '{url}': {e}") from e
