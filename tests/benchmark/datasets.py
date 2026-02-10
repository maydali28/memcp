"""Synthetic dataset generators for benchmarks.

All generators are **seeded** for full reproducibility.  Content is drawn from
the software-engineering domain (architecture decisions, bug reports, API
design, performance findings) — realistic MemCP use cases.
"""

from __future__ import annotations

import random
from typing import Any

from memcp.core.fileutil import content_hash, estimate_tokens

# ── Vocabulary pools ─────────────────────────────────────────────────

_CATEGORIES = ["decision", "fact", "preference", "finding", "todo", "general"]
_IMPORTANCES = ["low", "medium", "high", "critical"]
_IMPORTANCE_WEIGHTS = [0.20, 0.30, 0.30, 0.20]  # distribution

_TAG_POOL = [
    "api",
    "auth",
    "database",
    "performance",
    "security",
    "frontend",
    "backend",
    "testing",
    "ci",
    "deployment",
    "docker",
    "caching",
    "logging",
    "monitoring",
    "refactor",
    "bugfix",
    "migration",
    "schema",
    "config",
    "docs",
]

_ENTITY_POOL = [
    "src/memcp/server.py",
    "src/memcp/core/graph.py",
    "memcp.core.memory",
    "GraphMemory",
    "ContextStore",
    "PreCompactSave",
    "SQLite",
    "FastMCP",
    "src/memcp/config.py",
    "memcp.core.search",
    "BM25",
    "RetentionManager",
    "src/memcp/core/chunker.py",
    "AuthService",
    "UserController",
    "APIGateway",
]

_DECISION_TEMPLATES = [
    "Decided to use {tech} for {purpose} because {reason}",
    "Chose {tech} over {alt} for {purpose} due to {reason}",
    "Architecture decision: {purpose} will be implemented using {tech}",
    "Selected {tech} as the {purpose} solution after evaluating {alt}",
]

_FINDING_TEMPLATES = [
    "Found a {severity} issue in {component}: {description}",
    "Performance profiling shows {component} takes {metric} under load",
    "The {component} module has a {severity} bug when {condition}",
    "Discovered that {component} {description} which leads to {consequence}",
]

_FACT_TEMPLATES = [
    "API rate limit is {number} requests per {period}",
    "The {component} service runs on port {number}",
    "{component} uses {tech} internally for {purpose}",
    "Maximum payload size for {component} is {number}KB",
]

_PREFERENCE_TEMPLATES = [
    "Team prefers {tech} for {purpose}",
    "Use {style} naming convention for {component}",
    "Always {practice} when working with {component}",
    "Prefer {tech} over {alt} for new {purpose} code",
]

_TECHS = [
    "SQLite",
    "PostgreSQL",
    "Redis",
    "FastAPI",
    "asyncio",
    "pytest",
    "Docker",
    "Kubernetes",
    "gRPC",
    "REST",
    "WebSocket",
    "JWT",
    "OAuth2",
]
_PURPOSES = [
    "authentication",
    "caching",
    "data storage",
    "message queuing",
    "search indexing",
    "session management",
    "rate limiting",
    "logging",
]
_REASONS = [
    "better performance",
    "simpler API",
    "team familiarity",
    "lower latency",
    "better documentation",
    "active maintenance",
]
_ALTS = ["MongoDB", "Memcached", "Flask", "Django", "RabbitMQ", "Kafka"]
_SEVERITIES = ["minor", "moderate", "critical", "blocking"]
_COMPONENTS = [
    "user-service",
    "auth-module",
    "payment-gateway",
    "search-engine",
    "notification-service",
    "file-storage",
    "analytics-pipeline",
]
_DESCRIPTIONS = [
    "memory leak under concurrent connections",
    "incorrect error handling on timeout",
    "missing validation on user input",
    "race condition in write path",
    "slow query on large datasets",
]
_STYLES = ["snake_case", "camelCase", "PascalCase", "kebab-case"]
_PRACTICES = [
    "write tests first",
    "add type hints",
    "use async/await",
    "validate inputs",
    "log all errors",
    "use transactions",
]


