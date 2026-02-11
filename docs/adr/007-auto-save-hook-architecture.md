# ADR-007: Auto-Save Hook Architecture

## Status

Accepted

## Date

2026-02-08

## Context

Claude Code loses all conversation context after `/compact` (manual or automatic context compaction). Without intervention, decisions, findings, and in-progress work vanish. Users must manually remember to save before compacting.

Claude Code provides a **hooks system** — shell commands that execute in response to lifecycle events:

- `PreCompact` — Fires before context compaction (manual or auto)
- `PostToolUse` — Fires after a specific tool is called
- `Notification` — Fires on system notifications (including turn events)
- `Stop` — Fires when the agent stops

Hooks can return JSON with `systemMessage` to inject instructions into the conversation, or `decision: "block"` to prevent an action.

The challenge: How to ensure Claude saves critical context before compact, and how to progressively remind Claude to save during long sessions — without being so aggressive that it disrupts the workflow.

## Decision

Implement three hooks that work together as a coordinated auto-save system:

### 1. `pre_compact_save.py` (PreCompact)

Triggers before any `/compact` event. Returns a blocking `systemMessage`:

```
COMPACT DETECTED — SAVE REQUIRED
Before continuing, you MUST:
1. memcp_remember() — Save each decision, finding, or rule discovered
2. memcp_load_context() — Save a summary of this session's key points
What isn't saved will be LOST after compact.
```

This is the last line of defense — a hard gate before context is destroyed.

### 2. `auto_save_reminder.py` (Notification)

Tracks conversation turn count in `~/.memcp/state.json`. Progressive severity based on turn count AND context usage:

| Condition | Severity | Message |
|-----------|----------|---------|
| 10+ turns AND context >= 55% | Info | "Consider saving important context" |
| 20+ turns AND context >= 55% | Warning | "Recommended: save decisions and findings" |
| 30+ turns AND context >= 55% | Critical | "ACTION REQUIRED: save context now" |

The dual condition (turns AND context %) prevents premature reminders. Short conversations with large context loads don't trigger; long conversations with small context don't trigger either.

### 3. `reset_counter.py` (PostToolUse)

Triggers after `memcp_remember` or `memcp_load_context` calls. Resets the turn counter to 0, acknowledging that Claude just saved. This prevents repeated reminders after saves.

### Deployment

Hooks are registered in `hooks/snippets/settings.json` and merged into `~/.claude/settings.json` (user-level) by the installer. This makes hooks active across all projects.

## Consequences

### Positive

- **Automatic protection**: Users don't need to remember to save. The pre-compact hook catches every compact event.
- **Progressive, not disruptive**: Reminders escalate gradually. Low-context sessions are never interrupted.
- **Context-aware**: The 55% threshold means reminders only fire when context is actually filling up. Short Q&A sessions are silent.
- **Self-resetting**: After Claude saves, the counter resets. No reminder fatigue.
- **User-level scope**: Hooks in `~/.claude/settings.json` protect all projects, not just the MemCP project directory.

### Negative

- **Turn counting heuristic**: Turn count is a rough proxy for "important unsaved work". Some 50-turn sessions may be trivial; some 5-turn sessions may be critical.
- **Context % estimation**: Parsing context usage from the notification payload depends on Claude Code's internal format, which may change between versions.
- **State file dependency**: `~/.memcp/state.json` must be writable. If the data directory doesn't exist, the counter silently fails.
- **Hook execution overhead**: Each notification event runs a Python script. Sub-millisecond overhead, but adds up over hundreds of turns.

## Alternatives Considered

### No Hooks (Manual Save Only)

Rely on users to remember to save. Document best practices in `CLAUDE.md`. Rejected because:
- Users forget, especially during long or intense sessions
- `/compact` can be triggered automatically by Claude Code when context is full — user may not even see it coming
- The cost of lost context (repeating decisions, losing findings) far outweighs the minor overhead of hooks

### Aggressive Auto-Save (Save Everything Automatically)

Run `memcp_remember()` automatically after every tool call or user turn. Rejected because:
- Generates enormous amounts of low-value insights (noise)
- Consumes storage and makes recall less useful (signal-to-noise ratio drops)
- The RLM approach requires *selective* memory — Claude should decide what's worth saving
- Would significantly slow down every interaction

### Single Hook (PreCompact Only)

Only use the pre-compact hook, skip progressive reminders. Rejected because:
- By the time `/compact` fires, Claude may have 200K tokens of context to summarize under pressure
- Progressive reminders encourage incremental saves, spreading the work across the session
- The pre-compact hook is the safety net; reminders are the proactive measure

### Timer-Based Reminders (Instead of Turn-Based)

Remind based on elapsed time (every 15 minutes). Rejected because:
- Claude Code doesn't expose wall-clock time in notification payloads
- Turn count correlates better with "amount of work done" than elapsed time
- A user who steps away for 30 minutes shouldn't get bombarded on return
