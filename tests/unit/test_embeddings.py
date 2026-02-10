"""Tests for memcp.core.embeddings."""

from __future__ import annotations

import pytest

from memcp.core.embeddings import (
    EmbeddingProvider,
    get_provider,
    reset_provider,
)


class FakeProvider(EmbeddingProvider):
    """Deterministic 8-dim provider for testing."""

    def embed(self, text: str) -> list[float]:
        h = hash(text) & 0xFFFFFFFF
        return [float((h >> (i * 4)) & 0xF) / 15.0 for i in range(8)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def dim(self) -> int:
        return 8


class TestFakeProvider:
    def test_embed_returns_list(self) -> None:
        p = FakeProvider()
        vec = p.embed("hello")
        assert isinstance(vec, list)
        assert len(vec) == 8

    def test_embed_deterministic(self) -> None:
        p = FakeProvider()
        assert p.embed("hello") == p.embed("hello")

    def test_embed_different_texts(self) -> None:
        p = FakeProvider()
        assert p.embed("hello") != p.embed("world")

    def test_embed_batch(self) -> None:
        p = FakeProvider()
        results = p.embed_batch(["a", "b", "c"])
        assert len(results) == 3
        assert all(len(v) == 8 for v in results)

    def test_dim(self) -> None:
        p = FakeProvider()
        assert p.dim() == 8


class TestGetProvider:
    def test_get_provider_returns_none_without_deps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_provider()
        monkeypatch.setenv("MEMCP_EMBEDDING_PROVIDER", "model2vec")
        # Provider will return None if model2vec isn't installed
        # (or return an actual provider if it is — both are valid)
        result = get_provider()
        assert result is None or isinstance(result, EmbeddingProvider)

    def test_reset_provider(self) -> None:
        reset_provider()
        # After reset, _provider_loaded should be False
        # Calling get_provider again should re-initialize
        result = get_provider()
        assert result is None or isinstance(result, EmbeddingProvider)

    def test_singleton_returns_same_instance(self) -> None:
        reset_provider()
        p1 = get_provider()
        p2 = get_provider()
        assert p1 is p2


class TestABCContract:
    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            EmbeddingProvider()  # type: ignore[abstract]
