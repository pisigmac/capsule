"""
Unit and integration tests for CodeDriftDetector and 'caps verify-drift' CLI command.
"""

from pathlib import Path
import json
import pytest
from click.testing import CliRunner

from capsule_cli.main import cli
from services.analysis.drift_detector import CodeDriftDetector
from services.store.store import CapsuleStore


def test_drift_detector_dead_code(db_session, tmp_path: Path):
    store = CapsuleStore(db=db_session, capsules_dir=tmp_path / "capsules")
    
    file_cap = store.create(
        topic="File: services/utils.py",
        content="Module containing helper functions for services.",
        tags=["code", "python", "file"],
        source="services/utils.py",
        category="code/python",
        confidence="high",
    )
    unused_fn = store.create(
        topic="Function: unused_helper",
        content="Unused helper function with no caller references.",
        tags=["code", "python", "function"],
        source="services/utils.py#L10",
        category="code/python",
        confidence="high",
    )
    # File defines function
    store.link(file_cap.id, unused_fn.id, "defines")
    store.db.commit()

    detector = CodeDriftDetector(store)
    report = detector.analyze()

    assert report.dead_code_count >= 1
    assert any(v.symbol_name == "unused_helper" for v in report.violations)


def test_drift_detector_boundary_violation(db_session, tmp_path: Path):
    store = CapsuleStore(db=db_session, capsules_dir=tmp_path / "capsules")

    fe_file = store.create(
        topic="File: frontend/src/App.tsx",
        content="Frontend App root component and view layout.",
        tags=["code", "typescript", "file"],
        source="frontend/src/App.tsx",
        category="code/typescript",
        confidence="high",
    )
    db_model = store.create(
        topic="Class: CapsuleModel",
        content="SQLAlchemy Model for database storage layer.",
        tags=["code", "python", "class"],
        source="services/shared/models.py#L20",
        category="code/python",
        confidence="high",
    )

    # Frontend directly importing backend DB model
    store.link(fe_file.id, db_model.id, "imports")
    store.db.commit()

    detector = CodeDriftDetector(store)
    report = detector.analyze()

    assert report.boundary_violations_count >= 1
    assert any(v.rule == "boundary/frontend-to-database" for v in report.violations)
    assert not report.is_passing()


def test_drift_detector_circular_dependency(db_session, tmp_path: Path):
    store = CapsuleStore(db=db_session, capsules_dir=tmp_path / "capsules")

    mod_a = store.create(
        topic="File: services/a.py",
        content="Module A providing business services.",
        tags=["code", "python", "file"],
        source="services/a.py",
        category="code/python",
        confidence="high",
    )
    mod_b = store.create(
        topic="File: services/b.py",
        content="Module B providing helper logic.",
        tags=["code", "python", "file"],
        source="services/b.py",
        category="code/python",
        confidence="high",
    )

    # Circular import: A -> B and B -> A
    store.link(mod_a.id, mod_b.id, "imports")
    store.link(mod_b.id, mod_a.id, "imports")
    store.db.commit()

    detector = CodeDriftDetector(store)
    report = detector.analyze()

    assert report.boundary_violations_count >= 1
    assert any(v.rule == "boundary/circular-dependency" for v in report.violations)


def test_verify_drift_cli_json_output(db_session, tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-drift", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total_files_analyzed" in data
    assert "violations" in data
