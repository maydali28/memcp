"""MemCP MCP Server — persistent memory tools for Claude Code.

Phase 1: 5 tools (ping, remember, recall, forget, status).
Phase 2: +9 tools (context load/inspect/get/chunk/peek/filter/list/clear, search).
Phase 3: +2 tools (related, graph_stats).
Phase 6: +3 tools (retention_preview, retention_run, restore).
Phase 7: +2 tools (projects, sessions).
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from memcp.core.memory import (
    forget,
    memory_status,
    recall,
    remember,
)
from memcp.tools.context_tools import (
    do_chunk_context,
    do_clear_context,
    do_filter_context,
    do_list_contexts,
    do_peek_chunk,
    get_context,
    inspect_context,
    load_context,
)
from memcp.tools.graph_tools import do_graph_stats, do_related
from memcp.tools.project_tools import do_projects, do_sessions
from memcp.tools.retention_tools import do_restore, do_retention_preview, do_retention_run
from memcp.tools.search_tools import do_search

mcp = FastMCP("MemCP")


# ── Phase 1: Memory Tools ──────────────────────────────────────────────


@mcp.tool()
def memcp_ping() -> str:
    """Health check. Returns server status and memory statistics."""
    status = memory_status()
    return json.dumps(
        {
            "status": "ok",
            "server": "MemCP",
            "version": "0.1.0",
            "memory": status,
        },
        indent=2,
        default=str,
    )


@mcp.tool()
def memcp_remember(
    content: str,
    category: str = "general",
    importance: str = "medium",
    tags: str = "",
    summary: str = "",
    entities: str = "",
    project: str = "",
    session: str = "",
) -> str:
    """Save an important insight to persistent memory.

    Use this to remember key decisions, facts, user preferences, or technical
    findings that should be preserved across conversations.

    Args:
        content: The insight or fact to remember (be concise but complete)
        category: Type — decision, fact, preference, finding, todo, general
        importance: Priority — low, medium, high, critical
        tags: Comma-separated keywords for retrieval (e.g., "api,auth,v2")
        summary: Optional one-line summary
        entities: Optional comma-separated entities mentioned
        project: Optional project name
        session: Optional session ID
    """
    try:
        result = remember(
            content=content,
            category=category,
            importance=importance,
            tags=tags,
            summary=summary,
            entities=entities,
            project=project,
            session=session,
        )

        if result.get("_duplicate"):
            return json.dumps(
                {
                    "status": "duplicate",
                    "message": "This insight already exists in memory.",
                    "existing_id": result["id"],
                },
                indent=2,
                default=str,
            )

        response = {
            "status": "saved",
            "id": result["id"],
            "category": result["category"],
            "importance": result["importance"],
            "token_count": result["token_count"],
            "tags": result["tags"],
        }
        if result.get("_pruned"):
            response["pruned"] = result["_pruned"]
            response["message"] = (
                f"Saved. Auto-pruned {result['_pruned']}"
                " low-importance insights to stay within limits."
            )

        return json.dumps(response, indent=2, default=str)
    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=2)


@mcp.tool()
def memcp_recall(
    query: str = "",
    category: str = "",
    importance: str = "",
    limit: int = 10,
    max_tokens: int = 0,
    project: str = "",
    session: str = "",
    scope: str = "project",
) -> str:
    """Retrieve insights from memory.

    Use this to find previously stored knowledge — decisions, preferences,
    technical findings. Call at session start to load relevant context.

    Args:
        query: Search term (searches content, tags, and summary)
        category: Filter by type
        importance: Filter by priority
        limit: Max results (default 10)
        max_tokens: Token budget — returns results until budget is exhausted (0 = unlimited)
        project: Filter by project
        session: Filter by session ID
        scope: "project" (default), "session" (current only), "all" (cross-project)
    """
    try:
        results = recall(
            query=query,
            category=category,
            importance=importance,
            limit=limit,
            max_tokens=max_tokens,
            project=project,
            session=session,
            scope=scope,
        )

        if not results:
            return json.dumps(
                {
                    "status": "ok",
                    "count": 0,
                    "insights": [],
                    "message": "No matching insights found.",
                },
                indent=2,
                default=str,
            )

        insights = []
        for ins in results:
            insights.append(
                {
                    "id": ins["id"],
                    "content": ins["content"],
                    "category": ins.get("category", "general"),
                    "importance": ins.get("importance", "medium"),
                    "tags": ins.get("tags", []),
                    "project": ins.get("project", "default"),
                    "token_count": ins.get("token_count", 0),
                    "access_count": ins.get("access_count", 0),
                    "created_at": ins.get("created_at", ""),
                }
            )

        total_tokens = sum(i["token_count"] for i in insights)
        return json.dumps(
            {
                "status": "ok",
                "count": len(insights),
                "total_tokens": total_tokens,
                "insights": insights,
            },
            indent=2,
            default=str,
        )
    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=2)


@mcp.tool()
def memcp_forget(insight_id: str) -> str:
    """Remove an insight from memory by ID.

    Args:
        insight_id: The ID of the insight to remove
    """
    removed = forget(insight_id)
    if removed:
        return json.dumps(
            {"status": "removed", "id": insight_id},
            indent=2,
        )
    return json.dumps(
        {
            "status": "not_found",
            "message": f"No insight found with ID {insight_id!r}",
        },
        indent=2,
    )


@mcp.tool()
def memcp_status(project: str = "", session: str = "") -> str:
    """Current memory statistics — insight count, categories, importance distribution.

    Args:
        project: Filter stats by project
        session: Filter stats by session
    """
    status = memory_status(project=project, session=session)
    return json.dumps(
        {"status": "ok", **status},
        indent=2,
        default=str,
    )


# ── Phase 2: Context + Chunking + Search Tools ─────────────────────────


@mcp.tool()
def memcp_load_context(
    name: str,
    content: str = "",
    file_path: str = "",
    project: str = "",
) -> str:
    """Store content as a named context variable on disk.

    Use this to save large content (files, conversation history, code)
    that should be accessible without loading into the prompt.

    Args:
        name: Unique name for this context (alphanumeric, dots, hyphens, underscores)
        content: The content to store (provide content OR file_path, not both)
        file_path: Path to a file to load as context
        project: Optional project name
    """
    return load_context(name=name, content=content, file_path=file_path, project=project)


@mcp.tool()
def memcp_inspect_context(name: str) -> str:
    """Inspect a stored context — metadata and preview without loading full content.

    Use this to check a context's type, size, and token count before deciding
    whether to load it into the prompt.

    Args:
        name: Context name to inspect
    """
    return inspect_context(name=name)


@mcp.tool()
def memcp_get_context(name: str, start: int = 0, end: int = 0) -> str:
    """Read a stored context's content or a line range.

    Args:
        name: Context name
        start: Start line (1-indexed, 0 = from beginning)
        end: End line (1-indexed, inclusive, 0 = to end)
    """
    return get_context(name=name, start=start, end=end)


@mcp.tool()
def memcp_chunk_context(
    name: str,
    strategy: str = "auto",
    chunk_size: int = 0,
    overlap: int = 0,
) -> str:
    """Split a stored context into navigable numbered chunks.

    Args:
        name: Context name (must already be loaded)
        strategy: Splitting strategy — auto, lines, paragraphs, headings, chars, regex
        chunk_size: Size per chunk (lines for 'lines', chars for 'chars', tokens for 'paragraphs')
        overlap: Overlap between chunks (lines or chars)
    """
    return do_chunk_context(name=name, strategy=strategy, chunk_size=chunk_size, overlap=overlap)


@mcp.tool()
def memcp_peek_chunk(
    context_name: str,
    chunk_index: int,
    start: int = 0,
    end: int = 0,
) -> str:
    """Read a specific chunk from a chunked context.

    Args:
        context_name: Context name
        chunk_index: Chunk number (0-indexed)
        start: Start line within chunk (1-indexed, 0 = from beginning)
        end: End line within chunk (1-indexed, inclusive, 0 = to end)
    """
    return do_peek_chunk(context_name=context_name, chunk_index=chunk_index, start=start, end=end)


@mcp.tool()
def memcp_filter_context(name: str, pattern: str, invert: bool = False) -> str:
    """Filter context content by regex pattern.

    Returns only lines matching (or not matching) the pattern.

    Args:
        name: Context name
        pattern: Regex pattern to match lines
        invert: If True, return lines that DON'T match the pattern
    """
    return do_filter_context(name=name, pattern=pattern, invert=invert)


@mcp.tool()
def memcp_list_contexts(project: str = "") -> str:
    """List all stored context variables.

    Args:
        project: Filter by project name (empty = all projects)
    """
    return do_list_contexts(project=project)


@mcp.tool()
def memcp_clear_context(name: str) -> str:
    """Delete a stored context and its chunks.

    Args:
        name: Context name to delete
    """
    return do_clear_context(name=name)


@mcp.tool()
def memcp_search(
    query: str,
    limit: int = 10,
    source: str = "all",
    max_tokens: int = 0,
    project: str = "",
    scope: str = "project",
) -> str:
    """Search across memory insights and context chunks.

    Auto-selects the best available search method (BM25 > keyword).
    Install optional packages for better search: pip install memcp[search]

    Args:
        query: Search query
        limit: Max results (default 10)
        source: Where to search — "all" (default), "memory", "contexts"
        max_tokens: Token budget (0 = unlimited)
        project: Filter by project
        scope: "project" (default), "session", "all"
    """
    return do_search(
        query=query,
        limit=limit,
        source=source,
        max_tokens=max_tokens,
        project=project,
        scope=scope,
    )


# ── Phase 3: Graph Memory Tools ───────────────────────────────────────


@mcp.tool()
def memcp_related(
    insight_id: str,
    edge_type: str = "",
    depth: int = 1,
) -> str:
    """Traverse graph from an insight — find connected knowledge.

    Discovers insights related via semantic similarity, temporal proximity,
    causal chains, or shared entities.

    Args:
        insight_id: The ID of the insight to start from
        edge_type: Filter by edge type — semantic, temporal, causal, entity (empty = all)
        depth: How many hops to traverse (default 1)
    """
    return do_related(insight_id=insight_id, edge_type=edge_type, depth=depth)


@mcp.tool()
def memcp_graph_stats(project: str = "") -> str:
    """Graph statistics — node count, edge counts by type, top entities.

    Shows how knowledge is connected in the graph.

    Args:
        project: Filter by project (empty = all projects)
    """
    return do_graph_stats(project=project)


# ── Phase 6: Retention Lifecycle Tools ─────────────────────────────────


@mcp.tool()
def memcp_retention_preview(archive_days: int = 0, purge_days: int = 0) -> str:
    """Preview what would be archived or purged — dry-run, no changes made.

    Shows candidates for archiving (stale, low-access items) and purging
    (archived items past retention period). Items with high importance,
    frequent access, or protected tags are immune from archiving.

    Args:
        archive_days: Override archive threshold (default from env, 30 days)
        purge_days: Override purge threshold (default from env, 180 days)
    """
    return do_retention_preview(archive_days=archive_days, purge_days=purge_days)


@mcp.tool()
def memcp_retention_run(archive: bool = True, purge: bool = False) -> str:
    """Execute retention actions — archive old items, optionally purge.

    Archiving compresses and moves stale items to the archive directory.
    Purging permanently deletes archived items past the purge threshold
    and logs metadata to purge_log.json for audit.

    Args:
        archive: Archive eligible items (default True)
        purge: Purge archived items past retention period (default False)
    """
    return do_retention_run(archive=archive, purge=purge)


@mcp.tool()
def memcp_restore(name: str, item_type: str = "auto") -> str:
    """Restore an archived context or insight back to active.

    Decompresses archived contexts and re-inserts archived insights
    into the knowledge graph.

    Args:
        name: Context name or insight ID to restore
        item_type: "context", "insight", or "auto" (tries both)
    """
    return do_restore(name=name, item_type=item_type)


# ── Phase 7: Multi-Project & Session Tools ─────────────────────────


@mcp.tool()
def memcp_projects() -> str:
    """List all projects with insight/context/session counts.

    Shows every project that has data in MemCP.
    """
    return do_projects()


@mcp.tool()
def memcp_sessions(project: str = "", limit: int = 20) -> str:
    """List sessions, optionally filtered by project.

    Args:
        project: Filter by project (empty = all)
        limit: Max sessions to return (default 20)
    """
    return do_sessions(project=project, limit=limit)


def _init_session() -> None:
    """Detect project and register a new session on server startup.

    Ensures state.json has current_project/current_session and
    sessions.json tracks the session lifecycle.
    """
    from memcp.core.project import detect_project, generate_session_id, register_session

    project = detect_project()
    session_id = generate_session_id(project)
    register_session(session_id, project)


def main() -> None:
    """Run the MemCP MCP server."""
    _init_session()
    mcp.run()
