"""Tests for memcp.core.memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from memcp.core.memory import (
    IMPORTANCE_WEIGHTS,
    VALID_CATEGORIES,
    VALID_IMPORTANCES,
    _compute_effective_importance,
    forget,
    memory_status,
    recall,
    remember,
)


class TestRemember:
    def test_basic_save(self, isolated_data_dir: Path) -> None:
        result = remember("Test insight", category="fact", importance="medium")
        assert result["id"]
        assert result["content"] == "Test insight"
        assert result["category"] == "fact"
        assert result["importance"] == "medium"
        assert result["token_count"] >= 1
        assert result["access_count"] == 0
        assert result["last_accessed_at"] is None
        assert result["created_at"]

    def test_with_tags(self, isolated_data_dir: Path) -> None:
        result = remember("API uses JWT", tags="api,auth,jwt")
        assert result["tags"] == ["api", "auth", "jwt"]

    def test_with_entities(self, isolated_data_dir: Path) -> None:
        result = remember("Found bug in auth.py", entities="auth.py,UserService")
        assert result["entities"] == ["auth.py", "UserService"]

    def test_with_project_and_session(self, isolated_data_dir: Path) -> None:
        result = remember("Project insight", project="myapp", session="sess-1")
        assert result["project"] == "myapp"
        assert result["session"] == "sess-1"

    def test_default_project(self, isolated_data_dir: Path) -> None:
        result = remember("Default project insight")
        # Project is auto-detected (cwd basename or "default") when not specified
        assert isinstance(result["project"], str)
        assert len(result["project"]) > 0

    def test_invalid_category(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            remember("Test", category="invalid")

    def test_invalid_importance(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid importance"):
            remember("Test", importance="invalid")

    def test_empty_content(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Content cannot be empty"):
            remember("")

    def test_whitespace_only_content(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Content cannot be empty"):
            remember("   ")

    def test_content_stripped(self, isolated_data_dir: Path) -> None:
        result = remember("  spaces around  ")
        assert result["content"] == "spaces around"

    def test_duplicate_detection(self, isolated_data_dir: Path) -> None:
        remember("Unique insight")
        result = remember("Unique insight")
        assert result.get("_duplicate") is True

    def test_duplicate_normalized(self, isolated_data_dir: Path) -> None:
        remember("Hello World")
        result = remember("  hello world  ")
        assert result.get("_duplicate") is True

    def test_all_categories(self, isolated_data_dir: Path) -> None:
        for cat in VALID_CATEGORIES:
            result = remember(f"Insight for {cat}", category=cat)
            assert result["category"] == cat

    def test_all_importances(self, isolated_data_dir: Path) -> None:
        for imp in VALID_IMPORTANCES:
            result = remember(f"Insight {imp}", importance=imp)
            assert result["importance"] == imp

    def test_effective_importance_set(self, isolated_data_dir: Path) -> None:
        result = remember("High importance", importance="high")
        assert result["effective_importance"] == IMPORTANCE_WEIGHTS["high"]

    def test_token_count(self, isolated_data_dir: Path) -> None:
        text = "a" * 400  # ~100 tokens at 4 chars/token
        result = remember(text)
        assert result["token_count"] == 100

    def test_unique_ids(self, isolated_data_dir: Path) -> None:
        r1 = remember("Insight one")
        r2 = remember("Insight two")
        assert r1["id"] != r2["id"]

    def test_persistence(self, isolated_data_dir: Path) -> None:
        remember("Persisted insight", category="decision")
        results = recall(query="persisted", scope="all")
        assert len(results) == 1
        assert results[0]["content"] == "Persisted insight"


class TestRecall:
    def test_empty_memory(self, isolated_data_dir: Path) -> None:
        results = recall()
        assert results == []

    def test_recall_by_query(
        self, isolated_data_dir: Path, sample_insights: list[dict[str, str]]
    ) -> None:
        for ins in sample_insights:
            remember(**ins)

        results = recall(query="client", scope="all")
        assert len(results) >= 1
        assert any("client" in r["content"].lower() for r in results)

    def test_recall_by_category(
        self, isolated_data_dir: Path, sample_insights: list[dict[str, str]]
    ) -> None:
        for ins in sample_insights:
            remember(**ins)

        results = recall(category="decision", scope="all")
        assert len(results) == 1
        assert results[0]["category"] == "decision"

    def test_recall_by_importance(
        self, isolated_data_dir: Path, sample_insights: list[dict[str, str]]
    ) -> None:
        for ins in sample_insights:
            remember(**ins)

        results = recall(importance="critical", scope="all")
        assert len(results) == 1
        assert results[0]["importance"] == "critical"

    def test_recall_combined_filters(
        self, isolated_data_dir: Path, sample_insights: list[dict[str, str]]
    ) -> None:
        for ins in sample_insights:
            remember(**ins)

        results = recall(category="preference", importance="high", scope="all")
        assert len(results) == 1
        assert results[0]["category"] == "preference"
        assert results[0]["importance"] == "high"

    def test_recall_limit(self, isolated_data_dir: Path) -> None:
        for i in range(20):
            remember(f"Insight number {i}")

        results = recall(limit=5, scope="all")
        assert len(results) == 5

    def test_recall_max_tokens(self, isolated_data_dir: Path) -> None:
        # Each insight is ~25 chars = ~6 tokens
        for i in range(10):
            remember(f"Short insight number {i:02d}")

        results = recall(max_tokens=20, scope="all")
        total_tokens = sum(r.get("token_count", 0) for r in results)
        # Should stop before exceeding budget (first item always included)
        assert total_tokens <= 20 or len(results) == 1

    def test_recall_increments_access_count(self, isolated_data_dir: Path) -> None:
        remember("Access test insight")

        # First recall
        results = recall(query="access test", scope="all")
        assert len(results) == 1

        # Second recall — access_count should have incremented
        results = recall(query="access test", scope="all")
        assert results[0]["access_count"] >= 1

    def test_recall_updates_last_accessed(self, isolated_data_dir: Path) -> None:
        remember("Timestamp test")

        results = recall(query="timestamp test", scope="all")
        assert results[0].get("last_accessed_at") is not None

    def test_recall_by_tags(
        self, isolated_data_dir: Path, sample_insights: list[dict[str, str]]
    ) -> None:
        for ins in sample_insights:
            remember(**ins)

        results = recall(query="packaging", scope="all")
        assert len(results) >= 1

    def test_recall_invalid_category(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            recall(category="nonexistent")

    def test_recall_invalid_importance(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid importance"):
            recall(importance="nonexistent")

    def test_recall_scope_project(self, isolated_data_dir: Path) -> None:
        remember("Project A insight", project="project-a")
        remember("Project B insight", project="project-b")

        results = recall(project="project-a", scope="project")
        assert len(results) == 1
        assert results[0]["project"] == "project-a"

    def test_recall_scope_session(self, isolated_data_dir: Path) -> None:
        remember("Session 1 insight", session="s1")
        remember("Session 2 insight", session="s2")

        results = recall(session="s1", scope="session")
        assert len(results) == 1
        assert results[0]["session"] == "s1"

    def test_recall_scope_all(self, isolated_data_dir: Path) -> None:
        remember("Project A insight", project="project-a")
        remember("Project B insight", project="project-b")

        results = recall(scope="all")
        assert len(results) == 2

    def test_recall_recency_order(self, isolated_data_dir: Path) -> None:
        remember("First insight")
        remember("Second insight")
        remember("Third insight")

        results = recall(scope="all")
        # No query — should be sorted by recency (newest first)
        assert results[0]["content"] == "Third insight"
        assert results[-1]["content"] == "First insight"


class TestForget:
    def test_forget_existing(self, isolated_data_dir: Path) -> None:
        result = remember("To be forgotten")
        assert forget(result["id"]) is True

        # Verify it's gone
        results = recall(query="forgotten", scope="all")
        assert len(results) == 0

    def test_forget_nonexistent(self, isolated_data_dir: Path) -> None:
        assert forget("nonexistent-id") is False

    def test_forget_only_target(self, isolated_data_dir: Path) -> None:
        r1 = remember("Keep this")
        r2 = remember("Remove this")

        forget(r2["id"])

        results = recall(scope="all")
        assert len(results) == 1
        assert results[0]["id"] == r1["id"]


class TestMemoryStatus:
    def test_empty_status(self, isolated_data_dir: Path) -> None:
        status = memory_status()
        assert status["total_insights"] == 0
        assert status["total_tokens"] == 0
        assert status["capacity_pct"] == 0

    def test_status_with_insights(
        self, isolated_data_dir: Path, sample_insights: list[dict[str, str]]
    ) -> None:
        for ins in sample_insights:
            remember(**ins)

        status = memory_status()
        assert status["total_insights"] == 5
        assert status["total_tokens"] > 0
        assert status["by_category"]["preference"] == 1
        assert status["by_category"]["decision"] == 1
        assert status["by_importance"]["critical"] == 1
        assert status["by_importance"]["high"] == 2
        assert status["oldest"] is not None
        assert status["newest"] is not None

    def test_status_max_insights(self, isolated_data_dir: Path) -> None:
        status = memory_status()
        assert status["max_insights"] == 10000

    def test_status_filter_project(self, isolated_data_dir: Path) -> None:
        remember("Project A", project="a")
        remember("Project B", project="b")

        status = memory_status(project="a")
        assert status["total_insights"] == 1

    def test_status_filter_session(self, isolated_data_dir: Path) -> None:
        remember("Session 1", session="s1")
        remember("Session 2", session="s2")

        status = memory_status(session="s1")
        assert status["total_insights"] == 1

    def test_avg_effective_importance(self, isolated_data_dir: Path) -> None:
        remember("High", importance="high")
        remember("Low", importance="low")

        status = memory_status()
        assert 0 < status["avg_effective_importance"] < 1


class TestEffectiveImportance:
    def test_base_weights(self) -> None:
        for imp, weight in IMPORTANCE_WEIGHTS.items():
            insight = {"importance": imp, "access_count": 0}
            effective = _compute_effective_importance(insight)
            assert effective == weight

    def test_access_boost(self) -> None:
        insight_no_access = {
            "importance": "medium",
            "access_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        insight_accessed = {
            "importance": "medium",
            "access_count": 10,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed_at": datetime.now(timezone.utc).isoformat(),
        }

        eff_no = _compute_effective_importance(insight_no_access)
        eff_yes = _compute_effective_importance(insight_accessed)
        assert eff_yes > eff_no

    def test_time_decay(self) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=60)

        insight_recent = {
            "importance": "medium",
            "access_count": 0,
            "created_at": now.isoformat(),
            "last_accessed_at": now.isoformat(),
        }
        insight_old = {
            "importance": "medium",
            "access_count": 0,
            "created_at": old.isoformat(),
            "last_accessed_at": old.isoformat(),
        }

        eff_recent = _compute_effective_importance(insight_recent)
        eff_old = _compute_effective_importance(insight_old)
        assert eff_recent > eff_old

    def test_critical_floor(self) -> None:
        old = datetime.now(timezone.utc) - timedelta(days=365)
        insight = {
            "importance": "critical",
            "access_count": 0,
            "created_at": old.isoformat(),
            "last_accessed_at": old.isoformat(),
        }
        effective = _compute_effective_importance(insight)
        assert effective >= 0.5


class TestAutoPrune:
    def test_prune_at_capacity(
        self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import memcp.config as cfg

        cfg._config = None
        monkeypatch.setenv("MEMCP_MAX_INSIGHTS", "5")

        # Store 5 insights (at capacity)
        for i in range(5):
            remember(f"Insight {i}", importance="low")

        # 6th should trigger prune
        result = remember("Insight overflow", importance="medium")
        assert result.get("_pruned", 0) >= 1

        status = memory_status()
        assert status["total_insights"] <= 5

    def test_never_prune_critical(
        self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import memcp.config as cfg

        cfg._config = None
        monkeypatch.setenv("MEMCP_MAX_INSIGHTS", "3")

        remember("Critical 1", importance="critical")
        remember("Critical 2", importance="critical")
        remember("Low priority", importance="low")

        # This should prune the low-priority one, not the critical ones
        remember("New insight", importance="medium")

        results = recall(importance="critical", scope="all")
        assert len(results) == 2
