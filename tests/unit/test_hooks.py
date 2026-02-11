"""Tests for MemCP hooks — pre_compact_save, auto_save_reminder, reset_counter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"


class TestPreCompactSave:
    def test_outputs_blocking_message(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "pre_compact_save.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["blockExecution"] is True
        assert "COMPACT DETECTED" in output["systemMessage"]
        assert "memcp_remember" in output["systemMessage"]

    def test_handles_empty_stdin(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "pre_compact_save.py")],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["blockExecution"] is True

    def test_handles_invalid_json(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "pre_compact_save.py")],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["blockExecution"] is True


class TestAutoSaveReminder:
    def _run_reminder(
        self, data_dir: Path, context_pct: int = 0, turn_override: int | None = None
    ) -> dict:
        """Run the auto_save_reminder hook and return its output."""
        env = {"MEMCP_DATA_DIR": str(data_dir), "PATH": ""}
        input_data = json.dumps({"context_usage_pct": context_pct})

        # Pre-set turn count if needed
        if turn_override is not None:
            state_path = data_dir / "state.json"
            data_dir.mkdir(parents=True, exist_ok=True)
            # Set to turn_override - 1 because the hook increments
            state_path.write_text(json.dumps({"turn_count": turn_override - 1}))

        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "auto_save_reminder.py")],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=10,
            env={**dict(os.environ), **env},
        )
        assert result.returncode == 0
        return json.loads(result.stdout)

    def test_no_reminder_low_turns(self, isolated_data_dir: Path) -> None:
        output = self._run_reminder(isolated_data_dir, context_pct=60, turn_override=3)
        assert "systemMessage" not in output or output.get("systemMessage") is None

    def test_no_reminder_low_context(self, isolated_data_dir: Path) -> None:
        output = self._run_reminder(isolated_data_dir, context_pct=30, turn_override=35)
        assert "systemMessage" not in output or output.get("systemMessage") is None

    def test_consider_reminder_at_10_turns(self, isolated_data_dir: Path) -> None:
        output = self._run_reminder(isolated_data_dir, context_pct=60, turn_override=10)
        assert "systemMessage" in output
        assert "Consider" in output["systemMessage"]

    def test_recommended_reminder_at_20_turns(self, isolated_data_dir: Path) -> None:
        output = self._run_reminder(isolated_data_dir, context_pct=60, turn_override=20)
        assert "systemMessage" in output
        assert "Recommended" in output["systemMessage"]

    def test_action_required_at_30_turns(self, isolated_data_dir: Path) -> None:
        output = self._run_reminder(isolated_data_dir, context_pct=60, turn_override=30)
        assert "systemMessage" in output
        assert "ACTION REQUIRED" in output["systemMessage"]

    def test_increments_turn_counter(self, isolated_data_dir: Path) -> None:
        self._run_reminder(isolated_data_dir, context_pct=0)
        state_path = isolated_data_dir / "state.json"
        state = json.loads(state_path.read_text())
        assert state["turn_count"] == 1

        self._run_reminder(isolated_data_dir, context_pct=0)
        state = json.loads(state_path.read_text())
        assert state["turn_count"] == 2


class TestResetCounter:
    def test_resets_turn_counter(self, isolated_data_dir: Path) -> None:
        # Set a non-zero counter
        state_path = isolated_data_dir / "state.json"
        isolated_data_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"turn_count": 25}))

        env = {"MEMCP_DATA_DIR": str(isolated_data_dir)}
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "reset_counter.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env={**dict(os.environ), **env},
        )
        assert result.returncode == 0

        state = json.loads(state_path.read_text())
        assert state["turn_count"] == 0

    def test_preserves_other_state_keys(self, isolated_data_dir: Path) -> None:
        # Set state with project/session alongside turn_count
        state_path = isolated_data_dir / "state.json"
        isolated_data_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "turn_count": 15,
                    "current_project": "my-project",
                    "current_session": "my-project_2026-02-11_001",
                }
            )
        )

        env = {"MEMCP_DATA_DIR": str(isolated_data_dir)}
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "reset_counter.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env={**dict(os.environ), **env},
        )
        assert result.returncode == 0

        state = json.loads(state_path.read_text())
        assert state["turn_count"] == 0
        assert state["current_project"] == "my-project"
        assert state["current_session"] == "my-project_2026-02-11_001"

    def test_handles_missing_state(self, isolated_data_dir: Path) -> None:
        env = {"MEMCP_DATA_DIR": str(isolated_data_dir)}
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "reset_counter.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env={**dict(os.environ), **env},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output == {}


class TestAutoSaveReminderStatePreservation:
    def test_preserves_other_state_keys(self, isolated_data_dir: Path) -> None:
        # Set state with project/session alongside turn_count
        state_path = isolated_data_dir / "state.json"
        isolated_data_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "turn_count": 5,
                    "current_project": "my-project",
                    "current_session": "my-project_2026-02-11_001",
                }
            )
        )

        env = {"MEMCP_DATA_DIR": str(isolated_data_dir)}
        input_data = json.dumps({"context_usage_pct": 0})
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "auto_save_reminder.py")],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=10,
            env={**dict(os.environ), **env},
        )
        assert result.returncode == 0

        state = json.loads(state_path.read_text())
        assert state["turn_count"] == 6
        assert state["current_project"] == "my-project"
        assert state["current_session"] == "my-project_2026-02-11_001"
