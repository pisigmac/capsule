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
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".capsule.md", delete=False) as handle:
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
def search(query, tag, confidence, archived, limit):
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
def compose(tags, query, confidence_min, max_tokens, output):
    """Compose a context window from capsules."""
    db = session()
    try:
        engine = SearchEngine(db)
        result = engine.compose(
            tags=list(tags) if tags else None,
            query=query,
            confidence_min=confidence_min,
            max_tokens=max_tokens,
        )
        context = result["context"]
        if output:
            Path(output).write_text(context, encoding="utf-8")
            console.print(f"[green]Context written to {output}[/green]")
        else:
            syntax = Syntax(context or "[empty]", "markdown", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title="Composed Context", border_style="green"))
        console.print(
            f"[dim]capsules={result['capsule_count']} tokens≈{result['token_estimate']} "
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
def sync(directory, watch):
    """Reindex .capsule.md files into the search database."""
    watch_dir = directory or str(config.capsules_dir)
    service = CapsuleSyncService(watch_dirs=[watch_dir])
    count = service.initial_sync()
    console.print(f"[green]Synced {count} capsule(s) from {watch_dir}[/green]")
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


@cli.command("mcp")
def mcp_cmd():
    """Run the Capsule MCP server on stdio."""
    serve_mcp()


if __name__ == "__main__":
    cli()
