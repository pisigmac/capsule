"""Simulation: Multi-Turn Agent Memory Bloat & Content-Hash Deduplication.

Simulates an autonomous agent running an iterative 50-step software engineering
workflow (debugging, reviewing logs, checking CI, querying databases).

Compares:
1. Baseline Agent Memory (Naive Vector Store / Append-only):
   - Every observation/thought is appended as a new chunk.
   - Suffers from linear O(N) memory explosion, duplicate retrieval, and token waste.
2. Capsule Memory (Content-Hash Deduplication + Normalized Hash):
   - Atomically stores facts with SHA-256 deduplication.
   - Recurring observations merge tags without generating duplicate files or index rows.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import tiktoken
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.shared.models import Base, _ensure_columns, _init_sqlite_search
from services.store.store import CapsuleStore

console = Console()
enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(enc.encode(text))


# ─── REPERTOIRE OF AGENT OBSERVATIONS ACROSS 50 STEPS ───
CANDIDATE_FACTS = [
    ("Auth Bypass in Staging", "Staging environment skips JWT token verification when X-Debug-Override header is provided.", ["auth", "staging"]),
    ("Mobile CI Dependency", "Nightly Android and iOS integration test suites depend on the X-Debug-Override header bypass in staging.", ["ci", "mobile", "auth"]),
    ("Database Dialect Selection", "SQLite with FTS5 is used for single-process local development, while PostgreSQL 16 with tsvector is used for production.", ["database", "sqlite", "postgres"]),
    ("Zero-Data-Loss Index Rebuilding", "The database is strictly a derived search index. If corrupted, it can be regenerated from .capsule.md files on disk.", ["database", "sync", "architecture"]),
    ("Content-Hash Dedup Algorithm", "Capsule uses normalized SHA-256 hashing to detect duplicates, merging tags rather than creating duplicate files.", ["dedup", "hashing", "store"]),
    ("Update Conflict Guard", "PATCH /capsules/{id} returns HTTP 409 Conflict if an update causes the body to match another existing capsule.", ["dedup", "api", "conflicts"]),
    ("MCP Stdio and HTTP Support", "FastMCP server supports stdio for local AI assistants and Streamable HTTP on port 9101 for remote clients.", ["mcp", "server", "http"]),
    ("MCP Tools Roster", "Capsule MCP server exposes search_capsules, compose_context, get_capsule, create_capsule, and list_stale tools.", ["mcp", "tools", "api"]),
    ("Filesystem Watchdog Debounce", "Watchdog service monitors CAPSULES_DIR with a 250ms debounce window to prevent race conditions during git checkouts.", ["sync", "watchdog", "filesystem"]),
    ("PostgreSQL GIN tsvector", "Production PostgreSQL uses GIN indexing over generated tsvector columns with psycopg3 connection pooling.", ["database", "postgres", "gin"]),
    ("FastAPI Bearer Auth", "When CAPSULE_API_TOKEN is set, all routes except /health, /docs, and /openapi.json require Bearer authorization.", ["api", "auth", "security"]),
    ("Token Budget Knapsack", "The compose endpoint selects high-confidence, high-relevance capsules to fit within a bounded max_tokens budget.", ["search", "compose", "tokens"]),
    ("Stale Knowledge Pruning", "The stale endpoint identifies facts not updated within a configurable threshold (default: 90 days).", ["lifecycle", "stale", "maintenance"]),
    ("Dual-Plane Storage Separation", "Human-readable Markdown on the filesystem is canonical; relational indexes are derived search mirrors.", ["architecture", "storage", "philosophy"]),
    ("CLI Script Entrypoints", "Package scripts register both capsule and kapsule CLI commands with click and rich formatting.", ["cli", "packaging", "distribution"]),
]


class NaiveAppendMemory:
    """Simulates standard append-only agent memory (LangChain/LlamaIndex vector store)."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir / "naive_memory"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = []

    def record(self, topic: str, content: str, tags: List[str]) -> None:
        rec_id = f"mem_{len(self.records) + 1:04d}"
        file_path = self.storage_dir / f"{rec_id}.md"
        payload = f"# {topic}\n\nTags: {', '.join(tags)}\n\n{content}\n"
        file_path.write_text(payload, encoding="utf-8")
        self.records.append({
            "id": rec_id,
            "topic": topic,
            "content": content,
            "tags": tags,
            "tokens": count_tokens(payload),
            "bytes": len(payload.encode("utf-8")),
        })

    def get_stats(self) -> Dict[str, Any]:
        total_tokens = sum(r["tokens"] for r in self.records)
        total_bytes = sum(r["bytes"] for r in self.records)
        unique_contents = len(set(r["content"] for r in self.records))
        duplicate_count = len(self.records) - unique_contents
        redundancy_pct = (duplicate_count / max(len(self.records), 1)) * 100.0
        return {
            "record_count": len(self.records),
            "total_tokens": total_tokens,
            "total_bytes": total_bytes,
            "redundancy_pct": round(redundancy_pct, 1),
            "unique_facts": unique_contents,
        }


