# MemCP Architecture

## System Overview

MemCP follows a 3-layer delegation pattern: `server.py` defines MCP tool endpoints, `tools/*.py` handles JSON serialization, and `core/*.py` contains the business logic.

```mermaid
graph TB
    CC[Claude Code] -->|MCP Protocol| S[MemCP Server<br/>FastMCP]
    S --> M[Memory System]
    S --> C[Context Store]
    S --> SR[Search Engine]
    S --> G[Graph Memory]
    S --> R[Retention]
    S --> P[Project/Sessions]

    M -->|SQLite| GDB[(graph.db)]

    C --> CF[contexts/]
    C --> CH[chunks/]

    SR -->|stdlib| KW[Keyword]
    SR -->|bm25s| BM[BM25]
    SR -->|rapidfuzz| FZ[Fuzzy]
    SR -->|model2vec/fastembed| SE[Semantic]
    SR --> HY[Hybrid Fusion]

    G --> GDB
    G -->|Semantic| SE2[Similar content]
    G -->|Temporal| TE[Close in time]
    G -->|Causal| CA[Cause-Effect]
    G -->|Entity| EN[Shared entities]

    R --> AR[archive/]
    P --> SS[sessions.json]
    P --> ST[state.json]

    H[Hooks] -->|PreCompact| PS[Save before /compact]
    H -->|Notification| PR[Progressive reminders]
    H -->|PostToolUse| RC[Reset counter]
```

## Data Flow: Remember

When Claude calls `memcp_remember()`, the insight flows through:

```mermaid
flowchart LR
    A[memcp_remember] --> B[Validate + generate ID]
    B --> C[Insert node in graph.db]
    C --> D[Auto-generate edges]
    D --> D1[Temporal edges]
    D --> D2[Entity edges]
    D --> D3[Semantic edges]
    D --> D4[Causal edges]
```

1. `server.py:memcp_remember()` parses parameters
2. `core/memory.py:remember()` validates, generates an 8-char ID, computes `token_count` and `effective_importance`
3. `core/graph.py:GraphMemory.store()` inserts the node into SQLite and auto-generates 4 edge types:
   - **Temporal**: links to insights created within 30 minutes (same project)
   - **Entity**: links to insights sharing extracted entities (files, modules, URLs, CamelCase identifiers)
   - **Semantic**: links to top-3 most similar insights by keyword overlap (or cosine similarity if embeddings installed)
   - **Causal**: detects "because"/"therefore"/"due to" patterns and links to referenced insights

## Data Flow: Recall

```mermaid
flowchart LR
    A[memcp_recall] --> B{Graph available?}
    B -->|Yes| D[Detect intent]
    D -->|why| E[Boost causal edges]
    D -->|when| F[Boost temporal edges]
    D -->|what| G[Boost semantic edges]
    D -->|who/which| H[Boost entity edges]
    D -->|default| I[Hybrid traversal]
    E & F & G & H & I --> J[Rank + return results]
    J --> K{max_tokens?}
    K -->|Yes| L[Apply token budget]
    K -->|No| M[Return all matches]
```

Intent detection examines the query prefix:
- `"why..."` or `"reason"` or `"cause"` → emphasizes **causal** edges
- `"when..."` or `"timeline"` → emphasizes **temporal** edges
- `"who..."` or `"which..."` → emphasizes **entity** edges
- Default → emphasizes **semantic** edges

Ranking uses a weighted formula: `keyword_score * 0.7 + edge_boost * 0.3`.

## Search Tier Stack

```mermaid
flowchart TD
    subgraph "Search Tiers"
        direction TB
        K1[Keyword Search<br/>stdlib - always available] --> K2[BM25 Search<br/>bm25s - pip install memcp search]
        K2 --> K3[Fuzzy Search<br/>rapidfuzz - pip install memcp fuzzy]
        K3 --> K4[Semantic Search<br/>model2vec/fastembed - pip install memcp semantic]
        K4 --> K5[Hybrid Fusion<br/>alpha * semantic + 1-alpha * BM25]
    end

    Q[memcp_search query] --> AUTO{Auto-select<br/>best available}
    AUTO -->|all installed| K5
    AUTO -->|no semantic| K2
    AUTO -->|no bm25s| K1
```

