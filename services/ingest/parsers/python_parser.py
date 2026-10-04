"""
Python source AST parser and call-graph resolver.
Extracts module-level imports, classes (with inheritance), functions, docstrings,
signatures, type annotations, cyclomatic complexity, and resolves call-graph edges.
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


IGNORED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".idea", ".vscode",
    ".gemini", "data", "coverage", ".next"
}


def stable_id(*parts: str) -> str:
    """Deterministic node id so re-scans update in place rather than duplicate capsules."""
    raw = "::".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class VariableInfo:
    name: str
    kind: str  # "param" | "local" | "return"
    annotation: Optional[str] = None
    default: Optional[str] = None


@dataclass
class ResolvedCall:
    target_id: str
    target_func_name: str
    target_file_path: str


@dataclass
class FunctionInfo:
    id: str
    name: str
    qualified_name: str  # e.g., Module.Class.method or Module.func
    file_path: str
    class_name: Optional[str]
    docstring: Optional[str]
    signature: str
    params: List[VariableInfo] = field(default_factory=list)
    returns_annotation: Optional[str] = None
    calls: List[str] = field(default_factory=list)
    resolved_calls: List[ResolvedCall] = field(default_factory=list)
    lineno_start: int = 0
    lineno_end: int = 0
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)
    complexity: int = 1


@dataclass
class ClassInfo:
    id: str
    name: str
    qualified_name: str
    file_path: str
    docstring: Optional[str]
    bases: List[str] = field(default_factory=list)
    resolved_bases: List[str] = field(default_factory=list)  # class IDs
    methods: List[str] = field(default_factory=list)  # function IDs
    lineno_start: int = 0
    lineno_end: int = 0
    decorators: List[str] = field(default_factory=list)


@dataclass
class FileInfo:
    id: str
    path: str
    dir_path: str
    imports: List[str] = field(default_factory=list)
    resolved_imports: List[str] = field(default_factory=list)  # file IDs
    classes: List[str] = field(default_factory=list)  # class names
    class_defs: Dict[str, ClassInfo] = field(default_factory=dict)
    functions: List[FunctionInfo] = field(default_factory=list)
    loc: int = 0
    has_syntax_error: bool = False
    commit_author: Optional[str] = None
    commit_message: Optional[str] = None
    commit_date: Optional[str] = None


@dataclass
class RepoModel:
    root: str
    files: Dict[str, FileInfo] = field(default_factory=dict)
    classes: Dict[str, ClassInfo] = field(default_factory=dict)
    functions: Dict[str, FunctionInfo] = field(default_factory=dict)


def _unparse(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _calc_complexity(node: ast.AST) -> int:
    """Cyclomatic complexity heuristic."""
    count = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor,
                              ast.ExceptHandler, ast.With, ast.AsyncWith,
                              ast.Assert, ast.IfExp)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
    return count


class _CallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: List[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)


class PythonCodeParser:
    """Parses a Python source file using AST into structured FileInfo, ClassInfo, and FunctionInfo."""

    def parse_code(self, rel_path: str, source_code: str) -> FileInfo:
        file_id = stable_id("file", rel_path)
        dir_path = str(Path(rel_path).parent)
        if dir_path == ".":
            dir_path = ""
        loc = source_code.count("\n") + 1

        file_info = FileInfo(
            id=file_id,
            path=rel_path,
            dir_path=dir_path,
            loc=loc,
        )

        try:
            tree = ast.parse(source_code, filename=rel_path)
        except SyntaxError:
            file_info.has_syntax_error = True
            return file_info

        # 1. Imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    file_info.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    file_info.imports.append(f"{mod}.{alias.name}" if mod else alias.name)

        # 2. Classes and Functions
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_info = self._parse_function(node, rel_path, class_name=None)
                file_info.functions.append(fn_info)

            elif isinstance(node, ast.ClassDef):
                cls_info = self._parse_class(node, rel_path)
                file_info.classes.append(node.name)
                file_info.class_defs[node.name] = cls_info

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_info = self._parse_function(item, rel_path, class_name=node.name)
                        file_info.functions.append(method_info)
                        cls_info.methods.append(method_info.id)

        return file_info

    def _parse_class(self, node: ast.ClassDef, rel_path: str) -> ClassInfo:
        cls_id = stable_id("class", rel_path, node.name)
        doc = ast.get_docstring(node)
        bases = [_unparse(b) for b in node.bases if _unparse(b) is not None]
        decorators = [_unparse(d) for d in node.decorator_list if _unparse(d) is not None]

        return ClassInfo(
            id=cls_id,
            name=node.name,
            qualified_name=node.name,
            file_path=rel_path,
            docstring=doc.strip() if doc else None,
            bases=bases,
            lineno_start=node.lineno,
            lineno_end=getattr(node, "end_lineno", node.lineno),
            decorators=decorators,
        )

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        rel_path: str,
        class_name: Optional[str],
    ) -> FunctionInfo:
        qname = f"{class_name}.{node.name}" if class_name else node.name
        fn_id = stable_id("fn", rel_path, qname)
        doc = ast.get_docstring(node)

        # Params
        params: List[VariableInfo] = []
        args = node.args
        for arg in args.posonlyargs + args.args:
            if arg.arg in ("self", "cls"):
                continue
            ann = _unparse(arg.annotation)
            params.append(VariableInfo(name=arg.arg, kind="param", annotation=ann))

        if args.vararg:
            params.append(VariableInfo(name=f"*{args.vararg.arg}", kind="param"))
        for arg in args.kwonlyargs:
            ann = _unparse(arg.annotation)
            params.append(VariableInfo(name=arg.arg, kind="param", annotation=ann))
        if args.kwarg:
            params.append(VariableInfo(name=f"**{args.kwarg.arg}", kind="param"))

        # Returns
        returns_ann = _unparse(node.returns)

        # Signature string
        param_strs = [
            f"{p.name}: {p.annotation}" if p.annotation else p.name
            for p in params
        ]
        ret_str = f" -> {returns_ann}" if returns_ann else ""
        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        sig = f"{async_prefix}def {node.name}({', '.join(param_strs)}){ret_str}"

        # Calls
        call_visitor = _CallVisitor()
        for stmt in node.body:
            call_visitor.visit(stmt)

        decorators = [_unparse(d) for d in node.decorator_list if _unparse(d) is not None]
        complexity = _calc_complexity(node)

        return FunctionInfo(
            id=fn_id,
            name=node.name,
            qualified_name=qname,
            file_path=rel_path,
            class_name=class_name,
            docstring=doc.strip() if doc else None,
            signature=sig,
            params=params,
            returns_annotation=returns_ann,
            calls=list(dict.fromkeys(call_visitor.calls)),
            lineno_start=node.lineno,
            lineno_end=getattr(node, "end_lineno", node.lineno),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
            complexity=complexity,
        )


def _get_git_blame(root: Path, rel_path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Fetch latest commit author, date, and message for a file."""
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%an|%ad|%s", "--", rel_path],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split("|", 2)
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]
    except Exception:
        pass
    return None, None, None