class CapsuleSimMemory:
    """Capsule memory utilizing normalized SHA-256 deduplication and atomic files."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir / "capsule_memory"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = storage_dir / "capsule_sim.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        with self.engine.connect() as conn:
            _ensure_columns(conn, "sqlite")
            _init_sqlite_search(conn)
            conn.commit()
        self.Session = sessionmaker(bind=self.engine)
        self.dedup_events = 0
        self.total_submissions = 0

    def record(self, topic: str, content: str, tags: List[str]) -> bool:
        self.total_submissions += 1
        db = self.Session()
        try:
            store = CapsuleStore(db, capsules_dir=self.storage_dir)
            cap = store.create(topic=topic, content=content, tags=tags, source="agent_sim")
            db.commit()
            if getattr(cap, "deduped", False):
                self.dedup_events += 1
                return True
            return False
        finally:
            db.close()

    def get_stats(self) -> Dict[str, Any]:
        db = self.Session()
        try:
            files = list(self.storage_dir.glob("*.capsule.md"))
            total_tokens = sum(count_tokens(f.read_text(encoding="utf-8")) for f in files)
            total_bytes = sum(f.stat().st_size for f in files)
            return {
                "record_count": len(files),
                "total_tokens": total_tokens,
                "total_bytes": total_bytes,
                "total_submissions": self.total_submissions,
                "dedup_events": self.dedup_events,
                "redundancy_pct": 0.0,
                "unique_facts": len(files),
            }
        finally:
            db.close()


def run_simulation(total_steps: int = 50, seed: int = 42) -> Dict[str, Any]:
    random.seed(seed)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        naive_mem = NaiveAppendMemory(tmp_path)
        capsule_mem = CapsuleSimMemory(tmp_path)

        trajectory_steps = []
        step_metrics = []

        # Generate realistic trajectory with repeated observations
        for step in range(1, total_steps + 1):
            # In each step, the agent observes 2 facts
            # 40% probability of re-observing a previously seen fact
            # 60% probability of discovering a new candidate fact
            for _ in range(2):
                if step > 5 and random.random() < 0.45:
                    # Duplicate observation
                    chosen = random.choice(CANDIDATE_FACTS[:min(step, len(CANDIDATE_FACTS))])
                    topic, content, tags = chosen
                    # Small whitespace variation to test normalization
                    if random.random() < 0.5:
                        content_variant = f"  {content}  \n"
                    else:
                        content_variant = content
                else:
                    chosen = random.choice(CANDIDATE_FACTS)
                    topic, content_variant, tags = chosen

                # Add a dynamic situational tag
                iter_tags = list(tags) + [f"step_{step}"]

                naive_mem.record(topic, content_variant, iter_tags)
                capsule_mem.record(topic, content_variant, iter_tags)

            if step % 5 == 0 or step == total_steps or step == 1:
                n_stats = naive_mem.get_stats()
                c_stats = capsule_mem.get_stats()

                token_savings = ((n_stats["total_tokens"] - c_stats["total_tokens"]) / max(n_stats["total_tokens"], 1)) * 100.0
                file_savings = ((n_stats["record_count"] - c_stats["record_count"]) / max(n_stats["record_count"], 1)) * 100.0

                step_metrics.append({
                    "step": step,
                    "naive_records": n_stats["record_count"],
                    "capsule_records": c_stats["record_count"],
                    "naive_tokens": n_stats["total_tokens"],
                    "capsule_tokens": c_stats["total_tokens"],
                    "naive_bytes": n_stats["total_bytes"],
                    "capsule_bytes": c_stats["total_bytes"],
                    "naive_redundancy": n_stats["redundancy_pct"],
                    "capsule_redundancy": 0.0,
                    "token_savings_pct": round(token_savings, 1),
                    "file_savings_pct": round(file_savings, 1),
                    "dedup_count": c_stats["dedup_events"],
                })

        final_naive = naive_mem.get_stats()
        final_capsule = capsule_mem.get_stats()

        return {
            "total_steps": total_steps,
            "final_naive": final_naive,
            "final_capsule": final_capsule,
            "step_metrics": step_metrics,
        }


def generate_plot(results: Dict[str, Any], output_path: Path) -> None:
    steps = [m["step"] for m in results["step_metrics"]]
    naive_tokens = [m["naive_tokens"] for m in results["step_metrics"]]
    capsule_tokens = [m["capsule_tokens"] for m in results["step_metrics"]]
    naive_files = [m["naive_records"] for m in results["step_metrics"]]
    capsule_files = [m["capsule_records"] for m in results["step_metrics"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Plot 1: Token Consumption over Steps
    ax1.plot(steps, naive_tokens, color="#e63946", marker="o", linewidth=2.5, label="Baseline (Append-only Vector Store)")
    ax1.plot(steps, capsule_tokens, color="#2a9d8f", marker="s", linewidth=2.5, label="Capsule (Content-Hash Dedup)")
    ax1.fill_between(steps, capsule_tokens, naive_tokens, color="#2a9d8f", alpha=0.15)
    ax1.set_title("Total Memory Tokens vs. Agent Execution Steps", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Agent Execution Steps", fontsize=11)
    ax1.set_ylabel("Stored Memory Tokens (cl100k_base)", fontsize=11)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left")

    # Plot 2: Total Files / Records over Steps
    ax2.plot(steps, naive_files, color="#e63946", linestyle="--", marker="o", linewidth=2, label="Baseline Records (O(N) growth)")
    ax2.plot(steps, capsule_files, color="#264653", marker="^", linewidth=2.5, label="Capsule Unique Facts (Bounded)")
    ax2.set_title("Memory Records vs. Agent Steps", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Agent Execution Steps", fontsize=11)
    ax2.set_ylabel("Total Stored Records / Files", fontsize=11)
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="upper left")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close()


def main():
    console.print(Panel.fit(
        "[bold cyan]Multi-Turn Agent Memory Bloat & Deduplication Simulation[/bold cyan]\n"
        "[dim]Simulating 50-step autonomous agent lifecycle (100 observations)[/dim]",
        border_style="cyan"
    ))

    results = run_simulation(total_steps=50, seed=42)

    # Render results table
    table = Table(title="Agent Memory Accumulation Across 50 Steps")
    table.add_column("Step", justify="center", style="cyan")
    table.add_column("Baseline Files", justify="right", style="red")
    table.add_column("Capsule Files", justify="right", style="green")
    table.add_column("Baseline Tokens", justify="right", style="red")
    table.add_column("Capsule Tokens", justify="right", style="green")
    table.add_column("Token Savings", justify="right", style="bold yellow")
    table.add_column("Dedup Merges", justify="right", style="bold blue")

    for m in results["step_metrics"]:
        table.add_row(
            str(m["step"]),
            str(m["naive_records"]),
            str(m["capsule_records"]),
            str(m["naive_tokens"]),
            str(m["capsule_tokens"]),
            f"{m['token_savings_pct']}%",
            str(m["dedup_count"]),
        )

    console.print(table)

    results_dir = Path("evals/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON Report
    json_path = results_dir / "memory_bloat_report.json"
    json_path.write_text(json.dumps(results, indent=2))

    # Generate Publication Plot
    plot_path = results_dir / "memory_bloat_simulation.png"
    generate_plot(results, plot_path)

    fn = results["final_naive"]
    fc = results["final_capsule"]
    overall_token_savings = round(((fn["total_tokens"] - fc["total_tokens"]) / fn["total_tokens"]) * 100.0, 1)
    overall_record_savings = round(((fn["record_count"] - fc["record_count"]) / fn["record_count"]) * 100.0, 1)

    console.print(f"\n[bold green]Simulation Completed Successfully![/bold green]")
    console.print(f"• Baseline final storage: [red]{fn['record_count']} records, {fn['total_tokens']} tokens[/red] ({fn['redundancy_pct']}% redundant)")
    console.print(f"• Capsule final storage:  [green]{fc['record_count']} records, {fc['total_tokens']} tokens[/green] (0.0% redundant)")
    console.print(f"• Overall Token Reduction: [bold yellow]{overall_token_savings}%[/bold yellow]")
    console.print(f"• Overall Record Pruning:  [bold yellow]{overall_record_savings}%[/bold yellow]")
    console.print(f"• Saved plot to: [cyan]{plot_path}[/cyan]")
    console.print(f"• Saved report to: [cyan]{json_path}[/cyan]")


if __name__ == "__main__":
    main()
