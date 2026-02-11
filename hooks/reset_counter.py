#!/usr/bin/env python3
"""Hook: PostToolUse — reset turn counter after a save operation.

Triggers after memcp_remember or memcp_load_context to reset the
progressive reminder counter, since context has just been saved.

Usage in .claude/settings.json:
  "PostToolUse": [
    {"matcher": "mcp__memcp__memcp_remember",
     "hooks": [{"type": "command", "command": "python3 hooks/reset_counter.py"}]},
    {"matcher": "mcp__memcp__memcp_load_context",
     "hooks": [{"type": "command", "command": "python3 hooks/reset_counter.py"}]}
  ]
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


def main() -> None:
    # Read input (not used, but consume stdin)
    try:
        _input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        _input_data = {}

    # Reset turn counter while preserving other state (project, session, etc.)
    state_path = _get_state_path()
    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except (json.JSONDecodeError, ValueError):
            state = {}
    state["turn_count"] = 0
    state_path.write_text(json.dumps(state, indent=2))

    # No output needed — silent reset
    print(json.dumps({}))


if __name__ == "__main__":
    main()
