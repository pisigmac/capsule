"""Capsule CLI — atomic knowledge management from the terminal."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from services.gitcommit.committer import status as git_status
from services.mcp.server import serve as serve_mcp
from services.parser.parser import CapsuleParser
from services.search.engine import SearchEngine
from services.shared.config import config
from services.shared.logging import setup_logging
from services.shared.models import Capsule, CapsuleRelationship, get_session_factory, init_db, reset_engine
from services.store.store import CapsuleStore, StoreError
from services.sync.watcher import CapsuleSyncService

console = Console()


def boot() -> None:
    setup_logging(config.log_level)
    config.ensure_dirs()
    reset_engine()
    init_db()


def session():
    return get_session_factory()()


def resolve_capsule(db, capsule_id: str) -> Optional[Capsule]:
    try:
        uid = str(UUID(capsule_id))
        return db.query(Capsule).filter(Capsule.id == uid).first()
    except ValueError:
        return db.query(Capsule).filter(Capsule.id.like(f"{capsule_id}%")).first()


@click.group()
def cli():
    """Capsule — atomic knowledge for agents."""
    boot()


@cli.command()
@click.argument("topic")
@click.option("--tag", "-t", multiple=True, help="Tags to attach")
@click.option("--source", "-s", default=None, help="Source of this knowledge")
@click.option("--confidence", "-c", type=click.Choice(["high", "medium", "low", "hearsay"]), default="medium")
@click.option("--editor", "-e", is_flag=True, help="Open in $EDITOR")
def new(topic, tag, source, confidence, editor):
    """Create a new capsule file and index it."""
    parser = CapsuleParser()
    content = None
    if editor:
        import subprocess
        import tempfile

        template = parser.to_markdown(
            parser.parse_text(
                f"---\ntopic: {topic}\ntags: {list(tag)}\nsource: {source or ''}\nconfidence: {confidence}\n---\n\n"
                "Write your capsule content here. Be specific. One fact per capsule.\n"
            )
        )
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".caps.md", delete=False) as handle:
            handle.write(template)
            tmp_path = handle.name
        editor_cmd = os.getenv("EDITOR", "nano")
        subprocess.call([editor_cmd, tmp_path])
        parsed = parser.parse_file(Path(tmp_path))
        os.unlink(tmp_path)
        topic = parsed.topic
        content = parsed.content
        tag = parsed.tags or tag
        source = parsed.source or source
        confidence = parsed.confidence or confidence
    else:
        content = click.prompt("Enter capsule content")

    db = session()
    try:
        store = CapsuleStore(db)
        capsule = store.create(
            topic=topic,
            content=content,
            tags=list(tag),
            source=source,
            confidence=confidence,
        )
        db.commit()
        if getattr(capsule, "deduped", False):
            console.print(f"[yellow]Already exists[/yellow] {capsule.id}")
        else:
            console.print(f"[green]Created[/green] {capsule.id}")
        console.print(f"[dim]{capsule.file_path}[/dim]")
    except StoreError as exc:
        db.rollback()
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    finally:
        db.close()


@cli.command()
@click.argument("query", default="")
@click.option("--tag", "-t", multiple=True, help="Filter by tags")
@click.option("--confidence", "-c", type=click.Choice(["high", "medium", "low", "hearsay"]))
@click.option("--archived", is_flag=True, help="Include archived capsules")
@click.option("--limit", "-l", default=20, help="Max results")
@click.option("--mode", type=click.Choice(["fts", "semantic", "hybrid"]), default="fts")
def search(query, tag, confidence, archived, limit, mode):
    """Search capsules."""
    db = session()
    try:
        engine = SearchEngine(db)
        results = engine.search(
            query=query,
            tags=list(tag) if tag else None,
            confidence=confidence,
            archived=True if archived else False,
            limit=limit,
            mode=mode,
        )
        if not results:
            console.print("[dim]No capsules found.[/dim]")
            return

        table = Table(title=f"Found {len(results)} capsule(s)")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Topic", style="white")
        table.add_column("Tags", style="green")
        table.add_column("Confidence", style="yellow")
        table.add_column("Freshness", style="dim")
        for row in results:
            table.add_row(
                str(row["id"])[:8],
                row["topic"][:50],
                ", ".join(row.get("tags", []))[:30],
                row.get("confidence", "medium"),
                (row.get("freshness") or "")[:10],
            )
        console.print(table)
    finally:
        db.close()


@cli.command()
@click.argument("capsule_id")
def show(capsule_id):
    """Show a capsule in detail."""
    db = session()
    try:
        capsule = resolve_capsule(db, capsule_id)
        if not capsule:
            console.print("[red]Capsule not found[/red]")
            sys.exit(1)
        panel = Panel(
            f"[bold]{capsule.topic}[/bold]\n\n"
            f"{capsule.content}\n\n"
            f"[dim]Tags:[/dim] {', '.join(t.name for t in capsule.tags)}\n"
            f"[dim]Confidence:[/dim] {capsule.confidence}\n"
            f"[dim]Source:[/dim] {capsule.source or 'N/A'}\n"
            f"[dim]File:[/dim] {capsule.file_path or 'N/A'}\n"
            f"[dim]ID:[/dim] {capsule.id}",
            title=f"Capsule {capsule.id[:8]}",
            border_style="blue",
        )
        console.print(panel)
    finally:
        db.close()


@cli.command()
@click.argument("from_id")
@click.argument("to_id")
@click.option("--type", "-t", "rel_type", default="relates_to", help="Relationship type")
def link(from_id, to_id, rel_type):
    """Link two capsules together."""
    db = session()
    try:
        store = CapsuleStore(db)
        source = resolve_capsule(db, from_id)
        target = resolve_capsule(db, to_id)
        if not source or not target:
            console.print("[red]Capsule not found[/red]")
            sys.exit(1)
        store.link(source.id, target.id, rel_type)
        db.commit()
        console.print(f"[green]Linked[/green] {source.id[:8]} -> {target.id[:8]} ({rel_type})")
    except StoreError as exc:
        db.rollback()
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    finally:
        db.close()


@cli.command()
@click.option("--tags", "-t", multiple=True, help="Tags to include")
@click.option("--query", "-q", default=None, help="Search query")
@click.option("--confidence-min", "-c", type=click.Choice(["high", "medium", "low", "hearsay"]), default="medium")
@click.option("--max-tokens", "-m", default=4000, help="Max token budget")
@click.option("--output", "-o", type=click.Path(), help="Write to file instead of stdout")
@click.option("--mode", type=click.Choice(["fts", "semantic", "hybrid"]), default="fts")
@click.option("--graph/--no-graph", default=True, help="Enable graph-aware dependency closure expansion")
@click.option("--hops", default=1, type=int, help="Max graph expansion hops (default: 1)")
@click.option("--include-superseded", is_flag=True, default=False, help="Include deprecated or superseded capsules")
def compose(tags, query, confidence_min, max_tokens, output, mode, graph, hops, include_superseded):
    """Compose a token-budgeted context window from capsules with graph-aware affinity."""
    db = session()
    try:
        engine = SearchEngine(db)
        result = engine.compose(
            tags=list(tags) if tags else None,
            query=query,
            confidence_min=confidence_min,
            max_tokens=max_tokens,
            mode=mode,
            graph_expansion=graph,
            max_hops=hops,
            include_superseded=include_superseded,
        )
        context = result["context"]
        if output:
            Path(output).write_text(context, encoding="utf-8")
            console.print(f"[green]Context written to {output}[/green]")
        else:
            syntax = Syntax(context or "[empty]", "markdown", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title="Composed Context", border_style="green"))
        graph_label = " (graph-expanded)" if result.get("graph_expansion") else ""
        console.print(
            f"[dim]capsules={result['capsule_count']} tokens≈{result['token_estimate']}{graph_label} "
            f"truncated={result['truncated']}[/dim]"
        )
    finally:
        db.close()


@cli.command()
@click.option("--days", "-d", default=90, help="Days since last update")
def stale(days):
    """Show capsules that haven't been updated recently."""
    db = session()
    try:
        capsules = SearchEngine(db).stale_capsules(days=days)
        if not capsules:
            console.print("[green]All capsules are fresh.[/green]")
            return
        table = Table(title=f"{len(capsules)} stale capsule(s) (>{days} days)")
        table.add_column("ID", style="cyan")
        table.add_column("Topic", style="white")
        table.add_column("Last Updated", style="red")
        for row in capsules:
            table.add_row(str(row["id"])[:8], row["topic"][:50], (row.get("updated_at") or "")[:10])
        console.print(table)
    finally:
        db.close()


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False), required=False)
@click.option("--watch", "-w", is_flag=True, help="Keep watching for changes")
@click.option("--obsidian", type=click.Path(exists=True, file_okay=False), default=None, help="Sync an Obsidian vault directory")
@click.option("--tag", "-t", default=None, help="Filter Obsidian notes by tag (e.g. #agent-memory)")
@click.option("--dry-run", is_flag=True, help="Preview Obsidian notes to sync without importing")
def sync(directory, watch, obsidian, tag, dry_run):
    """Reindex .capsule.md files or sync an Obsidian vault."""
    if obsidian:
        from services.sync.obsidian_adapter import ObsidianVaultSync

        db = session()
        try:
            store = CapsuleStore(db)
            syncer = ObsidianVaultSync(store=store, vault_path=obsidian, tag_filter=tag)
            res = syncer.sync(dry_run=dry_run)
            if dry_run:
                console.print(f"[bold yellow]Obsidian Vault Dry Run:[/bold yellow] Found {res.scanned_count} matching note(s) in {obsidian}")
                for note in res.notes:
                    tags_s = ", ".join(note.tags)
                    console.print(f"  • [cyan]\"{note.topic}\"[/cyan] [dim][{tags_s}][/dim]")
                return

            console.print(
                f"[green]✓ Obsidian sync complete:[/green] Scanned {res.scanned_count} notes, "
                f"created {res.created_count}, updated {res.updated_count}, "
                f"linked {res.linked_count} [[WikiLink]] relationships."
            )
        finally:
            db.close()

        if not watch:
            return

    watch_dirs = [directory or str(config.capsules_dir)]
    if obsidian and watch:
        watch_dirs.append(obsidian)

    service = CapsuleSyncService(watch_dirs=watch_dirs, include_markdown=bool(obsidian))
    count = service.initial_sync()
    console.print(f"[green]Synced {count} capsule(s) from {', '.join(watch_dirs)}[/green]")
    if watch:
        console.print("[dim]Watching for changes... (Ctrl+C to stop)[/dim]")
        service.start()
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopping watcher...[/dim]")
        finally:
            service.stop()


