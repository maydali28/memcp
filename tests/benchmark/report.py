"""Benchmark report generator — JSON + Markdown output.

Collects all ``ComparisonResult`` entries from the session-scoped
``BenchmarkReport`` and writes:

  1. ``benchmark_results.json``  — machine-readable raw data
  2. ``benchmark_report.md``     — human-readable comparison tables
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .metrics import BenchmarkReport, ComparisonResult

# Metrics where lower is better even when unit is %
_LOWER_IS_BETTER_METRICS = {"utilisation", "utilization", "fill"}


def _format_value(value: float, unit: str) -> str:
    """Format a numeric value for display."""
    if value == float("inf"):
        return "inf"
    if unit == "%":
        return f"{value:.1f}%"
    if value == 0:
        return "0"
    if value >= 1000:
        return f"{value:,.0f}"
    if value == int(value):
        return f"{int(value)}"
    return f"{value:.1f}"


def _is_lower_better(r: ComparisonResult) -> bool:
    """Determine if lower values are better for this metric."""
    if r.unit == "tokens":
        return True
    metric_lower = r.metric.lower()
    return any(kw in metric_lower for kw in _LOWER_IS_BETTER_METRICS)


def _advantage_text(r: ComparisonResult) -> str:
    """Describe the RLM advantage in human-readable terms."""
    if _is_lower_better(r):
        # Lower is better (tokens, utilization %): RLM should be lower
        if r.rlm_value == 0:
            return "zero cost"
        if r.native_value == 0:
            return "N/A"
        ratio = r.native_value / r.rlm_value
        return f"{ratio:.1f}x less"
    else:
        # Higher is better (retention %, docs, turns): RLM should be higher
        if r.native_value == 0 and r.rlm_value > 0:
            return f"+{_format_value(r.rlm_value, r.unit)}"
        if r.rlm_value == 0 and r.native_value == 0:
            return "equal"
        if r.native_value > 0:
            ratio = r.rlm_value / r.native_value
            return f"{ratio:.1f}x more"
        return f"+{_format_value(r.rlm_value, r.unit)}"


def write_json_report(report: BenchmarkReport, output_dir: Path) -> Path:
    """Write the full benchmark results as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "benchmark_results.json"
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report.to_dict(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_markdown_report(report: BenchmarkReport, output_dir: Path) -> Path:
    """Write a human-readable Markdown comparison report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "benchmark_report.md"

    lines: list[str] = [
        "# Benchmark Report: Claude Native vs Claude with RLM\n",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n",
        "",
        "---\n",
        "",
    ]

    # Group results into logical categories
    categories: dict[str, list[ComparisonResult]] = defaultdict(list)
    for r in report.results:
        token_keywords = ("Token", "Session Startup", "Large Doc", "Cross-Ref", "Multi-turn")
        if any(kw in r.scenario for kw in token_keywords):
            categories["Token Efficiency"].append(r)
        elif "Context Rot" in r.scenario or "Importance" in r.scenario:
            categories["Context Rot Resistance"].append(r)
        elif any(kw in r.scenario for kw in ("Context Window", "Working Set", "Compaction")):
            categories["Context Window Management"].append(r)
        elif "Scale" in r.scenario:
            categories["Scale Behavior"].append(r)
        else:
            categories["Other"].append(r)

    # --- Token Efficiency ---
    if "Token Efficiency" in categories:
        lines.append("## Token Efficiency\n")
        lines.append("*Tokens consumed in the context window for equivalent operations.*\n")
        lines.append("")
        lines.append("| Scenario | Metric | Native | RLM | RLM Advantage | Unit |")
        lines.append("|----------|--------|--------|-----|---------------|------|")
        for r in categories["Token Efficiency"]:
            lines.append(
                f"| {r.scenario} "
                f"| {r.metric} "
                f"| {_format_value(r.native_value, r.unit)} "
                f"| {_format_value(r.rlm_value, r.unit)} "
                f"| {_advantage_text(r)} "
                f"| {r.unit} |"
            )
        lines.append("")

    # --- Context Rot ---
    if "Context Rot Resistance" in categories:
        lines.append("## Context Rot Resistance\n")
        lines.append("*Knowledge retained after simulated compaction or session boundaries.*\n")
        lines.append("")
        lines.append("| Scenario | Metric | Native | RLM | Unit |")
        lines.append("|----------|--------|--------|-----|------|")
        for r in categories["Context Rot Resistance"]:
            lines.append(
                f"| {r.scenario} "
                f"| {r.metric} "
                f"| {_format_value(r.native_value, r.unit)} "
                f"| {_format_value(r.rlm_value, r.unit)} "
                f"| {r.unit} |"
            )
        lines.append("")

    # --- Context Window ---
    if "Context Window Management" in categories:
        lines.append("## Context Window Management\n")
        lines.append("*How efficiently each mode uses the fixed-size context window.*\n")
        lines.append("")
        lines.append("| Scenario | Metric | Native | RLM | RLM Advantage | Unit |")
        lines.append("|----------|--------|--------|-----|---------------|------|")
        for r in categories["Context Window Management"]:
            lines.append(
                f"| {r.scenario} "
                f"| {r.metric} "
                f"| {_format_value(r.native_value, r.unit)} "
                f"| {_format_value(r.rlm_value, r.unit)} "
                f"| {_advantage_text(r)} "
                f"| {r.unit} |"
            )
        lines.append("")

    # --- Scale ---
    if "Scale Behavior" in categories:
        lines.append("## Scale Behavior\n")
        lines.append(
            "*How token costs grow as the knowledge base grows (N = number of insights).*\n"
        )
        lines.append("")
        lines.append("| N | Metric | Native (tokens) | RLM (tokens) | RLM Advantage |")
        lines.append("|---|--------|-----------------|--------------|---------------|")
        for r in categories["Scale Behavior"]:
            # Extract N from scenario name
            lines.append(
                f"| {r.scenario} "
                f"| {r.metric} "
                f"| {_format_value(r.native_value, r.unit)} "
                f"| {_format_value(r.rlm_value, r.unit)} "
                f"| {_advantage_text(r)} |"
            )
        lines.append("")

    # --- Methodology Notes ---
    lines.append("---\n")
    lines.append("## Methodology Notes\n")
    lines.append("")
    lines.append("### What this benchmark measures\n")
    lines.append("")
    lines.append("This benchmark compares two modes of operating Claude Code:\n")
    lines.append("")
    lines.append(
        "- **Native mode**: Models the worst-case scenario where all prior knowledge "
        "must be loaded into the context window as raw text to be searchable. "
        "This represents sessions where accumulated conversation history, documents, "
        "and decisions consume context window capacity.\n"
    )
    lines.append(
        "- **RLM mode**: Uses MemCP's persistent storage (SQLite + disk) to keep "
        "knowledge outside the context window, loading only targeted results "
        "(via `recall()`, `inspect()`, `filter_context()`) on demand.\n"
    )
    lines.append("")
    lines.append("### Caveats and limitations\n")
    lines.append("")
    lines.append(
        "1. **Native baseline is a worst-case model.** Real Claude Code doesn't preload "
        "all prior knowledge — it uses built-in tools (Read, Grep, Glob) for on-demand "
        "retrieval. The native numbers represent the cost *if* all knowledge needed to be "
        "in the active context window simultaneously.\n"
    )
    lines.append(
        "2. **MCP tool overhead is underestimated.** The benchmark counts ~15 tokens per "
        "`remember()` call. Real MCP tool calls include JSON request/response serialization "
        "that costs ~130-230 tokens per round-trip. This means RLM's actual token cost is "
        "higher than reported here.\n"
    )
    lines.append(
        "3. **Token estimation uses a 4-char heuristic** (`len(text) // 4`), not a real "
        "tokenizer. This is directionally accurate but can be off by 20-30% depending on "
        "content type.\n"
    )
    lines.append(
        "4. **Context rot retention percentages**: The native retention values for compaction "
        "tests use a FIFO eviction model (keep newest 5%). Claude's real `/compact` creates "
        "semantic summaries that preserve more information than raw FIFO would suggest.\n"
    )
    lines.append(
        "5. **Cross-session native = 0%** is hardcoded by definition (new sessions start "
        "with no prior context window content). In practice, Claude Code's CLAUDE.md and "
        "project files provide some cross-session continuity.\n"
    )
    lines.append(
        "6. **Scale ratios are theoretical bounds.** The O(N) vs O(1) scaling is "
        "mathematically correct for the retrieval model but the absolute ratios depend "
        "on corpus size — any bounded-result retrieval system shows similar scaling.\n"
    )
    lines.append(
        "7. **Graph traversal RLM = 0 tokens** occurs because the JSON backend is used "
        "(GraphMemory DB not initialized), so `get_related()` raises FileNotFoundError "
        "and no content is returned. These results should be interpreted with caution.\n"
    )
    lines.append("")
    lines.append("### What IS valid\n")
    lines.append("")
    lines.append(
        "- **Directional claims are sound**: Offloading knowledge to persistent storage "
        "genuinely reduces context window pressure.\n"
    )
    lines.append(
        "- **RLM-side measurements are real**: The actual tokens returned by `recall()`, "
        "`inspect()`, `filter_context()` are measured against the real MemCP implementation.\n"
    )
    lines.append(
        "- **Context rot resistance is the strongest claim**: After `/compact`, native mode "
        "loses context window content while RLM's SQLite/disk storage is completely unaffected. "
        "This is architecturally guaranteed, not a benchmark artifact.\n"
    )
    lines.append(
        "- **The working set efficiency** comparison is realistic: loading full documents into "
        "the context window vs. inspecting metadata + selective chunks is a genuine "
        "architectural difference.\n"
    )
    lines.append("")

    lines.append(f"**Total comparisons:** {len(report.results)}\n")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_reports(report: BenchmarkReport, output_dir: Path) -> dict[str, Path]:
    """Generate both JSON and Markdown reports. Returns paths."""
    return {
        "json": write_json_report(report, output_dir),
        "markdown": write_markdown_report(report, output_dir),
    }
