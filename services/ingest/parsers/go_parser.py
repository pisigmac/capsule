"""
Go (.go) source parser.
Extracts packages, imports, structs, interfaces, functions, and receiver methods
using deterministic structural AST and regex parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .python_parser import stable_id

PACKAGE_RE = re.compile(r"""^\s*package\s+([a-zA-Z_]\w*)""", re.MULTILINE)
IMPORT_SINGLE_RE = re.compile(r"""import\s+['\"]([^'\"]+)['\"]""")
IMPORT_BLOCK_RE = re.compile(r"""import\s*\(\s*([^)]+)\)""", re.DOTALL)
STRUCT_RE = re.compile(
    r"""type\s+([A-Z]\w*)\s+struct\s*\{""", re.MULTILINE
)
INTERFACE_RE = re.compile(
    r"""type\s+([A-Z]\w*)\s+interface\s*\{""", re.MULTILINE
)
FUNC_RE = re.compile(
    r"""^\s*func\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)(?:\s*([^{]+))?\s*\{""",
    re.MULTILINE,
)
METHOD_RE = re.compile(
    r"""^\s*func\s+\((?:(?:\w+\s+)?\*?([A-Z]\w*))\)\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)(?:\s*([^{]+))?\s*\{""",
    re.MULTILINE,
)


@dataclass
class GoFunctionInfo:
    id: str
    name: str
    qualified_name: str
    file_path: str
    receiver: Optional[str]
    params: str
    returns: Optional[str]
    docstring: Optional[str] = None
    calls: List[str] = field(default_factory=list)


@dataclass
class GoTypeInfo:
    id: str
    name: str
    file_path: str
    kind: str  # "struct" | "interface"
    docstring: Optional[str] = None
    methods: List[str] = field(default_factory=list)


@dataclass
class GoFileInfo:
    id: str
    path: str
    dir_path: str
    package: str
    loc: int
    imports: List[str] = field(default_factory=list)
    types: Dict[str, GoTypeInfo] = field(default_factory=dict)
    functions: List[GoFunctionInfo] = field(default_factory=list)


class GoCodeParser:
    """Parses Go source files into structural models."""

    def parse_code(self, rel_path: str, source: str) -> GoFileInfo:
        file_id = stable_id("go_file", rel_path)
        dir_path = str(Path(rel_path).parent)
        if dir_path == ".":
            dir_path = ""
        loc = source.count("\n") + 1

        pkg_match = PACKAGE_RE.search(source)
        package = pkg_match.group(1) if pkg_match else "main"

        info = GoFileInfo(
            id=file_id,
            path=rel_path,
            dir_path=dir_path,
            package=package,
            loc=loc,
        )

        # 1. Imports
        for match in IMPORT_SINGLE_RE.finditer(source):
            imp = match.group(1).strip()
            if imp not in info.imports:
                info.imports.append(imp)

        for block in IMPORT_BLOCK_RE.finditer(source):
            for line in block.group(1).splitlines():
                line = line.strip().strip('"')
                if line and not line.startswith("//"):
                    line = line.split()[-1].strip('"')
                    if line not in info.imports:
                        info.imports.append(line)

        # 2. Structs
        for match in STRUCT_RE.finditer(source):
            name = match.group(1).strip()
            type_id = stable_id("go_type", rel_path, name)
            info.types[name] = GoTypeInfo(
                id=type_id,
                name=name,
                file_path=rel_path,
                kind="struct",
            )

        # 3. Interfaces
        for match in INTERFACE_RE.finditer(source):
            name = match.group(1).strip()
            type_id = stable_id("go_type", rel_path, name)
            info.types[name] = GoTypeInfo(
                id=type_id,
                name=name,
                file_path=rel_path,
                kind="interface",
            )

        # 4. Methods & Functions
        seen_fn_names = set()
        for match in METHOD_RE.finditer(source):
            receiver = match.group(1).strip()
            name = match.group(2).strip()
            params = match.group(3).strip()
            returns = match.group(4).strip() if match.group(4) else None
            qual_name = f"{receiver}.{name}"
            fn_id = stable_id("go_fn", rel_path, qual_name)

            fn = GoFunctionInfo(
                id=fn_id,
                name=name,
                qualified_name=qual_name,
                file_path=rel_path,
                receiver=receiver,
                params=params,
                returns=returns,
            )
            info.functions.append(fn)
            seen_fn_names.add(qual_name)

            if receiver in info.types:
                info.types[receiver].methods.append(fn_id)

        for match in FUNC_RE.finditer(source):
            name = match.group(1).strip()
            if name in seen_fn_names:
                continue
            params = match.group(2).strip()
            returns = match.group(3).strip() if match.group(3) else None
            fn_id = stable_id("go_fn", rel_path, name)

            info.functions.append(
                GoFunctionInfo(
                    id=fn_id,
                    name=name,
                    qualified_name=name,
                    file_path=rel_path,
                    receiver=None,
                    params=params,
                    returns=returns,
                )
            )

        return info
