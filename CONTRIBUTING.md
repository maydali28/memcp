# Contributing to MemCP

Thank you for your interest in contributing to MemCP! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.10 or later
- Git
- A basic understanding of the [MCP protocol](https://modelcontextprotocol.io/)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/mohamedali-may/memcp.git
cd memcp

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode with all extras
pip install -e ".[all]"

# Or install with minimal dev dependencies only
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run a specific test file
pytest tests/unit/test_memory.py -v

# Run tests matching a pattern
pytest tests/unit/ -v -k "graph"

# Run with search extras (BM25, fuzzy)
pip install -e ".[dev,search,fuzzy]"
pytest tests/unit/test_search.py -v -k "bm25 or fuzzy"

# Run with semantic extras
pip install -e ".[dev,semantic]"
pytest tests/unit/test_search.py -v -k "semantic"

# Run benchmarks
pip install -e ".[dev,benchmark]"
pytest tests/benchmark/ --benchmark-only -v
```

Tests use `tmp_path` fixtures for isolation — each test gets its own data directory. No global state is shared between tests.

### Linting

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for lint errors
ruff check src/ tests/

# Auto-fix lint errors
ruff check src/ tests/ --fix

# Check formatting
ruff format --check src/ tests/

# Auto-format
ruff format src/ tests/
```

Configuration is in `pyproject.toml`:
- Target: Python 3.10
- Line length: 100
- Rules: E, F, W, I, UP, B, SIM

## Project Architecture

MemCP follows a 3-layer delegation pattern:

```
server.py         → @mcp.tool() definitions, string I/O
tools/*.py        → Tool implementations, JSON serialization
core/*.py         → Business logic, returns dicts/objects
```

When adding or modifying functionality:

1. **Business logic** goes in `src/memcp/core/` — this is where the real work happens
2. **Tool wrappers** go in `src/memcp/tools/` — these call core functions and format results as JSON strings
3. **Tool registration** goes in `src/memcp/server.py` — `@mcp.tool()` decorators with docstrings

### Templates Directory

The `templates/` directory contains Claude Code configuration files deployed by the installer:

- `templates/CLAUDE.md` — Session instructions for Claude Code (deployed to project root)
- `templates/agents/memcp-*.md` — RLM sub-agent definitions (frontmatter + system prompt), deployed to `~/.claude/agents/`
- `templates/settings.json` — Hook registration (PreCompact, PostToolUse, Notification), merged into `~/.claude/settings.json`

When modifying sub-agents, hooks, or session instructions, **edit the files in `templates/`**, not the deployed copies. The deployed files are generated from templates by the installer.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams and detailed explanations.

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/mohamedali-may/memcp/issues) first
2. Include: Python version, OS, steps to reproduce, expected vs actual behavior
3. If possible, include a minimal test case

### Suggesting Features

1. Open an issue with the `enhancement` label
2. Describe the use case and expected behavior
3. Explain how it fits with MemCP's architecture (RLM framework, MAGMA graph, tiered search)

### Submitting Pull Requests

1. Fork the repository and create a feature branch from `main`
2. Make your changes following the code style guidelines below
3. Add or update tests for your changes
4. Ensure all tests pass: `pytest tests/unit/ -v`
5. Ensure linting passes: `ruff check src/ tests/ && ruff format --check src/ tests/`
6. Write a clear commit message describing what and why
7. Open a PR against `main`

### PR Checklist

- [ ] Tests added or updated for new/changed functionality
- [ ] All tests pass (`pytest tests/unit/ -v`)
- [ ] Lint passes (`ruff check src/ tests/`)
- [ ] Format passes (`ruff format --check src/ tests/`)
- [ ] Docstrings added for new public functions
- [ ] Tool docstrings follow the existing pattern (see `server.py`)
- [ ] No new core dependencies added (optional deps are OK under `[project.optional-dependencies]`)

## Code Style Guidelines

### General

- Follow existing patterns in the codebase
- Keep functions focused and small
- Use type hints for function signatures
- Use Pydantic models for structured data

### MCP Tools

Tool docstrings are shown to Claude as tool descriptions. They should:

- Start with a one-line summary of what the tool does
- Include a "Use this to..." paragraph explaining when to use it
- Document all parameters with `Args:` section
- Keep descriptions concise — every token counts in the context window

Example:

```python
@mcp.tool()
def memcp_example(query: str, limit: int = 10) -> str:
    """Brief summary of what this tool does.

    Use this to [explain the scenario where Claude should use this tool].

    Args:
        query: What to search for
        limit: Max results (default 10)
    """
```

### Tests

- Use `tmp_path` fixture for file system isolation
- Test both success and error paths
- Test graceful degradation (deps installed vs missing)
- Keep tests independent — no shared mutable state
- Name test files `test_{module}.py` matching the module under test

### Dependencies

MemCP has a strict dependency policy:

- **Core dependencies** (mcp, pydantic): Must remain minimal. Adding a new core dep requires strong justification.
- **Optional dependencies**: Add under `[project.optional-dependencies]` with a named extra. Code must work without them (graceful degradation).
- **Dev dependencies**: Add under the `dev` extra.

Pattern for optional imports:

```python
try:
    import bm25s
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
```

## Areas for Contribution

Here are areas where contributions are especially welcome:

### Good First Issues

- Improving test coverage for edge cases
- Adding examples to tool docstrings
- Documentation improvements

### Medium Complexity

- New chunking strategies in `core/chunker.py`
- Additional entity extraction patterns in `core/graph.py`
- Search ranking improvements in `core/search.py`

### Advanced

- New embedding provider integrations in `core/embeddings.py`
- Graph traversal optimizations in `core/graph.py`
- Performance benchmarks for search tiers

## CI/CD

GitHub Actions runs automatically on every push and PR:

| Job | What it does |
|-----|-------------|
| `lint` | Ruff check + format on Python 3.12 |
| `test-core` | Core tests on Python 3.10, 3.11, 3.12 (no optional deps) |
| `test-search` | BM25 + fuzzy search tests (with search extras) |
| `test-semantic` | Semantic search tests (with model2vec) |
| `docker` | Docker image build verification |

All CI jobs must pass before a PR can be merged.

## Questions?

- Open an issue for technical questions
- Check [docs/](docs/) for detailed reference guides
- Read [templates/CLAUDE.md](templates/CLAUDE.md) for how MemCP is used in Claude Code sessions

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
