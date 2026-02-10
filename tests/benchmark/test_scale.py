"""Benchmark: Token cost at scale — how costs grow with data size.

Parameterised across N ∈ {10, 100, 500, 1_000, 5_000} to show that:
  - Native: token cost is O(N) — must load everything into context
  - RLM:    token cost is O(1) — always returns bounded results

Tests:
  1. Recall tokens at scale — tokens to retrieve 10 insights from N
  2. Context overhead at scale — tokens consumed to "have" N insights available
  3. Search tokens at scale — tokens to search across N insights
  4. Graph traversal at scale — tokens for "find related" across N nodes
"""

from __future__ import annotations

from typing import Any

import pytest

from memcp.core import memory
from memcp.core.graph import GraphMemory

from .datasets import generate_insights
from .metrics import BenchmarkReport, ComparisonResult, TokenLedger

# Scale parameters — 10K takes time, so kept as largest
_SCALES = [10, 100, 500, 1_000, 5_000]
_SCALE_IDS = ["10", "100", "500", "1K", "5K"]


# ── Test 1: Recall Tokens at Scale ──────────────────────────────────


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_recall_tokens_native(benchmark: Any, n: int, token_ledger: TokenLedger) -> None:
    """Native: must load all N insights to search — O(N) tokens."""
    insights = generate_insights(n, seed=42)

    def run() -> int:
        token_ledger.reset()
        # Native: all insights are in the context window
        full_text = "\n".join(ins["content"] for ins in insights)
        token_ledger.record_text("load_all", full_text)

        # Find 10 relevant results via linear scan
        query = "authentication"
        found = []
        for ins in insights:
            if query in ins["content"].lower():
                found.append(ins)
                if len(found) >= 10:
                    break

        for ins in found:
            token_ledger.record_text("result", ins["content"])

        return token_ledger.total

    result = benchmark(run)
    assert result > 0


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_recall_tokens_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    n: int,
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: recall(limit=10) — O(1) tokens regardless of N."""
    insights = generate_insights(n, seed=42)

    # Pre-populate
    for ins in insights:
        memory.remember(
            content=ins["content"],
            category=ins["category"],
            importance=ins["importance"],
            tags=",".join(ins["tags"]),
            project="benchmark-project",
        )

    def run() -> int:
        token_ledger.reset()
        # RLM: query returns at most 10 results
        results = memory.recall(query="authentication", limit=10, project="benchmark-project")
        for ins in results:
            token_ledger.record_text("result", ins["content"])
        return token_ledger.total

    result = benchmark(run)

    # Compute native cost for comparison
    native_tokens = sum(ins["token_count"] for ins in insights)
    benchmark_report.add(
        ComparisonResult(
            scenario=f"Scale: Recall from {n}",
            metric="Tokens to retrieve 10 insights",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )


# ── Test 2: Context Overhead at Scale ────────────────────────────────


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_context_overhead_native(benchmark: Any, n: int, token_ledger: TokenLedger) -> None:
    """Native: all N insights must be in the context window — O(N)."""
    insights = generate_insights(n, seed=42)

    def run() -> int:
        token_ledger.reset()
        # Cost of having N insights "available" = all of them in context
        total = sum(ins["token_count"] for ins in insights)
        token_ledger.record("context_overhead", total)
        return token_ledger.total

    result = benchmark(run)
    assert result > 0


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_context_overhead_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    n: int,
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: overhead is O(1) — only status metadata in context."""
    insights = generate_insights(n, seed=42)

    for ins in insights:
        memory.remember(
            content=ins["content"],
            category=ins["category"],
            importance=ins["importance"],
            tags=",".join(ins["tags"]),
            project="benchmark-project",
        )

    def run() -> int:
        token_ledger.reset()
        # RLM: only a small status summary needs to be in context
        status = memory.memory_status(project="benchmark-project")
        status_text = (
            f"Memory: {status['total_insights']} insights, "
            f"{status['total_tokens']} tokens stored, "
            f"backend={status['backend']}"
        )
        token_ledger.record_text("status_overhead", status_text)
        return token_ledger.total

    result = benchmark(run)

    native_tokens = sum(ins["token_count"] for ins in insights)
    benchmark_report.add(
        ComparisonResult(
            scenario=f"Scale: Overhead for {n} insights",
            metric="Tokens to keep knowledge available",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )


# ── Test 3: Search Tokens at Scale ──────────────────────────────────


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_search_tokens_native(benchmark: Any, n: int, token_ledger: TokenLedger) -> None:
    """Native: search = all docs in context → O(N) tokens consumed."""
    insights = generate_insights(n, seed=42)

    def run() -> int:
        token_ledger.reset()
        # All insights must be loaded to search
        full_text = "\n".join(ins["content"] for ins in insights)
        token_ledger.record_text("load_for_search", full_text)

        # Search result tokens
        query_tokens = {"database", "sqlite", "storage"}
        results = []
        for ins in insights:
            words = set(ins["content"].lower().split())
            if query_tokens & words:
                results.append(ins)
        for ins in results[:10]:
            token_ledger.record_text("search_result", ins["content"])

        return token_ledger.total

    result = benchmark(run)
    assert result > 0


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_search_tokens_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    n: int,
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: search returns top-K → O(1) tokens regardless of N."""
    insights = generate_insights(n, seed=42)

    for ins in insights:
        memory.remember(
            content=ins["content"],
            category=ins["category"],
            importance=ins["importance"],
            tags=",".join(ins["tags"]),
            project="benchmark-project",
        )

    def run() -> int:
        token_ledger.reset()
        results = memory.recall(
            query="database sqlite storage", limit=10, project="benchmark-project"
        )
        for ins in results:
            token_ledger.record_text("search_result", ins["content"])
        return token_ledger.total

    result = benchmark(run)

    native_tokens = sum(ins["token_count"] for ins in insights)
    benchmark_report.add(
        ComparisonResult(
            scenario=f"Scale: Search across {n}",
            metric="Tokens to search and return top-10",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )


# ── Test 4: Graph Traversal at Scale ────────────────────────────────


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_graph_traversal_native(benchmark: Any, n: int, token_ledger: TokenLedger) -> None:
    """Native: 'find related' = scan everything → O(N) tokens."""
    insights = generate_insights(n, seed=42)

    def run() -> int:
        token_ledger.reset()
        # Must load all to find relationships
        full_text = "\n".join(ins["content"] for ins in insights)
        token_ledger.record_text("load_all", full_text)

        # Simulate finding related: keyword overlap
        target = insights[0]
        target_words = set(target["content"].lower().split())
        related = []
        for ins in insights[1:]:
            words = set(ins["content"].lower().split())
            overlap = len(target_words & words)
            if overlap > 2:
                related.append(ins)
        for ins in related[:5]:
            token_ledger.record_text("related", ins["content"])

        return token_ledger.total

    result = benchmark(run)
    assert result > 0


@pytest.mark.parametrize("n", _SCALES, ids=_SCALE_IDS)
def test_graph_traversal_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    n: int,
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: graph.related() follows edges → O(1) tokens (bounded by edge count)."""
    insights = generate_insights(n, seed=42)

    for ins in insights:
        memory.remember(
            content=ins["content"],
            category=ins["category"],
            importance=ins["importance"],
            tags=",".join(ins["tags"]),
            project="benchmark-project",
        )

    def run() -> int:
        token_ledger.reset()
        graph = GraphMemory()
        try:
            # Get the first node
            all_results = memory.recall(limit=1, project="benchmark-project")
            if all_results:
                node_id = all_results[0]["id"]
                try:
                    traversal = graph.get_related(node_id)
                    for node in traversal.get("related", [])[:5]:
                        token_ledger.record_text("related", node["content"])
                except FileNotFoundError:
                    # Node may not have graph edges; count the recall itself
                    token_ledger.record_text("related", all_results[0]["content"])
        finally:
            graph.close()
        return token_ledger.total

    result = benchmark(run)

    native_tokens = sum(ins["token_count"] for ins in insights)
    benchmark_report.add(
        ComparisonResult(
            scenario=f"Scale: Graph traversal across {n}",
            metric="Tokens for 'find related'",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )
