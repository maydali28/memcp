"""Tests for project detection and session management (Phase 7)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from memcp.core.project import (
    _get_state,
    _load_sessions,
    _save_sessions,
    _set_state,
    detect_project,
    generate_session_id,
    get_current_project,
    get_current_session,
    list_projects,
    list_sessions,
    register_session,
    set_current_session,
)


class TestDetectProject:
    def test_env_var_takes_priority(
        self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MEMCP_PROJECT", "from-env")
        assert detect_project() == "from-env"

    def test_env_var_stripped(
        self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MEMCP_PROJECT", "  spaced  ")
        assert detect_project() == "spaced"

    def test_git_repo_detected(
        self, isolated_data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MEMCP_PROJECT", raising=False)
        # Create a fake git repo
        repo_dir = tmp_path / "my-project"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        sub_dir = repo_dir / "src" / "deep"
        sub_dir.mkdir(parents=True)
        assert detect_project(cwd=str(sub_dir)) == "my-project"

    def test_cwd_basename_fallback(
        self, isolated_data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MEMCP_PROJECT", raising=False)
        plain_dir = tmp_path / "plain-folder"
        plain_dir.mkdir()
        assert detect_project(cwd=str(plain_dir)) == "plain-folder"

    def test_default_fallback(
        self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MEMCP_PROJECT", raising=False)
        # Use root as cwd — basename is empty
        assert detect_project(cwd="/") == "default"


class TestGenerateSessionId:
    def test_format(self, isolated_data_dir: Path) -> None:
        sid = generate_session_id("myapp")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert sid == f"myapp_{today}_001"

    def test_auto_increment(self, isolated_data_dir: Path) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Register a session to occupy seq 001
        register_session(f"myapp_{today}_001", "myapp")
        sid = generate_session_id("myapp")
        assert sid == f"myapp_{today}_002"

    def test_different_projects_independent_seq(self, isolated_data_dir: Path) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        register_session(f"proj_a_{today}_001", "proj_a")
        sid_b = generate_session_id("proj_b")
        assert sid_b == f"proj_b_{today}_001"


class TestRegisterSession:
    def test_creates_entry(self, isolated_data_dir: Path) -> None:
        result = register_session("test_001", "testproj")
        assert result["session_id"] == "test_001"
        assert result["project"] == "testproj"
        assert result["insight_count"] == 0
        assert result["context_count"] == 0
        assert "started_at" in result

    def test_sets_state(self, isolated_data_dir: Path) -> None:
        register_session("test_002", "testproj")
        state = _get_state()
        assert state["current_project"] == "testproj"
        assert state["current_session"] == "test_002"

    def test_persists_in_sessions_json(self, isolated_data_dir: Path) -> None:
        register_session("test_003", "testproj")
        sessions = _load_sessions()
        assert "test_003" in sessions["sessions"]
        assert sessions["sessions"]["test_003"]["project"] == "testproj"
        assert sessions["current_session"] == "test_003"

    def test_multiple_sessions(self, isolated_data_dir: Path) -> None:
        register_session("s1", "proj_a")
        register_session("s2", "proj_b")
        sessions = _load_sessions()
        assert "s1" in sessions["sessions"]
        assert "s2" in sessions["sessions"]
        assert sessions["current_session"] == "s2"


class TestListSessions:
    def test_empty(self, isolated_data_dir: Path) -> None:
        result = list_sessions()
        assert result == []

    def test_all_sessions(self, isolated_data_dir: Path) -> None:
        register_session("s1", "proj_a")
        register_session("s2", "proj_b")
        result = list_sessions()
        assert len(result) == 2

    def test_filter_by_project(self, isolated_data_dir: Path) -> None:
        register_session("s1", "proj_a")
        register_session("s2", "proj_b")
        register_session("s3", "proj_a")
        result = list_sessions(project="proj_a")
        assert len(result) == 2
        assert all(s["project"] == "proj_a" for s in result)

    def test_limit(self, isolated_data_dir: Path) -> None:
        for i in range(5):
            register_session(f"s{i}", "proj")
        result = list_sessions(limit=3)
        assert len(result) == 3

    def test_sorted_most_recent_first(self, isolated_data_dir: Path) -> None:
        register_session("s1", "proj")
        register_session("s2", "proj")
        result = list_sessions()
        # s2 was registered after s1, so it should be first
        assert result[0]["session_id"] == "s2"


class TestListSessionsDynamicCounts:
    """Verify that list_sessions computes insight_count and context_count dynamically."""

    def test_insight_count_from_graph(self, isolated_data_dir: Path) -> None:
        register_session("sess_dyn", "dynproj")
        from memcp.core.memory import remember

        remember(content="Dynamic count insight 1", category="fact")
        remember(content="Dynamic count insight 2", category="fact")

        result = list_sessions()
        sess = next(s for s in result if s["session_id"] == "sess_dyn")
        assert sess["insight_count"] == 2

    def test_context_count_from_store(self, isolated_data_dir: Path) -> None:
        register_session("sess_ctx", "ctxproj")
        from memcp.core.context_store import load

        load(name="ctx-dyn-1", content="Some dynamic context")
        load(name="ctx-dyn-2", content="Another dynamic context")

        result = list_sessions()
        sess = next(s for s in result if s["session_id"] == "sess_ctx")
        assert sess["context_count"] == 2

    def test_mixed_counts(self, isolated_data_dir: Path) -> None:
        register_session("sess_mix", "mixproj")
        from memcp.core.context_store import load
        from memcp.core.memory import remember

        remember(content="Mixed insight", category="decision")
        load(name="ctx-mix", content="Mixed context content")

        result = list_sessions()
        sess = next(s for s in result if s["session_id"] == "sess_mix")
        assert sess["insight_count"] == 1
        assert sess["context_count"] == 1

    def test_zero_for_empty_session(self, isolated_data_dir: Path) -> None:
        register_session("sess_empty", "emptyproj")
        result = list_sessions()
        sess = next(s for s in result if s["session_id"] == "sess_empty")
        assert sess["insight_count"] == 0
        assert sess["context_count"] == 0

    def test_counts_isolated_between_sessions(self, isolated_data_dir: Path) -> None:
        register_session("sess_a", "proj")
        from memcp.core.memory import remember

        remember(content="Insight for session A", category="fact")

        register_session("sess_b", "proj")
        remember(content="Insight for session B", category="fact")

        result = list_sessions()
        sess_a = next(s for s in result if s["session_id"] == "sess_a")
        sess_b = next(s for s in result if s["session_id"] == "sess_b")
        assert sess_a["insight_count"] == 1
        assert sess_b["insight_count"] == 1


class TestGetSetCurrentSession:
    def test_empty_when_unset(self, isolated_data_dir: Path) -> None:
        assert get_current_session() == ""

    def test_roundtrip(self, isolated_data_dir: Path) -> None:
        set_current_session("my-session-id")
        assert get_current_session() == "my-session-id"

    def test_register_sets_current(self, isolated_data_dir: Path) -> None:
        register_session("reg_001", "proj")
        assert get_current_session() == "reg_001"


class TestGetCurrentProject:
    def test_from_state(self, isolated_data_dir: Path) -> None:
        _set_state({"current_project": "stateful-proj"})
        assert get_current_project() == "stateful-proj"

    def test_auto_detect_fallback(
        self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MEMCP_PROJECT", raising=False)
        # No state set — should auto-detect (will return cwd basename or "default")
        result = get_current_project()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_env_var_fallback(
        self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MEMCP_PROJECT", "env-proj")
        # No state set — should fallback to env var
        result = get_current_project()
        assert result == "env-proj"


class TestListProjects:
    def test_empty(self, isolated_data_dir: Path) -> None:
        result = list_projects()
        assert result == []

    def test_from_sessions(self, isolated_data_dir: Path) -> None:
        register_session("s1", "proj_a")
        register_session("s2", "proj_b")
        result = list_projects()
        names = [p["name"] for p in result]
        assert "proj_a" in names
        assert "proj_b" in names

    def test_from_graph(self, isolated_data_dir: Path) -> None:
        from memcp.core.memory import remember

        remember(content="Test insight for project listing", category="fact", project="graph-proj")
        result = list_projects()
        names = [p["name"] for p in result]
        assert "graph-proj" in names
        proj = next(p for p in result if p["name"] == "graph-proj")
        assert proj["insight_count"] >= 1

    def test_from_contexts(self, isolated_data_dir: Path) -> None:
        from memcp.core.context_store import load

        load(name="ctx-test", content="Some context content", project="ctx-proj")
        result = list_projects()
        names = [p["name"] for p in result]
        assert "ctx-proj" in names
        proj = next(p for p in result if p["name"] == "ctx-proj")
        assert proj["context_count"] >= 1

    def test_aggregates_all_sources(self, isolated_data_dir: Path) -> None:
        from memcp.core.context_store import load
        from memcp.core.memory import remember

        register_session("s1", "unified")
        remember(content="Insight for unified proj", category="fact", project="unified")
        load(name="ctx-uni", content="Context for unified", project="unified")

        result = list_projects()
        proj = next(p for p in result if p["name"] == "unified")
        assert proj["insight_count"] >= 1
        assert proj["context_count"] >= 1
        assert proj["session_count"] >= 1


class TestAutoProjectInheritance:
    def test_remember_inherits_project(self, isolated_data_dir: Path) -> None:
        register_session("s1", "auto-proj")
        from memcp.core.memory import remember

        result = remember(content="Auto-project insight", category="fact")
        assert result["project"] == "auto-proj"

    def test_load_context_inherits_project(self, isolated_data_dir: Path) -> None:
        register_session("s1", "auto-proj")
        from memcp.core.context_store import load

        result = load(name="auto-ctx", content="Auto-project context content")
        assert result["project"] == "auto-proj"


class TestAutoSessionInheritance:
    def test_remember_inherits_session(self, isolated_data_dir: Path) -> None:
        register_session("sess_001", "proj")
        from memcp.core.memory import remember

        result = remember(content="Auto-session insight", category="fact")
        assert result["session"] == "sess_001"

    def test_explicit_overrides_auto(self, isolated_data_dir: Path) -> None:
        register_session("sess_001", "proj")
        from memcp.core.memory import remember

        result = remember(
            content="Explicit override insight",
            category="fact",
            project="explicit-proj",
            session="explicit-sess",
        )
        assert result["project"] == "explicit-proj"
        assert result["session"] == "explicit-sess"


class TestStateHelpers:
    def test_set_and_get_state(self, isolated_data_dir: Path) -> None:
        _set_state({"key1": "value1", "key2": 42})
        state = _get_state()
        assert state["key1"] == "value1"
        assert state["key2"] == 42

    def test_merge_update(self, isolated_data_dir: Path) -> None:
        _set_state({"existing": "keep"})
        _set_state({"new_key": "added"})
        state = _get_state()
        assert state["existing"] == "keep"
        assert state["new_key"] == "added"

    def test_load_empty_sessions(self, isolated_data_dir: Path) -> None:
        sessions = _load_sessions()
        assert sessions["current_session"] == ""
        assert sessions["sessions"] == {}

    def test_save_and_load_sessions(self, isolated_data_dir: Path) -> None:
        data = {
            "current_session": "test_sess",
            "sessions": {"test_sess": {"project": "p", "started_at": "now"}},
        }
        _save_sessions(data)
        loaded = _load_sessions()
        assert loaded == data