@cli.command("link-vault")
@click.argument("vault_path", type=click.Path(exists=True, file_okay=False), required=False)
@click.option("--name", default="obsidian", help="Symlink folder name inside capsules_dir")
@click.option("--unlink", is_flag=True, help="Remove existing vault symlink")
@click.option("--dir", "capsules_dir", type=click.Path(), default=None, help="Custom capsules directory path")
def link_vault_cmd(vault_path, name, unlink, capsules_dir):
    """Link or unlink an Obsidian vault directory directly into Capsule memory."""
    from services.sync.symlink_manager import VaultSymlinkManager

    caps_path = Path(capsules_dir).resolve() if capsules_dir else config.capsules_dir.resolve()
    manager = VaultSymlinkManager(capsules_dir=caps_path)

    if unlink:
        res = manager.unlink_vault(link_name=name)
        if res.success:
            console.print(f"[green]✓[/green] {res.message}")
            db = session()
            try:
                store = CapsuleStore(db, capsules_dir=caps_path)
                count = store.reconcile()
                db.commit()
                console.print(f"[dim]Reconciled store: {count} active capsules remaining.[/dim]")
            finally:
                db.close()
        else:
            console.print(f"[red]✗[/red] {res.message}")
        return

    if not vault_path:
        links = manager.get_linked_vaults()
        if not links:
            console.print(f"[yellow]No linked vaults in {caps_path}[/yellow]")
            console.print("[dim]Usage: caps link-vault <path-to-obsidian-vault>[/dim]")
        else:
            console.print(f"[bold]Active Vault Links in {caps_path}:[/bold]")
            for link_name, link_p, target_p in links:
                console.print(f"  • [cyan]{link_name}[/cyan] → [dim]{target_p}[/dim]")
        return

    res = manager.link_vault(vault_path=vault_path, link_name=name)
    if res.success:
        console.print(f"[green]✓[/green] {res.message}")
        db = session()
        try:
            store = CapsuleStore(db, capsules_dir=caps_path)
            count = store.reconcile()
            db.commit()
            console.print(f"[green]Indexed {count} total capsule(s) (including notes from linked vault).[/green]")
        finally:
            db.close()
    else:
        console.print(f"[red]✗[/red] {res.message}")



