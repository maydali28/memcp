"""Project detection and session management.

Phase 7: Auto-detect project from git root, track sessions, enable
cross-project / cross-session data isolation.

Session index lives at ~/.memcp/sessions.json.
Active project/session are stored in ~/.memcp/state.json (alongside turn counter).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memcp.config import get_config
from memcp.core.fileutil import atomic_write_json, locked_read_json

# ── Project Detection ─────────────────────────────────────────────────


def detect_project(cwd: str = "") -> str:
    """Auto-detect project from environment.

    Priority:
        1. MEMCP_PROJECT env var
        2. Git repo name (walk up from cwd to find .git, use dirname)
        3. cwd basename
        4. "default"
    """
    # 1. Env var
    env_project = os.environ.get("MEMCP_PROJECT", "").strip()
    if env_project:
        return env_project

    # 2. Git repo name
    start = Path(cwd).resolve() if cwd else Path.cwd()
    git_name = _find_git_project(start)
    if git_name:
        return git_name

    # 3. cwd basename
    basename = start.name
    if basename and basename != "/":
        return basename

    # 4. Fallback
    return "default"


def _find_git_project(start: Path) -> str:
    """Walk up from *start* looking for .git directory.

    Returns the containing directory name, or "" if not found.
    """
    current = start
    for _ in range(50):  # Safety limit
        if (current / ".git").exists():
            return current.name
        parent = current.parent
        if parent == current:
            break
        current = parent
    return ""


# ── Session ID Generation ─────────────────────────────────────────────


def generate_session_id(project: str) -> str:
    """Generate session ID: ``{project}_{date}_{seq}``.

    Seq auto-increments per day per project from sessions.json.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sessions = _load_sessions()

    # Count existing sessions for this project+date
    prefix = f"{project}_{today}_"
    existing = [sid for sid in sessions.get("sessions", {}) if sid.startswith(prefix)]
    seq = len(existing) + 1

    return f"{project}_{today}_{seq:03d}"


# ── Session Registration ──────────────────────────────────────────────


def register_session(session_id: str, project: str, **kwargs: Any) -> dict[str, Any]:
    """Register a new session in sessions.json.

    Sets started_at, project, insight_count=0, context_count=0.
    Updates state.json with current_project and current_session.
    """
    now = datetime.now(timezone.utc).isoformat()

    session_entry: dict[str, Any] = {
        "project": project,
        "started_at": now,
        "last_active_at": now,
        "insight_count": 0,
        "context_count": 0,
        "summary": kwargs.get("summary", ""),
    }

    sessions = _load_sessions()
    sessions["sessions"][session_id] = session_entry
    sessions["current_session"] = session_id
    _save_sessions(sessions)

    # Update state.json
    _set_state({"current_project": project, "current_session": session_id})

    return {"session_id": session_id, **session_entry}


# ── Session Listing ───────────────────────────────────────────────────


