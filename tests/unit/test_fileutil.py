"""Tests for memcp.core.fileutil."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memcp.core.fileutil import (
    atomic_write_json,
    atomic_write_text,
    content_hash,
    estimate_tokens,
    locked_read_json,
    safe_name,
)


class TestSafeName:
    def test_valid_names(self) -> None:
        assert safe_name("hello") == "hello"
        assert safe_name("my-context") == "my-context"
        assert safe_name("report_v2") == "report_v2"
        assert safe_name("file.txt") == "file.txt"
        assert safe_name("CamelCase") == "CamelCase"
        assert safe_name("123") == "123"

    def test_invalid_empty(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            safe_name("")

    def test_invalid_spaces(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            safe_name("has space")

    def test_invalid_slashes(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            safe_name("path/traversal")

    def test_invalid_path_traversal(self) -> None:
        with pytest.raises(ValueError, match="path traversal"):
            safe_name("foo..bar")

    def test_invalid_special_chars(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            safe_name("hello@world")
        with pytest.raises(ValueError, match="Invalid name"):
            safe_name("rm -rf /")


class TestContentHash:
    def test_deterministic(self) -> None:
        h1 = content_hash("hello world")
        h2 = content_hash("hello world")
        assert h1 == h2

    def test_normalized(self) -> None:
        h1 = content_hash("Hello World")
        h2 = content_hash("  hello world  ")
        assert h1 == h2

    def test_different_content(self) -> None:
        h1 = content_hash("hello")
        h2 = content_hash("world")
        assert h1 != h2

    def test_length(self) -> None:
        h = content_hash("test")
        assert len(h) == 16

    def test_hex_chars(self) -> None:
        h = content_hash("test")
        assert all(c in "0123456789abcdef" for c in h)


class TestAtomicWriteJson:
    def test_write_and_read(self, tmp_path: Path) -> None:
        path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        atomic_write_json(path, data)

        assert path.exists()
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deep" / "test.json"
        atomic_write_json(path, {"ok": True})
        assert path.exists()

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "test.json"
        atomic_write_json(path, {"version": 1})
        atomic_write_json(path, {"version": 2})

        with open(path) as f:
            loaded = json.load(f)
        assert loaded["version"] == 2

    def test_unicode(self, tmp_path: Path) -> None:
        path = tmp_path / "unicode.json"
        data = {"emoji": "\U0001f680", "arabic": "\u0645\u0631\u062d\u0628\u0627"}
        atomic_write_json(path, data)

        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data


class TestAtomicWriteText:
    def test_write_and_read(self, tmp_path: Path) -> None:
        path = tmp_path / "test.md"
        content = "# Hello\n\nThis is a test."
        atomic_write_text(path, content)

        assert path.exists()
        assert path.read_text(encoding="utf-8") == content

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "test.txt"
        atomic_write_text(path, "hello")
        assert path.exists()


class TestLockedReadJson:
    def test_read_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"
        data = {"items": [1, 2, 3]}
        with open(path, "w") as f:
            json.dump(data, f)

        result = locked_read_json(path)
        assert result == data

    def test_read_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        result = locked_read_json(path)
        assert result is None

    def test_roundtrip_with_atomic_write(self, tmp_path: Path) -> None:
        path = tmp_path / "roundtrip.json"
        data = {"key": "value", "nested": {"a": 1}}
        atomic_write_json(path, data)
        result = locked_read_json(path)
        assert result == data


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert estimate_tokens("hello world") >= 1

    def test_empty(self) -> None:
        assert estimate_tokens("") == 1

    def test_proportional(self) -> None:
        short = estimate_tokens("hi")
        long = estimate_tokens("a" * 1000)
        assert long > short

    def test_heuristic(self) -> None:
        # ~4 chars per token
        text = "a" * 400
        tokens = estimate_tokens(text)
        assert tokens == 100
