"""Unit and integration tests for CI linter, invariant gatekeeper, and CLI."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from capsule_cli.ci import InvariantAlert, LintIssue, LintReport
from capsule_cli.ci.linter import CapsuleLinter
from capsule_cli.ci.pr_diff import PRDiffChecker
from capsule_cli.ci.summary import generate_markdown_summary, write_github_step_summary
from capsule_cli.main import cli


class TestCapsuleLinter:
    def test_lint_valid_capsule_content(self):
        content = """---
id: 11111111-1111-1111-1111-111111111111
topic: PostgreSQL Connection Pooling
tags: [postgres, database, performance]
confidence: high
source: dba_handbook
freshness: 2026-09-30T12:00:00Z
---

Set PgBouncer pool mode to transaction for optimal web server concurrency.
"""
        linter = CapsuleLinter()
        issues, fm, body = linter.lint_file_content(content)

        # There should be zero errors or warnings
        assert len(issues) == 0
        assert fm["topic"] == "PostgreSQL Connection Pooling"
        assert fm["confidence"] == "high"
        assert "PgBouncer" in body

    def test_lint_yaml_syntax_error(self):
        content = """---
id: 11111111-1111-1111-1111-111111111111
topic: Invalid YAML
tags: [unclosed list
---

Some valid body text here.
"""
        linter = CapsuleLinter()
        issues, _, _ = linter.lint_file_content(content)

        syntax_errors = [i for i in issues if i.rule == "schema/yaml-syntax"]
        assert len(syntax_errors) >= 1
        assert syntax_errors[0].level == "error"

    def test_lint_invalid_confidence(self):
        content = """---
id: 11111111-1111-1111-1111-111111111111
topic: Invalid Confidence
confidence: totally_sure
---

Body content with enough characters to pass validation.
"""
        linter = CapsuleLinter()
        issues, _, _ = linter.lint_file_content(content)

        conf_errors = [i for i in issues if i.rule == "schema/invalid-confidence"]
        assert len(conf_errors) == 1
        assert "Must be one of" in conf_errors[0].message

    def test_lint_short_topic_and_content(self):
        content = """---
id: 11111111-1111-1111-1111-111111111111
topic: ab
---

short
"""
        linter = CapsuleLinter()
        issues, _, _ = linter.lint_file_content(content)

        rules = {i.rule for i in issues}
        assert "schema/topic-too-short" in rules
        assert "schema/content-too-short" in rules

    def test_lint_invalid_tags(self):
        content = """---
id: 11111111-1111-1111-1111-111111111111
topic: Bad Tags
tags: "not-a-list"
---

Body content with enough characters to pass validation.
"""
        linter = CapsuleLinter()
        issues, _, _ = linter.lint_file_content(content)

        tag_errors = [i for i in issues if i.rule == "schema/invalid-tags-type"]
        assert len(tag_errors) == 1

    def test_lint_directory_clean(self, tmp_path):
        cap_dir = tmp_path / "valid_caps"
        cap_dir.mkdir()

        (cap_dir / "cap1.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: First Architecture Rule
tags: [arch]
confidence: high
---

Always isolate database operations behind domain repositories.
""",
            encoding="utf-8",
        )
        (cap_dir / "cap2.caps.md").write_text(
            """---
id: 22222222-2222-2222-2222-222222222222
topic: Second Architecture Rule
tags: [arch]
confidence: medium
relationships:
  - to: 11111111-1111-1111-1111-111111111111
    type: depends_on
---

Repositories should wrap SQLAlchemy queries inside session scope.
""",
            encoding="utf-8",
        )

        linter = CapsuleLinter()
        report = linter.lint_directory(cap_dir)

        assert report.is_success
        assert report.total_scanned == 2
        assert report.passed_count == 2
        assert len(report.errors) == 0
        assert len(report.broken_relationships) == 0

    def test_lint_directory_broken_relationship(self, tmp_path):
        cap_dir = tmp_path / "broken_caps"
        cap_dir.mkdir()

        (cap_dir / "cap1.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: First Architecture Rule
tags: [arch]
relationships:
  - to: 99999999-9999-9999-9999-999999999999
---

Always isolate database operations behind domain repositories.
""",
            encoding="utf-8",
        )

        linter = CapsuleLinter()
        report = linter.lint_directory(cap_dir)

        assert not report.is_success
        assert len(report.broken_relationships) == 1
        assert "99999999-9999-9999-9999-999999999999" in report.broken_relationships[0].message

    def test_lint_directory_duplicate_id(self, tmp_path):
        cap_dir = tmp_path / "dup_caps"
        cap_dir.mkdir()

        (cap_dir / "cap1.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: First Rule
---

Content text for first rule.
""",
            encoding="utf-8",
        )
        (cap_dir / "cap2.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: Second Rule Duplicate ID
---

Content text for second rule with same UUID.
""",
            encoding="utf-8",
        )

        linter = CapsuleLinter()
        report = linter.lint_directory(cap_dir)

        assert not report.is_success
        dup_errors = [e for e in report.errors if e.rule == "schema/duplicate-id"]
        assert len(dup_errors) == 1


class TestPRDiffChecker:
    def test_check_invariants_direct_match(self, tmp_path):
        cap_dir = tmp_path / "caps_invariants"
        cap_dir.mkdir()

        (cap_dir / "auth.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: Auth Middleware Header Invariant
tags: [auth, security]
confidence: high
file_path: services/auth/middleware.py
---

Never remove the X-Debug-Override bypass header in staging environment.
""",
            encoding="utf-8",
        )

        checker = PRDiffChecker()
        changed = ["services/auth/middleware.py", "README.md"]
        alerts = checker.check_invariants(changed, cap_dir)

        assert len(alerts) >= 1
        alert = alerts[0]
        assert isinstance(alert, InvariantAlert)
        assert alert.affected_file == "services/auth/middleware.py"
        assert alert.confidence == "high"
        assert alert.match_type == "direct_path"

    def test_check_invariants_tag_match(self, tmp_path):
        cap_dir = tmp_path / "caps_invariants_tag"
        cap_dir.mkdir()

        (cap_dir / "pg.caps.md").write_text(
            """---
id: 22222222-2222-2222-2222-222222222222
topic: Database Pool Limits
tags: [postgres, database]
confidence: high
---

Set max connection pool to 50 connections max.
""",
            encoding="utf-8",
        )

        checker = PRDiffChecker()
        changed = ["services/postgres/connector.py"]
        alerts = checker.check_invariants(changed, cap_dir)

        assert len(alerts) >= 1
        assert alerts[0].affected_file == "services/postgres/connector.py"
        assert alerts[0].match_type == "tag_match"


