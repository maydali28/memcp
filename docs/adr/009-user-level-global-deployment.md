# ADR-009: User-Level Global Deployment

## Status

Accepted (supersedes earlier project-level deployment)

## Date

2026-02-09

## Context

MemCP consists of three deployment artifacts beyond the Python package itself:

1. **Sub-agent definitions** — 4 `.md` files (`memcp-analyzer`, `memcp-mapper`, `memcp-synthesizer`, `memcp-entity-extractor`)
2. **Hook configuration** — JSON entries registering PreCompact, Notification, and PostToolUse hooks
3. **MCP server registration** — `claude mcp add memcp ... -s user`

Claude Code supports two scopes for configuration:
- **Project-level** (`.claude/` in project root) — Only active when working in that project directory
- **User-level** (`~/.claude/`) — Active across all projects for the current user

The original design deployed sub-agents and hooks to project-level `.claude/`. This meant:
- Sub-agents were only available when working in the MemCP project directory
- Hooks only triggered in the MemCP project
- Users working on other projects had no memory protection
- Each project needed its own copy of agent files and hook config

Since MemCP is a **cross-project memory system** (data lives at `~/.memcp/`, MCP server is registered with `-s user`), project-level deployment creates a scope mismatch.

## Decision

Deploy all configuration to **user-level** (`~/.claude/`):

| Artifact | Location | Method |
|----------|----------|--------|
| Sub-agents | `~/.claude/agents/memcp-*.md` | Copy from `agents/` |
| Hooks | `~/.claude/settings.json` | Merge from `hooks/snippets/settings.json` |
| MCP server | User scope | `claude mcp add memcp ... -s user` |

### Merge Strategy for Hooks

The installer does not overwrite `~/.claude/settings.json`. It merges MemCP hook entries into the existing file:

1. Read existing `~/.claude/settings.json` (or start with `{}` if absent)
2. For each hook entry in `hooks/snippets/settings.json`:
   - Check if an entry with the same `matcher` and `command` already exists
   - If not, append the entry to the appropriate event type array
3. Write back the merged result, preserving all non-MemCP settings

This is implemented as an inline Python script in the installer to avoid adding dependencies.

### Uninstall Strategy

The uninstaller surgically removes only MemCP artifacts:
- Deletes `~/.claude/agents/memcp-*.md` files (only MemCP agents, not other agents)
- Filters out MemCP hook entries from `~/.claude/settings.json` based on command strings containing `memcp`, `pre_compact_save`, `auto_save_reminder`, or `reset_counter`
- Preserves all non-MemCP settings and agents

### Source Templates

Configuration templates live in the repository at `templates/`:
- `agents/memcp-*.md` — Sub-agent definitions
- `hooks/snippets/settings.json` — Hook registration

Contributors edit templates, not deployed files. The installer copies from templates to `~/.claude/`.

## Consequences

### Positive

- **Cross-project coverage**: Sub-agents and hooks are available in every project, matching the user-level scope of the MCP server and data directory.
- **Single installation**: Install once, works everywhere. No per-project setup.
- **Non-destructive merge**: Existing `~/.claude/settings.json` content is preserved. MemCP hooks are added alongside other hook configurations.
- **Clean uninstall**: Only MemCP artifacts are removed. Other Claude Code settings, agents, and hooks are untouched.
- **Template-driven**: Source of truth is `templates/`, not the deployed files. Updates flow from templates via reinstall.

### Negative

- **Global side effects**: Installing MemCP affects all Claude Code sessions for the user, not just the current project. Users who want MemCP only in specific projects cannot scope it.
- **Merge complexity**: The JSON merge logic must handle edge cases (malformed JSON, missing keys, duplicate detection). Implemented as inline Python rather than a simple file copy.
- **Uninstall precision**: Surgical removal depends on string-matching hook commands. If command strings change, the uninstaller may miss entries or remove wrong ones.
- **No version tracking**: No mechanism to detect when deployed files are outdated vs. updated templates. Reinstalling overwrites without checking.

## Alternatives Considered

### Project-Level Deployment (Original Design)

Deploy to `.claude/` in the MemCP project directory. Rejected because:
- Sub-agents and hooks only work when the shell is in the MemCP directory
- Users working on other projects lose memory protection
- Scope mismatch with user-level MCP registration and `~/.memcp/` data directory
- Required `.claude/` to be in `.gitignore` to avoid committing user-specific config

### Symlink from Project to User Level

Create symlinks from `~/.claude/agents/` pointing to the repo's template files. Rejected because:
- Breaks if the repo is moved or deleted
- Symlink handling varies across OS (especially Windows/WSL)
- Adds complexity for a marginal benefit over copying

### Claude Code Config Command

Use `claude config set` or similar CLI to register agents and hooks programmatically. Rejected because:
- Claude Code does not expose a CLI for managing agents or hooks (as of v0.14)
- Hooks are configured via `settings.json` only
- Agents are discovered by scanning `~/.claude/agents/` for `.md` files