@cli.command()
@click.argument("capsule_id")
def archive(capsule_id):
    """Archive a capsule."""
    db = session()
    try:
        store = CapsuleStore(db)
        capsule = resolve_capsule(db, capsule_id)
        if not capsule:
            console.print("[red]Capsule not found[/red]")
            sys.exit(1)
        store.archive(capsule.id)
        db.commit()
        console.print(f"[green]Archived[/green] {capsule.id[:8]}")
    except StoreError as exc:
        db.rollback()
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    finally:
        db.close()


@cli.command()
def status():
    """Show system status."""
    db = session()
    try:
        counts = SearchEngine(db).counts()
        rel_count = db.query(CapsuleRelationship).count()
        console.print(
            Panel(
                f"[bold]Capsule Status[/bold]\n\n"
                f"Active capsules: {counts['active']}\n"
                f"Archived capsules: {counts['archived']}\n"
                f"Total tags: {counts['tags']}\n"
                f"Relationships: {rel_count}\n"
                f"Database: {config.database_url}\n"
                f"Capsules dir: {config.capsules_dir.resolve()}",
                border_style="blue",
            )
        )
    finally:
        db.close()


@cli.command()
def init():
    """Initialize the capsule workspace and seed a welcome file if empty."""
    db = session()
    try:
        store = CapsuleStore(db)
        indexed = store.reconcile()
        if indexed == 0 and db.query(Capsule).count() == 0:
            store.create(
                topic="Welcome to Capsule",
                content=(
                    "Capsule stores one fact per file. Each .capsule.md file is the source of truth; "
                    "SQLite is only a search index.\n\n"
                    "Use `capsule new` to create one, `capsule search` to find them, "
                    "and `capsule compose` to build an agent context window."
                ),
                tags=["welcome"],
                source="capsule-init",
                confidence="high",
            )
            db.commit()
            console.print("[green]Initialized workspace with a welcome capsule.[/green]")
        else:
            db.commit()
            console.print(f"[dim]Workspace ready. Indexed {indexed} existing capsule(s).[/dim]")
    finally:
        db.close()


@cli.command("demo")
@click.option("--non-interactive", is_flag=True, help="Run without interactive pause prompts")
def demo_cmd(non_interactive):
    """Run an interactive 30-second tour of Capsule memory & token savings."""
    from .demo.runner import DemoExperience

    DemoExperience(console=console, interactive=not non_interactive).run()


@cli.command("browse")
@click.option("--dir", "capsules_dir", type=click.Path(), default=None, help="Custom capsules directory path")
def browse_cmd(capsules_dir):
    """Launch the interactive terminal TUI browser for capsules."""
    from .tui.browser import TuiBrowser

    caps_path = Path(capsules_dir).resolve() if capsules_dir else config.capsules_dir.resolve()
    db = session()
    try:
        browser = TuiBrowser(db_session=db, capsules_dir=caps_path, console=console)
        browser.run()
    finally:
        db.close()


@cli.command("tui")
@click.option("--dir", "capsules_dir", type=click.Path(), default=None, help="Custom capsules directory path")
def tui_cmd(capsules_dir):
    """Interactive terminal browser alias for browse."""
    from .tui.browser import TuiBrowser

    caps_path = Path(capsules_dir).resolve() if capsules_dir else config.capsules_dir.resolve()
    db = session()
    try:
        browser = TuiBrowser(db_session=db, capsules_dir=caps_path, console=console)
        browser.run()
    finally:
        db.close()


def install_git_post_commit_hook(repo_path: Path) -> Path:
    """Installs or updates the post-commit git hook to auto-sync capsules."""
    hooks_dir = repo_path / ".git" / "hooks"
    if not hooks_dir.exists():
        hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "post-commit"
    hook_script = """#!/usr/bin/env bash
# Capsule Incremental Git Sync Hook
# Automatically indexes code changes on every commit in <15ms
if command -v caps &> /dev/null; then
    caps ingest --git-diff HEAD~1 > /dev/null 2>&1 &
fi
"""
    hook_file.write_text(hook_script, encoding="utf-8")
    hook_file.chmod(0o755)
    return hook_file


@cli.group("hook")
def hook_group():
    """Manage automated Git hooks for Capsule synchronization."""
    pass


@hook_group.command("install")
@click.option("--repo", "-r", type=click.Path(exists=True), default=None, help="Target git repository path")
def hook_install_cmd(repo):
    """Install the post-commit git hook to auto-sync on every commit."""
    repo_root = Path(repo).resolve() if repo else Path.cwd()
    hook_path = install_git_post_commit_hook(repo_root)
    console.print(f"[bold green]✓ Installed Capsule post-commit hook:[/bold green] [cyan]{hook_path}[/cyan]")


@hook_group.command("status")
@click.option("--repo", "-r", type=click.Path(exists=True), default=None, help="Target git repository path")
def hook_status_cmd(repo):
    """Check if the post-commit git hook is installed."""
    repo_root = Path(repo).resolve() if repo else Path.cwd()
    hook_file = repo_root / ".git" / "hooks" / "post-commit"
    if hook_file.exists():
        console.print(f"[green]✓ Post-commit hook is active at {hook_file}[/green]")
    else:
        console.print(f"[yellow]No post-commit hook found in {repo_root}. Run `caps hook install` to activate.[/yellow]")


