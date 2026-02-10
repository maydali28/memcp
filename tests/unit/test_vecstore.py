"""Tests for memcp.core.vecstore."""

from __future__ import annotations

from pathlib import Path

import pytest

from memcp.core.vecstore import NUMPY_AVAILABLE, VectorStore


@pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not installed")
class TestVectorStore:
    def test_add_and_search(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        store.add("a", [1.0, 0.0, 0.0])
        store.add("b", [0.0, 1.0, 0.0])
        store.add("c", [0.9, 0.1, 0.0])

        results = store.search([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0][0] == "a"
        assert results[0][1] > 0.9

    def test_add_batch(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        store.add_batch(["x", "y"], [[1.0, 0.0], [0.0, 1.0]])
        assert store.count() == 2

    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "persist.npz"
        store = VectorStore(path)
        store.add("a", [1.0, 0.0, 0.0])
        store.add("b", [0.0, 1.0, 0.0])
        store.save()

        store2 = VectorStore(path)
        assert store2.load()
        assert store2.count() == 2
        results = store2.search([1.0, 0.0, 0.0], top_k=1)
        assert results[0][0] == "a"

    def test_remove(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        store.add("a", [1.0, 0.0])
        store.add("b", [0.0, 1.0])
        assert store.remove("a")
        assert store.count() == 1
        assert not store.has_id("a")
        assert store.has_id("b")

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        assert not store.remove("nope")

    def test_replace_existing(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        store.add("a", [1.0, 0.0])
        store.add("a", [0.0, 1.0])
        assert store.count() == 1
        results = store.search([0.0, 1.0], top_k=1)
        assert results[0][0] == "a"
        assert results[0][1] > 0.9

    def test_empty_search(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        results = store.search([1.0, 0.0], top_k=5)
        assert results == []

    def test_zero_vector_query(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        store.add("a", [1.0, 0.0])
        results = store.search([0.0, 0.0], top_k=5)
        assert results == []

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "nope.npz")
        assert not store.load()

    def test_has_id(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        store.add("x", [1.0])
        assert store.has_id("x")
        assert not store.has_id("y")

    def test_count(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "test.npz")
        assert store.count() == 0
        store.add("a", [1.0])
        assert store.count() == 1
        store.add("b", [0.0])
        assert store.count() == 2


class TestVectorStoreWithoutNumpy:
    def test_numpy_flag_exists(self) -> None:
        assert isinstance(NUMPY_AVAILABLE, bool)
