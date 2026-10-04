"""Standardized benchmark datasets for Capsule."""
from evals.data.load_dataset import (
    load_technical_corpus,
    load_atomic_capsules,
    load_benchmark_queries,
    load_hotpotqa_100,
    load_hotpotqa_1000,
    load_bloat_simulation_stream,
)

__all__ = [
    "load_technical_corpus",
    "load_atomic_capsules",
    "load_benchmark_queries",
    "load_hotpotqa_100",
    "load_hotpotqa_1000",
    "load_bloat_simulation_stream",
]
