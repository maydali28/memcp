"""Tests for memcp.core.retention."""

from __future__ import annotations

import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from memcp.config import get_config
from memcp.core import context_store
from memcp.core.fileutil import atomic_write_json, locked_read_json
from memcp.core.memory import remember
from memcp.core.retention import (
    archive_context,
    archive_insight,
    get_archive_candidates,
    get_purge_candidates,
    is_immune,
    purge_archived,
    restore_context,
    restore_insight,
    retention_preview,
    retention_run,
)

# ── Helpers ────────────────────────────────────────────────────────────


def _make_old_context(name: str, days_ago: int, access_count: int = 0) -> dict[str, Any]:
    """Create a context with a backdated created_at."""
    context_store.load(name, content=f"Content for {name}\nLine two.")
    config = get_config()
    meta_path = config.contexts_dir / name / "meta.json"
    meta = locked_read_json(meta_path)
    assert meta is not None
    old_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    meta["created_at"] = old_ts
    meta["access_count"] = access_count
    atomic_write_json(meta_path, meta)
    return meta


def _make_old_insight(
    content: str,
    days_ago: int,
    access_count: int = 0,
    importance: str = "low",
    tags: str = "",
) -> dict[str, Any]:
    """Create an insight with a backdated created_at."""
    result = remember(
        content=content,
        importance=importance,
        tags=tags,
    )
    config = get_config()
    data = locked_read_json(config.memory_path)
    assert data is not None
    old_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    for ins in data["insights"]:
        if ins["id"] == result["id"]:
            ins["created_at"] = old_ts
            ins["access_count"] = access_count
            break
    atomic_write_json(config.memory_path, data)
    return result


# ── TestIsImmune ───────────────────────────────────────────────────────


class TestIsImmune:
    def test_critical_importance(self) -> None:
        assert is_immune({"importance": "critical"}) is True

    def test_high_importance(self) -> None:
        assert is_immune({"importance": "high"}) is True

    def test_medium_importance_not_immune(self) -> None:
        assert is_immune({"importance": "medium", "access_count": 0, "tags": []}) is False

    def test_low_importance_not_immune(self) -> None:
        assert is_immune({"importance": "low", "access_count": 0, "tags": []}) is False

    def test_high_access_count(self) -> None:
        assert is_immune({"importance": "low", "access_count": 5, "tags": []}) is True

    def test_access_count_exactly_three(self) -> None:
        assert is_immune({"importance": "low", "access_count": 3, "tags": []}) is True

    def test_access_count_below_threshold(self) -> None:
        assert is_immune({"importance": "low", "access_count": 2, "tags": []}) is False

    def test_protected_tag_keep(self) -> None:
        assert is_immune({"importance": "low", "access_count": 0, "tags": ["keep"]}) is True

    def test_protected_tag_important(self) -> None:
        assert is_immune({"importance": "low", "access_count": 0, "tags": ["important"]}) is True

    def test_protected_tag_pinned(self) -> None:
        assert is_immune({"importance": "low", "access_count": 0, "tags": ["pinned"]}) is True

    def test_protected_tag_case_insensitive(self) -> None:
        assert is_immune({"importance": "low", "access_count": 0, "tags": ["KEEP"]}) is True

    def test_tags_as_comma_string(self) -> None:
        assert is_immune({"importance": "low", "access_count": 0, "tags": "foo,keep,bar"}) is True

    def test_non_immune_item(self) -> None:
        assert is_immune({"importance": "low", "access_count": 0, "tags": ["misc"]}) is False

    def test_empty_item(self) -> None:
        assert is_immune({}) is False


# ── TestGetArchiveCandidates ───────────────────────────────────────────