@cli.command("ingest")
@click.argument("target", required=False, type=click.Path(exists=True))
@click.option("--code", "is_code", is_flag=True, help="Ingest source code (Python, TypeScript, Go, Rust, Java) into the Code Graph")
@click.option("--git-diff", default=None, help="Incremental sync from git diff (e.g. 'HEAD~1', 'origin/main...HEAD', 'staged')")
@click.option("--install-hook", is_flag=True, help="Install post-commit git hook for automated zero-overhead sync")
@click.option("--git", "use_git", is_flag=True, help="Harvest architectural decisions from Git commit logs")
@click.option("--depth", "-d", default=50, type=int, help="Maximum number of commits to scan when --git is enabled")
@click.option("--types", help="Filter git commits by type (e.g. 'fix,refactor,feat')")
@click.option("--since", help="Filter git commits by date/time (e.g. '30d', '2 weeks ago')")
@click.option("--prs", is_flag=True, help="Also harvest from merged GitHub pull requests")
@click.option("--tag", "-t", multiple=True, help="Tags to attach to ingested capsules")
@click.option("--mode", "-m", type=click.Choice(["ast", "llm"]), default="ast", help="Decomposition mode (ast or llm)")
@click.option("--model", default="gemini-2.5-flash", help="LLM model name for semantic extraction")
@click.option("--confidence", "-c", type=click.Choice(["high", "medium", "low", "hearsay"]), default="high")
@click.option("--dry-run", is_flag=True, help="Preview atomic capsules without saving to disk")
@click.option("--dir", "capsules_dir", type=click.Path(), default=None, help="Custom capsules directory path")
def ingest_cmd(target, is_code, git_diff, install_hook, use_git, depth, types, since, prs, tag, mode, model, confidence, dry_run, capsules_dir):
    """Decompose documentation, codebases, or git commit history into atomic capsules."""
    from services.ingest import DocumentDecomposer, CodeDecomposer, GitHarvester, PRHarvester

    # -------------------------------------------------------------
    # 0. Hook Installation
    # -------------------------------------------------------------
    if install_hook:
        repo_root = Path(target).resolve() if target else Path.cwd()
        hook_path = install_git_post_commit_hook(repo_root)
        console.print(f"[bold green]✓ Installed Capsule post-commit hook:[/bold green] [cyan]{hook_path}[/cyan]")
        return

    caps_path = Path(capsules_dir).resolve() if capsules_dir else config.capsules_dir.resolve()
    db = session()
    try:
        store = CapsuleStore(db, capsules_dir=caps_path)

        # -------------------------------------------------------------
        # 1. Incremental Git Diff Sync (--git-diff)
        # -------------------------------------------------------------
        if git_diff:
            repo_root = Path(target).resolve() if target else Path.cwd()
            dry_label = " [yellow](DRY RUN — Preview Only)[/yellow]" if dry_run else ""
            console.print(
                Panel(
                    f"[bold]Capsule Incremental Git Sync[/bold]{dry_label}\n"
                    f"Repository: [cyan]{repo_root}[/cyan]\n"
                    f"Revision: [green]{git_diff}[/green]\n"
                    f"Target Vault: [dim]{caps_path}[/dim]",
                    border_style="blue",
                )
            )
            code_decomposer = CodeDecomposer(store=store)
            result = code_decomposer.ingest_git_diff(repo_root, diff_rev=git_diff, dry_run=dry_run)
            if dry_run:
                console.print(
                    f"\n[bold yellow]Dry Run Complete:[/bold yellow] Diff contained {result.total_files} file(s), {result.total_classes} class(es), and {result.total_functions} function(s). Pruned {result.deleted_count} stale capsule(s)."
                )
            else:
                console.print(
                    f"\n[bold green]Incremental sync complete![/bold green] Ingested [bold cyan]{result.created_count}[/bold cyan] capsule(s), pruned [yellow]{result.deleted_count}[/yellow] stale capsule(s), and linked [bold green]{result.relationships_linked}[/bold green] edge(s) in [dim]{caps_path}[/dim]."
                )
            return

        # -------------------------------------------------------------
        # 2. Git Harvester Mode
        # -------------------------------------------------------------
        if use_git:
            repo_path = Path(target).resolve() if target else Path.cwd()
            commit_types = [t.strip() for t in types.split(",") if t.strip()] if types else None

            dry_label = " [yellow](DRY RUN — Preview Only)[/yellow]" if dry_run else ""
            console.print(
                Panel(
                    f"[bold]Capsule Git History Harvester[/bold]{dry_label}\n"
                    f"Repository: [cyan]{repo_path}[/cyan] (depth: {depth} commits)\n"
                    f"Target Dir: [dim]{caps_path}[/dim]\n"
                    f"Types: [green]{types or 'All architectural'}[/green]  Confidence: [yellow]{confidence}[/yellow]",
                    border_style="blue",
                )
            )

            harvester = GitHarvester()

            def on_git_progress(item, created, deduped):
                if dry_run:
                    tags_str = ", ".join(item.tags)
                    console.print(f"  [cyan][dry-run][/cyan] \"{item.topic}\" ({item.short_sha}) [dim][{tags_str}][/dim]")
                else:
                    status = "[green]✓ Created[/green]" if created else "[yellow]Duplicate skipped[/yellow]"
                    console.print(f"  {status} [bold]{item.topic}[/bold] ({item.short_sha})")

            result = harvester.harvest(
                repo_path=repo_path,
                store=store,
                depth=depth,
                types=commit_types,
                since=since,
                default_confidence=confidence,
                dry_run=dry_run,
                extra_tags=list(tag),
                on_progress=on_git_progress,
            )

            # Optional PR harvesting
            if prs:
                pr_harvester = PRHarvester()
                pr_items = pr_harvester.extract_merged_prs(
                    repo_path=repo_path,
                    limit=depth,
                    default_confidence=confidence,
                    extra_tags=list(tag),
                )
                if pr_items:
                    console.print(f"\n[bold]Harvesting {len(pr_items)} merged PR(s)...[/bold]")
                    for pr_item in pr_items:
                        if dry_run:
                            console.print(f"  [cyan][dry-run-pr][/cyan] \"{pr_item.topic}\" ({pr_item.short_sha})")
                            result.total_units += 1
                        else:
                            try:
                                cap = store.create(
                                    topic=pr_item.topic,
                                    content=pr_item.content,
                                    tags=pr_item.tags,
                                    source=pr_item.source,
                                    confidence=pr_item.confidence,
                                )
                                if getattr(cap, "deduped", False):
                                    result.deduped_count += 1
                                else:
                                    result.created_count += 1
                                result.total_units += 1
                                console.print(f"  [green]✓ Created[/green] [bold]{pr_item.topic}[/bold] ({pr_item.short_sha})")
                            except Exception as e:
                                logger.error("Failed to store PR cap: %s", e)

            if dry_run:
                console.print(
                    f"\n[bold yellow]Dry Run Complete:[/bold yellow] Found {result.total_units} candidate invariant(s) in git history. Zero files written to disk."
                )
            else:
                console.print(
                    f"\n[bold green]Git harvesting complete![/bold green] Created [bold cyan]{result.created_count}[/bold cyan] new cap(s) in [dim]{caps_path}[/dim]"
                    + (f" ([yellow]{result.deduped_count}[/yellow] duplicates skipped via content hash)" if result.deduped_count else "")
                    + ". Run [cyan]`caps browse`[/cyan] or [cyan]`caps search`[/cyan] to explore."
                )
            return

        # -------------------------------------------------------------
        # 3. Code Decomposer Mode (--code)
        # -------------------------------------------------------------
        if is_code:
            if not target:
                console.print("[red]Error:[/red] Missing argument 'TARGET'. Specify a source code file or directory.")
                sys.exit(1)

            target_path = Path(target).resolve()
            dry_label = " [yellow](DRY RUN — Preview Only)[/yellow]" if dry_run else ""
            console.print(
                Panel(
                    f"[bold]Capsule Code Decomposer & AST Linker[/bold]{dry_label}\n"
                    f"Source: [cyan]{target_path}[/cyan]\n"
                    f"Target Vault: [dim]{caps_path}[/dim]\n"
                    f"Languages: [green]Python, TypeScript/JavaScript, Go, Rust, Java[/green]",
                    border_style="blue",
                )
            )

            code_decomposer = CodeDecomposer(store=store)
            result = code_decomposer.ingest_code_path(target_path, dry_run=dry_run)

            if dry_run:
                console.print(
                    f"\n[bold yellow]Dry Run Complete:[/bold yellow] Found {result.total_files} file(s), {result.total_classes} class(es), and {result.total_functions} function(s). Zero files written to disk."
                )
            else:
                console.print(
                    f"\n[bold green]Code ingestion complete![/bold green] Created [bold cyan]{result.created_count}[/bold cyan] code capsule(s) and linked [bold green]{result.relationships_linked}[/bold green] relationship edge(s) in [dim]{caps_path}[/dim]. Run [cyan]`caps browse`[/cyan] or open the Web UI Code Graph."
                )
            return

        # -------------------------------------------------------------
        # 3. Document Decomposer Mode (Default)
        # -------------------------------------------------------------
        if not target:
            console.print("[red]Error:[/red] Missing argument 'TARGET'. Specify a markdown file/directory or pass '--git' / '--code'.")
            sys.exit(1)

        target_path = Path(target).resolve()
        decomposer = DocumentDecomposer(
            store=store,
            mode=mode,
            confidence=confidence,
            model=model,
            extra_tags=list(tag),
        )

        files = decomposer.collect_files(target_path)
        if not files:
            console.print(f"[yellow]No markdown files found under {target}[/yellow]")
            return

        dry_label = " [yellow](DRY RUN — Preview Only)[/yellow]" if dry_run else ""
        console.print(
            Panel(
                f"[bold]Capsule Document Decomposer[/bold]{dry_label}\n"
                f"Source: [cyan]{target_path}[/cyan] ({len(files)} markdown file{'s' if len(files) != 1 else ''})\n"
                f"Target Dir: [dim]{caps_path}[/dim]\n"
                f"Mode: [green]{mode.upper()}[/green]" + (f" ({model})" if mode == "llm" else "") + f"  Confidence: [yellow]{confidence}[/yellow]",
                border_style="blue",
            )
        )

        def on_progress(file_path: Path, units, created, deduped):
            rel_name = file_path.name
            if dry_run:
                console.print(f"\n[bold]Scanned {rel_name}[/bold] → Found {len(units)} candidate atomic cap(s):")
                for u in units:
                    tags_str = ", ".join(u.tags)
                    console.print(f"  [cyan][dry-run][/cyan] \"{u.topic}\" [dim][{tags_str}][/dim]")
            else:
                summary_parts = []
                if created:
                    summary_parts.append(f"[green]{created} created[/green]")
                if deduped:
                    summary_parts.append(f"[yellow]{deduped} duplicate(s) merged[/yellow]")
                summary_str = f" ({', '.join(summary_parts)})" if summary_parts else ""
                console.print(f"  [green]✓[/green] Ingested [bold]{rel_name}[/bold] → {len(units)} cap(s){summary_str}")

        result = decomposer.ingest_path(target_path, dry_run=dry_run, on_progress=on_progress)

        if dry_run:
            console.print(
                f"\n[bold yellow]Dry Run Complete:[/bold yellow] Found {result.total_units} atomic unit(s) across {result.total_files} file(s). Zero files written to disk."
            )
        else:
            console.print(
                f"\n[bold green]Ingestion complete![/bold green] Created [bold cyan]{result.created_count}[/bold cyan] new cap(s) in [dim]{caps_path}[/dim]"
                + (f" ([yellow]{result.deduped_count}[/yellow] duplicates skipped via content hash)" if result.deduped_count else "")
                + ". Run [cyan]`caps browse`[/cyan] or [cyan]`caps search`[/cyan] to explore."
            )
    finally:
        db.close()


