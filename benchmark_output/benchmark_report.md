# Benchmark Report: Claude Native vs Claude with RLM

*Generated: 2026-02-11 00:09 UTC*


---


## Token Efficiency

*Tokens consumed in the context window for equivalent operations.*


| Scenario | Metric | Native | RLM | RLM Advantage | Unit |
|----------|--------|--------|-----|---------------|------|
| Session Startup | Reload 50 insights | 896 | 167 | 5.4x less | tokens |
| Session Startup | Reload 200 insights | 3,768 | 433 | 8.7x less | tokens |
| Session Startup | Reload 500 insights | 9,380 | 462 | 20.3x less | tokens |
| Large Document Analysis | Analyse 5K-token doc | 5,077 | 231 | 22.0x less | tokens |
| Large Document Analysis | Analyse 20K-token doc | 20,209 | 231 | 87.5x less | tokens |
| Large Document Analysis | Analyse 50K-token doc | 50,460 | 231 | 218.4x less | tokens |
| Cross-Reference Knowledge | Find auth decisions + causes | 1,861 | 172 | 10.8x less | tokens |
| Multi-turn Accumulation | 30 turns, retrieve turn-5 finding | 548 | 505 | 1.1x less | tokens |

---

## Methodology Notes


### What this benchmark measures


This benchmark compares two modes of operating Claude Code:


- **Native mode**: Models the worst-case scenario where all prior knowledge must be loaded into the context window as raw text to be searchable. This represents sessions where accumulated conversation history, documents, and decisions consume context window capacity.

- **RLM mode**: Uses MemCP's persistent storage (SQLite + disk) to keep knowledge outside the context window, loading only targeted results (via `recall()`, `inspect()`, `filter_context()`) on demand.


### Caveats and limitations


1. **Native baseline is a worst-case model.** Real Claude Code doesn't preload all prior knowledge — it uses built-in tools (Read, Grep, Glob) for on-demand retrieval. The native numbers represent the cost *if* all knowledge needed to be in the active context window simultaneously.

2. **MCP tool overhead is underestimated.** The benchmark counts ~15 tokens per `remember()` call. Real MCP tool calls include JSON request/response serialization that costs ~130-230 tokens per round-trip. This means RLM's actual token cost is higher than reported here.

3. **Token estimation uses a 4-char heuristic** (`len(text) // 4`), not a real tokenizer. This is directionally accurate but can be off by 20-30% depending on content type.

4. **Context rot retention percentages**: The native retention values for compaction tests use a FIFO eviction model (keep newest 5%). Claude's real `/compact` creates semantic summaries that preserve more information than raw FIFO would suggest.

5. **Cross-session native = 0%** is hardcoded by definition (new sessions start with no prior context window content). In practice, Claude Code's CLAUDE.md and project files provide some cross-session continuity.

6. **Scale ratios are theoretical bounds.** The O(N) vs O(1) scaling is mathematically correct for the retrieval model but the absolute ratios depend on corpus size — any bounded-result retrieval system shows similar scaling.

7. **Graph traversal RLM = 0 tokens** occurs because the JSON backend is used (GraphMemory DB not initialized), so `get_related()` raises FileNotFoundError and no content is returned. These results should be interpreted with caution.


### What IS valid


- **Directional claims are sound**: Offloading knowledge to persistent storage genuinely reduces context window pressure.

- **RLM-side measurements are real**: The actual tokens returned by `recall()`, `inspect()`, `filter_context()` are measured against the real MemCP implementation.

- **Context rot resistance is the strongest claim**: After `/compact`, native mode loses context window content while RLM's SQLite/disk storage is completely unaffected. This is architecturally guaranteed, not a benchmark artifact.

- **The working set efficiency** comparison is realistic: loading full documents into the context window vs. inspecting metadata + selective chunks is a genuine architectural difference.


**Total comparisons:** 8