def list_sessions(
    project: str = "",
    domain: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List sessions sorted by last_active_at (most recent first).

    Optional project filter. The *domain* parameter is accepted for
    compatibility but currently unused.

    ``insight_count`` and ``context_count`` are computed dynamically from the
    graph DB and context store so they stay accurate across sessions.
    """
    sessions = _load_sessions()
    items: list[dict[str, Any]] = []

    # Compute per-session insight counts from graph DB
    insight_counts = _count_insights_per_session()
    # Compute per-session context counts from context store
    context_counts = _count_contexts_per_session()

    for sid, entry in sessions.get("sessions", {}).items():
        if project and entry.get("project") != project:
            continue
        enriched = {"session_id": sid, **entry}
        enriched["insight_count"] = insight_counts.get(sid, 0)
        enriched["context_count"] = context_counts.get(sid, 0)
        items.append(enriched)

    items.sort(key=lambda x: x.get("last_active_at", ""), reverse=True)
    return items[:limit]


# ── Current Session / Project ─────────────────────────────────────────


def get_current_session() -> str:
    """Get current session ID from state.json. Returns '' if unset."""
    state = _get_state()
    return state.get("current_session", "")


def set_current_session(session_id: str) -> None:
    """Set current session in state.json."""
    _set_state({"current_session": session_id})


def get_current_project() -> str:
    """Get current project from state.json, or auto-detect.

    Returns the project name (never empty — falls back to "default").
    """
    state = _get_state()
    project = state.get("current_project", "")
    if project:
        return project
    return detect_project()


# ── Project Listing ───────────────────────────────────────────────────


def list_projects() -> list[dict[str, Any]]:
    """List all known projects with aggregate stats.

    Scans graph.db nodes (DISTINCT project), contexts meta.json (DISTINCT
    project), and sessions.json (DISTINCT project).

    Returns per project: name, insight_count, context_count, session_count,
    last_activity.
    """
    config = get_config()
    projects: dict[str, dict[str, Any]] = {}

    def _ensure(name: str) -> dict[str, Any]:
        if name not in projects:
            projects[name] = {
                "name": name,
                "insight_count": 0,
                "context_count": 0,
                "session_count": 0,
                "last_activity": "",
            }
        return projects[name]

    # 1a. Graph insights
    if config.graph_db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(config.graph_db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT project, COUNT(*) as cnt, MAX(created_at) as latest "
                "FROM nodes GROUP BY project"
            ).fetchall()
            for row in rows:
                proj = _ensure(row["project"])
                proj["insight_count"] = row["cnt"]
                if row["latest"] and row["latest"] > proj["last_activity"]:
                    proj["last_activity"] = row["latest"]
            conn.close()
        except Exception:
            pass

    # 1b. JSON fallback insights (Phase 1 backend, only if graph is not active)
    if not config.graph_db_path.exists() and config.memory_path.exists():
        try:
            memory = locked_read_json(config.memory_path)
            if memory and memory.get("insights"):
                for ins in memory["insights"]:
                    name = ins.get("project", "default")
                    proj = _ensure(name)
                    proj["insight_count"] += 1
                    created = ins.get("created_at", "")
                    if created and created > proj["last_activity"]:
                        proj["last_activity"] = created
        except Exception:
            pass

    # 2. Contexts
    if config.contexts_dir.exists():
        for ctx_dir in config.contexts_dir.iterdir():
            if not ctx_dir.is_dir():
                continue
            meta = locked_read_json(ctx_dir / "meta.json")
            if meta is None:
                continue
            name = meta.get("project", "default")
            proj = _ensure(name)
            proj["context_count"] += 1
            created = meta.get("created_at", "")
            if created and created > proj["last_activity"]:
                proj["last_activity"] = created

    # 3. Sessions
    sessions = _load_sessions()
    for _sid, entry in sessions.get("sessions", {}).items():
        name = entry.get("project", "default")
        proj = _ensure(name)
        proj["session_count"] += 1
        last = entry.get("last_active_at", "")
        if last and last > proj["last_activity"]:
            proj["last_activity"] = last

    result = list(projects.values())
    result.sort(key=lambda x: x.get("last_activity", ""), reverse=True)
    return result


# ── Internal Helpers ──────────────────────────────────────────────────


def _count_insights_per_session() -> dict[str, int]:
    """Count insights per session from the graph DB (or JSON fallback).

    Returns a mapping of session_id -> count.
    """
    config = get_config()
    counts: dict[str, int] = {}

    # Try graph DB first
    if config.graph_db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(config.graph_db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT session, COUNT(*) as cnt FROM nodes WHERE session != '' GROUP BY session"
            ).fetchall()
            for row in rows:
                counts[row["session"]] = row["cnt"]
            conn.close()
        except Exception:
            pass
        return counts

    # JSON fallback
    if config.memory_path.exists():
        try:
            data = locked_read_json(config.memory_path)
            if data and data.get("insights"):
                for ins in data["insights"]:
                    sid = ins.get("session", "")
                    if sid:
                        counts[sid] = counts.get(sid, 0) + 1
        except Exception:
            pass

    return counts


def _count_contexts_per_session() -> dict[str, int]:
    """Count contexts per session from context store metadata.

    Returns a mapping of session_id -> count.
    """
    config = get_config()
    counts: dict[str, int] = {}

    if config.contexts_dir.exists():
        for ctx_dir in config.contexts_dir.iterdir():
            if not ctx_dir.is_dir():
                continue
            meta = locked_read_json(ctx_dir / "meta.json")
            if meta is None:
                continue
            sid = meta.get("session", "")
            if sid:
                counts[sid] = counts.get(sid, 0) + 1

    return counts


def _load_sessions() -> dict[str, Any]:
    """Load sessions.json or return default structure."""
    config = get_config()
    data = locked_read_json(config.sessions_path)
    if data is None:
        return {"current_session": "", "sessions": {}}
    return data


def _save_sessions(data: dict[str, Any]) -> None:
    """Save sessions.json atomically."""
    config = get_config()
    atomic_write_json(config.sessions_path, data)


def _get_state() -> dict[str, Any]:
    """Read state.json."""
    config = get_config()
    data = locked_read_json(config.state_path)
    if data is None:
        return {}
    return data


def _set_state(updates: dict[str, Any]) -> None:
    """Merge-update fields in state.json atomically."""
    config = get_config()
    state = _get_state()
    state.update(updates)
    atomic_write_json(config.state_path, state)
