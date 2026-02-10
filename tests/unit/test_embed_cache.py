"""Tests for memcp.core.embed_cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from memcp.core.embed_cache import (
    DISKCACHE_AVAILABLE,
    EmbedCache,
    get_embed_cache,
    reset_embed_cache,
)


class TestEmbedCacheMemory:
    def test_put_and_get(self) -> None:
        cache = EmbedCache()
        cache.put("hello", "test_provider", [1.0, 2.0, 3.0])
        result = cache.get("hello", "test_provider")
        assert result == [1.0, 2.0, 3.0]

    def test_miss_returns_none(self) -> None:
        cache = EmbedCache()
        result = cache.get("missing", "test_provider")
        assert result is None

    def test_different_provider_keys(self) -> None:
        cache = EmbedCache()
        cache.put("text", "providerA", [1.0])
        cache.put("text", "providerB", [2.0])
        assert cache.get("text", "providerA") == [1.0]
        assert cache.get("text", "providerB") == [2.0]

    def test_eviction_at_capacity(self) -> None:
        cache = EmbedCache(max_memory_items=3)
        cache.put("a", "p", [1.0])
        cache.put("b", "p", [2.0])
        cache.put("c", "p", [3.0])
        # Adding a 4th should evict the oldest
        cache.put("d", "p", [4.0])
        # "a" was first inserted, should be evicted
        assert cache.get("a", "p") is None
        assert cache.get("d", "p") == [4.0]

    def test_close_no_error(self) -> None:
        cache = EmbedCache()
        cache.close()  # Should not raise


class TestEmbedCacheSingleton:
    def test_get_embed_cache(self, isolated_data_dir: Path) -> None:
        cache = get_embed_cache()
        assert isinstance(cache, EmbedCache)

    def test_singleton_returns_same(self, isolated_data_dir: Path) -> None:
        c1 = get_embed_cache()
        c2 = get_embed_cache()
        assert c1 is c2

    def test_reset_clears_singleton(self, isolated_data_dir: Path) -> None:
        c1 = get_embed_cache()
        reset_embed_cache()
        c2 = get_embed_cache()
        assert c1 is not c2


@pytest.mark.skipif(not DISKCACHE_AVAILABLE, reason="diskcache not installed")
class TestEmbedCacheDisk:
    def test_disk_persistence(self, tmp_path: Path) -> None:
        cache_dir = str(tmp_path / "embed_cache")
        cache = EmbedCache(cache_dir=cache_dir)
        cache.put("hello", "provider", [1.0, 2.0])
        cache.close()

        cache2 = EmbedCache(cache_dir=cache_dir)
        result = cache2.get("hello", "provider")
        assert result == [1.0, 2.0]
        cache2.close()
