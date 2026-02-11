"""Context store — named content variables on disk.

Contexts are large pieces of content (files, conversation history, code)
stored as named variables that can be inspected, sliced, and chunked
without loading into the prompt.

Storage layout:
    ~/.memcp/contexts/{name}/
        content.md     # raw content
        meta.json      # metadata (name, type, size, tokens, hash, etc.)
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memcp.config import get_config
from memcp.core.fileutil import (
    atomic_write_json,
    atomic_write_text,
    content_hash,
    estimate_tokens,
    locked_read_json,
    safe_name,
)
from memcp.core.project import get_current_project, get_current_session

_TYPE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".json": "json",
    ".csv": "csv",
    ".md": "markdown",
    ".markdown": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".txt": "text",
}


def _detect_type(content: str, source: str = "") -> str:
    """Detect content type from source path or content heuristics."""
    if source:
        ext = Path(source).suffix.lower()
        if ext in _TYPE_EXTENSIONS:
            return _TYPE_EXTENSIONS[ext]

    # Heuristic detection from content
    stripped = content.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if stripped.startswith("# ") or "\n## " in content:
        return "markdown"
    if "def " in content and "import " in content:
        return "python"

    return "text"


def _context_dir(name: str) -> Path:
    """Get the directory for a named context."""
    safe_name(name)  # validates
    config = get_config()
    return config.contexts_dir / name


def load(
    name: str,
    content: str = "",
    file_path: str = "",
    project: str = "",
) -> dict[str, Any]:
    """Save content as a named context variable.

    Either `content` or `file_path` must be provided.
    Returns metadata dict.
    """
    safe_name(name)

    if not content and not file_path:
        raise ValueError("Either content or file_path must be provided")

    if file_path:
        fp = Path(file_path).expanduser().resolve()
        if not fp.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        config = get_config()
        max_bytes = config.max_context_size_mb * 1024 * 1024
        size = fp.stat().st_size
        if size > max_bytes:
            raise ValueError(f"File too large: {size} bytes (max {config.max_context_size_mb}MB)")
        content = fp.read_text(encoding="utf-8")
        source = str(fp)
    else:
        source = ""

    if not content.strip():
        raise ValueError("Content cannot be empty")

    config = get_config()
    max_bytes = config.max_context_size_mb * 1024 * 1024
    if len(content.encode("utf-8")) > max_bytes:
        raise ValueError(f"Content too large (max {config.max_context_size_mb}MB)")

    ctx_dir = _context_dir(name)
    content_path = ctx_dir / "content.md"
    meta_path = ctx_dir / "meta.json"

    # Check for duplicate content
    c_hash = content_hash(content)
    existing_meta = locked_read_json(meta_path)
    if existing_meta and existing_meta.get("hash") == c_hash:
        return {**existing_meta, "_duplicate": True}

    now = datetime.now(timezone.utc).isoformat()
    lines = content.split("\n")
    content_type = _detect_type(content, source)

    meta = {
        "name": name,
        "source": source,
        "type": content_type,
        "size_bytes": len(content.encode("utf-8")),
        "line_count": len(lines),
        "token_estimate": estimate_tokens(content),
        "hash": c_hash,
        "project": project or get_current_project(),
        "session": get_current_session(),
        "access_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    ctx_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(content_path, content)
    atomic_write_json(meta_path, meta)

    return meta


def inspect(name: str, preview_lines: int = 5) -> dict[str, Any]:
    """Get metadata and a preview without loading full content.

    Returns metadata dict with a 'preview' field.
    """
    safe_name(name)
    ctx_dir = _context_dir(name)
    meta_path = ctx_dir / "meta.json"
    content_path = ctx_dir / "content.md"

    meta = locked_read_json(meta_path)
    if meta is None:
        raise FileNotFoundError(f"Context {name!r} not found")

    # Read first N lines for preview
    preview = ""
    if content_path.exists():
        with open(content_path, encoding="utf-8") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= preview_lines:
                    break
                lines.append(line.rstrip("\n"))
            preview = "\n".join(lines)

    # Update access count
    meta["access_count"] = meta.get("access_count", 0) + 1
    meta["last_accessed_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(meta_path, meta)

    return {**meta, "preview": preview}


def get(name: str, start: int = 0, end: int = 0) -> dict[str, Any]:
    """Read context content or a line range.

    Args:
        name: Context name
        start: Start line (1-indexed, 0 = from beginning)
        end: End line (1-indexed, inclusive, 0 = to end)

    Returns dict with 'content', 'lines_returned', and metadata.
    """
    safe_name(name)
    ctx_dir = _context_dir(name)
    meta_path = ctx_dir / "meta.json"
    content_path = ctx_dir / "content.md"

    meta = locked_read_json(meta_path)
    if meta is None:
        raise FileNotFoundError(f"Context {name!r} not found")

    if not content_path.exists():
        raise FileNotFoundError(f"Context content for {name!r} missing")

    full_content = content_path.read_text(encoding="utf-8")

    if start > 0 or end > 0:
        lines = full_content.split("\n")
        s = max(0, start - 1) if start > 0 else 0
        e = end if end > 0 else len(lines)
        sliced = lines[s:e]
        result_content = "\n".join(sliced)
        lines_returned = len(sliced)
    else:
        result_content = full_content
        lines_returned = meta.get("line_count", len(full_content.split("\n")))

    # Update access count
    meta["access_count"] = meta.get("access_count", 0) + 1
    meta["last_accessed_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(meta_path, meta)

    return {
        "name": name,
        "content": result_content,
        "lines_returned": lines_returned,
        "total_lines": meta.get("line_count", 0),
        "token_estimate": estimate_tokens(result_content),
    }


def list_contexts(project: str = "") -> list[dict[str, Any]]:
    """List all stored contexts with their metadata."""
    config = get_config()
    contexts_dir = config.contexts_dir

    if not contexts_dir.exists():
        return []

    results = []
    for ctx_dir in sorted(contexts_dir.iterdir()):
        if not ctx_dir.is_dir():
            continue
        meta_path = ctx_dir / "meta.json"
        meta = locked_read_json(meta_path)
        if meta is None:
            continue
        if project and meta.get("project", "default") != project:
            continue
        results.append(meta)

    return results


def delete(name: str) -> bool:
    """Delete a context and its chunks. Returns True if found and removed."""
    safe_name(name)
    ctx_dir = _context_dir(name)

    if not ctx_dir.exists():
        return False

    shutil.rmtree(ctx_dir)

    # Also remove chunks if they exist
    config = get_config()
    chunks_dir = config.chunks_dir / name
    if chunks_dir.exists():
        shutil.rmtree(chunks_dir)

    return True


def filter_context(name: str, pattern: str, invert: bool = False) -> dict[str, Any]:
    """Filter context content by regex pattern.

    Args:
        name: Context name
        pattern: Regex pattern to match lines
        invert: If True, return lines that DON'T match

    Returns dict with filtered content.
    """
    safe_name(name)
    ctx_dir = _context_dir(name)
    content_path = ctx_dir / "content.md"
    meta_path = ctx_dir / "meta.json"

    meta = locked_read_json(meta_path)
    if meta is None:
        raise FileNotFoundError(f"Context {name!r} not found")

    if not content_path.exists():
        raise FileNotFoundError(f"Context content for {name!r} missing")

    content = content_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    compiled = re.compile(pattern)
    if invert:
        matched = [line for line in lines if not compiled.search(line)]
    else:
        matched = [line for line in lines if compiled.search(line)]

    result_content = "\n".join(matched)
    return {
        "name": name,
        "pattern": pattern,
        "invert": invert,
        "content": result_content,
        "lines_matched": len(matched),
        "total_lines": len(lines),
        "token_estimate": estimate_tokens(result_content),
    }
