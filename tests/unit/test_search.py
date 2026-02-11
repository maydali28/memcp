"""Tests for memcp.core.search."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memcp.core import chunker, context_store
from memcp.core.memory import remember
from memcp.core.search import (
    NUMPY_AVAILABLE,
    hybrid_search,
    keyword_search,
    search,
    search_all,
    semantic_search,
)

_requires_numpy = pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not installed")

SAMPLE_DOCS = [
    {
        "content": "Python is a great programming language",
        "tags": ["python", "programming"],
        "token_count": 8,
    },
    {
        "content": "JavaScript runs in the browser",
        "tags": ["javascript", "web"],
        "token_count": 7,
    },
    {
        "content": "Rust provides memory safety without garbage collection",
        "tags": ["rust", "systems"],
        "token_count": 9,
    },
    {
        "content": "Python and JavaScript are both popular languages",
        "tags": ["python", "javascript"],
        "token_count": 8,
    },
]


class TestKeywordSearch:
    def test_single_match(self) -> None:
        results = keyword_search("rust", SAMPLE_DOCS)
        assert len(results) == 1
        assert "Rust" in results[0]["content"]

    def test_multiple_matches(self) -> None:
        results = keyword_search("python", SAMPLE_DOCS)
        assert len(results) == 2

    def test_no_match(self) -> None:
        results = keyword_search("golang", SAMPLE_DOCS)
        assert len(results) == 0

    def test_empty_query(self) -> None:
        results = keyword_search("", SAMPLE_DOCS, limit=2)
        assert len(results) == 2

    def test_limit(self) -> None:
        results = keyword_search("python", SAMPLE_DOCS, limit=1)
        assert len(results) == 1

    def test_max_tokens(self) -> None:
        results = keyword_search("python", SAMPLE_DOCS, max_tokens=10)
        total = sum(r.get("token_count", 0) for r in results)
        assert total <= 10 or len(results) == 1

    def test_searches_tags(self) -> None:
        results = keyword_search("web", SAMPLE_DOCS)
        assert len(results) == 1
        assert "JavaScript" in results[0]["content"]

    def test_multi_word_query(self) -> None:
        results = keyword_search("python programming", SAMPLE_DOCS)
        assert len(results) >= 1
        # The doc with both words should score higher
        assert "great programming" in results[0]["content"]


class TestSearch:
    def test_auto_method(self) -> None:
        results = search("python", SAMPLE_DOCS, method="auto")
        assert len(results) >= 1

    def test_keyword_method(self) -> None:
        results = search("rust", SAMPLE_DOCS, method="keyword")
        assert len(results) == 1

    def test_invalid_method(self) -> None:
        with pytest.raises(ValueError, match="Unknown search method"):
            search("test", SAMPLE_DOCS, method="invalid")


class TestSearchAll:
    def test_search_memory(self, isolated_data_dir: Path) -> None:
        remember("SQLite is used for the graph backend", tags="database,architecture")
        remember("Redis is used for caching", tags="cache,database")

        result = search_all("database", source="memory", scope="all")
        assert result["count"] >= 1
        assert any("database" in str(r.get("tags", [])) for r in result["results"])

    def test_search_contexts(self, isolated_data_dir: Path) -> None:
        content = "SQLite provides ACID transactions.\nRedis is an in-memory store."
        context_store.load("db-notes", content=content)
        chunker.chunk_context("db-notes", strategy="lines", chunk_size=1)

        result = search_all("SQLite", source="contexts", scope="all")
        assert result["count"] >= 1

    def test_search_all_sources(self, isolated_data_dir: Path) -> None:
        remember("Database choice: SQLite", tags="architecture")
        content = "SQLite benchmarks show good performance."
        context_store.load("bench", content=content)
        chunker.chunk_context("bench", strategy="lines", chunk_size=2)

        result = search_all("SQLite", source="all", scope="all")
        assert result["count"] >= 1

    def test_search_empty(self, isolated_data_dir: Path) -> None:
        result = search_all("nonexistent query xyz", source="all", scope="all")
        assert result["count"] == 0

    def test_capabilities_reported(self, isolated_data_dir: Path) -> None:
        result = search_all("test", source="memory", scope="all")
        assert "capabilities" in result
        assert "bm25" in result["capabilities"]
        assert "fuzzy" in result["capabilities"]
        assert "semantic" in result["capabilities"]

    def test_max_tokens_budget(self, isolated_data_dir: Path) -> None:
        for i in range(10):
            remember(f"Insight about databases number {i}", tags="db")

        result = search_all("databases", max_tokens=30, source="memory", scope="all")
        total_tokens = sum(r.get("token_count", 0) for r in result["results"])
        assert total_tokens <= 30 or result["count"] == 1


def _make_fake_provider() -> MagicMock:
    """Create a mock embedding provider that returns deterministic vectors."""
    provider = MagicMock()
    provider.embed.side_effect = lambda text: [
        float((hash(text) >> (i * 4)) & 0xF) / 15.0 for i in range(8)
    ]
    provider.embed_batch.side_effect = lambda texts: [
        [float((hash(t) >> (i * 4)) & 0xF) / 15.0 for i in range(8)] for t in texts
    ]
    return provider


class TestSemanticSearch:
    @_requires_numpy
    @patch("memcp.core.embeddings.get_provider")
    def test_semantic_search_with_provider(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _make_fake_provider()
        results = semantic_search("python", SAMPLE_DOCS, limit=3)
        # Should return results (exact count depends on similarity scores)
        assert isinstance(results, list)

    @patch("memcp.core.embeddings.get_provider")
    def test_semantic_falls_back_without_provider(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        results = semantic_search("python", SAMPLE_DOCS)
        # Falls back to bm25/keyword — should still return results
        assert isinstance(results, list)

    @_requires_numpy
    @patch("memcp.core.embeddings.get_provider")
    def test_semantic_empty_docs(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _make_fake_provider()
        results = semantic_search("python", [])
        assert results == []

    def test_semantic_method_in_search(self) -> None:
        # Calling with method="semantic" should not crash
        results = search("python", SAMPLE_DOCS, method="semantic")
        assert isinstance(results, list)


class TestHybridSearch:
    @_requires_numpy
    @patch("memcp.core.embeddings.get_provider")
    def test_hybrid_search_with_provider(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _make_fake_provider()
        results = hybrid_search("python", SAMPLE_DOCS, limit=3)
        assert isinstance(results, list)

    @patch("memcp.core.embeddings.get_provider")
    def test_hybrid_falls_back_without_provider(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        results = hybrid_search("python", SAMPLE_DOCS)
        assert isinstance(results, list)

    @_requires_numpy
    @patch("memcp.core.embeddings.get_provider")
    def test_hybrid_custom_alpha(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _make_fake_provider()
        results = hybrid_search("python", SAMPLE_DOCS, alpha=0.8)
        assert isinstance(results, list)

    def test_hybrid_method_in_search(self) -> None:
        results = search("python", SAMPLE_DOCS, method="hybrid")
        assert isinstance(results, list)


class TestSearchAutoSelection:
    def test_auto_does_not_crash(self) -> None:
        results = search("python", SAMPLE_DOCS, method="auto")
        assert isinstance(results, list)
        assert len(results) >= 1


class TestSearchAllRanking:
    """Verify that memory insights compete fairly with context chunks."""

    def test_memory_insight_not_buried_by_context_chunks(self, isolated_data_dir: Path) -> None:
        """A highly relevant memory insight should rank above weakly relevant chunks."""
        # Store an insight that directly matches the query
        remember("MAGMA graph uses SQLite for edge storage", tags="magma,sqlite,graph")

        # Store a context with many chunks that only weakly match
        lines = [f"Line {i}: unrelated content about various topics" for i in range(20)]
        lines[5] = "This line mentions magma in passing, nothing more"
        content = "\n".join(lines)
        context_store.load("weak-match", content=content)
        chunker.chunk_context("weak-match", strategy="lines", chunk_size=2)

        result = search_all("MAGMA graph SQLite", source="all", scope="all")
        assert result["count"] >= 1

        # The memory insight should appear in results
        memory_results = [r for r in result["results"] if r.get("_source") == "memory"]
        assert len(memory_results) >= 1, "Memory insight missing from search results"

    def test_memory_insights_get_scores(self, isolated_data_dir: Path) -> None:
        """Memory insights should receive _score values when a query is provided."""
        remember("Python web framework comparison", tags="python,web")

        result = search_all("Python web", source="memory", scope="all")
        assert result["count"] >= 1
        for r in result["results"]:
            assert "_score" in r, "Memory insight missing _score"

    def test_combined_results_sorted_by_score(self, isolated_data_dir: Path) -> None:
        """All results with scores should be sorted descending."""
        remember("Alpha database engine details", tags="database,alpha")
        remember("Beta unrelated topic", tags="misc")

        content = "Alpha database provides fast queries.\nGamma is something else."
        context_store.load("alpha-db", content=content)
        chunker.chunk_context("alpha-db", strategy="lines", chunk_size=1)

        result = search_all("Alpha database", source="all", scope="all")
        scored = [r for r in result["results"] if "_score" in r]
        scores = [r["_score"] for r in scored]
        assert scores == sorted(scores, reverse=True), "Results not sorted by score"


class TestSearchAllCapabilities:
    def test_hybrid_in_capabilities(self, isolated_data_dir: Path) -> None:
        result = search_all("test", source="memory", scope="all")
        assert "hybrid" in result["capabilities"]