class TestSummaryFormatter:
    def test_generate_markdown_summary(self):
        report = LintReport(
            total_scanned=5,
            passed_count=4,
            errors=[
                LintIssue(
                    file_path="caps/bad.caps.md",
                    rule="schema/missing-topic",
                    message="Missing topic",
                    level="error",
                    line_number=2,
                )
            ],
            warnings=[
                LintIssue(
                    file_path="caps/warn.caps.md",
                    rule="schema/missing-id",
                    message="Missing UUID",
                    level="warning",
                )
            ],
            invariant_alerts=[
                InvariantAlert(
                    capsule_id="11111111-1111-1111-1111-111111111111",
                    capsule_topic="Auth Invariant",
                    capsule_file="caps/auth.caps.md",
                    confidence="high",
                    affected_file="services/auth.py",
                    match_type="direct_path",
                    summary="Explicit reference",
                )
            ],
        )

        md = generate_markdown_summary(report)
        assert "### ❌ Capsule Invariant & Schema Check" in md
        assert "Capsules Scanned**: `5`" in md
        assert "Schema Errors**: `1`" in md
        assert "`bad.caps.md`" in md
        assert "Auth Invariant" in md

    def test_write_github_step_summary(self, tmp_path, monkeypatch):
        summary_file = tmp_path / "step_summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        success = write_github_step_summary("# Hello Action")
        assert success
        assert summary_file.exists()
        assert "# Hello Action" in summary_file.read_text(encoding="utf-8")


class TestCliCommands:
    def test_ci_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ci", "--help"])
        assert result.exit_code == 0
        assert "check" in result.output

    def test_lint_alias_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["lint", "--help"])
        assert result.exit_code == 0
        assert "Verify schema integrity" in result.output

    def test_ci_check_valid_directory(self, tmp_path):
        cap_dir = tmp_path / "test_caps"
        cap_dir.mkdir()
        (cap_dir / "rule.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: Valid Capsule Rule
tags: [ci]
confidence: high
---

This is valid body content for capsule validation.
""",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["ci", "check", str(cap_dir), "--no-diff"])
        assert result.exit_code == 0
        assert "Passed" in result.output

    def test_ci_check_json_output(self, tmp_path):
        cap_dir = tmp_path / "test_caps_json"
        cap_dir.mkdir()
        (cap_dir / "rule.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: Valid Capsule Rule
tags: [ci]
confidence: high
---

This is valid body content for capsule validation.
""",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["ci", "check", str(cap_dir), "--no-diff", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["total_scanned"] == 1
        assert parsed["is_success"] is True

    def test_ci_check_invalid_directory_fails(self, tmp_path):
        cap_dir = tmp_path / "test_caps_invalid"
        cap_dir.mkdir()
        (cap_dir / "bad.caps.md").write_text(
            """---
topic: ab
---

short
""",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["ci", "check", str(cap_dir), "--no-diff"])
        assert result.exit_code == 1
        assert "Failed" in result.output

    def test_ci_check_output_md(self, tmp_path):
        cap_dir = tmp_path / "test_caps_md"
        cap_dir.mkdir()
        (cap_dir / "rule.caps.md").write_text(
            """---
id: 11111111-1111-1111-1111-111111111111
topic: Valid Capsule Rule
tags: [ci]
confidence: high
---

This is valid body content for capsule validation.
""",
            encoding="utf-8",
        )
        out_md = tmp_path / "summary_out.md"
        runner = CliRunner()
        result = runner.invoke(cli, ["ci", "check", str(cap_dir), "--no-diff", "--output-md", str(out_md)])
        assert result.exit_code == 0
        assert out_md.exists()
        assert "Capsule Invariant & Schema Check" in out_md.read_text(encoding="utf-8")