`search()` auto-selects: hybrid > bm25 > keyword. Each tier gracefully degrades if its dependencies aren't installed.

## MAGMA 4-Graph

```mermaid
graph LR
    subgraph "MAGMA 4-Graph"
        N1((Insight A)) ---|semantic| N2((Insight B))
        N1 -->|causal| N3((Insight C))
        N2 ---|entity: SQLite| N3
        N1 ---|temporal| N4((Insight D))
        N3 ---|temporal| N4
    end
```

All four edge types share the same node set (insights) and are stored in a single SQLite `edges` table with an `edge_type` column. Edges are bidirectional for semantic/temporal/entity and directional for causal (cause → effect).

## Auto-Save Hook Sequence

```mermaid
sequenceDiagram
    participant U as User
    participant CC as Claude Code
    participant H as Hook
    participant M as MemCP

    Note over CC: Context filling up...
    CC->>CC: Turn 30+, context >= 55%
    H->>CC: ACTION REQUIRED: save context now
    CC->>M: memcp_remember(decisions...)
    M->>H: PostToolUse triggers
    H->>H: Reset turn counter

    Note over U: Later...
    U->>CC: /compact
    H->>CC: COMPACT DETECTED - SAVE REQUIRED
    CC->>M: memcp_load_context(session summary)
    CC->>M: memcp_remember(remaining insights)
    Note over CC: Context compacted safely
```

## RLM Map-Reduce Pipeline

```mermaid
sequenceDiagram
    participant CC as Claude Code Main
    participant M1 as memcp-mapper 1
    participant M2 as memcp-mapper 2
    participant M3 as memcp-mapper 3
    participant S as memcp-synthesizer
    participant MCP as MemCP Server

    CC->>MCP: memcp_chunk_context("doc", "auto")
    MCP-->>CC: 3 chunks created

    par MAP Phase - Haiku - parallel
        CC->>M1: chunk 0 + question
        M1->>MCP: memcp_peek_chunk("doc", 0)
        M1-->>CC: FINDINGS from chunk 0
    and
        CC->>M2: chunk 1 + question
        M2->>MCP: memcp_peek_chunk("doc", 1)
        M2-->>CC: FINDINGS from chunk 1
    and
        CC->>M3: chunk 2 + question
        M3->>MCP: memcp_peek_chunk("doc", 2)
        M3-->>CC: FINDINGS from chunk 2
    end

    Note over CC: REDUCE Phase - Sonnet
    CC->>S: question + all mapper outputs
    S->>MCP: memcp_recall("related insights")
    S->>MCP: memcp_related(insight_id)
    S->>MCP: memcp_remember(synthesis)
    S-->>CC: Synthesized answer + sources + confidence
```

## 3-Layer Delegation Pattern

```
server.py          # @mcp.tool() decorators — parameter parsing, JSON response
  ↓
tools/*.py         # Tool logic — orchestrate core calls, format JSON output
  ↓
core/*.py          # Business logic — returns plain dicts, no JSON serialization
```

| Layer | Example | Responsibility |
|-------|---------|----------------|
| `server.py` | `memcp_remember(content, category, ...)` | Define MCP tool, parse string params, call tool layer |
| `tools/retention_tools.py` | `do_retention_preview(archive_days, ...)` | Orchestrate core calls, format JSON response string |
| `core/retention.py` | `retention_preview(archive_days, ...)` | Pure logic, returns dict |

## Template Deployment

MemCP separates source templates from deployed configuration. The `templates/` directory contains the canonical versions of Claude Code configuration files. The installer (`scripts/install.sh`) deploys these to their target locations at install time.

