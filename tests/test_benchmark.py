"""Test evaluation harness verifying Capsule's token efficiency advantages."""
from pathlib import Path
import tempfile
import pytest

from evals.benchmark_token_efficiency import (
    CapsuleBenchmarkStore,
    NaiveChunkingRAG,
    evaluate_retrieval,
    BENCHMARK_QUERIES,
)


def test_benchmark_token_efficiency():
    naive_rag = NaiveChunkingRAG(chunk_size=500, chunk_overlap=50)

    with tempfile.TemporaryDirectory() as tmp_dir:
        capsule_bench = CapsuleBenchmarkStore(Path(tmp_dir))

        naive_tokens_total = 0
        capsule_tokens_total = 0
        capsule_recalls = []

        for item in BENCHMARK_QUERIES:
            search_terms = item.get("search_terms") or item["query"]
            tags = item.get("tags")
            req_facts = item["required_facts"]
            kws = item["keywords"]

            naive_ctx = naive_rag.retrieve(search_terms, top_k=4)
            naive_metrics = evaluate_retrieval(naive_ctx, req_facts, kws)
            naive_tokens_total += naive_metrics["tokens"]

            capsule_ctx = capsule_bench.compose(tags=tags, query=None, max_tokens=800)
            capsule_metrics = evaluate_retrieval(capsule_ctx, req_facts, kws)
            capsule_tokens_total += capsule_metrics["tokens"]
            capsule_recalls.append(capsule_metrics["recall"])

        # Assert Capsule saves at least 25% tokens over naive chunking
        token_savings = ((naive_tokens_total - capsule_tokens_total) / naive_tokens_total) * 100.0
        assert token_savings > 25.0, f"Expected >25% token savings, got {token_savings:.1f}%"

        # Assert 100% average recall on the benchmark multi-hop set
        avg_recall = sum(capsule_recalls) / len(capsule_recalls)
        assert avg_recall == 100.0, f"Expected 100% recall, got {avg_recall:.1f}%"
