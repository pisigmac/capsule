"""Capsule CLI — atomic knowledge management from the terminal."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID

import click
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm

from ..services.parser.parser import CapsuleParser, ParsedCapsule
from ..services.shared.config import config
from ..services.shared.models import Capsule, Tag, CapsuleRelationship, SessionLocal, init_db
from ..services.search.engine import SearchEngine
from ..services.sync.watcher import CapsuleSyncService

console = Console()
API_BASE = os.getenv("CAPSULE_API_URL", "http://localhost:9000/api/v1")


def get_db():
    """Get a database session for CLI operations."""
    init_db()
    return SessionLocal()


@click.group()
@click.option("--api-url", default=None, help="Capsule API base URL")
@click.pass_context
def cli(ctx, api_url):
    """Capsule — atomic knowledge for the AI era."""
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url or API_BASE
    config.ensure_dirs()


@cli.command()
@click.argument("topic")
@click.option("--tag", "-t", multiple=True, help="Tags to attach")
@click.option("--source", "-s", default=None, help="Source of this knowledge")
@click.option("--confidence", "-c", type=click.Choice(["high", "medium", "low", "hearsay"]), default="medium")
@click.option("--editor", "-e", is_flag=True, help="Open in $EDITOR")
def new(topic, tag, source, confidence, editor):
    """Create a new capsule."""
    parser = CapsuleParser()

    if editor:
        import tempfile
        import subprocess

        template = f"""---
topic: {topic}
tags: {list(tag)}
source: {source or ""}
confidence: {confidence}
freshness: {datetime.now(timezone.utc).isoformat()}
---

Write your capsule content here. Be specific. One fact per capsule.
"""
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".capsule.md", delete=False) as f:
            f.write(template)
            tmp_path = f.name

        editor_cmd = os.getenv("EDITOR", "nano")
        subprocess.call([editor_cmd, tmp_path])

        parsed = parser.parse_file(Path(tmp_path))
        os.unlink(tmp_path)
    else:
        content = Prompt.ask("Enter capsule content")
        parsed = ParsedCapsule(
            topic=topic,
            content=content,
            tags=list(tag),
            source=source,
            confidence=confidence,
        )

    db = get_db()
    try:
        capsule = Capsule(
            topic=parsed.topic,
            content=parsed.content,
            freshness=parsed.freshness,
            source=parsed.source,
            confidence=parsed.confidence,
        )
        db.add(capsule)
        db.flush()

        for tag_name in parsed.tags:
            t = db.query(Tag).filter(Tag.name == tag_name).first()
            if not t:
                t = Tag(name=tag_name)
                db.add(t)
                db.flush()
            capsule.tags.append(t)

        db.commit()
        console.print(f"[green]Created capsule:[/green] {capsule.id}")
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
    db = get_db()
    try:
        engine = SearchEngine(db)

        if query:
            results = engine.search(query, tags=list(tag) if tag else None, confidence=confidence, archived=archived, limit=limit)
        elif tag:
            results = engine.search_by_tags(list(tag), limit=limit)
        else:
            capsules = db.query(Capsule).filter(Capsule.archived == archived).order_by(Capsule.updated_at.desc()).limit(limit).all()
            results = [c.to_dict() for c in capsules]

        if not results:
            console.print("[dim]No capsules found.[/dim]")
            return

        table = Table(title=f"Found {len(results)} capsule(s)")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Topic", style="white")
        table.add_column("Tags", style="green")
        table.add_column("Confidence", style="yellow")
        table.add_column("Freshness", style="dim")

        for r in results:
            table.add_row(
                str(r["id"])[:8],
                r["topic"][:50],
                ", ".join(r.get("tags", []))[:30],
                r.get("confidence", "medium"),
                r.get("freshness", "")[:10],
            )

        console.print(table)
    finally:
        db.close()


@cli.command()
@click.argument("capsule_id")
def show(capsule_id):
    """Show a capsule in detail."""
    db = get_db()
    try:
        try:
            uuid_obj = UUID(capsule_id)
        except ValueError:
            # Try partial match
            capsule = db.query(Capsule).filter(Capsule.id.like(f"%{capsule_id}%")).first()
        else:
            capsule = db.query(Capsule).filter(Capsule.id == uuid_obj).first()

        if not capsule:
            console.print("[red]Capsule not found[/red]")
            return

        panel = Panel(
            f"[bold]{capsule.topic}[/bold]\n\n"
            f"{capsule.content}\n\n"
            f"[dim]Tags:[/dim] {', '.join(t.name for t in capsule.tags)}\n"
            f"[dim]Confidence:[/dim] {capsule.confidence}\n"
            f"[dim]Source:[/dim] {capsule.source or 'N/A'}\n"
            f"[dim]Freshness:[/dim] {capsule.freshness.isoformat() if capsule.freshness else 'N/A'}\n"
            f"[dim]ID:[/dim] {capsule.id}",
            title=f"Capsule {str(capsule.id)[:8]}",
            border_style="blue",
        )
        console.print(panel)
    finally:
        db.close()


@cli.command()
@click.argument("from_id")
@click.argument("to_id")
@click.option("--type", "-t", default="relates_to", help="Relationship type")
def link(from_id, to_id, type):
    """Link two capsules together."""
    db = get_db()
    try:
        from_uuid = UUID(from_id)
        to_uuid = UUID(to_id)

        rel = CapsuleRelationship(
            from_capsule_id=from_uuid,
            to_capsule_id=to_uuid,
            relationship_type=type,
        )
        db.add(rel)
        db.commit()
        console.print(f"[green]Linked {from_id[:8]} -> {to_id[:8]} ({type})[/green]")
    except ValueError:
        console.print("[red]Invalid capsule ID format[/red]")
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
    db = get_db()
    try:
        engine = SearchEngine(db)
        context = engine.compose(
            tags=list(tags) if tags else None,
            query=query,
            confidence_min=confidence_min,
            max_tokens=max_tokens,
        )

        if output:
            Path(output).write_text(context)
            console.print(f"[green]Context written to {output}[/green]")
        else:
            syntax = Syntax(context, "markdown", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title="Composed Context", border_style="green"))
            console.print(f"\n[dim]Estimated tokens: {len(context.split())}[/dim]")
    finally:
        db.close()


@cli.command()
@click.option("--days", "-d", default=90, help="Days since last update")
def stale(days):
    """Show capsules that haven't been updated recently."""
    db = get_db()
    try:
        engine = SearchEngine(db)
        capsules = engine.stale_capsules(days=days)

        if not capsules:
            console.print("[green]All capsules are fresh.[/green]")
            return

        table = Table(title=f"{len(capsules)} stale capsule(s) (>{days} days)")
        table.add_column("ID", style="cyan")
        table.add_column("Topic", style="white")
        table.add_column("Last Updated", style="red")

        for c in capsules:
            table.add_row(
                str(c["id"])[:8],
                c["topic"][:50],
                c.get("updated_at", "")[:10],
            )

        console.print(table)
    finally:
        db.close()


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--watch", "-w", is_flag=True, help="Keep watching for changes")
def sync(directory, watch):
    """Sync a directory of .capsule.md files into the database."""
    service = CapsuleSyncService(watch_dirs=[directory])
    count = service.initial_sync()
    console.print(f"[green]Synced {count} capsule(s) from {directory}[/green]")

    if watch:
        console.print("[dim]Watching for changes... (Ctrl+C to stop)[/dim]")
        service.start()
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopping watcher...[/dim]")
        finally:
            service.stop()


