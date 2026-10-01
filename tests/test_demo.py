"""Unit and integration tests for caps demo."""
from __future__ import annotations

from pathlib import Path
from click.testing import CliRunner
from rich.console import Console

from capsule_cli.demo.comparator import count_tokens, format_token_savings
from capsule_cli.demo.fixtures import DEMO_CAPSULES, RAW_BLOATED_CONVERSATION
from capsule_cli.demo.runner import DemoExperience
from capsule_cli.main import cli


class TestDemoFixturesAndComparator:
    def test_demo_fixtures_validity(self):
        assert len(DEMO_CAPSULES) >= 5
        for cap in DEMO_CAPSULES:
            assert "topic" in cap
            assert "content" in cap
            assert "tags" in cap
            assert len(cap["tags"]) > 0

    def test_token_counter(self):
        text = "Hello world from Capsule atomic memory."
        tokens = count_tokens(text)
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_format_token_savings(self):
        raw_tokens = 2000
        caps_tokens = 400
        savings_pct, ratio = format_token_savings(raw_tokens, caps_tokens)
        assert savings_pct == 80.0
        assert ratio == 5.0


class TestDemoRunner:
    def test_demo_runner_non_interactive(self, tmp_path, monkeypatch):
        # Ensure it runs in isolation
        console = Console(record=True, width=100)
        demo = DemoExperience(console=console, interactive=False)
        
        # Working dir should remain clean
        before_files = set(Path.cwd().iterdir())
        demo.run()
        after_files = set(Path.cwd().iterdir())
        assert before_files == after_files

        output = console.export_text()
        assert "Capsule Interactive Tour" in output or "Capsule" in output
        assert "Deduplication" in output or "Collision" in output
        assert "Composed Context" in output or "Token Savings" in output

    def test_demo_cli_command(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["demo", "--non-interactive"])
        assert result.exit_code == 0
        assert "Capsule" in result.output
        assert "Savings" in result.output or "tokens" in result.output.lower()