@cli.command("git")
@click.argument("action", type=click.Choice(["status", "on", "off"]), default="status")
def git_cmd(action):
    """Show or toggle git auto-commit of capsules/ (this process only)."""
    if action == "on":
        os.environ["CAPSULE_GIT_COMMIT"] = "true"
    elif action == "off":
        os.environ["CAPSULE_GIT_COMMIT"] = "false"
    info = git_status()
    console.print(
        f"enabled={info['enabled']} git={info['git']} repo={info['repo'] or '-'} "
        f"last={info['last_commit'] or '-'}"
    )


@cli.group("mcp", invoke_without_command=True)
@click.option("--http", is_flag=True, help="Streamable HTTP instead of stdio")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=9101, type=int)
@click.pass_context
def mcp_cmd(ctx, http, host, port):
    """Run or configure the Capsule MCP server (official SDK, stdio or HTTP)."""
    if ctx.invoked_subcommand is None:
        serve_mcp(http=http, host=host, port=port)


@mcp_cmd.command("install")
@click.option("--claude", is_flag=True, help="Configure Claude Desktop")
@click.option("--cursor", is_flag=True, help="Configure Cursor IDE")
@click.option("--windsurf", is_flag=True, help="Configure Windsurf")
@click.option("--all", "all_clients", is_flag=True, help="Configure all detected clients")
@click.option("--dry-run", is_flag=True, help="Preview configuration changes without writing")
@click.option("--remove", is_flag=True, help="Remove Capsule from client configurations")
@click.option("--capsules-dir", type=click.Path(), default=None, help="Custom capsules directory path")
@click.option("--name", default="capsule", help="Server name in config (default: capsule)")
def mcp_install_cmd(claude, cursor, windsurf, all_clients, dry_run, remove, capsules_dir, name):
    """Auto-install Capsule MCP server into Claude Desktop, Cursor, and Windsurf."""
    from .installer.mcp_installer import McpInstaller, detect_installed_clients
    from .installer.targets import get_system_targets

    installer = McpInstaller()
    all_targets = get_system_targets()
    target_map = {t.client_id: t for t in all_targets}

    selected = []
    if claude and "claude" in target_map:
        selected.append(target_map["claude"])
    if cursor and "cursor" in target_map:
        selected.append(target_map["cursor"])
    if windsurf and "windsurf" in target_map:
        selected.append(target_map["windsurf"])

    if not selected:
        installed = detect_installed_clients(all_targets)
        if not installed:
            console.print("[yellow]No supported AI clients (Claude Desktop, Cursor, Windsurf) detected on this system.[/yellow]")
            console.print("[dim]Use --claude, --cursor, or --windsurf to force configuration for a specific client.[/dim]")
            return
        selected = installed

    caps_path = Path(capsules_dir).resolve() if capsules_dir else config.capsules_dir.resolve()

    mode_label = "DRY RUN (Preview Only)" if dry_run else ("Uninstall" if remove else "Install")
    console.print(
        Panel(
            f"[bold]Capsule MCP Installer[/bold]\n"
            f"Server Name: [cyan]{name}[/cyan]\n"
            f"Capsules Dir: [dim]{caps_path}[/dim]\n"
            f"Mode: [yellow]{mode_label}[/yellow]",
            border_style="blue",
        )
    )

    for target in selected:
        if remove:
            res = installer.remove_target(target, server_name=name, dry_run=dry_run)
        else:
            res = installer.install_target(target, capsules_dir=caps_path, server_name=name, dry_run=dry_run)

        if res.success:
            if dry_run and res.diff:
                console.print(f"[bold green]Target: {target.name}[/bold green] ([dim]{target.config_path}[/dim]):")
                syntax = Syntax(res.diff, "json", theme="monokai", line_numbers=True)
                console.print(Panel(syntax, title=f"Dry Run Diff: {target.name}", border_style="yellow"))
            else:
                console.print(f"[green]✓[/green] {res.message} ([dim]{target.config_path}[/dim])")
                if res.backup_path:
                    console.print(f"   [dim]Backup created: {res.backup_path}[/dim]")
        else:
            console.print(f"[red]✗ Failed {target.name}:[/red] {res.message}")

    if not dry_run and not remove:
        console.print("\n[bold cyan]Setup complete![/bold cyan] Restart your AI client to start using Capsule tools.")


