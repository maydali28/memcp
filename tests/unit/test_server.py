"""Integration tests for all 21 MemCP MCP tools via direct function calls."""

from __future__ import annotations

import json
from pathlib import Path

from memcp.server import (
    memcp_chunk_context,
    memcp_clear_context,
    memcp_filter_context,
    memcp_forget,
    memcp_get_context,
    memcp_graph_stats,
    memcp_inspect_context,
    memcp_list_contexts,
    memcp_load_context,
    memcp_peek_chunk,
    memcp_ping,
    memcp_projects,
    memcp_recall,
    memcp_related,
    memcp_remember,
    memcp_restore,
    memcp_retention_preview,
    memcp_retention_run,
    memcp_search,
    memcp_sessions,
    memcp_status,
)


class TestPing:
    def test_ping(self) -> None:
        result = json.loads(memcp_ping())
        assert result["status"] == "ok"
        assert result["server"] == "MemCP"
        assert result["version"] == "0.1.0"
        assert "memory" in result


class TestRememberRecallForget:
    def test_remember_and_recall(self, isolated_data_dir: Path) -> None:
        result = json.loads(
            memcp_remember(
                content="Integration test insight",
                category="fact",
                importance="high",
                tags="test,integration",
            )
        )
        assert result["status"] == "saved"
        insight_id = result["id"]

        recall_result = json.loads(memcp_recall(query="integration", scope="all"))
        assert recall_result["status"] == "ok"
        assert recall_result["count"] >= 1
        found = any(i["id"] == insight_id for i in recall_result["insights"])
        assert found

    def test_forget(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_remember(content="To be forgotten", category="general"))
        insight_id = result["id"]

        forget_result = json.loads(memcp_forget(insight_id))
        assert forget_result["status"] == "removed"

        recall_result = json.loads(memcp_recall(query="forgotten", scope="all"))
        found = any(i["id"] == insight_id for i in recall_result.get("insights", []))
        assert not found

    def test_remember_invalid_category(self) -> None:
        result = json.loads(memcp_remember(content="test", category="invalid"))
        assert result["status"] == "error"

    def test_remember_empty_content(self) -> None:
        result = json.loads(memcp_remember(content=""))
        assert result["status"] == "error"

    def test_forget_nonexistent(self) -> None:
        result = json.loads(memcp_forget("nonexistent-id"))
        assert result["status"] == "not_found"


class TestStatus:
    def test_status_empty(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_status())
        assert result["status"] == "ok"
        assert result["total_insights"] == 0

    def test_status_after_remember(self, isolated_data_dir: Path) -> None:
        memcp_remember(content="Status test", category="fact", importance="high")
        result = json.loads(memcp_status())
        assert result["total_insights"] == 1


class TestContextTools:
    def test_load_and_inspect(self, isolated_data_dir: Path) -> None:
        load_result = json.loads(
            memcp_load_context(name="test-ctx", content="Line 1\nLine 2\nLine 3\n")
        )
        assert load_result["status"] == "stored"

        inspect_result = json.loads(memcp_inspect_context(name="test-ctx"))
        assert inspect_result["status"] == "ok"
        assert inspect_result["name"] == "test-ctx"
        assert inspect_result["line_count"] >= 3

    def test_get_context(self, isolated_data_dir: Path) -> None:
        memcp_load_context(name="get-test", content="A\nB\nC\nD\nE\n")
        result = json.loads(memcp_get_context(name="get-test", start=2, end=3))
        assert result["status"] == "ok"
        assert "B" in result["content"]

    def test_chunk_and_peek(self, isolated_data_dir: Path) -> None:
        content = "\n".join(f"Line {i}" for i in range(100))
        memcp_load_context(name="chunk-test", content=content)

        chunk_result = json.loads(
            memcp_chunk_context(name="chunk-test", strategy="lines", chunk_size=20)
        )
        assert chunk_result["status"] == "chunked"
        assert chunk_result["count"] >= 2

        peek_result = json.loads(memcp_peek_chunk(context_name="chunk-test", chunk_index=0))
        assert peek_result["status"] == "ok"
        assert "Line 0" in peek_result["content"]

    def test_filter_context(self, isolated_data_dir: Path) -> None:
        memcp_load_context(name="filter-test", content="apple\nbanana\napricot\ncherry\n")
        result = json.loads(memcp_filter_context(name="filter-test", pattern="^a"))
        assert result["status"] == "ok"
        assert result["lines_matched"] == 2

    def test_list_and_clear(self, isolated_data_dir: Path) -> None:
        memcp_load_context(name="list-test", content="test content")
        list_result = json.loads(memcp_list_contexts())
        assert list_result["status"] == "ok"
        assert len(list_result["contexts"]) >= 1

        clear_result = json.loads(memcp_clear_context(name="list-test"))
        assert clear_result["status"] == "removed"

        list_result2 = json.loads(memcp_list_contexts())
        names = [c["name"] for c in list_result2.get("contexts", [])]
        assert "list-test" not in names

    def test_inspect_missing(self) -> None:
        result = json.loads(memcp_inspect_context(name="nonexistent"))
        assert result["status"] == "error"


