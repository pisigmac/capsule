"""Formatters for CI reports (Terminal, GitHub Step Summary, JSON)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from capsule_cli.ci import LintReport


def render_terminal_report(report: LintReport, console: Optional[Console] = None) -> None:
    """Print a rich formatted summary to the terminal."""
    console = console or Console()

    # Overview Banner
    if report.is_success:
        status_text = f"[bold green]✔ Passed[/bold green] ({report.passed_count}/{report.total_scanned} capsules clean)"
    else:
        status_text = f"[bold red]✖ Failed[/bold red] ({len(report.errors)} errors, {len(report.warnings)} warnings in {report.total_scanned} capsules)"

    console.print()
    console.print(Panel(status_text, title="🛡️ [bold]Capsule CI Gatekeeper[/bold]", expand=False))

    # Print Errors
    if report.errors:
        console.print()
        err_table = Table(title="[bold red]Schema & Link Errors[/bold red]", show_header=True)
        err_table.add_column("File", style="cyan")
        err_table.add_column("Rule", style="magenta")
        err_table.add_column("Line", justify="right", style="yellow")
        err_table.add_column("Message", style="red")

        for err in report.errors:
            err_table.add_row(
                Path(err.file_path).name,
                err.rule,
                str(err.line_number) if err.line_number else "-",
                err.message,
            )
        console.print(err_table)

    # Print Warnings
    if report.warnings:
        console.print()
        warn_table = Table(title="[bold yellow]Warnings[/bold yellow]", show_header=True)
        warn_table.add_column("File", style="cyan")
        warn_table.add_column("Rule", style="magenta")
        warn_table.add_column("Message", style="yellow")

        for warn in report.warnings:
            warn_table.add_row(
                Path(warn.file_path).name,
                warn.rule,
                warn.message,
            )
        console.print(warn_table)

    # Print Invariant Alerts
    if report.invariant_alerts:
        console.print()
        inv_table = Table(title="[bold cyan]⚠️ Architectural Invariant Alerts[/bold cyan]", show_header=True)
        inv_table.add_column("Modified Code File", style="yellow")
        inv_table.add_column("Associated Capsule Topic", style="green")
        inv_table.add_column("Confidence", style="magenta")
        inv_table.add_column("Reason", style="white")

        for alert in report.invariant_alerts:
            inv_table.add_row(
                alert.affected_file,
                alert.capsule_topic[:40],
                alert.confidence,
                alert.summary,
            )
        console.print(inv_table)


def generate_markdown_summary(report: LintReport) -> str:
    """Generate GitHub Step Summary compatible markdown."""
    status_emoji = "✅" if report.is_success else "❌"
    lines = [
        f"### {status_emoji} Capsule Invariant & Schema Check",
        "",
        f"- **Capsules Scanned**: `{report.total_scanned}`",
        f"- **Valid Capsules**: `{report.passed_count}`",
        f"- **Schema Errors**: `{len(report.errors)}`",
        f"- **Warnings**: `{len(report.warnings)}`",
    ]

    if report.broken_relationships:
        lines.append(f"- **Broken Links**: `{len(report.broken_relationships)}`")

    if report.invariant_alerts:
        lines.append(f"- **Invariant Alerts**: `{len(report.invariant_alerts)}`")

    lines.append("")

    if report.errors:
        lines.append("#### ❌ Schema & Link Errors")
        lines.append("| File | Rule | Line | Error Description |")
        lines.append("|---|---|---|---|")
        for err in report.errors:
            file_name = Path(err.file_path).name
            line_str = str(err.line_number) if err.line_number else "-"
            lines.append(f"| `{file_name}` | `{err.rule}` | {line_str} | {err.message} |")
        lines.append("")

    if report.warnings:
        lines.append("#### ⚠️ Schema Warnings")
        lines.append("| File | Rule | Warning Description |")
        lines.append("|---|---|---|")
        for warn in report.warnings:
            file_name = Path(warn.file_path).name
            lines.append(f"| `{file_name}` | `{warn.rule}` | {warn.message} |")
        lines.append("")

    if report.invariant_alerts:
        lines.append("#### 🛡️ Affected Invariants & Knowledge Checks")
        lines.append("> The following modified files intersect with established high-confidence architectural capsules:")
        lines.append("")
        for alert in report.invariant_alerts:
            cap_file = Path(alert.capsule_file).name
            lines.append(f"- **{alert.affected_file}**")
            lines.append(f"  - Topic: **{alert.capsule_topic}** (`{cap_file}`)")
            lines.append(f"  - Confidence: `{alert.confidence}` | {alert.summary}")
        lines.append("")

    if report.is_success and not report.invariant_alerts:
        lines.append("All capsule schemas and link references are valid! 🎉")

    return "\n".join(lines)


def write_github_step_summary(markdown: str) -> bool:
    """Write markdown summary to GITHUB_STEP_SUMMARY environment file if present."""
    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        try:
            with open(step_summary_path, "a", encoding="utf-8") as f:
                f.write("\n" + markdown + "\n")
            return True
        except Exception:
            pass
    return False
