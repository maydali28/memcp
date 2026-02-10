"""Benchmark: End-to-end token comparison — Claude Native vs Claude with RLM.

Simulates complete workflows and measures total tokens consumed in each mode.

Scenarios:
  A. Session startup — reload previous context
  B. Large document analysis — find a section in a big doc
  C. Cross-reference knowledge — follow causal chains
  D. Multi-turn accumulation — 30-turn session, retrieve early finding
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from memcp.core import chunker, context_store, memory
from memcp.core.fileutil import estimate_tokens

from .datasets import generate_document, generate_insights
from .metrics import BenchmarkReport, ComparisonResult, TokenLedger

# ── Scenario A: Session Startup ──────────────────────────────────────


@pytest.mark.parametrize("n_insights", [50, 200, 500], ids=["50ins", "200ins", "500ins"])
def test_session_startup_native(benchmark: Any, n_insights: int, token_ledger: TokenLedger) -> None:
    """Native: load all previous insights as raw text into context."""
    insights = generate_insights(n_insights, seed=42)

    def run() -> int:
        token_ledger.reset()
        # Native approach: dump everything into the context window
        full_text = "\n".join(ins["content"] for ins in insights)
        token_ledger.record_text("load_all_history", full_text)
        # Linear search for something relevant
        for ins in insights:
            if "authentication" in ins["content"].lower():
                token_ledger.record_text("search_result", ins["content"])
        return token_ledger.total

    result = benchmark(run)
    assert result > 0


@pytest.mark.parametrize("n_insights", [50, 200, 500], ids=["50ins", "200ins", "500ins"])
def test_session_startup_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    n_insights: int,
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: targeted recall of critical insights + specific queries."""
    insights = generate_insights(n_insights, seed=42)

    # Pre-populate memory
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
        # RLM approach: recall only critical decisions
        critical = memory.recall(importance="critical", limit=20, project="benchmark-project")
        for ins in critical:
            token_ledger.record_text("recall_critical", ins["content"])

        # Targeted search
        results = memory.recall(query="authentication", limit=5, project="benchmark-project")
        for ins in results:
            token_ledger.record_text("recall_targeted", ins["content"])

        return token_ledger.total

    result = benchmark(run)
    assert result > 0

    # Record comparison (use native's full-load cost for comparison)
    full_text = "\n".join(ins["content"] for ins in insights)
    native_tokens = estimate_tokens(full_text)
    benchmark_report.add(
        ComparisonResult(
            scenario="Session Startup",
            metric=f"Reload {n_insights} insights",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )


# ── Scenario B: Large Document Analysis ──────────────────────────────


@pytest.mark.parametrize("token_target", [5_000, 20_000, 50_000], ids=["5K", "20K", "50K"])
def test_large_doc_native(benchmark: Any, token_target: int, token_ledger: TokenLedger) -> None:
    """Native: load entire document, search via regex."""
    doc = generate_document(token_target, seed=42)

    def run() -> int:
        token_ledger.reset()
        # Native: load entire doc into context
        token_ledger.record_text("load_full_document", doc)
        # Find a section via regex
        matches = re.findall(r"(?:^|\n)(## .+)", doc)
        for m in matches[:3]:
            token_ledger.record_text("section_header", m)
        return token_ledger.total

    result = benchmark(run)
    assert result > 0


@pytest.mark.parametrize("token_target", [5_000, 20_000, 50_000], ids=["5K", "20K", "50K"])
def test_large_doc_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    token_target: int,
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: load as context variable, inspect metadata, peek specific chunks."""
    doc = generate_document(token_target, seed=42)

    def run() -> int:
        token_ledger.reset()

        # Store as context variable (tokens NOT loaded into prompt)
        context_store.load("design-doc", content=doc)

        # Inspect: metadata + 5-line preview
        meta = context_store.inspect("design-doc")
        preview_text = f"name={meta['name']} type={meta['type']} tokens={meta['token_estimate']}"
        if "preview" in meta:
            preview_text += f"\n{meta['preview']}"
        token_ledger.record_text("inspect_metadata", preview_text)

        # Chunk by headings for navigation
        chunks = chunker.by_headings(doc)
        chunk_index = " | ".join(f"chunk_{i}({c['tokens']}t)" for i, c in enumerate(chunks[:10]))
        token_ledger.record_text("chunk_index", chunk_index)

        # Peek at a specific section (first chunk with meaningful content)
        if chunks:
            token_ledger.record_text("peek_chunk", chunks[0]["content"][:800])

        # Filter for specific pattern
        result = context_store.filter_context("design-doc", pattern="(?i)auth")
        token_ledger.record_text("filter_result", result["content"][:500])

        return token_ledger.total

    result = benchmark(run)
    assert result > 0

    native_tokens = estimate_tokens(doc)
    benchmark_report.add(
        ComparisonResult(
            scenario="Large Document Analysis",
            metric=f"Analyse {token_target // 1000}K-token doc",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )


# ── Scenario C: Cross-Reference Knowledge ────────────────────────────


def test_cross_reference_native(
    benchmark: Any, session_history: dict[str, Any], token_ledger: TokenLedger
) -> None:
    """Native: load all history, keyword search for 'auth'."""
    insights = session_history["insights"]

    def run() -> int:
        token_ledger.reset()
        # Load everything
        full_text = "\n".join(ins["content"] for ins in insights)
        token_ledger.record_text("load_all", full_text)
        # Search for database/storage-related
        for ins in insights:
            content_lower = ins["content"].lower()
            if "database" in content_lower or "storage" in content_lower:
                token_ledger.record_text("match", ins["content"])
        return token_ledger.total

    result = benchmark(run)
    assert result > 0


def test_cross_reference_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    session_history: dict[str, Any],
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: targeted recall + graph traversal for causal chains."""
    insights = session_history["insights"]

    for ins in insights:
        memory.remember(
            content=ins["content"],
            category=ins["category"],
            importance=ins["importance"],
            tags=",".join(ins["tags"]),
            project="benchmark-project",
        )

    # Verify data was stored
    status = memory.memory_status(project="benchmark-project")
    assert status["total_insights"] > 0, "Setup failed: no insights stored"

    def run() -> int:
        token_ledger.reset()

        # Targeted recall — use terms from the dataset vocabulary
        results = memory.recall(query="storage", limit=5, project="benchmark-project", scope="all")
        if not results:
            results = memory.recall(limit=5, project="benchmark-project", scope="all")
        for ins in results:
            token_ledger.record_text("recall", ins["content"])

        # Follow up: second targeted recall (simulates graph traversal cost)
        if results:
            # Use a tag from the first result to find related insights
            first_tags = results[0].get("tags", [])
            if first_tags:
                related = memory.recall(
                    query=first_tags[0],
                    limit=5,
                    project="benchmark-project",
                    scope="all",
                )
                for ins in related:
                    token_ledger.record_text("related", ins["content"])

        return token_ledger.total

    result = benchmark(run)
    assert result > 0

    full_text = "\n".join(ins["content"] for ins in insights)
    native_tokens = estimate_tokens(full_text)
    benchmark_report.add(
        ComparisonResult(
            scenario="Cross-Reference Knowledge",
            metric="Find auth decisions + causes",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )


# ── Scenario D: Multi-turn Accumulation ──────────────────────────────


def test_multi_turn_native(benchmark: Any, token_ledger: TokenLedger) -> None:
    """Native: 30 turns of accumulating knowledge, then retrieve from turn 5."""
    insights = generate_insights(30, seed=99)

    def run() -> int:
        token_ledger.reset()
        # Each turn adds content to the context window
        accumulated = ""
        for ins in insights:
            accumulated += ins["content"] + "\n"

        # At turn 30, everything is in context
        token_ledger.record_text("context_at_turn_30", accumulated)

        # Search for turn-5 content
        target = insights[4]["content"]
        if target in accumulated:
            token_ledger.record_text("found_target", target)

        return token_ledger.total

    result = benchmark(run)
    assert result > 0


def test_multi_turn_rlm(
    benchmark: Any,
    isolated_data_dir: Any,
    token_ledger: TokenLedger,
    benchmark_report: BenchmarkReport,
) -> None:
    """RLM: save each turn's findings, retrieve specifically at turn 30.

    Token cost = context window tokens only.  The ``remember()`` calls
    write to SQLite, so only the tool-call overhead (request + response
    JSON) enters the window — we count a small fixed cost per call.
    The key metric is how many tokens are needed in the context window
    to retrieve turn-5 knowledge at turn 30.
    """
    insights = generate_insights(30, seed=99)

    def run() -> int:
        token_ledger.reset()

        # Each turn: save important finding to persistent storage.
        # Only the tool call + response enters the context window (~15 tokens).
        for ins in insights:
            memory.remember(
                content=ins["content"],
                category=ins["category"],
                importance=ins["importance"],
                tags=",".join(ins["tags"]),
                project="benchmark-project",
            )
            token_ledger.record("remember_tool_overhead", 15)

        # At turn 30: retrieve the turn-5 finding specifically
        target_content = insights[4]["content"]
        words = [w for w in target_content.split() if len(w) > 3 and w.isalpha()]
        query = " ".join(words[:3]) if words else "turn 5"

        results = memory.recall(query=query, limit=3, project="benchmark-project")
        for ins in results:
            token_ledger.record_text("recall_result", ins["content"])

        return token_ledger.total

    result = benchmark(run)
    assert result > 0

    # Native cost = all 30 insights in context
    all_text = "\n".join(ins["content"] for ins in insights)
    native_tokens = estimate_tokens(all_text)
    benchmark_report.add(
        ComparisonResult(
            scenario="Multi-turn Accumulation",
            metric="30 turns, retrieve turn-5 finding",
            native_value=native_tokens,
            rlm_value=result,
            unit="tokens",
        )
    )
