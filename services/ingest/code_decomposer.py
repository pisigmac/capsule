"""
Orchestration pipeline for decomposing multi-language source codebases into atomic capsules
and building deterministic code dependency graphs (Python, TypeScript/JavaScript, Go, Rust, Java).
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
from .parsers.go_parser import GoCodeParser, GoFileInfo
from .parsers.rust_parser import RustCodeParser, RustFileInfo
from .parsers.java_parser import JavaCodeParser, JavaFileInfo
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
        self.go_parser = GoCodeParser()
        self.rust_parser = RustCodeParser()
        self.java_parser = JavaCodeParser()

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
        # 3. Parse Go Files
        go_files: Dict[str, GoFileInfo] = {}
        # 4. Parse Rust Files
        rust_files: Dict[str, RustFileInfo] = {}
        # 5. Parse Java Files
        java_files: Dict[str, JavaFileInfo] = {}

        if root.is_dir():
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                parts = p.parts
                if any(part in IGNORED_DIRS or part.startswith(".") for part in parts):
                    continue
                rel_p = str(p.relative_to(root)).replace("\\", "/")
                ext = p.suffix.lower()

                if ext in {".ts", ".tsx", ".js", ".jsx"}:
                    src = p.read_text(encoding="utf-8", errors="replace")
                    ts_files[rel_p] = self.ts_parser.parse_code(rel_p, src)
                elif ext == ".go":
                    src = p.read_text(encoding="utf-8", errors="replace")
                    go_files[rel_p] = self.go_parser.parse_code(rel_p, src)
                elif ext == ".rs":
                    src = p.read_text(encoding="utf-8", errors="replace")
                    rust_files[rel_p] = self.rust_parser.parse_code(rel_p, src)
                elif ext == ".java":
                    src = p.read_text(encoding="utf-8", errors="replace")
                    java_files[rel_p] = self.java_parser.parse_code(rel_p, src)
        elif root.is_file():
            ext = root.suffix.lower()
            src = root.read_text(encoding="utf-8", errors="replace")
            if ext in {".ts", ".tsx", ".js", ".jsx"}:
                ts_files[root.name] = self.ts_parser.parse_code(root.name, src)
            elif ext == ".go":
                go_files[root.name] = self.go_parser.parse_code(root.name, src)
            elif ext == ".rs":
                rust_files[root.name] = self.rust_parser.parse_code(root.name, src)
            elif ext == ".java":
                java_files[root.name] = self.java_parser.parse_code(root.name, src)

        result.total_files = (
            len(py_model.files)
            + len(ts_files)
            + len(go_files)
            + len(rust_files)
            + len(java_files)
        )
        result.total_classes = (
            len(py_model.classes)
            + sum(len(t.classes) + len(t.interfaces) for t in ts_files.values())
            + sum(len(g.types) for g in go_files.values())
            + sum(len(r.types) for r in rust_files.values())
            + sum(len(j.classes) for j in java_files.values())
        )
        result.total_functions = (
            len(py_model.functions)
            + sum(len(t.functions) for t in ts_files.values())
            + sum(len(g.functions) for g in go_files.values())
            + sum(len(r.functions) for r in rust_files.values())
            + sum(len(j.methods) for j in java_files.values())
        )

        if dry_run:
            result.created_count = result.total_files + result.total_classes + result.total_functions
            return result

        # Map internal node IDs to Capsule UUIDs
        id_map: Dict[str, str] = {}

        # -------------------------------------------------------------
        # A. Python Capsules
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # B. TypeScript Capsules
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # C. Go Capsules
        # -------------------------------------------------------------
        for fpath, go_info in go_files.items():
            tags = ["code", "go", "file", go_info.package]
            content = f"### Go Package `{go_info.package}` — `{fpath}`\n\n- **Lines of Code**: {go_info.loc}\n- **Types**: {len(go_info.types)}\n- **Functions**: {len(go_info.functions)}"
            parent_dir = str(Path(fpath).parent)
            cat = f"code/go/{parent_dir}" if parent_dir and parent_dir != "." else "code/go"

            try:
                cap = self.store.create(
                    topic=f"File: {fpath}",
                    content=content,
                    tags=tags,
                    source=fpath,
                    confidence="high",
                    category=cat,
                )
                id_map[go_info.id] = cap.id
                result.created_capsules.append(cap)
                result.created_count += 1
            except Exception as exc:
                logger.warning("Failed to create Go file capsule %s: %s", fpath, exc)

            for tname, tinfo in go_info.types.items():
                try:
                    c = self.store.create(
                        topic=f"{tinfo.kind.title()}: {tname}",
                        content=f"### Go {tinfo.kind.title()} `{tname}`\n\n**Package**: `{go_info.package}`\n**File**: `{fpath}`",
                        tags=["code", "go", tinfo.kind],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[tinfo.id] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

            for fn in go_info.functions:
                try:
                    c = self.store.create(
                        topic=f"Function: {fn.qualified_name}",
                        content=f"### `func {fn.name}({fn.params}) {fn.returns or ''}`\n\n**Package**: `{go_info.package}`\n**File**: `{fpath}`",
                        tags=["code", "go", "function"],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[fn.id] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

        # -------------------------------------------------------------
        # D. Rust Capsules
        # -------------------------------------------------------------
        for fpath, rust_info in rust_files.items():
            tags = ["code", "rust", "file"]
            content = f"### Rust Module `{fpath}`\n\n- **Lines of Code**: {rust_info.loc}\n- **Types**: {len(rust_info.types)}\n- **Functions**: {len(rust_info.functions)}"
            parent_dir = str(Path(fpath).parent)
            cat = f"code/rust/{parent_dir}" if parent_dir and parent_dir != "." else "code/rust"

            try:
                cap = self.store.create(
                    topic=f"File: {fpath}",
                    content=content,
                    tags=tags,
                    source=fpath,
                    confidence="high",
                    category=cat,
                )
                id_map[rust_info.id] = cap.id
                result.created_capsules.append(cap)
                result.created_count += 1
            except Exception as exc:
                logger.warning("Failed to create Rust file capsule %s: %s", fpath, exc)

            for tname, tinfo in rust_info.types.items():
                try:
                    c = self.store.create(
                        topic=f"{tinfo.kind.title()}: {tname}",
                        content=f"### Rust {tinfo.kind.title()} `{tname}`\n\n**File**: `{fpath}`",
                        tags=["code", "rust", tinfo.kind],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[tinfo.id] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

            for fn in rust_info.functions:
                try:
                    c = self.store.create(
                        topic=f"Function: {fn.name}",
                        content=f"### `fn {fn.name}({fn.params}) -> {fn.returns or '()'}`\n\n**File**: `{fpath}`",
                        tags=["code", "rust", "function"],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[fn.id] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

        # -------------------------------------------------------------
        # E. Java Capsules
        # -------------------------------------------------------------
        for fpath, java_info in java_files.items():
            tags = ["code", "java", "file", java_info.package]
            content = f"### Java Package `{java_info.package}` — `{fpath}`\n\n- **Lines of Code**: {java_info.loc}\n- **Classes**: {len(java_info.classes)}\n- **Methods**: {len(java_info.methods)}"
            parent_dir = str(Path(fpath).parent)
            cat = f"code/java/{parent_dir}" if parent_dir and parent_dir != "." else "code/java"

            try:
                cap = self.store.create(
                    topic=f"File: {fpath}",
                    content=content,
                    tags=tags,
                    source=fpath,
                    confidence="high",
                    category=cat,
                )
                id_map[java_info.id] = cap.id
                result.created_capsules.append(cap)
                result.created_count += 1
            except Exception as exc:
                logger.warning("Failed to create Java file capsule %s: %s", fpath, exc)

            for cname, cinfo in java_info.classes.items():
                try:
                    ext_str = f" (extends `{cinfo.extends}`)" if cinfo.extends else ""
                    c = self.store.create(
                        topic=f"{cinfo.kind.title()}: {cname}",
                        content=f"### Java {cinfo.kind.title()} `{cname}`{ext_str}\n\n**Package**: `{java_info.package}`\n**File**: `{fpath}`",
                        tags=["code", "java", cinfo.kind],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[cinfo.id] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

            for m in java_info.methods:
                try:
                    c = self.store.create(
                        topic=f"Method: {m.name}",
                        content=f"### `{m.returns or 'void'} {m.name}({m.params})`\n\n**Package**: `{java_info.package}`\n**File**: `{fpath}`",
                        tags=["code", "java", "method"],
                        source=fpath,
                        confidence="high",
                        category=cat,
                    )
                    id_map[m.id] = c.id
                    result.created_capsules.append(c)
                    result.created_count += 1
                except Exception:
                    pass

        # -------------------------------------------------------------
        # 6. Link Structural AST Relationships
        # -------------------------------------------------------------
        # Python definitions
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

            for imp_fid in file_info.resolved_imports:
                tgt_cid = id_map.get(imp_fid)
                if tgt_cid:
                    self.store.link(src_cid, tgt_cid, "imports")
                    result.relationships_linked += 1

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

        for fn_id, fn_info in py_model.functions.items():
            fn_cid = id_map.get(fn_id)
            if not fn_cid:
                continue

            for call in fn_info.resolved_calls:
                tgt_cid = id_map.get(call.target_id)
                if tgt_cid and tgt_cid != fn_cid:
                    self.store.link(fn_cid, tgt_cid, "calls")
                    result.relationships_linked += 1

        # Go definitions
        for fpath, ginfo in go_files.items():
            f_cid = id_map.get(ginfo.id)
            if not f_cid:
                continue
            for tinfo in ginfo.types.values():
                t_cid = id_map.get(tinfo.id)
                if t_cid:
                    self.store.link(f_cid, t_cid, "defines")
                    result.relationships_linked += 1
            for fn in ginfo.functions:
                fn_cid = id_map.get(fn.id)
                if fn_cid:
                    self.store.link(f_cid, fn_cid, "defines")
                    result.relationships_linked += 1

        # Rust definitions
        for fpath, rinfo in rust_files.items():
            f_cid = id_map.get(rinfo.id)
            if not f_cid:
                continue
            for tinfo in rinfo.types.values():
                t_cid = id_map.get(tinfo.id)
                if t_cid:
                    self.store.link(f_cid, t_cid, "defines")
                    result.relationships_linked += 1
            for fn in rinfo.functions:
                fn_cid = id_map.get(fn.id)
                if fn_cid:
                    self.store.link(f_cid, fn_cid, "defines")
                    result.relationships_linked += 1

        # Java definitions
        for fpath, jinfo in java_files.items():
            f_cid = id_map.get(jinfo.id)
            if not f_cid:
                continue
            for cinfo in jinfo.classes.values():
                c_cid = id_map.get(cinfo.id)
                if c_cid:
                    self.store.link(f_cid, c_cid, "defines")
                    result.relationships_linked += 1
            for m in jinfo.methods:
                m_cid = id_map.get(m.id)
                if m_cid:
                    self.store.link(f_cid, m_cid, "defines")
                    result.relationships_linked += 1

        # -------------------------------------------------------------
        # 7. Cross-Layer Knowledge-to-Code Linking (implements / implemented_by)
        # -------------------------------------------------------------
        adr_linker = AdrCrossLayerLinker(self.store)
        adr_links = adr_linker.link_code_to_architecture(
            py_model=py_model,
            ts_files=ts_files,
            id_map=id_map,
        )
        result.relationships_linked += adr_links

        self.store.db.commit()
        return result
