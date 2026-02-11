# MemCP — Instructions for Claude Code Sessions

## Session Startup

At the beginning of every session:
1. Call `memcp_recall(importance="critical")` to load all critical rules and decisions
2. Call `memcp_status()` to see memory statistics
3. If working on a specific project, call `memcp_recall(project="project-name", limit=20)` to load project context

## When to Save

Call `memcp_remember()` whenever you encounter:
- **Decisions** (`category="decision"`): Architecture choices, library selections, approach decisions
- **Facts** (`category="fact"`): API limits, configuration values, system constraints
- **Preferences** (`category="preference"`): User's coding style, formatting preferences, tool preferences
- **Findings** (`category="finding"`): Bug discoveries, performance insights, edge cases found
- **TODOs** (`category="todo"`): Tasks to complete later, follow-up items
- **General** (`category="general"`): Anything else worth remembering

## Importance Levels

- `critical` — Must never be forgotten (e.g., "Never push to main without PR")
- `high` — Important context (e.g., "Client requires WCAG 2.1 AA compliance")
- `medium` — Useful knowledge (e.g., "API rate limit is 100/min")
- `low` — Nice to have (e.g., "Tried approach X, didn't work well")

## Tags

Always add relevant tags for better retrieval:
```
memcp_remember("...", tags="api,auth,jwt")
```

## Tool Quick Reference

### Phase 1: Memory Tools
| Tool | Purpose |
|------|---------|
| `memcp_ping()` | Health check + memory stats |
| `memcp_remember(content, category, importance, tags)` | Save an insight (graph node + auto-edges) |
| `memcp_recall(query, category, importance, limit, max_tokens)` | Intent-aware graph retrieval |
| `memcp_forget(insight_id)` | Remove an insight + edges |
| `memcp_status(project, session)` | Memory statistics |

### Phase 2: Context + Chunking + Search Tools
| Tool | Purpose |
|------|---------|
| `memcp_load_context(name, content, file_path)` | Store content as named disk variable |
| `memcp_inspect_context(name)` | Metadata + preview without loading |
| `memcp_get_context(name, start, end)` | Read content or line slice |
| `memcp_chunk_context(name, strategy, chunk_size, overlap)` | Split into numbered chunks |
| `memcp_peek_chunk(context_name, chunk_index, start, end)` | Read a specific chunk |
| `memcp_filter_context(name, pattern, invert)` | Regex filter within context |
| `memcp_list_contexts(project)` | List all variables |
| `memcp_clear_context(name)` | Delete variable |
| `memcp_search(query, limit, source, max_tokens)` | Search across memory + contexts |

### Phase 3: Graph Memory Tools
| Tool | Purpose |
|------|---------|
| `memcp_related(insight_id, edge_type, depth)` | Traverse graph — find connected insights |
| `memcp_graph_stats(project)` | Graph statistics: nodes, edges, top entities |

### Phase 6: Retention Lifecycle Tools
| Tool | Purpose |
|------|---------|
| `memcp_retention_preview(archive_days, purge_days)` | Dry-run — show what would be archived/purged |
| `memcp_retention_run(archive, purge)` | Execute archive/purge actions |
| `memcp_restore(name, item_type)` | Restore archived context or insight |

### Phase 7: Multi-Project & Session Tools
| Tool | Purpose |
|------|---------|
| `memcp_projects()` | List all projects with insight/context/session counts |
| `memcp_sessions(project, limit)` | Browse sessions by project |

## RLM Sub-Agents

MemCP includes 4 Claude Code sub-agents that implement the RLM (Recursive Language Model) map-reduce pattern. They run as independent Claude sessions with their own context windows, so they don't consume your main context.

### Setup

Sub-agent templates live in `agents/` and are deployed to `~/.claude/agents/` (user-level) by the installer, making them available across all projects:

```bash
# Via installer (recommended)
bash scripts/install.sh    # Step 6 deploys agents

# Manual deployment
mkdir -p ~/.claude/agents
cp agents/memcp-*.md ~/.claude/agents/
```

Each agent uses proper Claude Code frontmatter (`tools`, `mcpServers`, `model`, `maxTurns`). They reference the `memcp` MCP server and restrict their tool access to only the MCP tools they need.

### Available Sub-Agents

| Sub-Agent | Model | Purpose |
|-----------|-------|---------|
| `memcp-analyzer` | Haiku | Single-chunk analysis using peek-identify-load-analyze |
| `memcp-mapper` | Haiku | MAP phase — process one chunk in parallel |
| `memcp-synthesizer` | Sonnet | REDUCE phase — combine mapper outputs into coherent answer |
| `memcp-entity-extractor` | Haiku | Extract entities and relationships from content |

### Pattern 1: Single-Chunk Analysis

When you need to answer a question about a stored context without loading it all:

1. `memcp_search(query)` — find which contexts are relevant
2. Launch `memcp-analyzer` with the context name and question
3. The analyzer follows the RLM pattern: inspect, identify, load only relevant sections, answer with citations

### Pattern 2: Map-Reduce (Large Context Analysis)

When analyzing a context too large for a single pass:

1. `memcp_chunk_context(name, strategy="auto")` — partition the context
2. Launch N `memcp-mapper` instances in **background** (one per chunk):
   - Each mapper gets: context_name, chunk_index, and the question
   - Mappers run on Haiku in parallel — cheap and fast
3. Collect all mapper outputs
4. Launch `memcp-synthesizer` in **foreground** with the question + all mapper outputs:
   - Synthesizer runs on Sonnet — better reasoning for combining results
   - Cross-references with `memcp_recall()` and `memcp_related()` for verification
   - May save new insights via `memcp_remember()` if synthesis produces novel findings

### Pattern 3: Entity Enrichment

After storing new content, enrich it with LLM-extracted entities:

1. Store content: `memcp_remember(content, ...)` or `memcp_load_context(name, content)`
2. Launch `memcp-entity-extractor` in background with the content
3. Collect extracted entities
4. Update the insight: `memcp_remember(content, entities="entity1,entity2,...")`

This creates richer entity edges in the MAGMA graph, improving future
`memcp_related()` and `memcp_recall()` results.

### When to Use Sub-Agents vs Direct Tools

**Use sub-agents when:**
- Analyzing large contexts (>4000 tokens) — avoid loading everything into main context
- Answering complex questions that need cross-referencing across chunks
- Processing multiple chunks in parallel for speed
- Extracting entities from lengthy content

**Use direct tools when:**
- Simple recall: `memcp_recall(query)` — fast, already optimized
- Saving a quick insight: `memcp_remember(content)` — one call
- Checking status: `memcp_status()`, `memcp_graph_stats()`
- Small context operations: inspect, peek, filter on known locations

## Auto-Save Hooks

Hooks are configured in `~/.claude/settings.json` and run automatically — you don't need to trigger them:

- **PreCompact**: Before `/compact`, you'll get a blocking message requiring you to save context first
- **Progressive reminders**: At 10+ turns (consider), 20+ (recommended), 30+ (action required) — only when context >= 55% full
- **Reset counter**: After `memcp_remember()` or `memcp_load_context()`, the turn counter resets

