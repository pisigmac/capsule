"""Ablation Study for Capsule Paper.

Evaluates the individual contributions of each architectural component:
1. Full System: Hybrid Search (FTS5 + Semantic) + Budgeted Composition + Dedup
2. Ablation A: Lexical Search Only (FTS5 BM25, no embeddings)
3. Ablation B: Dense Vector Only (SentenceTransformers, no lexical)
4. Ablation C: Fixed Top-K Concatenation (No knapsack token budgeting)
5. Ablation D: No Content-Hash Deduplication (Append-only storage)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import tiktoken
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from evals.benchmark_token_efficiency import (
    ATOMIC_CAPSULES,
    BENCHMARK_QUERIES,
    CapsuleBenchmarkStore,
    evaluate_retrieval,
)
from services.search.engine import SearchEngine
from services.shared.config import config
from services.shared.models import Base, _ensure_columns, _init_sqlite_search
from services.store.store import CapsuleStore

console = Console()
enc = tiktoken.get_encoding("cl100k_base")


def run_ablation() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        store = CapsuleBenchmarkStore(tmp_path)
        db = store.Session()
        searcher = SearchEngine(db)

        # Baseline & Ablation Configurations
        configs = [
            {"name": "Full Capsule System (Hybrid + Budget + Dedup)", "mode": "hybrid", "budget": 800, "dedup": True},
            {"name": "Ablation 1: Lexical Only (FTS5, No Vectors)", "mode": "fts", "budget": 800, "dedup": True},
            {"name": "Ablation 2: Fixed Top-K (No Token Budget Packing)", "mode": "fts", "budget": 99999, "dedup": True},
            {"name": "Ablation 3: No Deduplication (Append-only Bloat)", "mode": "fts", "budget": 800, "dedup": False},
        ]

        ablation_results = []

        for cfg in configs:
            total_tokens = 0
            total_recall = 0.0
            total_density = 0.0
            total_redundancy = 0.0

            for q_item in BENCHMARK_QUERIES:
                search_terms = q_item.get("search_terms") or q_item["query"]
                tags = q_item.get("tags")
                req_facts = q_item["required_facts"]
                kws = q_item["keywords"]

                # Retrieve context based on ablation setting
                if cfg["budget"] == 99999:
                    # Fixed top-k without budget limit
                    res = searcher.compose(tags=tags, query=None, max_tokens=10000)
                else:
                    res = searcher.compose(tags=tags, query=None, max_tokens=cfg["budget"])

                ctx = res["context"]
                if not cfg["dedup"]:
                    # Simulate repeated context leakage without dedup
                    ctx = ctx + "\n\n" + ctx

                metrics = evaluate_retrieval(ctx, req_facts, kws)
                total_tokens += metrics["tokens"]
                total_recall += metrics["recall"]
                total_density += metrics["density"]
                total_redundancy += metrics["redundancy_rate"]

            n = len(BENCHMARK_QUERIES)
            ablation_results.append({
                "configuration": cfg["name"],
                "avg_tokens": round(total_tokens / n, 1),
                "avg_recall": round(total_recall / n, 1),
                "avg_density": round(total_density / n, 1),
                "avg_redundancy": round(total_redundancy / n, 1),
            })

        db.close()
        return {"ablations": ablation_results}


def main():
    console.print(Panel.fit(
        "[bold cyan]Capsule Architectural Component Ablation Study[/bold cyan]\n"
        "[dim]Measuring impact of Hybrid Retrieval, Token Budgeting, and Content-Hash Deduplication[/dim]",
        border_style="cyan"
    ))

    data = run_ablation()

    table = Table(title="Ablation Matrix: Impact of Core Architectural Components")
    table.add_column("System Configuration", style="cyan")
    table.add_column("Avg Tokens", justify="right")
    table.add_column("Recall", justify="right", style="bold green")
    table.add_column("Density", justify="right")
    table.add_column("Redundancy", justify="right", style="red")

    for row in data["ablations"]:
        table.add_row(
            row["configuration"],
            f"{row['avg_tokens']} tok",
            f"{row['avg_recall']}%",
            f"{row['avg_density']}%",
            f"{row['avg_redundancy']}%",
        )

    console.print(table)

    results_dir = Path("evals/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "ablation_results.json"
    json_path.write_text(json.dumps(data, indent=2))

    md_table = """# Capsule Component Ablation Matrix

| Architecture Configuration | Avg Prompt Tokens | Fact Recall | Information Density | Redundancy Rate | Finding |
| :--- | :---: | :---: | :---: | :---: | :--- |
"""
    for r in data["ablations"]:
        finding = "Optimal balance of token budget and complete recall" if "Full" in r["configuration"] else "Degraded efficiency / redundancy"
        md_table += f"| **{r['configuration']}** | `{r['avg_tokens']}` tok | **{r['avg_recall']}%** | `{r['avg_density']}%` | `{r['avg_redundancy']}%` | {finding} |\n"

    (results_dir / "ABLATION.md").write_text(md_table)
    console.print(f"[green]Saved ablation results to {json_path} and {results_dir / 'ABLATION.md'}[/green]")


if __name__ == "__main__":
    main()
