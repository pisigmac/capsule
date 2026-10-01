"""LlamaIndex Reader adapter for Capsule vault and .caps.md files."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

try:
    from llama_index.core.readers.base import BaseReader
    from llama_index.core.schema import Document
except ImportError as exc:
    raise ImportError(
        "The LlamaIndex adapter requires 'llama-index-core'. "
        "Please install it with: pip install kapsule[llamaindex] or pip install llama-index-core"
    ) from exc

from services.parser.parser import CapsuleParser


class CapsuleReader(BaseReader):
    """LlamaIndex Reader for loading Capsule markdown files into Documents."""

    def __init__(self, parser: Optional[CapsuleParser] = None) -> None:
        super().__init__()
        self._parser = parser or CapsuleParser()

    def _discover_files(
        self,
        folder_path: Optional[Union[str, Path]] = None,
        file_paths: Optional[Sequence[Union[str, Path]]] = None,
        recursive: bool = True,
    ) -> List[Path]:
        """Collect all capsule markdown files to process."""
        target_files: List[Path] = []
        if file_paths:
            for fp in file_paths:
                p = Path(fp)
                if p.is_file():
                    target_files.append(p)

        if folder_path:
            folder = Path(folder_path)
            if folder.is_dir():
                pattern = "**/*" if recursive else "*"
                for p in folder.glob(pattern):
                    if p.is_file() and (p.name.endswith(".caps.md") or p.name.endswith(".capsule.md") or p.suffix == ".md"):
                        # Avoid duplicates
                        if p not in target_files:
                            target_files.append(p)
            elif folder.is_file():
                if folder not in target_files:
                    target_files.append(folder)

        return sorted(target_files)

    def lazy_load_data(
        self,
        folder_path: Optional[Union[str, Path]] = None,
        file_paths: Optional[Sequence[Union[str, Path]]] = None,
        recursive: bool = True,
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Document]:
        """Lazily load documents from Capsule markdown files."""
        files = self._discover_files(folder_path=folder_path, file_paths=file_paths, recursive=recursive)

        for f in files:
            parsed = self._parser.parse_file(f)
            metadata: Dict[str, Any] = {
                "topic": parsed.topic,
                "tags": parsed.tags,
                "confidence": parsed.confidence,
                "source": parsed.source,
                "archived": parsed.archived,
                "file_path": str(f.resolve()),
                "file_name": f.name,
            }
            if parsed.id:
                metadata["id"] = parsed.id
            if parsed.freshness:
                metadata["freshness"] = parsed.freshness.isoformat()
            if extra_info:
                metadata.update(extra_info)

            # Filter out None values
            metadata = {k: v for k, v in metadata.items() if v is not None}

            text = f"{parsed.topic}\n\n{parsed.content}".strip() if parsed.topic else parsed.content
            doc_id = parsed.id or str(f.resolve())

            yield Document(
                text=text,
                doc_id=doc_id,
                metadata=metadata,
            )

    def load_data(
        self,
        folder_path: Optional[Union[str, Path]] = None,
        file_paths: Optional[Sequence[Union[str, Path]]] = None,
        recursive: bool = True,
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """Synchronously load all Capsule documents into a list."""
        return list(
            self.lazy_load_data(
                folder_path=folder_path,
                file_paths=file_paths,
                recursive=recursive,
                extra_info=extra_info,
            )
        )
