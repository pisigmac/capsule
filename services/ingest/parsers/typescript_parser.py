"""
TypeScript / JavaScript parser.
Extracts interfaces, types, classes, exported functions, ES6/CommonJS imports,
and frontend API calls (fetch/axios endpoints) using high-precision structural regex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .python_parser import stable_id

IMPORT_RE = re.compile(
    r"""import\s+(?:type\s+)?(?:[\w*\s{},]+)\s+from\s+['\"]([^'\"]+)['\"]"""
)
FETCH_RE = re.compile(
    r"""(?:fetch|axios\.(?:get|post|put|patch|delete)|\$fetch)\(\s*[`'"]([^`'"]+)[`'"]"""
)
EXPORT_FN_RE = re.compile(
    r"""(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*([^;{]+))?"""
)
EXPORT_CONST_FN_RE = re.compile(
    r"""export\s+const\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)(?:\s*:\s*([^=>]+))?\s*=>"""
)
INTERFACE_RE = re.compile(
    r"""(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([^{]+))?\s*\{"""
)
TYPE_RE = re.compile(
    r"""(?:export\s+)?type\s+(\w+)(?:<[^>]+>)?\s*=\s*"""
)
CLASS_RE = re.compile(
    r"""(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?\s*\{"""
)


@dataclass
class TsFunctionInfo:
    id: str
    name: str
    file_path: str
    params: str
    returns: Optional[str]
    is_async: bool = False


@dataclass
class TsFileInfo:
    id: str
    path: str
    dir_path: str
    loc: int
    imports: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    types: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    functions: List[TsFunctionInfo] = field(default_factory=list)
    http_endpoints: List[str] = field(default_factory=list)


class TypeScriptCodeParser:
    """Parses TypeScript and JavaScript source files."""

    def parse_code(self, rel_path: str, source: str) -> TsFileInfo:
        file_id = stable_id("ts_file", rel_path)
        dir_path = str(Path(rel_path).parent)
        if dir_path == ".":
            dir_path = ""
        loc = source.count("\n") + 1

        info = TsFileInfo(
            id=file_id,
            path=rel_path,
            dir_path=dir_path,
            loc=loc,
        )

        # 1. Imports
        for match in IMPORT_RE.finditer(source):
            imp_path = match.group(1).strip()
            if imp_path not in info.imports:
                info.imports.append(imp_path)

        # 2. Interfaces
        for match in INTERFACE_RE.finditer(source):
            name = match.group(1).strip()
            if name not in info.interfaces:
                info.interfaces.append(name)

        # 3. Types
        for match in TYPE_RE.finditer(source):
            name = match.group(1).strip()
            if name not in info.types:
                info.types.append(name)

        # 4. Classes
        for match in CLASS_RE.finditer(source):
            name = match.group(1).strip()
            if name not in info.classes:
                info.classes.append(name)

        # 5. Functions
        for match in EXPORT_FN_RE.finditer(source):
            name = match.group(1).strip()
            params = match.group(2).strip()
            ret = match.group(3).strip() if match.group(3) else None
            fn_id = stable_id("ts_fn", rel_path, name)
            info.functions.append(
                TsFunctionInfo(
                    id=fn_id,
                    name=name,
                    file_path=rel_path,
                    params=params,
                    returns=ret,
                    is_async="async" in match.group(0),
                )
            )

        for match in EXPORT_CONST_FN_RE.finditer(source):
            name = match.group(1).strip()
            params = match.group(2).strip()
            ret = match.group(3).strip() if match.group(3) else None
            fn_id = stable_id("ts_fn", rel_path, name)
            info.functions.append(
                TsFunctionInfo(
                    id=fn_id,
                    name=name,
                    file_path=rel_path,
                    params=params,
                    returns=ret,
                    is_async="async" in match.group(0),
                )
            )

        # 6. HTTP API fetch calls
        for match in FETCH_RE.finditer(source):
            raw_url = match.group(1).strip()
            # Normalize path: /api/v1/search?q=... -> /api/v1/search
            endpoint = raw_url.split("?")[0].split("${")[0].strip()
            if endpoint.startswith("/") and endpoint not in info.http_endpoints:
                info.http_endpoints.append(endpoint)

        return info
