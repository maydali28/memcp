# MemCP vs Alternatives

## Feature Comparison

| Feature | MemCP | rlm-claude | CLAUDE.md | Letta/MemGPT | mem0 | MAGMA |
|---------|-------|-----------|-----------|-------------|------|-------|
| MCP Native | Yes | Yes | No | No | No | No |
| Local-First | Yes | Yes | Yes | Optional | Cloud/hybrid | Optional |
| Storage | SQLite + Filesystem | JSON + Filesystem | Text file | Hierarchical + VectorDB | VectorDB | 4-Graph + VectorDB |
| Keyword Search | Yes (stdlib) | Yes | Manual | No | No | No |
| BM25 Search | Yes (bm25s) | Yes (bm25s) | No | No | No | No |
| Fuzzy Search | Yes (rapidfuzz) | Yes (thefuzz) | No | No | No | No |
| Semantic Search | Yes (model2vec/fastembed) | Yes (model2vec/fastembed) | No | Yes | Yes | Yes |
| Hybrid Search | Yes (BM25 + semantic) | Yes (BM25 + semantic) | No | Partial | No | Yes (RRF fusion) |
| Graph Memory | Yes (MAGMA 4-graph) | No | No | No | No | Yes (core) |
| Intent-Aware Recall | Yes (why/when/who/what) | No | No | No | No | Yes |
| Entity Extraction | Yes (regex + LLM) | Partial (filtering) | No | No | Unknown | Yes (LLM-based) |
| Causal Edges | Yes | No | No | No | No | Yes |
| Chunking/Navigation | Yes (6 strategies) | Yes (semantic + others) | Manual | No | No | No |
| Context Variables | Yes (named disk vars) | Yes (contexts) | No | Yes (memory blocks) | No | No |
| Auto-Save Hooks | Yes (PreCompact) | Yes (PreCompact) | No | Self-directed | Unknown | Yes (dual-stream) |
| Progressive Reminders | Yes (turn + context %) | Yes (turn + context %) | No | No | No | No |
| Concurrency Safety | Yes (flock + SQLite WAL) | Yes (flock + atomic) | No | Unknown | Unknown | Yes |
| Sub-Agents (RLM) | Yes (agents/ → ~/.claude/agents/) | Yes (skills) | No | Yes (agent) | Unknown | Yes (required) |
| Map-Reduce | Yes (mapper + synthesizer) | Yes (skills) | No | No | No | Partial |
| Multi-Project | Yes | Yes | Partial (per-dir) | Unknown | Unknown | Unknown |
| Multi-Session | Yes | Yes | No | Yes | Yes | Yes |
| Retention Lifecycle | Yes (3-zone) | Yes (3-zone) | Manual | Unknown | Unknown | Unknown |
| Open Source | Yes | Yes | N/A | Yes | Partial | Yes |
| Core Dependencies | 2 (mcp, pydantic) | 2 (mcp, pydantic) | 0 | Heavy | Heavy | Heavy |

## Key Differentiators

### MemCP vs rlm-claude

MemCP and rlm-claude share the same RLM-based approach (context-as-variable, tiered search). Key differences:

- **Graph memory**: MemCP adds MAGMA 4-graph (semantic, temporal, causal, entity edges) with intent-aware traversal. rlm-claude uses flat storage.
- **SQLite backend**: MemCP stores insights in SQLite with WAL mode, supporting ACID transactions and efficient queries. rlm-claude uses JSON files.
- **Sub-agents vs skills**: MemCP uses Claude Code custom sub-agents (defined in `agents/`, deployed to `~/.claude/agents/` by the installer) — independent sessions with their own context windows, proper frontmatter (`tools`, `mcpServers`, `model`). rlm-claude uses skills (prompt templates in the main session).
- **Maturity**: rlm-claude has more mature multi-project/session support from earlier development. MemCP rebuilds these features with graph integration.

### MemCP vs CLAUDE.md

CLAUDE.md is a static text file that Claude reads at session start. Limitations:

- **Manual**: You write and maintain the file yourself
- **Context-limited**: The entire file loads into the context window
- **No persistence**: Everything is lost on `/compact`
- **No search**: No way to query subsets of stored knowledge
- **No structure**: Free-form text, no categories or importance levels

MemCP automates memory management with hooks, provides structured search across 21 tools, and persists across sessions in SQLite + filesystem.

### MemCP vs Letta/MemGPT

Letta (formerly MemGPT) is designed for autonomous agents, not MCP-integrated coding assistants:

