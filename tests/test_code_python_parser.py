"""Tests for Python AST Parser and Call Graph Resolver."""
import tempfile
from pathlib import Path
import pytest

from services.ingest.parsers.python_parser import (
    PythonCodeParser,
    stable_id,
    scan_python_repo,
)


def test_stable_id_deterministic():
    id1 = stable_id("py", "services/store.py", "CapsuleStore.link")
    id2 = stable_id("py", "services/store.py", "CapsuleStore.link")
    id3 = stable_id("py", "services/store.py", "CapsuleStore.get")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 16


def test_parse_python_file_ast():
    code = '''
"""Module docstring for store."""
import os
from pathlib import Path

class BaseStore:
    """Base storage interface."""
    pass

class CapsuleStore(BaseStore):
    """File-first store."""
    
    def __init__(self, db: str):
        self.db = db

    def write_file(self, path: Path) -> bool:
        """Writes file to disk."""
        return True

    def link(self, from_id: str, to_id: str) -> bool:
        """Link two nodes."""
        self.write_file(Path("test"))
        return True
'''
    parser = PythonCodeParser()
    file_info = parser.parse_code("services/store.py", code)

    assert file_info.path == "services/store.py"
    assert "os" in file_info.imports
    assert "pathlib.Path" in file_info.imports or "pathlib" in file_info.imports
    assert len(file_info.classes) == 2
    assert "BaseStore" in file_info.classes
    assert "CapsuleStore" in file_info.classes

    # Check inheritance
    capsule_store_cls = file_info.class_defs.get("CapsuleStore")
    assert capsule_store_cls is not None
    assert "BaseStore" in capsule_store_cls.bases
    assert capsule_store_cls.docstring == "File-first store."

    # Check methods
    assert len(file_info.functions) == 3
    fn_map = {fn.name: fn for fn in file_info.functions}
    assert "link" in fn_map
    link_fn = fn_map["link"]
    assert link_fn.class_name == "CapsuleStore"
    assert "write_file" in link_fn.calls
    assert link_fn.docstring == "Link two nodes."


def test_scan_python_repo_call_resolution():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "pkg").mkdir()
        (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        
        file_a = root / "pkg" / "helper.py"
        file_a.write_text('''
def compute_hash(val: str) -> str:
    """Compute hash helper."""
    return val + "_hashed"
''', encoding="utf-8")

        file_b = root / "pkg" / "service.py"
        file_b.write_text('''
from pkg.helper import compute_hash

def process_item(item: str) -> str:
    """Process an item using compute_hash."""
    return compute_hash(item)
''', encoding="utf-8")

        repo_model = scan_python_repo(str(root))
        assert len(repo_model.files) == 3
        
        # Check that process_item resolves call to compute_hash
        service_file = repo_model.files.get("pkg/service.py")
        assert service_file is not None
        proc_fn = next(f for f in service_file.functions if f.name == "process_item")
        assert "compute_hash" in proc_fn.calls
        assert len(proc_fn.resolved_calls) >= 1
        assert any(call.target_func_name == "compute_hash" for call in proc_fn.resolved_calls)
