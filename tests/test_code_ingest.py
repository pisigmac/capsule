"""Tests for CodeDecomposer orchestration and CLI integration."""
import tempfile
from pathlib import Path
import pytest
from click.testing import CliRunner

from capsule_cli.main import cli
from services.shared.config import config
from services.store.store import CapsuleStore
from services.ingest.code_decomposer import CodeDecomposer


def test_code_decomposer_ingest_directory(db_session):
    store = CapsuleStore(db=db_session, capsules_dir=config.capsules_dir)
    
    with tempfile.TemporaryDirectory() as src_dir:
        src = Path(src_dir)
        (src / "services").mkdir()
        
        # 1. Base model file
        (src / "services" / "models.py").write_text('''
"""Domain models."""
class BaseModel:
    pass

class CapsuleModel(BaseModel):
    """Capsule entity model."""
    id: str
    topic: str
''', encoding="utf-8")

        # 2. Logic file with imports and calls
        (src / "services" / "store.py").write_text('''
"""Storage logic."""
from services.models import CapsuleModel

def save_capsule(capsule: CapsuleModel) -> bool:
    """Saves a capsule."""
    return True

def ingest_capsule(data: dict) -> bool:
    """Ingests data."""
    capsule = CapsuleModel()
    return save_capsule(capsule)
''', encoding="utf-8")

        decomposer = CodeDecomposer(store=store)
        result = decomposer.ingest_code_path(src, dry_run=False)

        assert result.total_files == 2
        assert result.created_count >= 4  # files, classes, functions

        # Verify capsules exist on disk
        capsule_files = list(config.capsules_dir.rglob("*.caps.md"))
        assert len(capsule_files) >= 4
        assert result.relationships_linked > 0


def test_code_decomposer_cli_dry_run(db_session):
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as src_dir:
        src = Path(src_dir)
        (src / "demo.py").write_text("def hello(): pass\n", encoding="utf-8")
        
        res = runner.invoke(cli, ["ingest", str(src), "--code", "--dry-run"])
        assert res.exit_code == 0
        assert "Dry Run Complete" in res.output
        assert "Found 1 file" in res.output
