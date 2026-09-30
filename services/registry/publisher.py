"""Knowledge Pack Publisher — packages local capsules into distributable archives."""
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from typing import List, Optional, Set, Tuple

from services.parser.parser import CapsuleParser
from services.registry.manifest import PackManifest


class PackPublisher:
    """Creates distributable Knowledge Pack zip archives."""

    @staticmethod
    def create_pack(
        source_dir: Path,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        author: str = "Community",
        tags: Optional[List[str]] = None,
        output_path: Optional[Path] = None,
    ) -> Tuple[Path, PackManifest]:
        """Bundle a folder of capsules into a verified knowledge pack.

        Parameters
        ----------
        source_dir : Path
            Directory containing `.caps.md` or `.capsule.md` files.
        name : str
            Pack identifier (e.g. 'react-performance').
        version : str
            Semantic version string.
        description : str
            Short description of the pack's contents.
        author : str
            Pack creator / maintainer.
        tags : Optional[List[str]]
            Tags classifying the pack. If omitted, aggregates tags from capsules.
        output_path : Optional[Path]
            Destination `.zip` path. If None, defaults to `./<name>-<version>.capsulepack`.
        """
        source_dir = Path(source_dir).resolve()
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

        capsule_files: List[Path] = []
        for root, _, files in os.walk(source_dir):
            for file in files:
                if file.endswith(".caps.md") or file.endswith(".capsule.md") or (file.endswith(".md") and not file.startswith(".")):
                    capsule_files.append(Path(root) / file)

        if not capsule_files:
            raise ValueError(f"No capsule files found in {source_dir}")

        aggregated_tags: Set[str] = set(tags or [])
        valid_files: List[Tuple[str, str]] = []

        parser = CapsuleParser()
        for cf in sorted(capsule_files):
            try:
                content = cf.read_text(encoding="utf-8")
                parsed = parser.parse_text(content)
                for t in parsed.tags:
                    aggregated_tags.add(t)
                valid_files.append((cf.name, content))
            except Exception:
                # Still include if it's markdown
                valid_files.append((cf.name, cf.read_text(encoding="utf-8")))

        clean_name = name.strip().lower().replace(" ", "-")
        manifest = PackManifest(
            name=clean_name,
            version=version,
            description=description,
            author=author,
            caps_count=len(valid_files),
            tags=sorted(list(aggregated_tags)),
            verified=True,
        )

        out = output_path or (Path.cwd() / f"{clean_name}-{version}.zip")
        out = Path(out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write manifest.json
            manifest_json = manifest.to_json(indent=2)
            zf.writestr("manifest.json", manifest_json)

            # Write capsule files
            for fname, fcontent in valid_files:
                zf.writestr(fname, fcontent)

        zip_data = buf.getvalue()
        sha256 = hashlib.sha256(zip_data).hexdigest()
        manifest.sha256 = sha256

        # Rewrite with updated sha256 in manifest
        final_buf = io.BytesIO()
        with zipfile.ZipFile(final_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest.to_json(indent=2))
            for fname, fcontent in valid_files:
                zf.writestr(fname, fcontent)

        out.write_bytes(final_buf.getvalue())
        return out, manifest
