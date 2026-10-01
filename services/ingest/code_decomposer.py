"""
Orchestration pipeline for decomposing source codebases into atomic capsules
and building deterministic code dependency graphs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from services.shared.models import Capsule
from services.store.store import CapsuleStore
from .parsers.python_parser import (
    PythonCodeParser,
    RepoModel,
    scan_python_repo,
    stable_id,
    IGNORED_DIRS,
)
from .parsers.typescript_parser import TypeScriptCodeParser, TsFileInfo
from .parsers.adr_linker import AdrCrossLayerLinker

logger = logging.getLogger("capsule.ingest.code")


@dataclass
class CodeIngestResult:
    total_files: int = 0
    total_classes: int = 0
    total_functions: int = 0
    created_count: int = 0
    relationships_linked: int = 0
    created_capsules: List[Capsule] = field(default_factory=list)


class CodeDecomposer:
    """Scans and decomposes source code into atomic code capsules and dependency graphs."""

    def __init__(self, store: CapsuleStore) -> None:
        self.store = store
        self.ts_parser = TypeScriptCodeParser()

    def ingest_code_path(
        self,
        target_path: Path | str,
        dry_run: bool = False,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> CodeIngestResult:
        root = Path(target_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {target_path}")

        result = CodeIngestResult()

        # 1. Parse Python Files
        py_model = scan_python_repo(str(root)) if root.is_dir() else RepoModel(root=str(root.parent))
        if root.is_file() and root.suffix == ".py":
            parser = PythonCodeParser()
            rel_path = root.name
            fi = parser.parse_code(rel_path, root.read_text(encoding="utf-8", errors="replace"))
            py_model.files[rel_path] = fi
            for c in fi.class_defs.values():
                py_model.classes[c.id] = c
            for fn in fi.functions:
                py_model.functions[fn.id] = fn

        # 2. Parse TypeScript / JavaScript Files
        ts_files: Dict[str, TsFileInfo] = {}
        if root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".ts", ".tsx", ".js", ".jsx"}:
                    parts = p.parts
                    if any(part in IGNORED_DIRS or part.startswith(".") for part in parts):
                        continue
                    rel_p = str(p.relative_to(root)).replace("\\", "/")
                    src = p.read_text(encoding="utf-8", errors="replace")
                    ts_files[rel_p] = self.ts_parser.parse_code(rel_p, src)
        elif root.is_file() and root.suffix.lower() in {".ts", ".tsx", ".js", ".jsx"}:
            src = root.read_text(encoding="utf-8", errors="replace")
            ts_files[root.name] = self.ts_parser.parse_code(root.name, src)

        result.total_files = len(py_model.files) + len(ts_files)
        result.total_classes = len(py_model.classes) + sum(len(t.classes) + len(t.interfaces) for t in ts_files.values())
        result.total_functions = len(py_model.functions) + sum(len(t.functions) for t in ts_files.values())

        if dry_run:
            result.created_count = result.total_files + result.total_classes + result.total_functions
            return result

        # Map internal node IDs to Capsule UUIDs
        id_map: Dict[str, str] = {}

        # 3. Create Capsules for Python Entities
        for fpath, file_info in py_model.files.items():
            mod_tag = fpath.replace("/", ".").replace(".py", "")
            tags = ["code", "python", "file", mod_tag]
            author_blame = f"\n\n**Last Commit**: `{file_info.commit_author}` on `{file_info.commit_date}` — _{file_info.commit_message}_" if file_info.commit_author else ""
            content = f"### Module `{fpath}`\n\n- **Lines of Code**: {file_info.loc}\n- **Classes**: {', '.join(file_info.classes) or 'None'}\n- **Functions**: {len(file_info.functions)}{author_blame}"
            parent_dir = str(Path(fpath).parent)
            cat = f"code/python/{parent_dir}" if parent_dir and parent_dir != "." else "code/python"

            try:
                cap = self.store.create(
                    topic=f"File: {fpath}",
                    content=content,
                    tags=tags,
                    source=fpath,
                    confidence="high",
                    category=cat,
                )
                id_map[file_info.id] = cap.id
                result.created_capsules.append(cap)
                result.created_count += 1
            except Exception as exc:
                logger.warning("Failed to create file capsule %s: %s", fpath, exc)

        # Python Classes
        for cls_id, cls_info in py_model.classes.items():
            mod_tag = cls_info.file_path.replace("/", ".").replace(".py", "")
            tags = ["code", "python", "class", mod_tag]
            bases_str = f" (inherits `{', '.join(cls_info.bases)}`)" if cls_info.bases else ""
            doc_str = f"\n\n{cls_info.docstring}" if cls_info.docstring else ""
            content = f"### Class `{cls_info.name}`{bases_str}\n\n**File**: `{cls_info.file_path}#L{cls_info.lineno_start}-L{cls_info.lineno_end}`{doc_str}"
            parent_dir = str(Path(cls_info.file_path).parent)
            cat = f"code/python/{parent_dir}" if parent_dir and parent_dir != "." else "code/python"

            try:
                cap = self.store.create(
                    topic=f"Class: {cls_info.name}",
                    content=content,
                    tags=tags,
                    source=f"{cls_info.file_path}#L{cls_info.lineno_start}",
                    confidence="high",
                    category=cat,
                )
                id_map[cls_id] = cap.id
                result.created_capsules.append(cap)
                result.created_count += 1
            except Exception as exc:
                logger.warning("Failed to create class capsule %s: %s", cls_info.name, exc)

        # Python Functions / Methods
        for fn_id, fn_info in py_model.functions.items():
            mod_tag = fn_info.file_path.replace("/", ".").replace(".py", "")
            tags = ["code", "python", "function", mod_tag]
            doc_str = f"\n\n{fn_info.docstring}" if fn_info.docstring else ""
            calls_str = f"\n\n**Calls**: `{', '.join(fn_info.calls)}`" if fn_info.calls else ""
            content = f"### `{fn_info.signature}`\n\n**Location**: `{fn_info.file_path}#L{fn_info.lineno_start}-L{fn_info.lineno_end}`\n**Complexity**: {fn_info.complexity}{doc_str}{calls_str}"
            parent_dir = str(Path(fn_info.file_path).parent)
            cat = f"code/python/{parent_dir}" if parent_dir and parent_dir != "." else "code/python"

            try:
                cap = self.store.create(
                    topic=f"Function: {fn_info.qualified_name}",
                    content=content,
                    tags=tags,
                    source=f"{fn_info.file_path}#L{fn_info.lineno_start}",
                    confidence="high",
                    category=cat,
                )
                id_map[fn_id] = cap.id
                result.created_capsules.append(cap)
                result.created_count += 1
            except Exception as exc:
                logger.warning("Failed to create function capsule %s: %s", fn_info.qualified_name, exc)

        # 4. Create Capsules for TypeScript Entities
        for fpath, ts_info in ts_files.items():
            tags = ["code", "typescript", "file"]
            content = f"### TypeScript Module `{fpath}`\n\n- **Lines of Code**: {ts_info.loc}\n- **Interfaces**: {', '.join(ts_info.interfaces) or 'None'}\n- **Types**: {', '.join(ts_info.types) or 'None'}\n- **Classes**: {', '.join(ts_info.classes) or 'None'}\n- **Functions**: {len(ts_info.functions)}"
            parent_dir = str(Path(fpath).parent)
            cat = f"code/typescript/{parent_dir}" if parent_dir and parent_dir != "." else "code/typescript"

            try:
                cap = self.store.create(
                    topic=f"File: {fpath}",
                    content=content,
                    tags=tags,
                    source=fpath,
                    confidence="high",
                    category=cat,
                )
                id_map[ts_info.id] = cap.id
                result.created_capsules.append(cap)
                result.created_count += 1
            except Exception as exc:
                logger.warning("Failed to create TS file capsule %s: %s", fpath, exc)

            for iface in ts_info.interfaces:
                try:
                    c = self.store.create(
                        topic=f"Interface: {iface}",
                        content=f"### TypeScript Interface `{iface}`\n\n**File**: `{fpath}`",
                        tags=["code", "typescript", "interface"],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[f"{ts_info.id}::{iface}"] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

            for fn in ts_info.functions:
                try:
                    c = self.store.create(
                        topic=f"Function: {fn.name}",
                        content=f"### `{fn.name}({fn.params}): {fn.returns or 'void'}`\n\n**File**: `{fpath}`",
                        tags=["code", "typescript", "function"],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[fn.id] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

        # 5. Link Relationships
        # A. File -> Classes / Functions (defines)
        for fpath, file_info in py_model.files.items():
            src_cid = id_map.get(file_info.id)
            if not src_cid:
                continue

            for cls_info in file_info.class_defs.values():
                tgt_cid = id_map.get(cls_info.id)
                if tgt_cid:
                    self.store.link(src_cid, tgt_cid, "defines")
                    result.relationships_linked += 1

            for fn_info in file_info.functions:
                if not fn_info.class_name:
                    tgt_cid = id_map.get(fn_info.id)
                    if tgt_cid:
                        self.store.link(src_cid, tgt_cid, "defines")
                        result.relationships_linked += 1

            # Module imports
            for imp_fid in file_info.resolved_imports:
                tgt_cid = id_map.get(imp_fid)
                if tgt_cid:
                    self.store.link(src_cid, tgt_cid, "imports")
                    result.relationships_linked += 1

        # B. Class -> Methods (defines) & Class -> Base Class (inherits)
        for cls_id, cls_info in py_model.classes.items():
            cls_cid = id_map.get(cls_id)
            if not cls_cid:
                continue

            for m_id in cls_info.methods:
                m_cid = id_map.get(m_id)
                if m_cid:
                    self.store.link(cls_cid, m_cid, "defines")
                    result.relationships_linked += 1

            for base_id in cls_info.resolved_bases:
                base_cid = id_map.get(base_id)
                if base_cid:
                    self.store.link(cls_cid, base_cid, "inherits")
                    result.relationships_linked += 1

        # C. Function -> Function (calls)
        for fn_id, fn_info in py_model.functions.items():
            fn_cid = id_map.get(fn_id)
            if not fn_cid:
                continue

            for call in fn_info.resolved_calls:
                tgt_cid = id_map.get(call.target_id)
                if tgt_cid and tgt_cid != fn_cid:
                    self.store.link(fn_cid, tgt_cid, "calls")
                    result.relationships_linked += 1

        # 6. Cross-Layer Knowledge-to-Code Linking (implements / implemented_by)
        adr_linker = AdrCrossLayerLinker(self.store)
        adr_links = adr_linker.link_code_to_architecture(
            py_model=py_model,
            ts_files=ts_files,
            id_map=id_map,
        )
        result.relationships_linked += adr_links

        self.store.db.commit()
        return result
