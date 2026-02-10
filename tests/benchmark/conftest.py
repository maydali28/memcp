"""Shared fixtures for benchmark tests.

Reuses the ``isolated_data_dir`` pattern from the main test suite and adds
benchmark-specific fixtures for data generation, token tracking, and report
collection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import memcp.config as config_module

from .datasets import (
    generate_document,
    generate_insights,
    generate_multi_session_history,
    generate_query_pairs,
    generate_session_history,
)
from .metrics import BenchmarkReport, ContextWindowSimulator, TokenLedger

# ── Singleton reset (mirrors tests/conftest.py) ─────────────────────


def _reset_singletons() -> None:
    config_module._config = None
    try:
        from memcp.core.embeddings import reset_provider

        reset_provider()
    except ImportError:
        pass
    try:
        from memcp.core.embed_cache import reset_embed_cache

        reset_embed_cache()
    except ImportError:
        pass


# ── Isolation ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give every benchmark its own data directory."""
    data_dir = tmp_path / "memcp-bench"
    monkeypatch.setenv("MEMCP_DATA_DIR", str(data_dir))
    monkeypatch.delenv("MEMCP_PROJECT", raising=False)
    _reset_singletons()
    yield data_dir
    _reset_singletons()


# ── Metric fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def token_ledger() -> TokenLedger:
    return TokenLedger()


@pytest.fixture()
def context_window() -> ContextWindowSimulator:
    """Default 128K context window."""
    return ContextWindowSimulator(capacity=128_000)


@pytest.fixture(params=[32_000, 64_000, 128_000, 200_000], ids=["32K", "64K", "128K", "200K"])
def context_window_sized(request: pytest.FixtureRequest) -> ContextWindowSimulator:
    """Parameterised context window for capacity tests."""
    return ContextWindowSimulator(capacity=request.param)


# ── Data fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def small_insights() -> list[dict[str, Any]]:
    """50 insights for quick benchmarks."""
    return generate_insights(50, seed=42)


@pytest.fixture()
def medium_insights() -> list[dict[str, Any]]:
    """200 insights."""
    return generate_insights(200, seed=42)


@pytest.fixture()
def large_insights() -> list[dict[str, Any]]:
    """500 insights."""
    return generate_insights(500, seed=42)


@pytest.fixture()
def session_history() -> dict[str, Any]:
    """Single session: 100 insights + 3 context documents + 20 queries."""
    return generate_session_history(100, 3, seed=42)


@pytest.fixture()
def multi_session() -> list[dict[str, Any]]:
    """5 sessions for cross-session benchmarks."""
    return generate_multi_session_history(5, seed=42)


@pytest.fixture(params=[5_000, 20_000, 50_000], ids=["5K", "20K", "50K"])
def sized_document(request: pytest.FixtureRequest) -> str:
    """Parameterised document by token target."""
    return generate_document(token_target=request.param, seed=42)


@pytest.fixture()
def query_pairs(small_insights: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    return generate_query_pairs(small_insights, n_queries=20, seed=42)


# ── Helpers for populating the RLM backend ───────────────────────────


@pytest.fixture()
def populated_memory(
    isolated_data_dir: Path, small_insights: list[dict[str, Any]]
) -> dict[str, Any]:
    """Pre-populate GraphMemory with 50 insights and return metadata."""
    from memcp.core.memory import remember

    stored_ids: list[str] = []
    for ins in small_insights:
        result = remember(
            content=ins["content"],
            category=ins["category"],
            importance=ins["importance"],
            tags=",".join(ins["tags"]),
            entities=",".join(ins["entities"]),
            project=ins["project"],
            session=ins["session"],
        )
        stored_ids.append(result["id"])

    return {"count": len(stored_ids), "ids": stored_ids, "insights": small_insights}


# ── Report collection ────────────────────────────────────────────────

# Session-scoped report that accumulates across all benchmark modules.
_report = BenchmarkReport()


@pytest.fixture()
def benchmark_report() -> BenchmarkReport:
    return _report


@pytest.fixture(scope="session")
def benchmark_output_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("benchmark_results")
    return d


def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,  # noqa: ARG001
    config: Any,  # noqa: ARG001
) -> None:
    """Print a condensed benchmark comparison table and generate report files."""
    if not _report.results:
        return

    try:
        from tabulate import tabulate
    except ImportError:
        terminalreporter.write_line("\n[benchmark] Install 'tabulate' for comparison tables")
        return

    terminalreporter.write_line("")
    terminalreporter.write_line("=" * 72)
    terminalreporter.write_line("  BENCHMARK COMPARISON: Claude Native vs Claude with RLM")
    terminalreporter.write_line("=" * 72)

    rows = []
    for r in _report.results:
        rows.append(
            [
                r.scenario,
                r.metric,
                f"{r.native_value:,.0f}",
                f"{r.rlm_value:,.0f}",
                f"{r.savings_pct}%",
                f"{r.ratio}x",
                r.unit,
            ]
        )

    headers = ["Scenario", "Metric", "Native", "RLM", "Savings", "Ratio", "Unit"]
    terminalreporter.write_line(tabulate(rows, headers=headers, tablefmt="simple"))
    terminalreporter.write_line("=" * 72)

    # Generate report files in the project root
    from .report import generate_reports

    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir = project_root / "benchmark_output"
    paths = generate_reports(_report, output_dir)
    terminalreporter.write_line(f"\n  Reports written to: {output_dir}")
    for name, path in paths.items():
        terminalreporter.write_line(f"    {name}: {path}")
