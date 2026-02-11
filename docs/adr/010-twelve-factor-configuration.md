# ADR-010: 12-Factor Configuration

## Status

Accepted

## Date

2026-02-07

## Context

MemCP must run in multiple environments:

- **Local development** — Developer's machine, source checkout, `pip install -e ".[dev]"`
- **User installation** — `pip install memcp`, registered as user-level MCP server
- **Docker** — Container with volume-mounted data directory
- **CI/CD** — Isolated test runs with temporary data directories

Each environment may need different values for:
- Data directory path (`~/.memcp` locally, `/data` in Docker, `$RUNNER_TEMP/memcp-test` in CI)
- Memory limits (2GB default, maybe lower in constrained environments)
- Retention thresholds (30/180 day defaults, shorter for testing)
- Maximum insight count (10K default)

The [12-Factor App](https://12factor.net/) methodology mandates: *"Store config in the environment"* — environment variables, not config files.

## Decision

Use a **Python dataclass** (`MemCPConfig`) that reads environment variables with sensible defaults:

```python
@dataclass
class MemCPConfig:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("MEMCP_DATA_DIR", "~/.memcp"))
    )
    max_memory_mb: int = field(
        default_factory=lambda: int(os.getenv("MEMCP_MAX_MEMORY_MB", "2048"))
    )
    max_insights: int = field(
        default_factory=lambda: int(os.getenv("MEMCP_MAX_INSIGHTS", "10000"))
    )
    max_context_size_mb: int = field(
        default_factory=lambda: int(os.getenv("MEMCP_MAX_CONTEXT_SIZE_MB", "10"))
    )
    importance_decay_days: int = field(
        default_factory=lambda: int(os.getenv("MEMCP_IMPORTANCE_DECAY_DAYS", "30"))
    )
    retention_archive_days: int = field(
        default_factory=lambda: int(os.getenv("MEMCP_RETENTION_ARCHIVE_DAYS", "30"))
    )
    retention_purge_days: int = field(
        default_factory=lambda: int(os.getenv("MEMCP_RETENTION_PURGE_DAYS", "180"))
    )
```

### Design Principles

- **All env vars prefixed with `MEMCP_`** — No namespace collisions with other tools
- **Sensible defaults** — Zero configuration required for standard local usage
- **Singleton pattern** — `get_config()` creates one instance, reused everywhere
- **Directory auto-creation** — `ensure_dirs()` creates all subdirectories on first access
- **Path expansion** — `~/.memcp` is expanded to absolute path in `__post_init__`

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEMCP_DATA_DIR` | `~/.memcp` | Root data directory |
| `MEMCP_MAX_MEMORY_MB` | `2048` | Maximum memory usage |
| `MEMCP_MAX_INSIGHTS` | `10000` | Hard limit on insight count |
| `MEMCP_MAX_CONTEXT_SIZE_MB` | `10` | Maximum size per context variable |
| `MEMCP_IMPORTANCE_DECAY_DAYS` | `30` | Half-life for importance decay |
| `MEMCP_RETENTION_ARCHIVE_DAYS` | `30` | Days before archiving unused items |
| `MEMCP_RETENTION_PURGE_DAYS` | `180` | Days before purging archived items |

## Consequences

### Positive

- **Environment parity**: Same code runs locally and in Docker — only env vars differ.
- **Docker-native**: `docker run -e MEMCP_DATA_DIR=/data` overrides the data directory without code changes.
- **CI-friendly**: `MEMCP_DATA_DIR=$RUNNER_TEMP/memcp-test` isolates test data per CI run.
- **No config file parsing**: No YAML, TOML, or INI files to read, validate, and handle errors for. Env vars are built into every OS and container runtime.
- **Discoverable**: All configuration is visible in one dataclass. Grep for `MEMCP_` to find every configurable value.
- **Immutable after init**: Config is read once at startup. No runtime config changes that could cause inconsistent state.

### Negative

- **No config file option**: Users who prefer `.memcprc` or `memcp.toml` must use env vars or wrapper scripts. This is intentional — config files add parsing code, file discovery logic, and merge-with-env-var precedence rules.
- **Type conversion in lambdas**: `int(os.getenv(...))` will raise `ValueError` on malformed input with an unhelpful error message. Mitigated by simple types (all ints and paths).
- **No validation**: No range checks on values. `MEMCP_MAX_INSIGHTS=-1` would be accepted. Kept simple since this is operator-facing config, not user input.
- **Singleton**: Global mutable state (the `_config` singleton). Makes testing harder — tests must reset the singleton. Mitigated by `conftest.py` fixtures that create isolated `MemCPConfig` instances with `tmp_path`.

## Alternatives Considered

### TOML/YAML Config File

Read configuration from `~/.memcp/config.toml` or `memcp.yaml`. Rejected because:
- Adds a dependency (tomli for Python <3.11, or PyYAML)
- Config file discovery logic adds complexity (where to look, merge order with env vars)
- Docker and CI environments pass config more naturally via env vars than mounted config files
- The 12-Factor methodology explicitly recommends against config files for deployment configuration

### Pydantic Settings

Use `pydantic-settings` for automatic env var binding with validation. Rejected because:
- Adds a dependency (`pydantic-settings` is separate from `pydantic`)
- Our config is simple enough (7 fields, all primitive types) that a plain dataclass suffices
- `pydantic-settings` is powerful but overkill for this use case

### Click/Typer CLI Arguments

Pass configuration as CLI arguments: `memcp --data-dir /data --max-insights 5000`. Rejected because:
- MCP servers are started by Claude Code, not directly by users. CLI args would need to be configured in the MCP registration command.
- `claude mcp add memcp ... -- -m memcp --data-dir /data` is less ergonomic than setting an env var
- Env vars are inherited automatically by child processes; CLI args are not