def _fill_template(rng: random.Random, template: str) -> str:
    """Fill a template string with random choices."""
    replacements = {
        "{tech}": rng.choice(_TECHS),
        "{alt}": rng.choice(_ALTS),
        "{purpose}": rng.choice(_PURPOSES),
        "{reason}": rng.choice(_REASONS),
        "{severity}": rng.choice(_SEVERITIES),
        "{component}": rng.choice(_COMPONENTS),
        "{description}": rng.choice(_DESCRIPTIONS),
        "{consequence}": rng.choice(_REASONS),
        "{condition}": rng.choice(_DESCRIPTIONS),
        "{metric}": f"{rng.randint(50, 500)}ms",
        "{number}": str(rng.randint(100, 10000)),
        "{period}": rng.choice(["minute", "second", "hour"]),
        "{style}": rng.choice(_STYLES),
        "{practice}": rng.choice(_PRACTICES),
    }
    result = template
    for key, value in replacements.items():
        result = result.replace(key, value, 1)
    return result


# ── Insight generators ───────────────────────────────────────────────


def generate_insights(n: int, seed: int = 42) -> list[dict[str, Any]]:
    """Generate *n* realistic insights with deterministic content.

    Each insight has a unique ``id`` derived from its content so that
    ground-truth query pairs can reference exact IDs.
    """
    rng = random.Random(seed)
    insights: list[dict[str, Any]] = []

    template_map = {
        "decision": _DECISION_TEMPLATES,
        "finding": _FINDING_TEMPLATES,
        "fact": _FACT_TEMPLATES,
        "preference": _PREFERENCE_TEMPLATES,
        "todo": ["TODO: {practice} for {component}"],
        "general": ["{component} notes: {description}"],
    }

    for i in range(n):
        category = rng.choices(_CATEGORIES, weights=[0.25, 0.20, 0.15, 0.20, 0.10, 0.10])[0]
        importance = rng.choices(_IMPORTANCES, weights=_IMPORTANCE_WEIGHTS)[0]
        templates = template_map[category]
        content = _fill_template(rng, rng.choice(templates))

        # Ensure uniqueness by appending index
        content = f"{content} (insight #{i})"

        tags = rng.sample(_TAG_POOL, k=rng.randint(1, 4))
        entities = rng.sample(_ENTITY_POOL, k=rng.randint(0, 3))
        insight_id = content_hash(content + str(i))

        insights.append(
            {
                "id": insight_id,
                "content": content,
                "summary": "",
                "category": category,
                "importance": importance,
                "tags": tags,
                "entities": entities,
                "project": "benchmark-project",
                "session": f"session-{i // 50}",
                "token_count": estimate_tokens(content),
            }
        )

    return insights


def generate_query_pairs(
    insights: list[dict[str, Any]], n_queries: int = 20, seed: int = 42
) -> list[tuple[str, list[str]]]:
    """Generate (query, expected_insight_ids) pairs from known content.

    Queries are derived by extracting key terms from randomly selected
    insights, so ground truth is deterministic.
    """
    rng = random.Random(seed)
    pairs: list[tuple[str, list[str]]] = []

    for _ in range(n_queries):
        # Pick 1-3 insights as the "expected" results
        sample_size = min(rng.randint(1, 3), len(insights))
        targets = rng.sample(insights, k=sample_size)

        # Build query from shared terms
        all_words: list[str] = []
        for t in targets:
            words = t["content"].split()
            # Pick 2-3 significant words (skip short ones)
            significant = [w for w in words if len(w) > 3 and w.isalpha()]
            if significant:
                all_words.extend(rng.sample(significant, k=min(2, len(significant))))

        query = " ".join(all_words[:4]) if all_words else "general query"
        expected_ids = [t["id"] for t in targets]
        pairs.append((query, expected_ids))

    return pairs


# ── Document generators ──────────────────────────────────────────────

_SECTION_TITLES = [
    "Overview",
    "Architecture",
    "Authentication",
    "Database Design",
    "API Endpoints",
    "Error Handling",
    "Performance",
    "Security",
    "Deployment",
    "Monitoring",
    "Testing Strategy",
    "Migration Plan",
    "Configuration",
    "Dependencies",
    "Caching Strategy",
    "Rate Limiting",
]

_CODE_SNIPPETS = [
    """\
```python
class AuthService:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self._token_cache: dict[str, str] = {}

    async def authenticate(self, token: str) -> User:
        if token in self._token_cache:
            return self._token_cache[token]
        user = await self._verify_token(token)
        self._token_cache[token] = user
        return user
```""",
    """\
```python
async def handle_request(request: Request) -> Response:
    try:
        data = await request.json()
        validated = Schema.parse(data)
        result = await process(validated)
        return Response(status=200, body=result)
    except ValidationError as e:
        return Response(status=400, body={"error": str(e)})
```""",
    """\
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_users_email ON users(email);
```""",
]

