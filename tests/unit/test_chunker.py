"""Tests for memcp.core.chunker."""

from __future__ import annotations

from pathlib import Path

import pytest

from memcp.core import chunker, context_store


class TestByLines:
    def test_basic(self) -> None:
        content = "\n".join(f"Line {i}" for i in range(100))
        chunks = chunker.by_lines(content, size=20, overlap=0)
        assert len(chunks) == 5
        assert chunks[0]["start_line"] == 1
        assert chunks[0]["end_line"] == 20

    def test_with_overlap(self) -> None:
        content = "\n".join(f"Line {i}" for i in range(20))
        chunks = chunker.by_lines(content, size=10, overlap=2)
        assert len(chunks) >= 2
        # Second chunk should start 8 lines after first
        assert chunks[1]["start_line"] == 9

    def test_single_chunk(self) -> None:
        content = "Short content"
        chunks = chunker.by_lines(content, size=50)
        assert len(chunks) == 1

    def test_empty(self) -> None:
        chunks = chunker.by_lines("", size=10)
        assert len(chunks) == 1
        assert chunks[0]["tokens"] >= 1


class TestByParagraphs:
    def test_basic(self) -> None:
        # Each paragraph ~4 tokens, max_tokens=5 forces splits
        content = "Para 1 content.\n\nPara 2 content.\n\nPara 3 content."
        chunks = chunker.by_paragraphs(content, max_tokens=5)
        assert len(chunks) >= 2

    def test_large_paragraph(self) -> None:
        content = "A " * 1000 + "\n\n" + "B " * 10
        chunks = chunker.by_paragraphs(content, max_tokens=100)
        assert len(chunks) >= 2

    def test_single_paragraph(self) -> None:
        content = "Just one paragraph."
        chunks = chunker.by_paragraphs(content, max_tokens=1000)
        assert len(chunks) == 1


class TestByHeadings:
    def test_markdown_headings(self) -> None:
        content = "# Title\n\nIntro\n\n## Section 1\n\nContent 1\n\n## Section 2\n\nContent 2"
        chunks = chunker.by_headings(content)
        assert len(chunks) == 3

    def test_no_headings(self) -> None:
        content = "Plain text without any headings."
        chunks = chunker.by_headings(content)
        assert len(chunks) == 1

    def test_nested_headings(self) -> None:
        content = "# H1\n\nText\n\n## H2\n\nText\n\n### H3\n\nText"
        chunks = chunker.by_headings(content)
        assert len(chunks) == 3


class TestByChars:
    def test_basic(self) -> None:
        content = "a" * 10000
        chunks = chunker.by_chars(content, size=3000, overlap=0)
        assert len(chunks) >= 3

    def test_with_overlap(self) -> None:
        content = "a" * 1000
        chunks = chunker.by_chars(content, size=400, overlap=50)
        assert len(chunks) >= 2

    def test_small_content(self) -> None:
        content = "small"
        chunks = chunker.by_chars(content, size=1000)
        assert len(chunks) == 1


class TestByRegex:
    def test_split_on_separator(self) -> None:
        content = "Part 1\n---\nPart 2\n---\nPart 3"
        chunks = chunker.by_regex(content, r"\n---\n")
        assert len(chunks) == 3

    def test_split_on_blank_lines(self) -> None:
        content = "Section 1\n\n\nSection 2\n\n\nSection 3"
        chunks = chunker.by_regex(content, r"\n\n\n")
        assert len(chunks) == 3


class TestAuto:
    def test_markdown_uses_headings(self) -> None:
        content = "# Title\n\nIntro\n\n## S1\n\nC1\n\n## S2\n\nC2"
        chunks = chunker.auto(content, content_type="markdown")
        assert len(chunks) == 3

    def test_python_uses_lines(self) -> None:
        content = "\n".join(f"line_{i} = {i}" for i in range(100))
        chunks = chunker.auto(content, content_type="python", target=5)
        assert len(chunks) >= 3

    def test_prose_uses_paragraphs(self) -> None:
        # Make paragraphs long enough to exceed per-chunk token budget
        content = "\n\n".join(f"Paragraph {i} " + "word " * 50 for i in range(20))
        chunks = chunker.auto(content, content_type="text", target=5)
        assert len(chunks) >= 2


class TestChunkContext:
    def test_chunk_and_persist(self, isolated_data_dir: Path) -> None:
        content = "\n".join(f"Line {i}" for i in range(50))
        context_store.load("lines-ctx", content=content)

        result = chunker.chunk_context("lines-ctx", strategy="lines", chunk_size=10, overlap=0)
        assert result["count"] == 5
        assert result["strategy"] == "lines"

    def test_chunk_auto(self, isolated_data_dir: Path) -> None:
        content = "# Title\n\nIntro\n\n## S1\n\nC1\n\n## S2\n\nC2"
        context_store.load("md-ctx", content=content)

        result = chunker.chunk_context("md-ctx", strategy="auto")
        assert result["count"] >= 2

    def test_chunk_missing_context(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            chunker.chunk_context("nonexistent")

    def test_invalid_strategy(self, isolated_data_dir: Path) -> None:
        context_store.load("ctx", content="test")
        with pytest.raises(ValueError, match="Unknown strategy"):
            chunker.chunk_context("ctx", strategy="invalid")


class TestPeekChunk:
    def test_peek_basic(self, isolated_data_dir: Path) -> None:
        content = "\n".join(f"Line {i}" for i in range(30))
        context_store.load("peek-ctx", content=content)
        chunker.chunk_context("peek-ctx", strategy="lines", chunk_size=10, overlap=0)

        result = chunker.peek_chunk("peek-ctx", chunk_index=1)
        assert result["chunk_index"] == 1
        assert result["total_chunks"] == 3
        assert result["content"]

    def test_peek_with_slice(self, isolated_data_dir: Path) -> None:
        content = "\n".join(f"Line {i}" for i in range(30))
        context_store.load("slice-ctx", content=content)
        chunker.chunk_context("slice-ctx", strategy="lines", chunk_size=10)

        result = chunker.peek_chunk("slice-ctx", chunk_index=0, start=2, end=4)
        lines = result["content"].split("\n")
        assert len(lines) == 3

    def test_peek_out_of_range(self, isolated_data_dir: Path) -> None:
        content = "Short content"
        context_store.load("short-ctx", content=content)
        chunker.chunk_context("short-ctx", strategy="lines", chunk_size=10)

        with pytest.raises(ValueError, match="out of range"):
            chunker.peek_chunk("short-ctx", chunk_index=99)

    def test_peek_no_chunks(self, isolated_data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No chunks found"):
            chunker.peek_chunk("no-chunks", chunk_index=0)
