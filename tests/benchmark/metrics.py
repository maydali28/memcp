"""Benchmark metrics — TokenLedger, ContextWindowSimulator, AccuracyMetrics.

These classes model the real constraints Claude operates under and measure
how Native vs RLM modes differ in token consumption, context rot, and
context window utilisation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from memcp.core.fileutil import estimate_tokens

# ── Token Ledger ─────────────────────────────────────────────────────


class TokenLedger:
    """Tracks cumulative tokens consumed by each approach.

    Usage::

        ledger = TokenLedger()
        ledger.record("recall_critical", 200)
        ledger.record("inspect_doc", 50)
        assert ledger.total == 250
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._by_op: dict[str, int] = defaultdict(int)
        self._total: int = 0

    def record(self, operation: str, tokens: int) -> None:
        """Record tokens consumed by an operation."""
        self._entries.append({"operation": operation, "tokens": tokens})
        self._by_op[operation] += tokens
        self._total += tokens

    def record_text(self, operation: str, text: str) -> int:
        """Record tokens for a text string (auto-estimates). Returns token count."""
        tokens = estimate_tokens(text)
        self.record(operation, tokens)
        return tokens

    @property
    def total(self) -> int:
        return self._total

    @property
    def by_operation(self) -> dict[str, int]:
        return dict(self._by_op)

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def reset(self) -> None:
        self._entries.clear()
        self._by_op.clear()
        self._total = 0

    def summary(self) -> dict[str, Any]:
        return {
            "total_tokens": self._total,
            "operation_count": len(self._entries),
            "by_operation": dict(self._by_op),
        }


# ── Context Window Simulator ─────────────────────────────────────────


@dataclass
class _WindowEntry:
    label: str
    tokens: int
    content_preview: str = ""


class ContextWindowSimulator:
    """Simulates a fixed-size context window (e.g., 128K tokens).

    Models the real constraint Claude operates under.  "Native" mode loads
    everything into the window.  "RLM" mode loads only metadata + targeted
    chunks.

    On overflow the *oldest* entries are evicted (FIFO), matching how Claude's
    context window drops the earliest messages when it runs out of space.
    """

    def __init__(self, capacity: int = 128_000) -> None:
        self.capacity = capacity
        self._entries: list[_WindowEntry] = []
        self._used: int = 0
        self._total_evicted: int = 0
        self._eviction_count: int = 0
        self._history: list[dict[str, Any]] = []

    # ── public API ────────────────────────────────────────────────

    def load(self, content: str, label: str) -> dict[str, Any]:
        """Load content into the window.

        Returns a dict describing what happened:
            tokens_added, tokens_evicted, overflow, utilization_pct
        """
        tokens = estimate_tokens(content)
        evicted = 0

        # Evict oldest entries until there's room
        while self._used + tokens > self.capacity and self._entries:
            oldest = self._entries.pop(0)
            self._used -= oldest.tokens
            evicted += oldest.tokens
            self._total_evicted += oldest.tokens
            self._eviction_count += 1

        overflow = self._used + tokens > self.capacity
        if not overflow:
            self._entries.append(
                _WindowEntry(label=label, tokens=tokens, content_preview=content[:80])
            )
            self._used += tokens

        result = {
            "tokens_added": tokens if not overflow else 0,
            "tokens_evicted": evicted,
            "overflow": overflow,
            "utilization_pct": round(self._used / self.capacity * 100, 2),
        }
        self._history.append({"action": "load", "label": label, **result})
        return result

    def compact(self, retain_pct: float = 0.05) -> dict[str, Any]:
        """Simulate /compact — keep only *retain_pct* of the window contents.

        Retains the most recent entries up to *retain_pct* of current usage,
        matching how Claude retains a small summary after compaction.
        """
        tokens_before = self._used
        retain_tokens = int(self._used * retain_pct)

        # Keep most recent entries up to budget
        kept: list[_WindowEntry] = []
        kept_tokens = 0
        for entry in reversed(self._entries):
            if kept_tokens + entry.tokens > retain_tokens and kept:
                break
            kept.insert(0, entry)
            kept_tokens += entry.tokens

        lost = tokens_before - kept_tokens
        self._entries = kept
        self._used = kept_tokens
        self._total_evicted += lost

        result = {
            "tokens_before": tokens_before,
            "tokens_after": kept_tokens,
            "tokens_lost": lost,
            "entries_before": len(self._entries) + (tokens_before - kept_tokens > 0),
            "entries_after": len(self._entries),
            "utilization_pct": round(self._used / self.capacity * 100, 2),
        }
        self._history.append({"action": "compact", **result})
        return result

    @property
    def utilization(self) -> float:
        """Current window utilisation as a percentage."""
        return round(self._used / self.capacity * 100, 2)

    @property
    def used_tokens(self) -> int:
        return self._used

    @property
    def total_evicted(self) -> int:
        return self._total_evicted

    @property
    def eviction_count(self) -> int:
        return self._eviction_count

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def contents(self) -> list[dict[str, Any]]:
        return [{"label": e.label, "tokens": e.tokens} for e in self._entries]

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def reset(self) -> None:
        self._entries.clear()
        self._used = 0
        self._total_evicted = 0
        self._eviction_count = 0
        self._history.clear()


# ── Accuracy Metrics ─────────────────────────────────────────────────


class AccuracyMetrics:
    """Precision / recall / F1 / MRR for retrieval benchmarks."""

    @staticmethod
    def evaluate(retrieved_ids: list[str], expected_ids: list[str]) -> dict[str, float]:
        """Compute retrieval quality metrics.

        Args:
            retrieved_ids: IDs returned by the system (ordered by rank).
            expected_ids: Ground-truth IDs that should be returned.

        Returns:
            {"precision", "recall", "f1", "mrr"}
        """
        if not expected_ids:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "mrr": 1.0}

        retrieved_set = set(retrieved_ids)
        expected_set = set(expected_ids)

        true_positives = len(retrieved_set & expected_set)

        precision = true_positives / len(retrieved_set) if retrieved_set else 0.0
        recall = true_positives / len(expected_set) if expected_set else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # Mean Reciprocal Rank — rank of first relevant result
        mrr = 0.0
        for i, rid in enumerate(retrieved_ids):
            if rid in expected_set:
                mrr = 1.0 / (i + 1)
                break

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "mrr": round(mrr, 4),
        }


# ── Comparison Result ────────────────────────────────────────────────


@dataclass
class ComparisonResult:
    """Holds a side-by-side Native vs RLM measurement."""

    scenario: str
    metric: str
    native_value: float
    rlm_value: float
    unit: str = "tokens"

    @property
    def savings_pct(self) -> float:
        if self.native_value == 0:
            return 0.0
        return round((1 - self.rlm_value / self.native_value) * 100, 1)

    @property
    def ratio(self) -> float:
        if self.rlm_value == 0:
            return float("inf")
        return round(self.native_value / self.rlm_value, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "metric": self.metric,
            "native": self.native_value,
            "rlm": self.rlm_value,
            "unit": self.unit,
            "savings_pct": self.savings_pct,
            "ratio": f"{self.ratio}x",
        }


@dataclass
class BenchmarkReport:
    """Accumulates ComparisonResults across all benchmark modules."""

    results: list[ComparisonResult] = field(default_factory=list)

    def add(self, result: ComparisonResult) -> None:
        self.results.append(result)

    def to_dict(self) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in self.results:
            grouped[r.scenario].append(r.to_dict())
        return {"scenarios": dict(grouped), "total_comparisons": len(self.results)}