@cli.command()
@click.argument("pack")
@click.option("--dir", "capsules_dir", default=None, type=click.Path(), help="Target capsules directory (defaults to configured caps directory)")
@click.option("--dry-run", is_flag=True, help="Preview capsules in pack without writing to disk")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing capsule files")
def pull(pack: str, capsules_dir: Optional[str], dry_run: bool, force: bool):
    """Pull a verified knowledge pack into Capsule memory."""
    from services.registry.client import RegistryClient, RegistryError, ZipSlipError

    target_path = Path(capsules_dir).resolve() if capsules_dir else config.capsules_dir.resolve()
    client = RegistryClient()

    with session() as s:
        try:
            console.print(f"[bold cyan]Fetching knowledge pack[/bold cyan] [yellow]'{pack}'[/yellow] ...")
            res = client.pull(pack, target_dir=target_path, dry_run=dry_run, force=force, db_session=s)
        except (RegistryError, ZipSlipError, ValueError, Exception) as e:
            console.print(f"[red]Error pulling pack:[/red] {e}")
            sys.exit(1)

    mode_text = " [yellow](DRY RUN — Preview Only)[/yellow]" if dry_run else ""
    manifest = res.manifest
    author_text = f" (Author: [cyan]@{manifest.author}[/cyan])" if manifest else ""
    console.print(
        Panel(
            f"[bold green]Knowledge Pack:[/bold green] [bold]{res.pack_name}[/bold]{author_text}{mode_text}\n"
            f"[dim]Target Directory: {target_path}[/dim]\n"
            f"Installed: [bold green]{res.total_installed}[/bold green] | Skipped (Existing): [yellow]{res.total_skipped}[/yellow]",
            border_style="green" if not dry_run else "yellow",
        )
    )

    if res.installed:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Filename", style="dim")
        table.add_column("Topic", style="bold")
        table.add_column("Confidence", style="cyan")
        table.add_column("Tags", style="green")

        for item in res.installed:
            tags_str = ", ".join(item.tags)
            table.add_row(item.filename, item.topic, item.confidence, tags_str)

        console.print(table)

    if not dry_run:
        console.print(f"[green]✓[/green] Successfully merged [bold]{res.total_installed}[/bold] capsules into [dim]{target_path}[/dim].")
        if res.reconciled:
            console.print("[dim]Index reconciled and updated.[/dim]")


@cli.group()
def pack():
    """Manage and discover Capsule Knowledge Packs."""
    pass


@pack.command("list")
@click.option("--search", "-s", default=None, help="Filter packs by keyword or tag")
def pack_list(search: Optional[str]):
    """List available knowledge packs in the registry."""
    from services.registry.client import RegistryClient

    client = RegistryClient()
    packs = client.list_packs(query=search)

    if not packs:
        msg = f"No knowledge packs found matching '{search}'." if search else "No knowledge packs available."
        console.print(f"[yellow]{msg}[/yellow]")
        return

    table = Table(title="Capsule Knowledge Packs Registry", show_header=True, header_style="bold blue")
    table.add_column("Pack Name", style="bold cyan", no_wrap=True)
    table.add_column("Version", style="dim")
    table.add_column("Author", style="dim")
    table.add_column("Caps", justify="right")
    table.add_column("Tags", style="green")
    table.add_column("Description")

    for p in packs:
        tags_str = ", ".join(p.tags[:4])
        if len(p.tags) > 4:
            tags_str += f" (+{len(p.tags)-4})"
        table.add_row(p.name, p.version, p.author, str(p.caps_count), tags_str, p.description)

    console.print(table)
    console.print("\n[dim]To install a pack, run:[/dim] [bold cyan]caps pull <pack-name>[/bold cyan]")


