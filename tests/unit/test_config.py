"""Tests for memcp.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from memcp.config import get_config


class TestMemCPConfig:
    def test_defaults(self, isolated_data_dir: Path) -> None:
        config = get_config()
        assert config.data_dir == isolated_data_dir
        assert config.max_memory_mb == 2048
        assert config.max_insights == 10000
        assert config.max_context_size_mb == 10
        assert config.importance_decay_days == 30

    def test_env_overrides(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import memcp.config as cfg

        cfg._config = None
        custom_dir = tmp_path / "custom"
        monkeypatch.setenv("MEMCP_DATA_DIR", str(custom_dir))
        monkeypatch.setenv("MEMCP_MAX_MEMORY_MB", "512")
        monkeypatch.setenv("MEMCP_MAX_INSIGHTS", "500")
        monkeypatch.setenv("MEMCP_MAX_CONTEXT_SIZE_MB", "5")
        monkeypatch.setenv("MEMCP_IMPORTANCE_DECAY_DAYS", "7")

        config = get_config()
        assert config.data_dir == custom_dir.resolve()
        assert config.max_memory_mb == 512
        assert config.max_insights == 500
        assert config.max_context_size_mb == 5
        assert config.importance_decay_days == 7

    def test_paths(self, isolated_data_dir: Path) -> None:
        config = get_config()
        assert config.memory_path == isolated_data_dir / "memory.json"
        assert config.contexts_dir == isolated_data_dir / "contexts"
        assert config.chunks_dir == isolated_data_dir / "chunks"
        assert config.state_path == isolated_data_dir / "state.json"
        assert config.cache_dir == isolated_data_dir / "cache"

    def test_ensure_dirs(self, isolated_data_dir: Path) -> None:
        config = get_config()
        # get_config() calls ensure_dirs automatically
        assert config.data_dir.exists()
        assert config.contexts_dir.exists()
        assert config.chunks_dir.exists()
        assert config.cache_dir.exists()

    def test_singleton(self, isolated_data_dir: Path) -> None:
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_expanduser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import memcp.config as cfg

        cfg._config = None
        monkeypatch.setenv("MEMCP_DATA_DIR", "~/.memcp")
        config = get_config()
        assert "~" not in str(config.data_dir)
        assert config.data_dir.is_absolute()