class TestSearch:
    def test_search_memory(self, isolated_data_dir: Path) -> None:
        memcp_remember(content="Search integration test fact", category="fact", tags="search")
        result = json.loads(memcp_search(query="integration", source="memory", scope="all"))
        assert result["status"] == "ok"
        assert result["count"] >= 1

    def test_search_contexts(self, isolated_data_dir: Path) -> None:
        memcp_load_context(name="search-ctx", content="Searchable context content here")
        memcp_chunk_context(name="search-ctx", strategy="lines")
        result = json.loads(memcp_search(query="searchable", source="contexts", scope="all"))
        assert result["status"] == "ok"

    def test_search_empty(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_search(query="nonexistent_query_xyz", source="all", scope="all"))
        assert result["status"] == "ok"
        assert result["count"] == 0


class TestGraphTools:
    def test_graph_stats(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_graph_stats())
        assert result["status"] == "ok"
        assert "node_count" in result

    def test_related_not_found(self) -> None:
        result = json.loads(memcp_related(insight_id="nonexistent"))
        assert result["status"] == "error"

    def test_related_after_remember(self, isolated_data_dir: Path) -> None:
        # Initialize graph.db so remember() uses the graph backend
        memcp_graph_stats()

        r1 = json.loads(
            memcp_remember(
                content="SQLite is used for the graph backend",
                category="decision",
                tags="architecture",
            )
        )
        memcp_remember(
            content="SQLite was chosen because it is zero-config",
            category="fact",
            tags="architecture",
        )
        result = json.loads(memcp_related(insight_id=r1["id"]))
        assert result["status"] == "ok"
        assert "center" in result


class TestRetentionTools:
    def test_retention_preview_empty(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_retention_preview())
        assert result["status"] == "ok"
        assert result["archive_candidates"]["total"] == 0
        assert result["purge_candidates"]["total"] == 0

    def test_retention_run_empty(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_retention_run())
        assert result["status"] == "ok"
        assert result["total_archived"] == 0

    def test_restore_not_found(self) -> None:
        result = json.loads(memcp_restore(name="nonexistent"))
        assert result["status"] == "not_found"


class TestProjectSessionTools:
    def test_projects_empty(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_projects())
        assert result["status"] == "ok"
        assert result["count"] == 0
        assert result["projects"] == []

    def test_sessions_empty(self, isolated_data_dir: Path) -> None:
        result = json.loads(memcp_sessions())
        assert result["status"] == "ok"
        assert result["count"] == 0
        assert result["sessions"] == []

    def test_projects_after_remember(self, isolated_data_dir: Path) -> None:
        memcp_remember(content="Project listing test", category="fact", project="test-proj")
        result = json.loads(memcp_projects())
        assert result["status"] == "ok"
        assert result["count"] >= 1
        names = [p["name"] for p in result["projects"]]
        assert "test-proj" in names