@pack.command("create")
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--name", "-n", required=True, help="Pack name (e.g. 'python-performance')")
@click.option("--version", "-v", default="1.0.0", help="Pack semantic version")
@click.option("--author", "-a", default="Community", help="Pack author")
@click.option("--desc", "-d", default="", help="Short description of pack")
@click.option("--tag", "-t", multiple=True, help="Tags classifying this pack")
@click.option("--output", "-o", default=None, type=click.Path(), help="Output .zip archive path")
def pack_create(source_dir: str, name: str, version: str, author: str, desc: str, tag: tuple[str, ...], output: Optional[str]):
    """Export local capsules into a distributable knowledge pack archive."""
    from services.registry.publisher import PackPublisher

    try:
        out_path, manifest = PackPublisher.create_pack(
            source_dir=Path(source_dir),
            name=name,
            version=version,
            description=desc,
            author=author,
            tags=list(tag) if tag else None,
            output_path=Path(output) if output else None,
        )
        console.print(f"[bold green]✓ Created Knowledge Pack:[/bold green] [cyan]{out_path}[/cyan]")
        console.print(f"  Name: [bold]{manifest.name}[/bold] (v{manifest.version})")
        console.print(f"  Capsules: [bold]{manifest.caps_count}[/bold]")
        console.print(f"  Tags: [green]{', '.join(manifest.tags)}[/green]")
        console.print(f"  SHA-256: [dim]{manifest.sha256}[/dim]")
    except Exception as e:
        console.print(f"[red]Error creating pack:[/red] {e}")
        sys.exit(1)


# Register registry as an alias for pack
cli.add_command(pack, name="registry")


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--tag", "-t", required=True, help="OCI reference tag (e.g. 'ghcr.io/org/repo:1.0.0')")
@click.option("--author", "-a", default="Community", help="Author attribution")
@click.option("--desc", "-d", default="", help="Description of memory pack")
def push(directory: str, tag: str, author: str, desc: str):
    """Push a directory of capsules to an OCI container registry (GHCR, Docker Hub, ECR)."""
    from services.registry.oci import OCIClient, OCIClientError

    client = OCIClient()
    console.print(f"[bold cyan]Packaging and pushing[/bold cyan] [yellow]'{directory}'[/yellow] to [bold]{tag}[/bold] ...")
    try:
        res = client.push(
            source_dir=Path(directory),
            reference=tag,
            author=author,
            description=desc,
        )
        console.print(f"[bold green]✓ Successfully pushed OCI memory artifact:[/bold green] [cyan]{res.reference}[/cyan]")
        console.print(f"  Manifest Digest: [dim]{res.manifest_digest}[/dim]")
        console.print(f"  Layer Digest:    [dim]{res.layer_digest}[/dim]")
        console.print(f"  Capsules:        [bold]{res.caps_count}[/bold] ({res.layer_size / 1024:.1f} KB)")
    except (OCIClientError, Exception) as e:
        console.print(f"[red]Error pushing to registry:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.argument("registry")
@click.option("--username", "-u", required=True, help="Registry username")
@click.option("--password", "-p", required=True, help="Registry password or personal access token")
def login(registry: str, username: str, password: str):
    """Authenticate with an OCI container registry (GHCR, Docker Hub, ECR)."""
    from services.registry.oci.auth import OCIAuthManager

    mgr = OCIAuthManager()
    mgr.store_credentials(registry, username, password)
    console.print(f"[bold green]✓ Login Succeeded[/bold green] for [cyan]{registry}[/cyan] (user: {username})")


@cli.command("inspect")
@click.argument("reference")
def inspect_cmd(reference: str):
    """Inspect remote OCI artifact manifest and configuration without downloading."""
    from services.registry.oci import OCIClient, OCIClientError

    client = OCIClient()
    console.print(f"[bold cyan]Inspecting remote artifact[/bold cyan] [yellow]'{reference}'[/yellow] ...")
    try:
        info = client.inspect(reference)
        console.print(
            Panel(
                f"[bold]Reference:[/bold] [cyan]{info['reference']}[/cyan]\n"
                f"[bold]Digest:[/bold] [dim]{info['digest']}[/dim]\n"
                f"[bold]Media Type:[/bold] {info['mediaType']}\n"
                f"[bold]Layers:[/bold] {len(info['layers'])}\n"
                f"[bold]Author:[/bold] {info['annotations'].get('org.opencontainers.image.authors', 'N/A')}\n"
                f"[bold]Created:[/bold] {info['annotations'].get('org.opencontainers.image.created', 'N/A')}\n"
                f"[bold]Description:[/bold] {info['annotations'].get('org.opencontainers.image.description', 'N/A')}",
                title="OCI Artifact Metadata",
                border_style="blue",
            )
        )
    except (OCIClientError, Exception) as e:
        console.print(f"[red]Error inspecting artifact:[/red] {e}")
        sys.exit(1)


@cli.group()
def ci():
    """CI verification, schema linting, and invariant conflict checks."""
    pass


@ci.command("check")
@click.argument("path", required=False, type=click.Path())
@click.option("--strict", is_flag=True, help="Fail on warnings or invariant alerts")
@click.option("--base", "-b", default=None, help="Base git branch/ref for PR diff checking (e.g. 'origin/main')")
@click.option("--diff/--no-diff", "check_diff", default=True, help="Enable or disable git diff invariant checking")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON")
@click.option("--github-summary", is_flag=True, help="Write markdown report to $GITHUB_STEP_SUMMARY")
@click.option("--output-md", type=click.Path(), help="Write markdown summary to specified file")
def ci_check(
    path: Optional[str],
    strict: bool,
    base: Optional[str],
    check_diff: bool,
    output_json: bool,
    github_summary: bool,
    output_md: Optional[str],
):
    """Verify schema integrity of all capsules and detect PR invariant conflicts."""
    import json as json_lib
    from capsule_cli.ci.linter import CapsuleLinter
    from capsule_cli.ci.pr_diff import PRDiffChecker
    from capsule_cli.ci.summary import (
        generate_markdown_summary,
        render_terminal_report,
        write_github_step_summary,
    )

    # Determine target directory
    if path:
        target_dir = Path(path)
    else:
        target_dir = Path("caps") if Path("caps").is_dir() else Path(config.capsules_dir)

    linter = CapsuleLinter()
    report = linter.lint_directory(target_dir)

    if check_diff:
        checker = PRDiffChecker()
        changed_files = checker.get_changed_files(base_ref=base)
        alerts = checker.check_invariants(changed_files, target_dir)
        report.invariant_alerts = alerts

    if output_json:
        click.echo(json_lib.dumps(report.to_dict(), indent=2))
    else:
        render_terminal_report(report, console)

    md_summary = generate_markdown_summary(report)

    if github_summary or os.environ.get("GITHUB_STEP_SUMMARY"):
        write_github_step_summary(md_summary)

    if output_md:
        try:
            Path(output_md).write_text(md_summary, encoding="utf-8")
        except Exception as e:
            console.print(f"[red]Error writing markdown summary to '{output_md}':[/red] {e}")

    # Determine exit code
    if strict:
        if not report.is_strict_success():
            sys.exit(1)
    else:
        if not report.is_success:
            sys.exit(1)


# Register lint as a direct top-level alias for ci check
cli.add_command(ci_check, name="lint")


@cli.command("verify-drift")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--fail-on-violation", is_flag=True, help="Exit with code 1 if violations found")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON report")
@click.option("--strict", is_flag=True, help="Treat dead code warnings as errors")
def verify_drift(path, fail_on_violation, json_output, strict):
    """Detect code drift, dead code, and architectural boundary violations."""
    import json as json_lib
    from services.analysis.drift_detector import CodeDriftDetector
    from services.store.store import CapsuleStore

    db = session()
    store = CapsuleStore(db)
    detector = CodeDriftDetector(store)
    report = detector.analyze(target_path=path)

    if json_output:
        click.echo(json_lib.dumps(report.to_dict(), indent=2))
    else:
        table = Table(title="📐 Code Drift & Architectural Boundary Verification", expand=True)
        table.add_column("Severity", style="bold", width=10)
        table.add_column("Rule", style="cyan", width=25)
        table.add_column("Details", style="white")
        table.add_column("Source", style="dim", width=28)

        for v in report.violations:
            sev_color = "[red]ERROR[/red]" if v.severity == "error" else "[yellow]WARN[/yellow]"
            table.add_row(
                sev_color,
                v.rule,
                f"{v.title}\n[dim]{v.description}[/dim]",
                v.source_file or "-",
            )

        console.print(table)
        console.print(
            f"\n[bold]Summary:[/bold] Analyzed [cyan]{report.total_files_analyzed}[/cyan] files, "
            f"[cyan]{report.total_symbols_analyzed}[/cyan] symbols. "
            f"Found [yellow]{report.dead_code_count}[/yellow] dead code warnings, "
            f"[red]{report.boundary_violations_count}[/red] boundary violations, "
            f"[yellow]{report.orphan_adrs_count}[/yellow] orphan ADRs."
        )

        if report.is_passing(strict=strict):
            console.print("\n[bold green]✓ Architectural boundaries verified successfully![/bold green]\n")
        else:
            console.print("\n[bold red]✗ Architectural violations detected![/bold red]\n")

    if fail_on_violation and not report.is_passing(strict=strict):
        sys.exit(1)