```
hooks/snippets/
└── settings.json                   # Hook registration → merged into ~/.claude/settings.json

agents/                             # RLM sub-agent definitions → ~/.claude/agents/
├── memcp-analyzer.md               # Peek → identify → load → analyze (Haiku)
├── memcp-mapper.md                 # MAP phase (Haiku, parallel)
├── memcp-synthesizer.md            # REDUCE phase (Sonnet)
└── memcp-entity-extractor.md       # LLM entity extraction (Haiku)

templates/                          # Source (tracked in git)
└── CLAUDE.md                       # Session instructions → deployed to project root

~/.claude/                          # Deployed (user-level, global)
├── settings.json                   # ← hooks merged from hooks/snippets/settings.json
└── agents/                         # ← cp agents/memcp-*.md
    └── memcp-*.md

<project>/CLAUDE.md                 # ← cp templates/CLAUDE.md (project-level)
```

Sub-agent files use Claude Code frontmatter with:
- `tools` — comma-separated allowlist of MCP tools (e.g., `mcp__memcp__memcp_peek_chunk`)
- `mcpServers` — references the `memcp` MCP server
- `model` — Haiku for map/extract, Sonnet for synthesis
- `maxTurns` — limits agent execution length

## Data Directory Layout

```
~/.memcp/
  memory.json              # Phase 1 JSON backend (migrated to graph.db)
  graph.db                 # SQLite — MAGMA 4-graph (nodes + edges tables)
  state.json               # Turn counter, current project/session
  sessions.json            # Session registry
  contexts/                # Named context variables
    {name}/
      content.md           # Raw content
      meta.json            # Metadata (type, size, tokens, hash, access_count)
  chunks/                  # Chunked contexts
    {context_name}/
      index.json           # Chunk index (strategy, count, chunk metadata)
      0000.md              # Chunk files
      0001.md
      ...
  cache/                   # Embedding cache
    insight_embeddings.npz # Vectors for graph insights
  archive/                 # Retention archive
    contexts/              # Compressed archived contexts
      {name}/
        content.md.gz      # gzip-compressed content
        meta.json           # Original meta + archived_at
    insights.json          # Archived insights array
    purge_log.json         # Audit trail for purged items
```

## Configuration

All configuration is via environment variables (12-factor):

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMCP_DATA_DIR` | `~/.memcp` | Data directory path |
| `MEMCP_MAX_MEMORY_MB` | `2048` | Max memory usage |
| `MEMCP_MAX_INSIGHTS` | `10000` | Max insight count before auto-pruning |
| `MEMCP_MAX_CONTEXT_SIZE_MB` | `10` | Max size per context |
| `MEMCP_IMPORTANCE_DECAY_DAYS` | `30` | Half-life for importance decay |
| `MEMCP_RETENTION_ARCHIVE_DAYS` | `30` | Days before archiving stale items |
| `MEMCP_RETENTION_PURGE_DAYS` | `180` | Days before purging archived items |
| `MEMCP_EMBEDDING_PROVIDER` | `auto` | `model2vec`, `fastembed`, or `auto` |
| `MEMCP_EMBEDDING_MODEL` | (default per provider) | Custom model name |
| `MEMCP_SEARCH_ALPHA` | `0.6` | Hybrid search weight (0=BM25 only, 1=semantic only) |

## Technology Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Framework | FastMCP | Standard `@mcp.tool()` decorator pattern |
| Storage | SQLite (graph) + Filesystem (contexts) | ACID graph + human-readable files |
| Data dir | `~/.memcp/` | Global, persists across projects |
| Config | Env vars via dataclass | 12-factor, works in local and Docker |
| Safety | Atomic writes + flock + input validation | Crash-safe, concurrent-safe |
| Search | Tiered: keyword → BM25 → semantic → hybrid | Zero deps minimum, optional upgrades |

Core deps: `mcp>=1.0.0`, `pydantic>=2.0.0` (2 packages).

For detailed rationale behind each architectural decision, see the [Architecture Decision Records](adr/).
