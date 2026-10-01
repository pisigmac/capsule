"""
Rust (.rs) source parser.
Extracts modules, uses/imports, structs, enums, traits, impl blocks, and functions
using deterministic structural AST and regex parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .python_parser import stable_id

USE_RE = re.compile(r"""use\s+([^;]+);""")
STRUCT_RE = re.compile(
    r"""(?:pub(?:\([^)]+\))?\s+)?struct\s+([A-Z]\w*)""", re.MULTILINE
)
ENUM_RE = re.compile(
    r"""(?:pub(?:\([^)]+\))?\s+)?enum\s+([A-Z]\w*)""", re.MULTILINE
)
TRAIT_RE = re.compile(
    r"""(?:pub(?:\([^)]+\))?\s+)?trait\s+([A-Z]\w*)""", re.MULTILINE
)
IMPL_RE = re.compile(
    r"""impl(?:<[^>]+>)?\s+(?:([A-Z]\w*)\s+for\s+)?([A-Z]\w*)""", re.MULTILINE
)
FN_RE = re.compile(
    r"""(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?fn\s+([a-zA-Z_]\w*)\s*(?:<[^>]+>)?\s*\(([^)]*)\)(?:\s*->\s*([^{;]+))?\s*[{;]""",
    re.MULTILINE,
)


@dataclass
class RustFunctionInfo:
    id: str
    name: str
    qualified_name: str
    file_path: str
    impl_target: Optional[str]
    trait_name: Optional[str]
    params: str
    returns: Optional[str]
    is_async: bool = False
    docstring: Optional[str] = None
    calls: List[str] = field(default_factory=list)


@dataclass
class RustTypeInfo:
    id: str
    name: str
    file_path: str
    kind: str  # "struct" | "enum" | "trait"
    docstring: Optional[str] = None
    traits_implemented: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)


@dataclass
class RustFileInfo:
    id: str
    path: str
    dir_path: str
    loc: int
    imports: List[str] = field(default_factory=list)
    types: Dict[str, RustTypeInfo] = field(default_factory=dict)
    functions: List[RustFunctionInfo] = field(default_factory=list)


class RustCodeParser:
    """Parses Rust source files into structural models."""

    def parse_code(self, rel_path: str, source: str) -> RustFileInfo:
        file_id = stable_id("rust_file", rel_path)
        dir_path = str(Path(rel_path).parent)
        if dir_path == ".":
            dir_path = ""
        loc = source.count("\n") + 1

        info = RustFileInfo(
            id=file_id,
            path=rel_path,
            dir_path=dir_path,
            loc=loc,
        )

        # 1. Uses / Imports
        for match in USE_RE.finditer(source):
            use_path = match.group(1).strip()
            if use_path not in info.imports:
                info.imports.append(use_path)

        # 2. Structs
        for match in STRUCT_RE.finditer(source):
            name = match.group(1).strip()
            type_id = stable_id("rust_type", rel_path, name)
            info.types[name] = RustTypeInfo(
                id=type_id,
                name=name,
                file_path=rel_path,
                kind="struct",
            )

        # 3. Enums
        for match in ENUM_RE.finditer(source):
            name = match.group(1).strip()
            type_id = stable_id("rust_type", rel_path, name)
            info.types[name] = RustTypeInfo(
                id=type_id,
                name=name,
                file_path=rel_path,
                kind="enum",
            )

        # 4. Traits
        for match in TRAIT_RE.finditer(source):
            name = match.group(1).strip()
            type_id = stable_id("rust_type", rel_path, name)
            info.types[name] = RustTypeInfo(
                id=type_id,
                name=name,
                file_path=rel_path,
                kind="trait",
            )

        # 5. Functions
        for match in FN_RE.finditer(source):
            name = match.group(1).strip()
            params = match.group(2).strip()
            returns = match.group(3).strip() if match.group(3) else None
            fn_id = stable_id("rust_fn", rel_path, name)

            info.functions.append(
                RustFunctionInfo(
                    id=fn_id,
                    name=name,
                    qualified_name=name,
                    file_path=rel_path,
                    impl_target=None,
                    trait_name=None,
                    params=params,
                    returns=returns,
                    is_async="async" in match.group(0),
                )
            )

        return info
