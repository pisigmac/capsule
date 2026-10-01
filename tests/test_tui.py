"""Unit and integration tests for caps browse / caps tui."""
from __future__ import annotations

from pathlib import Path
import pytest
from click.testing import CliRunner
from rich.layout import Layout

from capsule_cli.tui.browser import TuiBrowser
from capsule_cli.main import cli
from services.store.store import CapsuleStore


@pytest.fixture
def populated_store(db_session, temp_capsule_dir):
    store = CapsuleStore(db_session, capsules_dir=temp_capsule_dir)
    store.reconcile()
    db_session.commit()
    return store, temp_capsule_dir


class TestTuiBrowserState:
    def test_browser_initial_state(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()

        assert len(browser.capsules) == 2
        assert browser.selected_index == 0
        assert browser.search_mode is False
        assert browser.query == ""

    def test_browser_navigation(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()

        # Navigate down
        browser.handle_action("down")
        assert browser.selected_index == 1

        # Clamping at boundary
        browser.handle_action("down")
        assert browser.selected_index == 1

        # Navigate up
        browser.handle_action("up")
        assert browser.selected_index == 0

        # Clamping at top
        browser.handle_action("up")
        assert browser.selected_index == 0

    def test_browser_filtering(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)

        browser.query = "Auth"
        browser.refresh()
        assert len(browser.capsules) == 1
        assert "Auth" in browser.capsules[0]["topic"]

        browser.query = "xyz_nonexistent_term"
        browser.refresh()
        assert len(browser.capsules) == 0
        assert browser.get_selected_capsule() is None

    def test_browser_archive_action(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()
        initial_count = len(browser.capsules)

        # Archive selected
        browser.handle_action("a")
        assert len(browser.capsules) == initial_count - 1

    def test_browser_delete_action(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()
        initial_count = len(browser.capsules)

        # Delete selected
        browser.handle_action("d")
        assert len(browser.capsules) == initial_count - 1

    def test_browser_reconcile_action(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()
        assert len(browser.capsules) == 2

        # Create new capsule file directly on disk
        new_file = caps_dir / "redis.caps.md"
        new_file.write_text("---\ntopic: Redis caching layer\ntags: [cache]\n---\nRedis in-memory caching.")

        # Reconcile action
        browser.handle_action("r")
        assert len(browser.capsules) == 3

    def test_browser_search_mode_toggles(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)

        browser.handle_action("/")
        assert browser.search_mode is True

        browser.handle_action("esc")
        assert browser.search_mode is False

    def test_browser_key_handling(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()

        # Quit returns False
        assert browser.handle_key("q") is False
        assert browser.handle_key("\x03") is False

        # Vi navigation keys
        assert browser.handle_key("j") is True
        assert browser.selected_index == 1
        assert browser.handle_key("k") is True
        assert browser.selected_index == 0

        # Jump to bottom and top
        assert browser.handle_key("G") is True
        assert browser.selected_index == 1
        assert browser.handle_key("g") is True
        assert browser.selected_index == 0

        # Enter search mode with slash
        assert browser.handle_key("/") is True
        assert browser.search_mode is True

        # Type query characters
        for char in "Auth":
            assert browser.handle_key(char) is True
        assert browser.query == "Auth"
        assert len(browser.capsules) == 1

        # Backspace
        assert browser.handle_key("\x7f") is True
        assert browser.query == "Aut"

        # Confirm search with Enter
        assert browser.handle_key("\r") is True
        assert browser.search_mode is False

    def test_render_layout(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()

        layout = browser.render_layout()
        assert isinstance(layout, Layout)
        assert "header" in layout.map
        assert "body" in layout.map
        assert "footer" in layout.map
        assert "list" in layout.map
        assert "preview" in layout.map

    def test_render_preview_with_relationships(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        browser.refresh()
        assert len(browser.capsules) == 2

        # Link capsules
        store.link(browser.capsules[0]["id"], browser.capsules[1]["id"], "relates_to")
        db_session.commit()

        layout = browser.render_layout()
        assert layout is not None

    def test_browser_run_non_interactive(self, db_session, populated_store):
        store, caps_dir = populated_store
        browser = TuiBrowser(db_session=db_session, capsules_dir=caps_dir)
        # In pytest, stdin is not a tty so run() renders layout once and returns cleanly
        browser.run()


class TestTuiCli:
    def test_browse_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["browse", "--help"])
        assert result.exit_code == 0
        assert "browse" in result.output.lower() or "terminal" in result.output.lower()

    def test_tui_alias_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tui", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.output.lower() or "browse" in result.output.lower()

    def test_browse_execution(self, populated_store):
        store, caps_dir = populated_store
        runner = CliRunner()
        result = runner.invoke(cli, ["browse", "--dir", str(caps_dir)])
        assert result.exit_code == 0

    def test_tui_execution(self, populated_store):
        store, caps_dir = populated_store
        runner = CliRunner()
        result = runner.invoke(cli, ["tui", "--dir", str(caps_dir)])
        assert result.exit_code == 0