@cli.group("supersession")
def supersession_group():
    """Detect and manage architectural contradictions and supersession lineage."""
    pass


@supersession_group.command("scan")
@click.option("--target", "-t", default=None, help="Target capsule ID to compare against the vault")
@click.option("--min-confidence", "-c", default=0.5, type=float, help="Minimum confidence threshold (0.0 - 1.0)")
@click.option("--apply", is_flag=True, help="Automatically create supersedes edges and deprecate older capsules")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON report")
def supersession_scan(target, min_confidence, apply, json_output):
    """Scan vault for invariant contradictions and supersession opportunities."""
    import json as json_lib
    from services.analysis.supersession import InvariantSupersessionEngine
    from services.store.store import CapsuleStore

    db = session()
    try:
        store = CapsuleStore(db)
        engine = InvariantSupersessionEngine(store)
        report = engine.detect_contradictions(
            target_capsule_id=target,
            min_confidence=min_confidence,
            apply_supersession=apply,
        )
        if apply:
            db.commit()

        if json_output:
            click.echo(json_lib.dumps(report.to_dict(), indent=2))
        else:
            table = Table(title="🔄 Invariant Contradiction & Supersession Analysis", expand=True)
            table.add_column("Type", style="cyan", width=20)
            table.add_column("Confidence", style="bold", width=12)
            table.add_column("Newer Capsule", style="green", width=25)
            table.add_column("Older Capsule", style="yellow", width=25)
            table.add_column("Reason", style="white")
            table.add_column("Applied", style="magenta", width=10)

            for f in report.findings:
                conf_str = f"{int(f.confidence_score * 100)}%"
                table.add_row(
                    f.contradiction_type,
                    conf_str,
                    f"{f.newer_topic}\n[dim]{f.newer_capsule_id[:8]}[/dim]",
                    f"{f.older_topic}\n[dim]{f.older_capsule_id[:8]}[/dim]",
                    f.reason,
                    "✓ Linked" if f.applied else "Pending",
                )

            console.print(table)
            console.print(
                f"\n[bold]Summary:[/bold] Analyzed [cyan]{report.total_analyzed}[/cyan] capsule pairs. "
                f"Detected [yellow]{report.contradictions_found}[/yellow] contradictions / supersessions. "
                f"Applied [green]{report.superseded_applied}[/green] graph linkages."
            )
    finally:
        db.close()


@supersession_group.command("resolve")
@click.argument("newer_id")
@click.argument("older_id")
@click.option("--deprecate/--no-deprecate", default=True, help="Mark older capsule confidence as deprecated")
def supersession_resolve(newer_id, older_id, deprecate):
    """Explicitly link newer capsule superseding older capsule."""
    from services.analysis.supersession import InvariantSupersessionEngine
    from services.store.store import CapsuleStore

    db = session()
    try:
        store = CapsuleStore(db)
        engine = InvariantSupersessionEngine(store)
        newer = resolve_capsule(db, newer_id)
        older = resolve_capsule(db, older_id)
        if not newer or not older:
            console.print("[red]One or both capsules not found[/red]")
            sys.exit(1)

        result = engine.resolve_supersession(newer.id, older.id, deprecate_older=deprecate)
        db.commit()
        console.print(
            f"[green]✓ Linked supersession:[/green] [cyan]{newer.topic}[/cyan] ({newer.id[:8]}) "
            f"supersedes [yellow]{older.topic}[/yellow] ({older.id[:8]})"
            + (" [dim](deprecated)[/dim]" if deprecate else "")
        )
    finally:
        db.close()


if __name__ == "__main__":
    cli()