- **Infrastructure**: Letta requires a separate server, vector database, and agent runtime. MemCP is a single-process MCP server with SQLite.
- **Focus**: Letta targets general-purpose autonomous agents. MemCP is built specifically for Claude Code workflows.
- **Integration**: Letta has its own agent framework. MemCP integrates via MCP protocol, the standard for Claude Code extensions.
- **Dependencies**: Letta has heavy deps (embedding models, vector DB, agent framework). MemCP core requires only 2 packages.

### MemCP vs MAGMA

MAGMA (arXiv:2601.03236) defines the theoretical 4-graph architecture that MemCP implements:

- **Implementation**: MAGMA is a research paper describing a memory framework. MemCP is a working implementation adapted for Claude Code.
- **Entity extraction**: MAGMA requires a full LLM backbone for graph construction. MemCP uses lightweight regex (Phase 3) with optional LLM extraction via sub-agents (Phase 4).
- **Dual-stream write**: MAGMA's fast/slow path is adapted in MemCP: fast path = `memcp_remember()` with regex entities + auto-edges; slow path = background `memcp-entity-extractor` sub-agent for deeper extraction.
- **Scope**: MAGMA focuses on memory. MemCP adds context variables, chunking, search, retention lifecycle, hooks, and project/session management.

### MemCP vs mem0

mem0 is an embedding-only memory system:

- **Search**: mem0 uses pure vector similarity. MemCP's tiered search starts with keywords and progressively adds BM25, fuzzy, and semantic. Research shows BM25 outperforms pure embeddings on many retrieval tasks (Letta benchmark: filesystem 74.0% vs mem0 68.5%).
- **Graph**: mem0 has no graph structure. MemCP's MAGMA 4-graph enables intent-aware traversal ("why did we decide X?" follows causal edges).
- **Local-first**: mem0 is primarily cloud-hosted. MemCP is fully local with zero network requirements.
- **MCP**: mem0 doesn't integrate with Claude Code via MCP. MemCP is MCP-native.

## RLM Framework Compliance

MemCP implements the Recursive Language Model framework (arXiv:2512.24601):

| RLM Concept | MemCP Implementation |
|-------------|---------------------|
| Context-as-variable | `memcp_load_context()` + `memcp_inspect_context()` |
| Peeking | `memcp_peek_chunk()` + `memcp_get_context(start, end)` |
| Grepping | `memcp_filter_context(name, pattern)` |
| Partition | `memcp_chunk_context()` with 6 strategies |
| Sub-LLM calls | `memcp-mapper` sub-agent (Haiku, via `mcpServers: [memcp]`) |
| Map-reduce | Multiple `memcp-mapper` (parallel) + `memcp-synthesizer` |
| Verification | `memcp-synthesizer` cross-references with `memcp_recall` + `memcp_related` |
| Graph memory | MAGMA 4-graph in SQLite |

The key distinction from RAG: MemCP uses **active exploration** (model decides what to load) vs **passive retrieval** (fixed embed → search → top-K pipeline). Content stays on disk as named variables; the model navigates via tools.

## Quantitative Comparison (Benchmarks)

MemCP includes a [benchmark suite](../tests/benchmark/) with 77 benchmarks comparing native context-window-only operation against RLM-mode persistent memory. Key findings:

### Token Efficiency — Context Window Tokens Consumed

| Operation | Native (worst-case) | RLM | Advantage |
|-----------|-------------------|-----|-----------|
| Reload 500 prior insights | 9,380 tokens | 462 tokens | 20.3x less |
| Analyse a 50K-token document | 50,460 tokens | 231 tokens | 218.4x less |
| Cross-reference decisions | 1,861 tokens | 172 tokens | 10.8x less |
| Search across 5K insights | 91,705 tokens | 192 tokens | 477.6x less |

### Context Rot — Knowledge Retained After Compaction

| Event | Native | RLM |
|-------|--------|-----|
| Single `/compact` | ~5% | 100% |
| 3 cascading compactions | ~2% | 100% |
| Cross-session (session 1 → session 5) | 0% | 92% |
| Critical insights after 60 days | 0% | 100% |

### Context Window Pressure

| Metric | Native | RLM |
|--------|--------|-----|
| Window utilisation with 10 docs | 93.6% | 1.0% |
| Docs manageable in 128K window | 13 | 50 |

**Methodology**: The native baseline models worst-case loading (all knowledge in the context window). Real Claude Code also uses built-in tools (Read, Grep) for on-demand retrieval, so the native numbers represent an upper bound. RLM-side measurements are against the real MemCP implementation. See the [full benchmark report](../benchmark_output/benchmark_report.md) for all 40 comparisons and detailed methodology notes.