_PARAGRAPHS = [
    "The system uses a layered architecture with clear separation of concerns. "
    "Each layer communicates through well-defined interfaces, allowing components "
    "to be replaced or upgraded independently.",
    "Authentication is handled via JWT tokens with a 24-hour expiry. Refresh "
    "tokens are stored server-side in Redis with a 30-day TTL. All sensitive "
    "endpoints require valid authentication.",
    "Database queries are optimized using connection pooling (max 20 connections) "
    "and prepared statements. The ORM layer caches frequently accessed records "
    "in a local LRU cache with 5-minute TTL.",
    "Error handling follows a consistent pattern: all exceptions are caught at "
    "the middleware level, logged with full context, and returned as structured "
    "JSON responses with appropriate HTTP status codes.",
    "Deployment uses a blue-green strategy with automatic rollback on health "
    "check failure. The CI pipeline runs the full test suite, builds the Docker "
    "image, and pushes to the container registry.",
    "Performance monitoring uses Prometheus metrics exported via /metrics endpoint. "
    "Key metrics include request latency (p50, p95, p99), error rate, and "
    "active connection count.",
    "The caching layer uses a two-tier approach: L1 is an in-process LRU cache "
    "for hot data, L2 is Redis for shared state across instances. Cache "
    "invalidation follows a write-through pattern.",
    "Rate limiting is implemented at the API gateway level using a sliding "
    "window algorithm. Default limits are 100 requests per minute for "
    "authenticated users, 20 for anonymous.",
]


def generate_document(token_target: int, doc_type: str = "design-doc", seed: int = 42) -> str:
    """Generate a realistic Markdown document of approximately *token_target* tokens."""
    rng = random.Random(seed)
    sections: list[str] = []
    current_tokens = 0

    title = f"# {doc_type.replace('-', ' ').title()}\n\n"
    sections.append(title)
    current_tokens += estimate_tokens(title)

    section_titles = list(_SECTION_TITLES)
    rng.shuffle(section_titles)

    while current_tokens < token_target:
        if not section_titles:
            section_titles = list(_SECTION_TITLES)
            rng.shuffle(section_titles)

        heading = f"## {section_titles.pop(0)}\n\n"
        sections.append(heading)
        current_tokens += estimate_tokens(heading)

        # Add 2-4 paragraphs per section
        for _ in range(rng.randint(2, 4)):
            if current_tokens >= token_target:
                break
            para = rng.choice(_PARAGRAPHS) + "\n\n"
            sections.append(para)
            current_tokens += estimate_tokens(para)

        # Optionally add a code snippet
        if rng.random() < 0.4 and current_tokens < token_target:
            snippet = rng.choice(_CODE_SNIPPETS) + "\n\n"
            sections.append(snippet)
            current_tokens += estimate_tokens(snippet)

    return "".join(sections)


# ── Session history generators ───────────────────────────────────────


def generate_session_history(
    n_insights: int = 100,
    n_contexts: int = 3,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate a complete simulated session with insights + documents + queries."""
    insights = generate_insights(n_insights, seed=seed)
    contexts = [
        {
            "name": f"doc-{i}",
            "content": generate_document(
                token_target=10_000 + i * 5_000,
                doc_type=["design-doc", "code-file", "meeting-notes"][i % 3],
                seed=seed + i,
            ),
        }
        for i in range(n_contexts)
    ]
    queries = generate_query_pairs(insights, n_queries=20, seed=seed)
    total_tokens = sum(i["token_count"] for i in insights) + sum(
        estimate_tokens(c["content"]) for c in contexts
    )

    return {
        "insights": insights,
        "contexts": contexts,
        "queries": queries,
        "total_tokens": total_tokens,
    }


def generate_multi_session_history(
    n_sessions: int = 5,
    insights_per_session: int = 50,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Generate history spanning multiple sessions for cross-session tests."""
    sessions = []
    for i in range(n_sessions):
        session = generate_session_history(
            n_insights=insights_per_session,
            n_contexts=1,
            seed=seed + i * 1000,
        )
        # Tag all insights with session ID
        for ins in session["insights"]:
            ins["session"] = f"session-{i}"
            ins["project"] = "benchmark-project"
        sessions.append(session)
    return sessions
