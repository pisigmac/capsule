"""
Java (.java) source parser.
Extracts packages, imports, classes, interfaces, records, and methods
using deterministic structural AST and regex parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .python_parser import stable_id

PACKAGE_RE = re.compile(r"""^\s*package\s+([a-zA-Z_][\w.]*);""", re.MULTILINE)
IMPORT_RE = re.compile(r"""^\s*import\s+(?:static\s+)?([a-zA-Z_][\w.*]*);""", re.MULTILINE)
CLASS_RE = re.compile(
    r"""(?:(?:public|protected|private|abstract|final|static)\s+)*class\s+([A-Z]\w*)(?:<[^>]+>)?(?:\s+extends\s+([A-Z]\w*))?(?:\s+implements\s+([^{]+))?\s*\{""",
    re.MULTILINE,
)
INTERFACE_RE = re.compile(
    r"""(?:(?:public|protected|private|abstract|static)\s+)*interface\s+([A-Z]\w*)(?:<[^>]+>)?(?:\s+extends\s+([^{]+))?\s*\{""",
    re.MULTILINE,
)
RECORD_RE = re.compile(
    r"""(?:(?:public|protected|private|final|static)\s+)*record\s+([A-Z]\w*)(?:<[^>]+>)?\s*\(([^)]*)\)""",
    re.MULTILINE,
)
METHOD_RE = re.compile(
    r"""(?:(?:public|protected|private|static|final|synchronized|abstract|default)\s+)+(?:<[^>]+>\s+)?([a-zA-Z_]\w*(?:<[^>]+>)?(?:\[\])?)\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)(?:\s*throws\s+[^{;]+)?\s*[{;]""",
    re.MULTILINE,
)


@dataclass
class JavaMethodInfo:
    id: str
    name: str
    qualified_name: str
    file_path: str
    class_name: Optional[str]
    params: str
    returns: Optional[str]
    docstring: Optional[str] = None
    calls: List[str] = field(default_factory=list)


@dataclass
class JavaClassInfo:
    id: str
    name: str
    file_path: str
    kind: str  # "class" | "interface" | "record"
    extends: Optional[str] = None
    implements: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[str] = field(default_factory=list)


@dataclass
class JavaFileInfo:
    id: str
    path: str
    dir_path: str
    package: str
    loc: int
    imports: List[str] = field(default_factory=list)
    classes: Dict[str, JavaClassInfo] = field(default_factory=dict)
    methods: List[JavaMethodInfo] = field(default_factory=list)


class JavaCodeParser:
    """Parses Java source files into structural models."""

    def parse_code(self, rel_path: str, source: str) -> JavaFileInfo:
        file_id = stable_id("java_file", rel_path)
        dir_path = str(Path(rel_path).parent)
        if dir_path == ".":
            dir_path = ""
        loc = source.count("\n") + 1

        pkg_match = PACKAGE_RE.search(source)
        package = pkg_match.group(1) if pkg_match else "default"

        info = JavaFileInfo(
            id=file_id,
            path=rel_path,
            dir_path=dir_path,
            package=package,
            loc=loc,
        )

        # 1. Imports
        for match in IMPORT_RE.finditer(source):
            imp = match.group(1).strip()
            if imp not in info.imports:
                info.imports.append(imp)

        # 2. Classes
        for match in CLASS_RE.finditer(source):
            name = match.group(1).strip()
            ext = match.group(2).strip() if match.group(2) else None
            impl_str = match.group(3).strip() if match.group(3) else ""
            impls = [i.strip() for i in impl_str.split(",") if i.strip()]
            cid = stable_id("java_class", rel_path, name)
            info.classes[name] = JavaClassInfo(
                id=cid,
                name=name,
                file_path=rel_path,
                kind="class",
                extends=ext,
                implements=impls,
            )

        # 3. Interfaces
        for match in INTERFACE_RE.finditer(source):
            name = match.group(1).strip()
            ext_str = match.group(2).strip() if match.group(2) else ""
            exts = [e.strip() for e in ext_str.split(",") if e.strip()]
            cid = stable_id("java_class", rel_path, name)
            info.classes[name] = JavaClassInfo(
                id=cid,
                name=name,
                file_path=rel_path,
                kind="interface",
                implements=exts,
            )

        # 4. Records
        for match in RECORD_RE.finditer(source):
            name = match.group(1).strip()
            cid = stable_id("java_class", rel_path, name)
            info.classes[name] = JavaClassInfo(
                id=cid,
                name=name,
                file_path=rel_path,
                kind="record",
            )

        # 5. Methods
        for match in METHOD_RE.finditer(source):
            ret = match.group(1).strip()
            name = match.group(2).strip()
            params = match.group(3).strip()
            mid = stable_id("java_method", rel_path, name)

            # Ignore control structures
            if name in {"if", "while", "for", "switch", "catch"}:
                continue

            info.methods.append(
                JavaMethodInfo(
                    id=mid,
                    name=name,
                    qualified_name=name,
                    file_path=rel_path,
                    class_name=None,
                    params=params,
                    returns=ret,
                )
            )

        return info