class TestGetArchiveCandidates:
    def test_fresh_data_returns_empty(self, isolated_data_dir: Path) -> None:
        context_store.load("fresh", content="Just created.")
        result = get_archive_candidates(days=30)
        assert result["total"] == 0

    def test_old_context_is_candidate(self, isolated_data_dir: Path) -> None:
        _make_old_context("stale-ctx", days_ago=45)
        result = get_archive_candidates(days=30)
        assert len(result["contexts"]) == 1
        assert result["contexts"][0]["name"] == "stale-ctx"

    def test_old_insight_is_candidate(self, isolated_data_dir: Path) -> None:
        _make_old_insight("stale insight", days_ago=45)
        result = get_archive_candidates(days=30)
        assert len(result["insights"]) == 1

    def test_immune_items_excluded(self, isolated_data_dir: Path) -> None:
        # High importance — should be immune
        _make_old_insight("immune: high", days_ago=100, importance="high")
        # High access count — should be immune
        _make_old_insight("immune: accessed", days_ago=100, access_count=5)
        # Protected tag — should be immune
        _make_old_insight("immune: pinned", days_ago=100, tags="pinned")

        result = get_archive_candidates(days=30)
        assert result["total"] == 0

    def test_accessed_items_excluded(self, isolated_data_dir: Path) -> None:
        _make_old_context("accessed-ctx", days_ago=45, access_count=1)
        result = get_archive_candidates(days=30)
        assert len(result["contexts"]) == 0

    def test_mixed_candidates_and_immune(self, isolated_data_dir: Path) -> None:
        _make_old_context("stale-one", days_ago=60)
        _make_old_context("stale-immune", days_ago=60, access_count=5)
        _make_old_insight("stale insight", days_ago=60)
        _make_old_insight("critical insight", days_ago=60, importance="critical")

        result = get_archive_candidates(days=30)
        assert len(result["contexts"]) == 1
        assert len(result["insights"]) == 1
        assert result["total"] == 2


# ── TestArchiveContext ─────────────────────────────────────────────────


