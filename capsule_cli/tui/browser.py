"""Terminal User Interface (TUI) browser for Capsule knowledge bases."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from sqlalchemy.orm import Session

from services.search.engine import SearchEngine
from services.shared.config import config
from services.shared.models import CapsuleRelationship
from services.store.store import CapsuleStore


class LayoutMap(dict):
    """Custom dictionary allowing key lookup by string name or Layout instance."""

    def __contains__(self, key: Any) -> bool:
        if isinstance(key, str):
            for k in self.keys():
                if k == key or getattr(k, "name", None) == key:
                    return True
        return super().__contains__(key)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            for k, v in self.items():
                if k == key or getattr(k, "name", None) == key:
                    return v
        return super().__getitem__(key)


class TuiLayout(Layout):
    """Rich Layout supporting named layout discovery via layout.map."""

    @property
    def map(self) -> LayoutMap:
        res = LayoutMap()
        for k, v in super().map.items():
            res[k] = v

        def _collect(node: Layout) -> None:
            if node.name:
                res[node.name] = node
            for child in node.children:
                _collect(child)

        _collect(self)
        return res


class TuiBrowser:
    """Zero-dependency terminal browser for exploring, searching, and managing capsules."""

    def __init__(
        self,
        db_session: Session,
        capsules_dir: Optional[Path | str] = None,
        console: Optional[Console] = None,
    ) -> None:
        self.db_session = db_session
        self.capsules_dir = Path(capsules_dir) if capsules_dir else config.capsules_dir
        self.console = console or Console()
        self.store = CapsuleStore(self.db_session, capsules_dir=self.capsules_dir)
        self.search_engine = SearchEngine(self.db_session)

        # State
        self.query: str = ""
        self.search_mode: bool = False
        self.selected_index: int = 0
        self.capsules: List[Dict[str, Any]] = []
        self.status_message: str = ""
        self._live: Optional[Live] = None

    def refresh(self) -> List[Dict[str, Any]]:
        """Query search engine and update internal capsule list and index bounds."""
        try:
            self.capsules = self.search_engine.search(
                query=self.query,
                archived=False,
                limit=100,
            )
        except Exception as exc:
            self.status_message = f"Search error: {exc}"
            self.capsules = []

        if not self.capsules:
            self.selected_index = 0
        elif self.selected_index >= len(self.capsules):
            self.selected_index = max(0, len(self.capsules) - 1)
        elif self.selected_index < 0:
            self.selected_index = 0

        return self.capsules

    def get_selected_capsule(self) -> Optional[Dict[str, Any]]:
        """Return the dictionary of the currently selected capsule, or None."""
        if not self.capsules or self.selected_index < 0 or self.selected_index >= len(self.capsules):
            return None
        return self.capsules[self.selected_index]

    def get_relationships(self, capsule_id: str) -> Tuple[List[CapsuleRelationship], List[CapsuleRelationship]]:
        """Query outgoing and incoming relationships for a capsule."""
        outgoing = (
            self.db_session.query(CapsuleRelationship)
            .filter(CapsuleRelationship.from_capsule_id == capsule_id)
            .all()
        )
        incoming = (
            self.db_session.query(CapsuleRelationship)
            .filter(CapsuleRelationship.to_capsule_id == capsule_id)
            .all()
        )
        return outgoing, incoming

    def handle_action(self, action: str) -> None:
        """Handle semantic navigation or command action."""
        act = action.strip().lower()

        if act in ("up", "k"):
            if self.selected_index > 0:
                self.selected_index -= 1
        elif act in ("down", "j"):
            if self.selected_index < len(self.capsules) - 1:
                self.selected_index += 1
        elif act == "/":
            self.search_mode = True
            self.status_message = "Search mode: type your query, press Enter or Esc to finish."
        elif act in ("esc", "escape"):
            self.search_mode = False
            self.status_message = "Normal navigation mode."
        elif act == "a":
            self.archive_selected()
        elif act == "d":
            self.delete_selected()
        elif act == "r":
            self.reconcile()
        elif act in ("e", "enter"):
            self.edit_selected(live=self._live)

    def handle_key(self, ch: str) -> bool:
        """Process a raw key input from the terminal. Returns False to exit browser."""
        # 1. Search Mode Key Handling
        if self.search_mode:
            if ch in ("\x1b", "esc"):
                self.handle_action("esc")
                return True
            if ch in ("\r", "\n"):
                self.search_mode = False
                self.status_message = "Search filter applied."
                return True
            if ch in ("\x7f", "\x08", "\b"):
                if self.query:
                    self.query = self.query[:-1]
                    self.refresh()
                return True
            if ch in ("\x1b[A", "\x1bOA"):
                self.handle_action("up")
                return True
            if ch in ("\x1b[B", "\x1bOB"):
                self.handle_action("down")
                return True
            if len(ch) == 1 and ch.isprintable():
                self.query += ch
                self.refresh()
                return True
            return True

        # 2. Normal Navigation Mode Key Handling
        if ch in ("q", "Q", "\x03", "\x04"):
            return False
        if ch in ("\x1b[A", "\x1bOA", "k"):
            self.handle_action("up")
        elif ch in ("\x1b[B", "\x1bOB", "j"):
            self.handle_action("down")
        elif ch == "/":
            self.handle_action("/")
        elif ch in ("\x1b", "esc"):
            if self.query:
                self.query = ""
                self.status_message = "Search filter cleared."
                self.refresh()
        elif ch in ("e", "\r", "\n"):
            self.handle_action("e")
        elif ch in ("a", "A"):
            self.handle_action("a")
        elif ch in ("d", "D"):
            self.handle_action("d")
        elif ch in ("r", "R"):
            self.handle_action("r")
        elif ch in ("c", "C"):
            self.query = ""
            self.refresh()
        elif ch == "g":
            self.selected_index = 0
        elif ch == "G":
            if self.capsules:
                self.selected_index = len(self.capsules) - 1

        return True

    def archive_selected(self) -> None:
        """Archive the currently selected capsule and refresh."""
        selected = self.get_selected_capsule()
        if not selected:
            self.status_message = "No capsule selected to archive."
            return
        try:
            self.store.archive(selected["id"])
            self.db_session.commit()
            self.status_message = f"Archived {selected['id'][:8]} — {selected.get('topic', '')}"
        except Exception as exc:
            self.status_message = f"Archive error: {exc}"
        self.refresh()

    def delete_selected(self) -> None:
        """Delete the currently selected capsule and refresh."""
        selected = self.get_selected_capsule()
        if not selected:
            self.status_message = "No capsule selected to delete."
            return
        try:
            self.store.delete(selected["id"])
            self.db_session.commit()
            self.status_message = f"Deleted {selected['id'][:8]}"
        except Exception as exc:
            self.status_message = f"Delete error: {exc}"
        self.refresh()

    def reconcile(self) -> None:
        """Reconcile markdown disk files with database and refresh."""
        try:
            count = self.store.reconcile()
            self.db_session.commit()
            self.status_message = f"Reconciled repository: indexed {count} capsule(s)."
        except Exception as exc:
            self.status_message = f"Reconcile error: {exc}"
        self.refresh()

    def edit_selected(self, live: Optional[Live] = None) -> None:
        """Open the selected capsule file in $EDITOR, then reindex on return."""
        selected = self.get_selected_capsule()
        if not selected or not selected.get("file_path"):
            self.status_message = "No file path available for selected capsule."
            return

        file_path = selected["file_path"]
        if live:
            live.stop()

        try:
            editor_cmd = os.getenv("EDITOR", "nano")
            import subprocess

            subprocess.call([editor_cmd, str(file_path)])
            count = self.store.reconcile()
            self.db_session.commit()
            self.status_message = f"Updated and reindexed {selected['id'][:8]} (total: {count})."
        except Exception as exc:
            self.status_message = f"Editor error: {exc}"
        finally:
            if live:
                live.start()
            self.refresh()

    def _render_header(self) -> Panel:
        """Render top search bar and current mode status."""
        if self.search_mode:
            query_text = f"[bold green]Search:[/bold green] [white on black] {self.query} [/white on black] [bold green blink]█[/bold green blink]"
            mode_badge = "[black on green] SEARCH MODE [/black on green]"
        else:
            prompt = self.query if self.query else "[dim](press / to search)[/dim]"
            query_text = f"[bold cyan]Search:[/bold cyan] {prompt}"
            mode_badge = "[black on cyan] NORMAL MODE [/black on cyan]"

        match_count = f"[dim]({len(self.capsules)} matching)[/dim]"

        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="right")
        grid.add_row(Text.from_markup(query_text), Text.from_markup(f"{mode_badge}  {match_count}"))

        return Panel(grid, box=box.ROUNDED, style="blue")

    def _render_list(self) -> Panel:
        """Render cursor-navigable table of capsules in left pane."""
        table = Table(box=box.SIMPLE_HEAD, expand=True, show_header=True, header_style="bold magenta")
        table.add_column("", width=2)
        table.add_column("ID", width=8, style="dim")
        table.add_column("Topic", ratio=2)
        table.add_column("Conf", width=6)
        table.add_column("Tags", ratio=1)

        total = len(self.capsules)
        visible_rows = 16
        start_idx = max(0, min(self.selected_index - visible_rows // 2, total - visible_rows))
        end_idx = min(total, start_idx + visible_rows)

        conf_colors = {
            "high": "green",
            "medium": "yellow",
            "low": "red",
            "hearsay": "dim red",
        }

        for i in range(start_idx, end_idx):
            cap = self.capsules[i]
            is_selected = (i == self.selected_index)
            pointer = "▶" if is_selected else " "
            cid = cap["id"][:8]
            topic = cap.get("topic", "")
            conf = cap.get("confidence", "medium")
            conf_col = conf_colors.get(conf, "white")
            tags = ", ".join(cap.get("tags") or [])

            if is_selected:
                row_style = "bold on blue" if not self.search_mode else "bold on dark_blue"
            else:
                row_style = None

            table.add_row(
                pointer,
                cid,
                topic,
                f"[{conf_col}]{conf}[/{conf_col}]",
                f"[dim]{tags}[/dim]",
                style=row_style,
            )

        title_pos = f"[{self.selected_index + 1 if total else 0}/{total}]"
        border_style = "cyan" if not self.search_mode else "dim"
        return Panel(table, title=f"Capsules {title_pos}", box=box.ROUNDED, border_style=border_style)

    def _render_preview(self) -> Panel:
        """Render live markdown and relationship preview in right pane."""
        selected = self.get_selected_capsule()
        if not selected:
            return Panel(
                Align.center("\n[dim]No capsule selected[/dim]\n"),
                title="Preview",
                box=box.ROUNDED,
                border_style="dim",
            )

        conf = selected.get("confidence", "medium")
        conf_colors = {"high": "green", "medium": "yellow", "low": "red", "hearsay": "dim red"}
        conf_col = conf_colors.get(conf, "white")

        tags = selected.get("tags") or []
        tags_markup = " ".join(f"[black on cyan] {t} [/black on cyan]" for t in tags) if tags else "[dim]none[/dim]"
        topic = selected.get("topic", "Untitled")
        freshness = selected.get("freshness") or "N/A"
        source = selected.get("source") or "N/A"
        file_path = selected.get("file_path") or "N/A"
        cid = selected.get("id", "")

        meta_lines = [
            f"[bold underline]{topic}[/bold underline]",
            f"[dim]Tags:[/dim] {tags_markup}",
            f"[dim]Conf:[/dim] [{conf_col}]{conf}[/{conf_col}]  [dim]Freshness:[/dim] {freshness}",
            f"[dim]Source:[/dim] {source}",
            f"[dim]File:[/dim] [dim italic]{file_path}[/dim italic]",
            f"[dim]ID:[/dim] [dim]{cid}[/dim]",
            f"[dim]{'─' * 48}[/dim]",
        ]
        meta_renderable = Text.from_markup("\n".join(meta_lines) + "\n")
        body_renderable = Markdown(selected.get("content") or "")

        # Relationships
        renderables: List[Any] = [meta_renderable, body_renderable]
        outgoing, incoming = self.get_relationships(cid)
        if outgoing or incoming:
            rel_lines = [f"\n[dim]{'─' * 48}[/dim]", "[bold cyan]Relationships:[/bold cyan]"]
            for r in outgoing:
                rel_lines.append(f"  [cyan]→[/cyan] [dim]{r.to_capsule_id[:8]}[/dim] ([italic]{r.relationship_type}[/italic])")
            for r in incoming:
                rel_lines.append(f"  [magenta]←[/magenta] [dim]{r.from_capsule_id[:8]}[/dim] ([italic]{r.relationship_type}[/italic])")
            renderables.append(Text.from_markup("\n".join(rel_lines)))

        return Panel(
            Group(*renderables),
            title=f"Preview: {cid[:8]}",
            box=box.ROUNDED,
            border_style="green",
        )

    def _render_footer(self) -> Panel:
        """Render keybindings and current status bar in footer."""
        if self.search_mode:
            keys_text = (
                "[bold green][Typing Search Query][/bold green]  "
                "[bold cyan][Enter][/bold cyan] Apply  "
                "[bold cyan][Esc][/bold cyan] Cancel  "
                "[bold cyan][Backspace][/bold cyan] Delete"
            )
        else:
            keys_text = (
                "[bold cyan][↑/↓/k/j][/bold cyan] Nav  "
                r"[bold cyan]\[/][/bold cyan] Search  "
                "[bold cyan][e/Enter][/bold cyan] Edit  "
                "[bold cyan][a][/bold cyan] Archive  "
                "[bold cyan][d][/bold cyan] Delete  "
                "[bold cyan][r][/bold cyan] Reconcile  "
                "[bold cyan][q][/bold cyan] Quit"
            )

        status_text = f"  [yellow]ℹ {self.status_message}[/yellow]" if self.status_message else ""
        content = Text.from_markup(f"{keys_text}{status_text}")
        return Panel(content, box=box.ROUNDED, border_style="dim")


    def render_layout(self) -> Layout:
        """Build the full TUI Layout with header, body (list + preview), and footer."""
        layout = TuiLayout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(
            Layout(name="list", ratio=1),
            Layout(name="preview", ratio=1),
        )

        layout["header"].update(self._render_header())
        layout["body"]["list"].update(self._render_list())
        layout["body"]["preview"].update(self._render_preview())
        layout["footer"].update(self._render_footer())

        return layout

    def run(self) -> None:
        """Launch the full-screen terminal event loop."""
        self.refresh()

        if not sys.stdin.isatty():
            self.console.print(self.render_layout())
            return

        with self.console.screen():
            with Live(self.render_layout(), screen=True, auto_refresh=False) as live:
                self._live = live
                try:
                    while True:
                        live.update(self.render_layout(), refresh=True)
                        ch = click.getchar()
                        if not self.handle_key(ch):
                            break
                except (KeyboardInterrupt, EOFError):
                    pass
                finally:
                    self._live = None
