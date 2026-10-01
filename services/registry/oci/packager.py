"""OCI Layer packager and safe tar.gz extractor."""
from __future__ import annotations

import hashlib
import io
import os
import tarfile
from pathlib import Path
from typing import List, Optional, Tuple


class TarSlipError(Exception):
    """Raised when an archive member attempts directory traversal."""
    pass


class OCIPackager:
    """Creates and extracts deterministic OCI layer blobs for capsule vaults."""

    @staticmethod
    def pack_layer(source_dir: Path) -> Tuple[bytes, str, int]:
        """Bundle directory of capsules into a deterministic tar.gz layer.

        Returns (layer_bytes, digest, size_bytes).
        """
        source_dir = Path(source_dir).resolve()
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

        files_to_pack: List[Path] = []
        for root, _, files in os.walk(source_dir):
            for f in sorted(files):
                if f.endswith(".caps.md") or f.endswith(".capsule.md") or (f.endswith(".md") and not f.startswith(".")):
                    files_to_pack.append(Path(root) / f)

        if not files_to_pack:
            raise ValueError(f"No capsule markdown files found in {source_dir}")

        buf = io.BytesIO()
        # Create deterministic tar.gz archive
        with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
            for file_path in sorted(files_to_pack):
                content = file_path.read_bytes()
                ti = tarfile.TarInfo(name=file_path.name)
                ti.size = len(content)
                ti.mtime = 0  # Normalize mtime for reproducible layer hashing
                ti.uid = 0
                ti.gid = 0
                ti.mode = 0o644
                tar.addfile(ti, io.BytesIO(content))

        layer_bytes = buf.getvalue()
        sha256_hex = hashlib.sha256(layer_bytes).hexdigest()
        digest = f"sha256:{sha256_hex}"
        size_bytes = len(layer_bytes)

        return layer_bytes, digest, size_bytes

    @staticmethod
    def unpack_layer(
        layer_bytes: bytes,
        target_dir: Path,
        force: bool = False,
    ) -> Tuple[List[str], List[str]]:
        """Safely extract tar.gz layer with Tar Slip path traversal prevention.

        Returns (installed_files, skipped_files).
        """
        target_dir = Path(target_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        resolved_root = str(target_dir)

        installed: List[str] = []
        skipped: List[str] = []

        try:
            with tarfile.open(fileobj=io.BytesIO(layer_bytes), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.isdir():
                        continue

                    # TAR SLIP DEFENSE: Validate member path components
                    member_path = Path(member.name)
                    if ".." in member_path.parts or member.name.startswith("/") or member.name.startswith("\\"):
                        raise TarSlipError(
                            f"Security violation: Archive member '{member.name}' attempts directory traversal!"
                        )

                    if member_path.name.startswith("."):
                        continue

                    dest_file = (target_dir / member_path.name).resolve()
                    if not str(dest_file).startswith(resolved_root):
                        raise TarSlipError(
                            f"Security violation: Dest file '{dest_file}' escapes target directory '{resolved_root}'!"
                        )

                    # Only extract markdown files
                    if not (member.name.endswith(".caps.md") or member.name.endswith(".capsule.md") or member.name.endswith(".md")):
                        continue

                    if dest_file.exists() and not force:
                        skipped.append(member_path.name)
                        continue

                    f = tar.extractfile(member)
                    if f:
                        dest_file.write_bytes(f.read())
                        installed.append(member_path.name)
        except tarfile.TarError as e:
            raise ValueError(f"Corrupted or invalid tar.gz layer: {e}") from e

        return installed, skipped
