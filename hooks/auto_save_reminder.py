#!/usr/bin/env python3
"""Hook: Notification — progressive reminders to save context.

Tracks turn count in ~/.memcp/state.json. When context usage is high
AND turn count exceeds thresholds, outputs progressively urgent reminders.

Severity levels:
  - 10+ turns AND context >= 55%: "Consider saving important context"
  - 20+ turns AND context >= 55%: "Recommended: save decisions and findings"
  - 30+ turns AND context >= 55%: "ACTION REQUIRED: save context now"

Usage in .claude/settings.json:
  "Notification": [{
    "matcher": "",
    "hooks": [{"type": "command", "command": "python3 hooks/auto_save_reminder.py"}]
  }]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _get_state_path() -> Path:
    data_dir = Path(os.getenv("MEMCP_DATA_DIR", "~/.memcp")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "state.json"


def _load_state() -> dict:
    path = _get_state_path()
    if path.exists():
        try:
            state = json.loads(path.read_text())
            state.setdefault("turn_count", 0)
            return state
        except (json.JSONDecodeError, ValueError):
            pass
    return {"turn_count": 0}


def _save_state(state: dict) -> None:
    path = _get_state_path()
    path.write_text(json.dumps(state, indent=2))


def main() -> None:
    # Read notification from stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        input_data = {}

    # Increment turn counter
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + 1
    _save_state(state)

    turns = state["turn_count"]

    # Check context usage from input
    context_pct = input_data.get("context_usage_pct", 0)

    # Only remind when context is actually filling up
    if context_pct < 55:
        print(json.dumps({}))
        return

    message = None

    if turns >= 30:
        message = (
            "ACTION REQUIRED: Context is filling up and you have been working "
            f"for {turns} turns. Save important decisions, findings, and rules "
            "using memcp_remember() NOW to avoid losing context."
        )
    elif turns >= 20:
        message = (
            f"Recommended: After {turns} turns with {context_pct}% context used, "
            "consider saving key decisions and findings with memcp_remember()."
        )
    elif turns >= 10:
        message = (
            f"Consider saving important context — {turns} turns completed, "
            f"{context_pct}% context used."
        )

    if message:
        print(json.dumps({"systemMessage": message}))
    else:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
