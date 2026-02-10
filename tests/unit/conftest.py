"""Shared test fixtures for MemCP tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import memcp.config as config_module


def _reset_singletons() -> None:
    """Reset all module-level singletons for test isolation."""
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


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give every test its own data directory and reset all singletons."""
    data_dir = tmp_path / "memcp-test"
    monkeypatch.setenv("MEMCP_DATA_DIR", str(data_dir))
    monkeypatch.delenv("MEMCP_PROJECT", raising=False)

    _reset_singletons()

    yield data_dir

    _reset_singletons()


@pytest.fixture()
def sample_insights() -> list[dict[str, str]]:
    """A few sample insights for testing recall/search."""
    return [
        {
            "content": "The client prefers 500ml bottles over 1L",
            "category": "preference",
            "importance": "high",
            "tags": "client,packaging",
        },
        {
            "content": "API rate limit is 100 requests per minute",
            "category": "fact",
            "importance": "medium",
            "tags": "api,limits",
        },
        {
            "content": "Decided to use SQLite for the graph backend",
            "category": "decision",
            "importance": "critical",
            "tags": "architecture,database",
        },
        {
            "content": "Found a race condition in the file writer",
            "category": "finding",
            "importance": "high",
            "tags": "bug,concurrency",
        },
        {
            "content": "TODO: Add pagination to the search results",
            "category": "todo",
            "importance": "low",
            "tags": "search,ux",
        },
    ]