def scan_python_repo(repo_root: str) -> RepoModel:
    """Scans all Python files in a directory and resolves cross-file call and inheritance graphs."""
    root = Path(repo_root).resolve()
    parser = PythonCodeParser()
    model = RepoModel(root=str(root))

    # 1. Parse all files
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for fname in filenames:
            if fname.endswith(".py"):
                full_path = Path(dirpath) / fname
                rel_path = str(full_path.relative_to(root)).replace("\\", "/")
                source_code = full_path.read_text(encoding="utf-8", errors="replace")
                file_info = parser.parse_code(rel_path, source_code)

                # Add git rationale if repository
                author, date_str, msg = _get_git_blame(root, rel_path)
                file_info.commit_author = author
                file_info.commit_date = date_str
                file_info.commit_message = msg

                model.files[rel_path] = file_info
                for cls_name, cls_info in file_info.class_defs.items():
                    model.classes[cls_info.id] = cls_info
                for fn_info in file_info.functions:
                    model.functions[fn_info.id] = fn_info

    # 2. Build Symbol Tables
    fn_by_name: Dict[str, List[FunctionInfo]] = {}
    cls_by_name: Dict[str, List[ClassInfo]] = {}
    file_by_mod: Dict[str, str] = {}  # "pkg.helper" -> "pkg/helper.py"

    for rel_path in model.files:
        mod_key = rel_path[:-3].replace("/", ".")
        file_by_mod[mod_key] = rel_path
        if mod_key.endswith(".__init__"):
            file_by_mod[mod_key[:-9]] = rel_path

    for fn in model.functions.values():
        fn_by_name.setdefault(fn.name, []).append(fn)
    for cls in model.classes.values():
        cls_by_name.setdefault(cls.name, []).append(cls)

    # 3. Resolve Imports, Inheritance, and Function Calls
    for f in model.files.values():
        local_fns = {fn.name: fn for fn in f.functions}
        local_classes = {cls.name: cls for cls in f.class_defs.values()}

        # Resolve imported files
        for imp in f.imports:
            target_rel = file_by_mod.get(imp)
            if not target_rel and "." in imp:
                base_mod = imp.rsplit(".", 1)[0]
                target_rel = file_by_mod.get(base_mod)
            if target_rel and target_rel != f.path:
                target_file = model.files.get(target_rel)
                if target_file and target_file.id not in f.resolved_imports:
                    f.resolved_imports.append(target_file.id)

        # Resolve class inheritance
        for cls in f.class_defs.values():
            for base_name in cls.bases:
                base_cls = local_classes.get(base_name)
                if not base_cls:
                    candidates = cls_by_name.get(base_name, [])
                    if len(candidates) == 1:
                        base_cls = candidates[0]
                if base_cls and base_cls.id != cls.id:
                    cls.resolved_bases.append(base_cls.id)

        # Resolve function calls
        for fn in f.functions:
            for call_name in fn.calls:
                target_fn = local_fns.get(call_name)
                if not target_fn:
                    candidates = fn_by_name.get(call_name, [])
                    if len(candidates) == 1:
                        target_fn = candidates[0]
                if target_fn and target_fn.id != fn.id:
                    fn.resolved_calls.append(
                        ResolvedCall(
                            target_id=target_fn.id,
                            target_func_name=target_fn.name,
                            target_file_path=target_fn.file_path,
                        )
                    )

    return model
