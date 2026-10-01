import os
import subprocess
from pathlib import Path
import pytest
from click.testing import CliRunner

from capsule_cli.main import cli, install_git_post_commit_hook
from services.ingest.code_decomposer import CodeDecomposer
from services.shared.models import Capsule
from services.store.store import CapsuleStore


@pytest.fixture
def mock_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Configure git
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=str(repo_dir), check=True, capture_output=True)

    # Initial commit
    init_file = repo_dir / "init.txt"
    init_file.write_text("initial commit file", encoding="utf-8")
    subprocess.run(["git", "add", "init.txt"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(repo_dir), check=True, capture_output=True)

    return repo_dir


def test_git_hook_installer(mock_git_repo):
    hook_path = install_git_post_commit_hook(mock_git_repo)
    assert hook_path.exists()
    assert os.access(str(hook_path), os.X_OK)
    content = hook_path.read_text(encoding="utf-8")
    assert "caps ingest --git-diff HEAD~1" in content


def test_cli_hook_commands(mock_git_repo):
    runner = CliRunner()
    result = runner.invoke(cli, ["hook", "install", "--repo", str(mock_git_repo)])
    assert result.exit_code == 0
    assert "Installed Capsule post-commit hook" in result.output

    status_result = runner.invoke(cli, ["hook", "status", "--repo", str(mock_git_repo)])
    assert status_result.exit_code == 0
    assert "Post-commit hook is active" in status_result.output


def test_incremental_git_ingest_add_modify_delete(mock_git_repo, db_session, tmp_path):
    caps_dir = tmp_path / "capsules"
    caps_dir.mkdir(exist_ok=True)
    store = CapsuleStore(db=db_session, capsules_dir=caps_dir)
    decomposer = CodeDecomposer(store=store)

    # 1. Add a python service file and commit
    srv = mock_git_repo / "service.py"
    srv.write_text(
        '"""Authentication service module."""\n\n'
        "class AuthService:\n"
        '    """Handles user auth."""\n'
        "    def login(self, username: str) -> bool:\n"
        '        """Perform login."""\n'
        "        return True\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "service.py"], cwd=str(mock_git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: add auth service"], cwd=str(mock_git_repo), check=True, capture_output=True)

    # Run ingest_git_diff HEAD~1
    res1 = decomposer.ingest_git_diff(mock_git_repo, diff_rev="HEAD~1")
    assert res1.total_files == 1
    assert res1.total_classes == 1
    assert res1.total_functions == 1
    assert res1.created_count == 3

    auth_caps = db_session.query(Capsule).filter(Capsule.topic == "Class: AuthService").first()
    assert auth_caps is not None
    assert "Handles user auth." in auth_caps.content

    # 2. Modify python service and add Go handler in a second commit
    srv.write_text(
        '"""Authentication service module updated."""\n\n'
        "class AuthService:\n"
        '    """Handles enterprise user auth."""\n'
        "    def login(self, username: str) -> bool:\n"
        '        """Perform login."""\n'
        "        return True\n"
        "    def logout(self) -> None:\n"
        '        """Perform logout."""\n'
        "        pass\n",
        encoding="utf-8",
    )
    go_handler = mock_git_repo / "handler.go"
    go_handler.write_text(
        "package auth\n\n"
        "type SessionManager struct {}\n\n"
        "func (s *SessionManager) ValidateSession(token string) bool {\n"
        "    return true\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "service.py", "handler.go"], cwd=str(mock_git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: update auth and add go handler"], cwd=str(mock_git_repo), check=True, capture_output=True)

    res2 = decomposer.ingest_git_diff(mock_git_repo, diff_rev="HEAD~1")
    assert res2.total_files == 2
    assert res2.total_classes == 2  # AuthService + SessionManager
    assert res2.total_functions == 3  # login + logout + ValidateSession

    # Verify updated content
    auth_caps_updated = db_session.query(Capsule).filter(Capsule.topic == "Class: AuthService").first()
    assert auth_caps_updated is not None
    assert "Handles enterprise user auth." in auth_caps_updated.content

    # 3. Delete service.py in a third commit
    srv.unlink()
    subprocess.run(["git", "add", "service.py"], cwd=str(mock_git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "refactor: remove service.py"], cwd=str(mock_git_repo), check=True, capture_output=True)

    res3 = decomposer.ingest_git_diff(mock_git_repo, diff_rev="HEAD~1")
    assert res3.deleted_count >= 1

    # Verify AuthService capsule is deleted
    auth_caps_deleted = db_session.query(Capsule).filter(Capsule.topic == "Class: AuthService").first()
    assert auth_caps_deleted is None

    # Go SessionManager should still exist
    go_caps = db_session.query(Capsule).filter(Capsule.topic == "Struct: SessionManager").first()
    assert go_caps is not None


def test_incremental_git_ingest_dry_run(mock_git_repo, db_session, tmp_path):
    caps_dir = tmp_path / "capsules"
    caps_dir.mkdir(exist_ok=True)
    store = CapsuleStore(db=db_session, capsules_dir=caps_dir)
    decomposer = CodeDecomposer(store=store)

    srv = mock_git_repo / "test.ts"
    srv.write_text(
        "export interface Config {\n  api_url: string;\n}\n\nexport function setup(): void {}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "test.ts"], cwd=str(mock_git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: add ts"], cwd=str(mock_git_repo), check=True, capture_output=True)

    res = decomposer.ingest_git_diff(mock_git_repo, diff_rev="HEAD~1", dry_run=True)
    assert res.total_files == 1
    assert res.total_classes == 1  # 1 interface
    assert res.total_functions == 1  # 1 function
    assert len(res.created_capsules) == 0
