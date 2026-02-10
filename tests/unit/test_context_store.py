"""Tests for memcp.core.context_store."""

from __future__ import annotations

from pathlib import Path

import pytest

from memcp.core import context_store


class TestLoad:
    def test_load_content(self, isolated_data_dir: Path) -> None:
        result = context_store.load("test-ctx", content="Hello World")
        assert result["name"] == "test-ctx"
        assert result["type"] == "text"
        assert result["size_bytes"] > 0
        assert result["line_count"] == 1
        assert result["token_estimate"] >= 1

    def test_load_file(self, isolated_data_dir: Path, tmp_path: Path) -> None:
        fp = tmp_path / "sample.py"
        fp.write_text("def hello():\n    return 'world'\n")

        result = context_store.load("code", file_path=str(fp))
        assert result["name"] == "code"
        assert result["type"] == "python"
        assert result["source"] == str(fp)

    def test_load_markdown(self, isolated_data_dir: Path) -> None:
        md = "# Title\n\n## Section 1\n\nContent here.\n\n## Section 2\n\nMore content."
        result = context_store.load("report", content=md)
        assert result["type"] == "markdown"

    def test_load_json_content(self, isolated_data_dir: Path) -> None:
        result = context_store.load("data", content='{"key": "value"}')
        assert result["type"] == "json"

    def test_duplicate_detection(self, isolated_data_dir: Path) -> None:
        context_store.load("ctx1", content="Same content")
        result = context_store.load("ctx1", content="Same content")
        assert result.get("_duplicate") is True

    def test_invalid_name(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            context_store.load("bad/name", content="test")

    def test_empty_content(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Content cannot be empty"):
            context_store.load("empty", content="   ")

    def test_no_content_or_file(self, isolated_data_dir: Path) -> None:
        with pytest.raises(ValueError, match="Either content or file_path"):
            context_store.load("nothing")

    def test_missing_file(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            context_store.load("missing", file_path="/nonexistent/file.txt")

    def test_overwrite_different_content(self, isolated_data_dir: Path) -> None:
        context_store.load("ctx", content="Version 1")
        result = context_store.load("ctx", content="Version 2")
        assert result.get("_duplicate") is None
        assert result["name"] == "ctx"

    def test_project_field(self, isolated_data_dir: Path) -> None:
        result = context_store.load("proj-ctx", content="test", project="myapp")
        assert result["project"] == "myapp"


class TestInspect:
    def test_inspect_existing(self, isolated_data_dir: Path) -> None:
        context_store.load("test", content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6")
        result = context_store.inspect("test")
        assert result["name"] == "test"
        assert "preview" in result
        assert result["line_count"] == 6
        assert result["access_count"] >= 1

    def test_inspect_preview_lines(self, isolated_data_dir: Path) -> None:
        lines = "\n".join(f"Line {i}" for i in range(20))
        context_store.load("multiline", content=lines)
        result = context_store.inspect("multiline", preview_lines=3)
        preview_lines = result["preview"].split("\n")
        assert len(preview_lines) == 3

    def test_inspect_missing(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            context_store.inspect("nonexistent")

    def test_inspect_increments_access(self, isolated_data_dir: Path) -> None:
        context_store.load("access-test", content="test content")
        context_store.inspect("access-test")
        result = context_store.inspect("access-test")
        assert result["access_count"] >= 2


class TestGet:
    def test_get_full(self, isolated_data_dir: Path) -> None:
        content = "Line 1\nLine 2\nLine 3"
        context_store.load("full", content=content)
        result = context_store.get("full")
        assert result["content"] == content
        assert result["lines_returned"] == 3

    def test_get_slice(self, isolated_data_dir: Path) -> None:
        content = "\n".join(f"Line {i}" for i in range(1, 11))
        context_store.load("sliced", content=content)
        result = context_store.get("sliced", start=3, end=5)
        lines = result["content"].split("\n")
        assert len(lines) == 3
        assert lines[0] == "Line 3"
        assert lines[2] == "Line 5"

    def test_get_missing(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            context_store.get("nonexistent")


class TestListContexts:
    def test_empty(self, isolated_data_dir: Path) -> None:
        result = context_store.list_contexts()
        assert result == []

    def test_multiple(self, isolated_data_dir: Path) -> None:
        context_store.load("ctx-a", content="Content A")
        context_store.load("ctx-b", content="Content B")
        result = context_store.list_contexts()
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"ctx-a", "ctx-b"}

    def test_filter_by_project(self, isolated_data_dir: Path) -> None:
        context_store.load("proj-a", content="A", project="alpha")
        context_store.load("proj-b", content="B", project="beta")
        result = context_store.list_contexts(project="alpha")
        assert len(result) == 1
        assert result[0]["name"] == "proj-a"


class TestDelete:
    def test_delete_existing(self, isolated_data_dir: Path) -> None:
        context_store.load("to-delete", content="delete me")
        assert context_store.delete("to-delete") is True
        assert context_store.list_contexts() == []

    def test_delete_nonexistent(self, isolated_data_dir: Path) -> None:
        assert context_store.delete("nonexistent") is False

    def test_delete_removes_chunks(self, isolated_data_dir: Path) -> None:
        from memcp.core import chunker

        context_store.load("chunked", content="A\nB\nC\nD\nE\nF\nG\nH\nI\nJ")
        chunker.chunk_context("chunked", strategy="lines", chunk_size=3)

        config = context_store.get_config()
        chunks_dir = config.chunks_dir / "chunked"
        assert chunks_dir.exists()

        context_store.delete("chunked")
        assert not chunks_dir.exists()


class TestFilterContext:
    def test_filter_match(self, isolated_data_dir: Path) -> None:
        content = "apple pie\nbanana split\napple sauce\ncherry tart"
        context_store.load("fruits", content=content)
        result = context_store.filter_context("fruits", pattern="apple")
        assert result["lines_matched"] == 2
        assert "apple pie" in result["content"]
        assert "apple sauce" in result["content"]

    def test_filter_invert(self, isolated_data_dir: Path) -> None:
        content = "apple pie\nbanana split\napple sauce\ncherry tart"
        context_store.load("fruits2", content=content)
        result = context_store.filter_context("fruits2", pattern="apple", invert=True)
        assert result["lines_matched"] == 2
        assert "banana split" in result["content"]
        assert "cherry tart" in result["content"]

    def test_filter_missing(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            context_store.filter_context("nonexistent", pattern="test")