@cli.command()
@click.argument("capsule_id")
def archive(capsule_id):
    """Archive a capsule."""
    db = get_db()
    try:
        uuid_obj = UUID(capsule_id)
        capsule = db.query(Capsule).filter(Capsule.id == uuid_obj).first()
        if not capsule:
            console.print("[red]Capsule not found[/red]")
            return

        capsule.archived = True
        db.commit()
        console.print(f"[green]Archived {capsule_id[:8]}[/green]")
    except ValueError:
        console.print("[red]Invalid capsule ID[/red]")
    finally:
        db.close()


@cli.command()
def status():
    """Show system status."""
    db = get_db()
    try:
        total = db.query(Capsule).count()
        archived = db.query(Capsule).filter(Capsule.archived == True).count()
        active = total - archived
        tag_count = db.query(Tag).count()
        rel_count = db.query(CapsuleRelationship).count()

        console.print(Panel(
            f"[bold]Capsule Status[/bold]\n\n"
            f"Active capsules: {active}\n"
            f"Archived capsules: {archived}\n"
            f"Total tags: {tag_count}\n"
            f"Relationships: {rel_count}\n"
            f"Database: {config.database_url}\n"
            f"Capsules dir: {config.capsules_dir}",
            border_style="blue",
        ))
    finally:
        db.close()


@cli.command()
def init():
    """Initialize the capsule workspace."""
    config.ensure_dirs()
    init_db()

    # Create a sample capsule
    db = get_db()
    try:
        if db.query(Capsule).count() == 0:
            sample = Capsule(
                topic="Welcome to Capsule",
                content="Capsule is atomic knowledge management for the AI era.\n\n"
                        "Each capsule is one fact, fully qualified.\n"
                        "Use `capsule new` to create one.\n"
                        "Use `capsule search` to find them.\n"
                        "Use `capsule compose` to build context windows.",
                freshness=datetime.now(timezone.utc),
                source="capsule-init",
                confidence="high",
            )
            db.add(sample)
            db.flush()

            welcome_tag = Tag(name="welcome")
            db.add(welcome_tag)
            db.flush()
            sample.tags.append(welcome_tag)
            db.commit()
            console.print("[green]Initialized capsule workspace with sample capsule.[/green]")
        else:
            console.print("[dim]Capsule workspace already initialized.[/dim]")
    finally:
        db.close()


if __name__ == "__main__":
    cli()
