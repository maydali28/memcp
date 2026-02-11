# ADR-004: Sub-Agents over Sub-LLMs and Skills

## Status

Accepted (supersedes earlier Sub-LLM and Skills approaches)

## Date

2026-02-08

## Context

The RLM paper (arXiv:2512.24601) requires a `llm_query()` function — the ability to dispatch analysis tasks to independent model instances that process subsets of data with their own context windows. This is the core of the map-reduce pattern: partition content into chunks, MAP each chunk to a sub-model, REDUCE results with a stronger model.

Three approaches were evaluated over the course of development:

1. **Sub-LLMs via Ollama** (original Phase 4 design) — Direct HTTP calls to local Ollama models
2. **Skills** (revised design) — Markdown prompt templates that instruct the main Claude session to use Task tools
3. **Custom sub-agents** (final design) — `.claude/agents/*.md` files defining independent Claude sessions

The chosen approach must support:
- Independent context windows (sub-queries must not pollute the main conversation)
- MCP tool access (sub-agents need to call MemCP tools like `memcp_peek_chunk`)
- Model selection (cheaper models for map phase, stronger for reduce)
- Parallel execution (multiple mappers running simultaneously)
- Zero infrastructure (no additional servers to set up)

## Decision

Use **Claude Code custom sub-agents** defined as `.md` files in `agents/`, deployed to `~/.claude/agents/` by the installer.

Four sub-agents implement the RLM pattern:

| Sub-Agent | Model | RLM Role | Tool Access |
|-----------|-------|----------|-------------|
| `memcp-analyzer` | Haiku | Peek + grep + single-chunk analysis | Read-only MemCP tools |
| `memcp-mapper` | Haiku | MAP phase (one chunk per instance) | `memcp_peek_chunk`, `memcp_recall` |
| `memcp-synthesizer` | Sonnet | REDUCE phase (fuse mapper outputs) | Full MemCP access including `memcp_remember` |
| `memcp-entity-extractor` | Haiku | LLM entity extraction | `memcp_recall` (for dedup) |

Each agent `.md` file uses Claude Code frontmatter:

```yaml
---
name: memcp-mapper
description: MAP phase sub-agent
model: haiku
tools:
  allow:
    - mcp__memcp__memcp_peek_chunk
    - mcp__memcp__memcp_recall
mcpServers:
  - memcp
maxTurns: 8
---
```

## Consequences

### Positive

- **True independence**: Each sub-agent runs in its own context window. Mapper analysis of 5 chunks does not consume the main session's context.
- **Native parallel execution**: Multiple mappers can run in background simultaneously.
- **MCP tool access**: Sub-agents call MemCP tools directly via `mcpServers: [memcp]`.
- **Model-tier optimization**: Haiku for cheap map phase, Sonnet for quality reduce — matches the RLM paper's cost model.
- **Zero infrastructure**: No Ollama server, no additional API keys, no Docker containers. Sub-agents are plain Markdown files.
- **Persistent memory**: Sub-agents with `memory: project` retain analysis patterns across sessions.
- **Tool restrictions**: Each agent's `tools.allow` list enforces least-privilege access.
- **Ollama compatible**: Users can point sub-agents at local models via `ANTHROPIC_BASE_URL=http://localhost:11434` for free execution.

### Negative

- **Claude Code dependency**: Sub-agents only work within Claude Code sessions. Not usable from other MCP clients.
- **Depth-1 recursion only**: Sub-agents cannot spawn other sub-agents. Matches the RLM paper's depth=1 but limits more complex recursive patterns.
- **Background result collection**: Collecting results from parallel background mappers requires manual coordination in the main session.
- **API costs**: Sub-agents use Claude API credits (unless configured with Ollama backend). Multiple mapper instances can add up.

## Alternatives Considered

### Sub-LLMs via Ollama (Original Design)

Direct HTTP calls to local Ollama models from Python using `httpx`:

```python
async def llm_query(prompt: str, model: str = "qwen3-coder") -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post("http://localhost:11434/api/generate", ...)
    return response.json()["response"]
```

Rejected because:
- **Infrastructure burden**: Requires users to install and run Ollama (`ollama serve`)
- **No MCP access**: Sub-LLMs cannot call MemCP tools natively — would need to implement an MCP client in Python
- **No persistent memory**: Each call is stateless; must pass all context in the prompt
- **Dependency**: Adds `httpx` as a required dependency for the core map-reduce feature
- **Model quality**: Open-source models at 7-20B params are significantly less capable than Haiku for code analysis tasks

### Skills (Task Tool Templates)

Markdown templates that instruct the main Claude session to use the Task tool for parallel operations:

```markdown
# memcp-mapper skill
When chunking analysis is needed:
1. Use the Task tool to launch a subagent for each chunk
2. Collect results
3. Synthesize...
```

Rejected because:
- **Not independent**: Skills run as prompt injections in the main session's context — they consume the same context window
- **No tool restrictions**: Skills inherit the main session's full tool access — cannot enforce least-privilege
- **No model selection**: Locked to the main session's model (cannot use Haiku for map phase)
- **No persistent memory**: Skills have no state between invocations
- **Unreliable parallelism**: Prompt-based instructions to "run in parallel" are less reliable than native background execution
