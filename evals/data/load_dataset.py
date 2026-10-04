"""Convenience loader for Capsule benchmark evaluation datasets.

Usage:
    from evals.data.load_dataset import (
        load_technical_corpus,
        load_atomic_capsules,
        load_benchmark_queries,
        load_bloat_simulation_stream,
        load_hotpotqa_100,
    )

    corpus = load_technical_corpus()
    capsules = load_atomic_capsules()
    queries = load_benchmark_queries()
    stream = load_bloat_simulation_stream()
    hotpotqa = load_hotpotqa_100()
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

DATA_DIR = Path(__file__).resolve().parent


def load_technical_corpus() -> List[Dict[str, Any]]:
    """Loads 5 technical software architecture specification documents."""
    path = DATA_DIR / "technical_corpus.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_atomic_capsules() -> List[Dict[str, Any]]:
    """Loads 10 ground-truth atomic capsules with frontmatter and hashes."""
    path = DATA_DIR / "atomic_capsules.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_benchmark_queries() -> List[Dict[str, Any]]:
    """Loads 5 multi-hop benchmark queries with ground-truth required facts."""
    path = DATA_DIR / "benchmark_queries.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_bloat_simulation_stream() -> List[Dict[str, Any]]:
    """Loads 100-submission agent memory stream across 50 execution steps."""
    path = DATA_DIR / "bloat_simulation_stream.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_hotpotqa_100() -> List[Dict[str, Any]]:
    """Loads 100 verified multi-hop reasoning questions from the official HotpotQA validation set."""
    path = DATA_DIR / "hotpotqa_100.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_hotpotqa_1000() -> List[Dict[str, Any]]:
    """Loads 1,000 verified multi-hop reasoning questions from the official HotpotQA validation set."""
    path = DATA_DIR / "hotpotqa_1000.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

