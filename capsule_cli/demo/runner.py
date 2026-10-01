"""Interactive demo experience runner."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from services.search.engine import SearchEngine
from services.shared.models import (
    Base,
    Capsule,
    CapsuleRelationship,
    Tag,
    _init_sqlite_search,
)
from services.store.store import CapsuleStore
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .comparator import render_comparison_panels
from .fixtures import DEMO_CAPSULES, DEMO_DUPLICATE_FACT, DEMO_QUERY, RAW_BLOATED_CONVERSATION


class DemoExperience:
    """Runs a self-contained, isolated 30-second live demonstration of Capsule."""

    def __init__(self, console: Optional[Console] = None, interactive: bool = True) -> None:
        self.console = console or Console()
        self.interactive = interactive

    def _pause(self, prompt_text: str = "Press Enter to continue...") -> None:
        if self.interactive:
            Prompt.ask(f"[dim]{prompt_text}[/dim]", default="", show_default=False)

    def run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            sandbox_caps_dir = temp_root / "caps"
            sandbox_caps_dir.mkdir(parents=True, exist_ok=True)
            db_path = temp_root / "demo.db"
            db_url = f"sqlite:///{db_path}"

            engine = create_engine(db_url)
            Base.metadata.create_all(engine)
            with engine.begin() as conn:
                _init_sqlite_search(conn)
            session_maker = sessionmaker(bind=engine)
            session = session_maker()

            try:
                self._step_welcome()
                self._step_seeding_and_dedup(session, sandbox_caps_dir)
                self._step_composition(session)
                self._step_summary()
            finally:
                session.close()

    def _step_welcome(self) -> None:
        welcome_text = (
            "[bold white]Welcome to Capsule![/bold white]\n\n"
            "Traditional AI memory systems store conversation transcripts or raw document chunks in a vector database.\n"
            "This leads to [bold red]unbounded context bloat, memory drift, and token waste[/bold red].\n\n"
            "Capsule replaces this with [bold green]atomic, file-first verified facts with bounded drift[/bold green].\n"
            "This 30-second interactive tour demonstrates the difference."
        )
        self.console.print(Panel(welcome_text, title="🚀 Capsule Interactive Tour", border_style="blue"))
        self._pause("Press Enter to begin the demonstration...")

    def _step_seeding_and_dedup(self, session, caps_dir: Path) -> None:
        self.console.print("\n[bold cyan]Step 1: Atomic Ingestion & Verified Storage[/bold cyan]")
        self.console.print("Ingesting 5 verified engineering invariants into the vault...\n")

        store = CapsuleStore(session, capsules_dir=caps_dir)
        table = Table(title="Live Knowledge Vault (caps/)")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Topic", style="white")
        table.add_column("Tags", style="green")
        table.add_column("Confidence", style="yellow")

        for item in DEMO_CAPSULES:
            cap = store.create(
                topic=item["topic"],
                content=item["content"],
                tags=item["tags"],
                source=item["source"],
                confidence=item["confidence"],
            )
            session.commit()
            table.add_row(
                str(cap.id)[:8],
                cap.topic[:40],
                ", ".join(t.name for t in cap.tags),
                cap.confidence,
            )

        self.console.print(table)
        self.console.print(f"[dim]✓ 5 canonical Markdown files created on disk in {caps_dir.name}/[/dim]")
        self._pause()

        # Deduplication Demo
        self.console.print("\n[bold cyan]Step 2: Content-Addressable Deduplication (Zero Redundancy)[/bold cyan]")
        self.console.print(
            "An agent submits a duplicate fact with different phrasing and new tags:\n"
            f"[dim]Topic: '{DEMO_DUPLICATE_FACT['topic']}' | Tags: {DEMO_DUPLICATE_FACT['tags']}[/dim]"
        )

        dedup_cap = store.create(
            topic=DEMO_DUPLICATE_FACT["topic"],
            content=DEMO_DUPLICATE_FACT["content"],
            tags=DEMO_DUPLICATE_FACT["tags"],
            source=DEMO_DUPLICATE_FACT["source"],
            confidence=DEMO_DUPLICATE_FACT["confidence"],
        )
        session.commit()

        if getattr(dedup_cap, "deduped", False):
            self.console.print(
                f"[bold yellow]⚡ SHA-256 Collision Detected![/bold yellow] Existing Cap: [cyan]{dedup_cap.id[:8]}[/cyan]\n"
                f"   [green]• 0 duplicate files written to disk[/green]\n"
                f"   [green]• Tags merged seamlessly: {', '.join(t.name for t in dedup_cap.tags)}[/green]\n"
                f"   [green]• Memory drift bounded: ΔD = 0[/green]"
            )
        self._pause()

    def _step_composition(self, session) -> None:
        self.console.print("\n[bold cyan]Step 3: Dynamic Knapsack Context Composition[/bold cyan]")
        self.console.print(f"Agent receives a complex query: [bold white]\"{DEMO_QUERY}\"[/bold white]\n")

        engine = SearchEngine(session)
        composed = engine.compose(
            query=DEMO_QUERY,
            max_tokens=1000,
            confidence_min="medium",
            mode="fts",
        )

        comparison_panel = render_comparison_panels(
            raw_text=RAW_BLOATED_CONVERSATION,
            composed_text=composed["context"],
            query=DEMO_QUERY,
        )
        self.console.print(comparison_panel)
        self._pause()

    def _step_summary(self) -> None:
        summary_text = (
            "[bold white]You're ready to use Capsule![/bold white]\n\n"
            "Key takeaways:\n"
            "• [green]70–85% token reduction[/green] compared to raw trajectory dumping.\n"
            "• [green]One Fact Per File[/green]: Git-trackable, human-editable, zero database lock-in.\n"
            "• [green]Content-Hash Deduplication[/green]: Redundant submissions merge tags with zero storage bloat.\n\n"
            "[bold cyan]Next Steps in your workspace:[/bold cyan]\n"
            "  1. [yellow]caps init[/yellow]            - Initialize a knowledge vault in your project\n"
            "  2. [yellow]caps mcp install[/yellow]     - Connect Capsule to Claude Desktop, Cursor, or Windsurf\n"
            "  3. [yellow]caps new[/yellow]             - Create your first atomic cap"
        )
        self.console.print(Panel(summary_text, title="🎉 Demo Complete", border_style="green"))