class TestArchiveContext:
    def test_archive_creates_gz(self, isolated_data_dir: Path) -> None:
        context_store.load("to-archive", content="Archive me!\nSecond line.")
        config = get_config()

        meta = archive_context("to-archive")

        # Original removed
        assert not (config.contexts_dir / "to-archive").exists()

        # Archive created
        archive_dir = config.archive_dir / "contexts" / "to-archive"
        assert (archive_dir / "content.md.gz").exists()
        assert (archive_dir / "meta.json").exists()

        # archived_at field added
        assert "archived_at" in meta

    def test_archive_content_preserved(self, isolated_data_dir: Path) -> None:
        original = "Line one\nLine two\nLine three"
        context_store.load("preserved", content=original)
        config = get_config()

        archive_context("preserved")

        gz_path = config.archive_dir / "contexts" / "preserved" / "content.md.gz"
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            restored = f.read()
        assert restored == original

    def test_archive_removes_chunks(self, isolated_data_dir: Path) -> None:
        context_store.load("chunked", content="A\nB\nC\nD\nE")
        from memcp.core import chunker

        chunker.chunk_context("chunked", strategy="lines", chunk_size=2)

        config = get_config()
        assert (config.chunks_dir / "chunked").exists()

        archive_context("chunked")
        assert not (config.chunks_dir / "chunked").exists()

    def test_archive_nonexistent_raises(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            archive_context("nope")


# ── TestArchiveInsight ─────────────────────────────────────────────────


class TestArchiveInsight:
    def test_archive_insight_to_json(self, isolated_data_dir: Path) -> None:
        result = remember("to archive", importance="low")
        config = get_config()

        archived = archive_insight(result["id"])

        # Check archived_at set
        assert "archived_at" in archived

        # Check in archive file
        insights_path = config.archive_dir / "insights.json"
        archived_list = locked_read_json(insights_path)
        assert archived_list is not None
        assert len(archived_list) == 1
        assert archived_list[0]["id"] == result["id"]

        # Check removed from active memory
        data = locked_read_json(config.memory_path)
        assert all(ins["id"] != result["id"] for ins in data.get("insights", []))

    def test_archive_nonexistent_insight_raises(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            archive_insight("nonexistent-id")


# ── TestRestoreContext ─────────────────────────────────────────────────


class TestRestoreContext:
    def test_restore_roundtrip(self, isolated_data_dir: Path) -> None:
        original = "Restore me!\nMultiple lines.\nThird."
        context_store.load("roundtrip", content=original)
        config = get_config()

        # Archive
        archive_context("roundtrip")
        assert not (config.contexts_dir / "roundtrip").exists()

        # Restore
        result = restore_context("roundtrip")
        assert result["name"] == "roundtrip"

        # Content intact
        content_path = config.contexts_dir / "roundtrip" / "content.md"
        assert content_path.exists()
        assert content_path.read_text(encoding="utf-8") == original

        # Archive cleaned up
        assert not (config.archive_dir / "contexts" / "roundtrip").exists()

    def test_restore_nonexistent_raises(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            restore_context("ghost")


# ── TestRestoreInsight ─────────────────────────────────────────────────


class TestRestoreInsight:
    def test_restore_insight_roundtrip(self, isolated_data_dir: Path) -> None:
        result = remember("insight to restore", importance="low", tags="test")
        insight_id = result["id"]
        config = get_config()

        # Archive
        archive_insight(insight_id)
        data = locked_read_json(config.memory_path)
        assert all(ins["id"] != insight_id for ins in data.get("insights", []))

        # Restore
        restored = restore_insight(insight_id)
        assert restored["id"] == insight_id

        # Back in active memory
        data = locked_read_json(config.memory_path)
        assert any(ins["id"] == insight_id for ins in data.get("insights", []))

        # Removed from archive
        archived = locked_read_json(config.archive_dir / "insights.json") or []
        assert all(ins["id"] != insight_id for ins in archived)

    def test_restore_nonexistent_insight_raises(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            restore_insight("ghost-id")


# ── TestPurgeArchived ──────────────────────────────────────────────────


class TestPurgeArchived:
    def test_purge_archived_context(self, isolated_data_dir: Path) -> None:
        context_store.load("purge-me", content="Bye forever.")
        config = get_config()

        archive_context("purge-me")
        assert (config.archive_dir / "contexts" / "purge-me").exists()

        result = purge_archived("purge-me", item_type="context")
        assert result["status"] == "purged"
        assert not (config.archive_dir / "contexts" / "purge-me").exists()

        # Check purge log
        log = locked_read_json(config.archive_dir / "purge_log.json")
        assert log is not None
        assert len(log) == 1
        assert log[0]["type"] == "context"
        assert "purged_at" in log[0]

    def test_purge_archived_insight(self, isolated_data_dir: Path) -> None:
        result = remember("purge this insight", importance="low")
        config = get_config()

        archive_insight(result["id"])
        purge_result = purge_archived(result["id"], item_type="insight")
        assert purge_result["status"] == "purged"

        # Check gone from archive
        archived = locked_read_json(config.archive_dir / "insights.json") or []
        assert all(ins["id"] != result["id"] for ins in archived)

        # Check purge log
        log = locked_read_json(config.archive_dir / "purge_log.json")
        assert log is not None
        assert any(entry["id"] == result["id"] for entry in log)

    def test_purge_nonexistent_context_raises(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            purge_archived("nope", item_type="context")

    def test_purge_nonexistent_insight_raises(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            purge_archived("nope", item_type="insight")

    def test_purge_auto_detects_type(self, isolated_data_dir: Path) -> None:
        context_store.load("auto-purge", content="Auto detect.")
        archive_context("auto-purge")

        result = purge_archived("auto-purge")
        assert result["status"] == "purged"
        assert result["type"] == "context"


# ── TestRetentionPreview ───────────────────────────────────────────────


class TestRetentionPreview:
    def test_preview_empty(self, isolated_data_dir: Path) -> None:
        result = retention_preview(archive_days=30, purge_days=180)
        assert result["archive_candidates"]["total"] == 0
        assert result["purge_candidates"]["total"] == 0

    def test_preview_shows_candidates(self, isolated_data_dir: Path) -> None:
        _make_old_context("stale", days_ago=45)
        _make_old_insight("old insight", days_ago=45)

        result = retention_preview(archive_days=30, purge_days=180)
        assert result["archive_candidates"]["total"] == 2
        assert len(result["archive_candidates"]["contexts"]) == 1
        assert len(result["archive_candidates"]["insights"]) == 1

    def test_preview_does_not_modify(self, isolated_data_dir: Path) -> None:
        _make_old_context("preview-only", days_ago=45)
        config = get_config()

        retention_preview(archive_days=30)

        # Context still exists in active
        assert (config.contexts_dir / "preview-only").exists()

    def test_preview_shows_thresholds(self, isolated_data_dir: Path) -> None:
        result = retention_preview(archive_days=60, purge_days=365)
        assert result["archive_threshold_days"] == 60
        assert result["purge_threshold_days"] == 365


# ── TestRetentionRun ───────────────────────────────────────────────────


class TestRetentionRun:
    def test_run_archives_stale_items(self, isolated_data_dir: Path) -> None:
        _make_old_context("run-stale", days_ago=45)
        _make_old_insight("run stale insight", days_ago=45)
        config = get_config()

        summary = retention_run(archive=True, purge=False)
        assert summary["archived_contexts"] == 1
        assert summary["archived_insights"] == 1
        assert summary["total_archived"] == 2

        # Context archived
        assert not (config.contexts_dir / "run-stale").exists()
        assert (config.archive_dir / "contexts" / "run-stale").exists()

    def test_run_purges_old_archives(self, isolated_data_dir: Path) -> None:
        # Create + archive a context
        context_store.load("purge-target", content="Will be purged.")
        archive_context("purge-target")
        config = get_config()

        # Backdate the archived_at
        meta_path = config.archive_dir / "contexts" / "purge-target" / "meta.json"
        meta = locked_read_json(meta_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        meta["archived_at"] = old_ts
        atomic_write_json(meta_path, meta)

        summary = retention_run(archive=False, purge=True)
        assert summary["purged_contexts"] == 1
        assert summary["total_purged"] == 1
        assert not (config.archive_dir / "contexts" / "purge-target").exists()

    def test_run_empty_data(self, isolated_data_dir: Path) -> None:
        summary = retention_run(archive=True, purge=True)
        assert summary["total_archived"] == 0
        assert summary["total_purged"] == 0

    def test_run_skips_immune(self, isolated_data_dir: Path) -> None:
        _make_old_insight("critical stays", days_ago=100, importance="critical")
        _make_old_insight("accessed stays", days_ago=100, access_count=5)

        summary = retention_run(archive=True, purge=False)
        assert summary["total_archived"] == 0


# ── TestRetentionEdgeCases ─────────────────────────────────────────────


class TestRetentionEdgeCases:
    def test_archive_then_purge_lifecycle(self, isolated_data_dir: Path) -> None:
        """Full lifecycle: create → archive → purge."""
        context_store.load("lifecycle", content="Full cycle test.")
        config = get_config()

        # Archive
        archive_context("lifecycle")
        assert (config.archive_dir / "contexts" / "lifecycle").exists()

        # Purge
        purge_archived("lifecycle", item_type="context")
        assert not (config.archive_dir / "contexts" / "lifecycle").exists()

        # Purge log has entry
        log = locked_read_json(config.archive_dir / "purge_log.json")
        assert len(log) == 1

    def test_archive_restore_archive_again(self, isolated_data_dir: Path) -> None:
        """Archive, restore, then archive again."""
        context_store.load("re-archive", content="Archive me twice.")

        archive_context("re-archive")
        restore_context("re-archive")
        archive_context("re-archive")

        config = get_config()
        assert (config.archive_dir / "contexts" / "re-archive").exists()
        assert not (config.contexts_dir / "re-archive").exists()

    def test_get_purge_candidates_empty_archive(self, isolated_data_dir: Path) -> None:
        result = get_purge_candidates(days=1)
        assert result["total"] == 0

    def test_invalid_item_type_raises(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid item_type"):
            purge_archived("anything", item_type="invalid")

    def test_multiple_insights_archive(self, isolated_data_dir: Path) -> None:
        """Archive multiple insights, verify all in archive file."""
        ids = []
        for i in range(3):
            result = remember(f"Insight number {i}", importance="low")
            ids.append(result["id"])

        config = get_config()
        for iid in ids:
            archive_insight(iid)

        archived = locked_read_json(config.archive_dir / "insights.json")
        assert len(archived) == 3
        archived_ids = {ins["id"] for ins in archived}
        assert archived_ids == set(ids)
