"""Unit and integration tests for Git Commit and Merged PR Harvester."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from capsule_cli.main import cli
from services.ingest.git_harvester import GitHarvester, GitHarvestItem
from services.ingest.pr_harvester import PRHarvester
from services.store.store import CapsuleStore


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a mock git repository with diverse commit messages."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    def git(*args):
        subprocess.run(
            ["git", "-C", str(repo_dir)] + list(args),
            check=True,
            capture_output=True,
            text=True,
        )

    git("init")
    git("config", "user.name", "Test Committer")
    git("config", "user.email", "test@capsule.dev")

    # 1. Architectural Feature Commit
    (repo_dir / "auth.py").write_text("def auth(): pass", encoding="utf-8")
    git("add", "auth.py")
    git(
        "commit",
        "-m",
        "feat(auth): staging bypass requires X-Debug-Override header\n\nWhen testing on mobile CI, staging allows bypassing JWT authentication when the debug override header is passed.",
    )

    # 2. Critical Bug Fix Invariant
    (repo_dir / "db.py").write_text("def db(): pass", encoding="utf-8")
    git("add", "db.py")
    git(
        "commit",
        "-m",
        "fix(db): pool size upper limit to prevent Postgres exhaustion\n\nSet maximum connection pool size to 2x CPU cores plus spindle count.",
    )

    # 3. Trivial Chore (should be skipped)
    (repo_dir / "version.txt").write_text("1.0.1", encoding="utf-8")
    git("add", "version.txt")
    git("commit", "-m", "chore(deps): bump version to 1.0.1")

    # 4. Trivial Formatting (should be skipped)
    (repo_dir / "style.py").write_text("# style", encoding="utf-8")
    git("add", "style.py")
    git("commit", "-m", "style: format code with black")

    # 5. Non-conventional commit with strong keyword signal
    (repo_dir / "cache.py").write_text("# cache", encoding="utf-8")
    git("add", "cache.py")
    git(
        "commit",
        "-m",
        "Workaround for redis deadlock under high concurrency\n\nAcquire distributed lock with 500ms timeout to avoid thread contention.",
    )

    return repo_dir


class TestGitHarvester:
    def test_extract_candidates_filters_noise(self, temp_git_repo):
        harvester = GitHarvester()
        candidates = harvester.extract_candidates(temp_git_repo, depth=10)

        # Should extract 3 semantic commits (auth feat, db fix, redis workaround) and ignore chore & style
        assert len(candidates) == 3

        topics = [c.topic for c in candidates]
        assert any("Staging bypass requires X-Debug-Override header" in t for t in topics)
        assert any("Pool size upper limit to prevent Postgres exhaustion" in t for t in topics)
        assert any("Workaround for redis deadlock" in t for t in topics)

        # Check metadata
        for c in candidates:
            assert isinstance(c, GitHarvestItem)
            assert c.sha
            assert c.short_sha
            assert c.source.startswith("git:")
            assert len(c.tags) >= 1
            assert "git" in c.tags
            assert len(c.content) >= 15

    def test_extract_candidates_type_filter(self, temp_git_repo):
        harvester = GitHarvester()
        fix_only = harvester.extract_candidates(temp_git_repo, depth=10, types=["fix"])

        assert len(fix_only) == 1
        assert "Pool size upper limit" in fix_only[0].topic
        assert "db" in fix_only[0].tags
        assert "fix" in fix_only[0].tags

    def test_harvest_ingests_into_store(self, temp_git_repo, db_session, tmp_path):
        caps_dir = tmp_path / "caps_git_harvest"
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        harvester = GitHarvester()
        result = harvester.harvest(temp_git_repo, store=store, depth=10)

        assert result.total_units == 3
        assert result.created_count == 3
        assert result.deduped_count == 0

        # Verify files created on disk
        caps_files = list(caps_dir.glob("*.caps.md"))
        assert len(caps_files) == 3

    def test_harvest_dry_run_creates_zero_files(self, temp_git_repo, db_session, tmp_path):
        caps_dir = tmp_path / "caps_git_dry"
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        harvester = GitHarvester()
        result = harvester.harvest(temp_git_repo, store=store, depth=10, dry_run=True)

        assert result.total_units == 3
        assert result.created_count == 0
        assert len(list(caps_dir.glob("*.caps.md"))) == 0

    def test_harvest_idempotency(self, temp_git_repo, db_session, tmp_path):
        caps_dir = tmp_path / "caps_git_idempotent"
        store = CapsuleStore(db_session, capsules_dir=caps_dir)

        harvester = GitHarvester()
        # First run
        res1 = harvester.harvest(temp_git_repo, store=store, depth=10)
        assert res1.created_count == 3

        # Second run should deduplicate all 3
        res2 = harvester.harvest(temp_git_repo, store=store, depth=10)
        assert res2.created_count == 0
        assert res2.deduped_count == 3


class TestPRHarvester:
    def test_extract_merged_prs_mocked(self, tmp_path):
        harvester = PRHarvester()
        mock_gh_output = [
            {
                "number": 42,
                "title": "feat(api): token refresh invariant",
                "body": "Ensure tokens are refreshed every 15 minutes to prevent stale session attacks.",
                "author": {"login": "octocat"},
                "mergedAt": "2026-09-30T10:00:00Z",
                "labels": [{"name": "security"}, {"name": "backend"}],
            },
            {
                "number": 43,
                "title": "chore: bump dependencies",
                "body": "routine bump",
                "author": {"login": "bot"},
                "mergedAt": "2026-09-30T11:00:00Z",
                "labels": [],
            },
        ]

        with patch.object(harvester, "is_gh_available", return_value=True):
            with patch("subprocess.run") as mock_run:
                import json

                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = json.dumps(mock_gh_output)

                items = harvester.extract_merged_prs(tmp_path, limit=10)

                # Should filter out chore PR 43 and keep security PR 42
                assert len(items) == 1
                item = items[0]
                assert item.source == "pr:#42"
                assert "token refresh invariant" in item.topic.lower()
                assert "security" in item.tags
                assert "backend" in item.tags
                assert item.author == "octocat"


class TestCliCommands:
    def test_ingest_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--git" in result.output
        assert "--depth" in result.output
        assert "--types" in result.output
        assert "--prs" in result.output

    def test_ingest_git_dry_run_cli(self, temp_git_repo, tmp_path):
        runner = CliRunner()
        caps_dir = tmp_path / "caps_cli_test"
        result = runner.invoke(
            cli,
            ["ingest", str(temp_git_repo), "--git", "--depth", "10", "--dry-run", "--dir", str(caps_dir)],
        )
        assert result.exit_code == 0
        assert "Capsule Git History Harvester" in result.output
        assert "Dry Run Complete" in result.output

    def test_ingest_git_execution_cli(self, temp_git_repo, tmp_path):
        runner = CliRunner()
        caps_dir = tmp_path / "caps_cli_exec"
        result = runner.invoke(
            cli,
            ["ingest", str(temp_git_repo), "--git", "--depth", "10", "--dir", str(caps_dir)],
        )
        assert result.exit_code == 0
        assert "Git harvesting complete!" in result.output
        assert len(list(caps_dir.glob("*.caps.md"))) == 3
