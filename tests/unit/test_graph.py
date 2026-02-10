"""Tests for memcp.core.graph — MAGMA-inspired 4-graph memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memcp.core.fileutil import content_hash, estimate_tokens
from memcp.core.graph import (
    _CAUSAL_PATTERNS,
    GraphMemory,
    RegexEntityExtractor,
)

# ── Entity Extraction ─────────────────────────────────────────────────


class TestRegexEntityExtractor:
    def setup_method(self) -> None:
        self.extractor = RegexEntityExtractor()

    def test_extracts_file_paths(self) -> None:
        entities = self.extractor.extract("Modified src/memcp/server.py for Phase 3")
        assert any("server.py" in e for e in entities)

    def test_extracts_module_paths(self) -> None:
        entities = self.extractor.extract("Import from memcp.core.graph module")
        assert any("memcp.core.graph" in e for e in entities)

    def test_extracts_urls(self) -> None:
        entities = self.extractor.extract("See https://example.com/docs for details")
        assert any("https://example.com/docs" in e for e in entities)

    def test_extracts_camel_case(self) -> None:
        entities = self.extractor.extract("The GraphMemory class handles storage")
        assert any("GraphMemory" in e for e in entities)

    def test_no_duplicates(self) -> None:
        entities = self.extractor.extract("Use GraphMemory for GraphMemory operations")
        lower_entities = [e.lower() for e in entities]
        assert len(lower_entities) == len(set(lower_entities))

    def test_ignores_short_strings(self) -> None:
        entities = self.extractor.extract("The xy thing")
        # "xy" is too short (< 3 chars) and shouldn't match entity patterns
        assert not any(e == "xy" for e in entities)

    def test_empty_content(self) -> None:
        entities = self.extractor.extract("")
        assert entities == []


# ── Causal Pattern Detection ──────────────────────────────────────────


class TestCausalPatterns:
    def test_detects_because(self) -> None:
        assert _CAUSAL_PATTERNS.search("Chose SQLite because it's zero-config")

    def test_detects_therefore(self) -> None:
        assert _CAUSAL_PATTERNS.search("It failed, therefore we switched")

    def test_detects_due_to(self) -> None:
        assert _CAUSAL_PATTERNS.search("Error due to missing import")

    def test_detects_decided_to(self) -> None:
        assert _CAUSAL_PATTERNS.search("We decided to use FastMCP")

    def test_no_match_normal_text(self) -> None:
        assert not _CAUSAL_PATTERNS.search("The quick brown fox jumps")


# ── GraphMemory Node Operations ───────────────────────────────────────


class TestGraphMemoryNodes:
    def setup_method(self) -> None:
        # Use in-memory SQLite for tests
        self.graph = GraphMemory(db_path=":memory:")

    def teardown_method(self) -> None:
        self.graph.close()

    def _make_insight(self, **kwargs: str) -> dict:
        now = datetime.now(timezone.utc)
        defaults = {
            "id": content_hash(kwargs.get("content", "test") + now.isoformat()),
            "content": "Test insight",
            "summary": "",
            "category": "general",
            "importance": "medium",
            "effective_importance": 0.5,
            "tags": [],
            "entities": [],
            "project": "default",
            "session": "",
            "token_count": estimate_tokens(kwargs.get("content", "Test insight")),
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": now.isoformat(),
        }
        defaults.update(kwargs)
        return defaults

    def test_store_and_get(self) -> None:
        insight = self._make_insight(content="SQLite is great for graphs")
        self.graph.store(insight)
        result = self.graph.get_node(insight["id"])
        assert result is not None
        assert result["content"] == "SQLite is great for graphs"

    def test_store_auto_extracts_entities(self) -> None:
        insight = self._make_insight(content="Modified src/memcp/graph.py for GraphMemory")
        result = self.graph.store(insight)
        assert len(result["entities"]) > 0

    def test_store_preserves_provided_entities(self) -> None:
        insight = self._make_insight(
            content="Some content",
            entities=["CustomEntity"],
        )
        # Override entities with a list
        insight["entities"] = ["CustomEntity"]
        result = self.graph.store(insight)
        assert "CustomEntity" in result["entities"]

    def test_get_nonexistent_node(self) -> None:
        result = self.graph.get_node("nonexistent")
        assert result is None

    def test_delete_node(self) -> None:
        insight = self._make_insight(content="To be deleted")
        self.graph.store(insight)
        assert self.graph.delete_node(insight["id"]) is True
        assert self.graph.get_node(insight["id"]) is None

    def test_delete_nonexistent(self) -> None:
        assert self.graph.delete_node("nonexistent") is False

    def test_update_node(self) -> None:
        insight = self._make_insight(content="Original content")
        self.graph.store(insight)
        self.graph.update_node(insight["id"], {"access_count": 5})
        result = self.graph.get_node(insight["id"])
        assert result["access_count"] == 5

    def test_update_ignores_disallowed_fields(self) -> None:
        insight = self._make_insight(content="Protected content")
        self.graph.store(insight)
        # content is not in the allowed update fields
        result = self.graph.update_node(insight["id"], {"content": "hacked"})
        assert result is False
        node = self.graph.get_node(insight["id"])
        assert node["content"] == "Protected content"


# ── Edge Generation ───────────────────────────────────────────────────


class TestGraphMemoryEdges:
    def setup_method(self) -> None:
        self.graph = GraphMemory(db_path=":memory:")

    def teardown_method(self) -> None:
        self.graph.close()

    def _make_insight(self, content: str, **kwargs: str) -> dict:
        now = datetime.now(timezone.utc)
        defaults = {
            "id": content_hash(content + now.isoformat()),
            "content": content,
            "summary": "",
            "category": "general",
            "importance": "medium",
            "effective_importance": 0.5,
            "tags": kwargs.get("tags", []),
            "entities": kwargs.get("entities", []),
            "project": kwargs.get("project", "default"),
            "session": "",
            "token_count": estimate_tokens(content),
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": kwargs.get("created_at", now.isoformat()),
        }
        # Apply overrides
        for k, v in kwargs.items():
            if k not in defaults or k in ("tags", "entities", "project", "session", "created_at"):
                defaults[k] = v
        return defaults

    def test_temporal_edges_created(self) -> None:
        now = datetime.now(timezone.utc)
        ins1 = self._make_insight("First insight", created_at=now.isoformat())
        ins2 = self._make_insight(
            "Second insight",
            created_at=(now + timedelta(minutes=5)).isoformat(),
        )
        self.graph.store(ins1)
        self.graph.store(ins2)

        edges = self.graph._get_edges(ins2["id"], "temporal")
        assert len(edges) >= 1

    def test_no_temporal_edge_for_old(self) -> None:
        now = datetime.now(timezone.utc)
        ins1 = self._make_insight(
            "Old insight",
            created_at=(now - timedelta(hours=2)).isoformat(),
        )
        ins2 = self._make_insight("New insight", created_at=now.isoformat())
        self.graph.store(ins1)
        self.graph.store(ins2)

        edges = self.graph._get_edges(ins2["id"], "temporal")
        assert len(edges) == 0

    def test_entity_edges_created(self) -> None:
        ins1 = self._make_insight(
            "Working on src/memcp/graph.py",
            entities=["src/memcp/graph.py"],
        )
        ins2 = self._make_insight(
            "Updated src/memcp/graph.py tests",
            entities=["src/memcp/graph.py"],
        )
        self.graph.store(ins1)
        self.graph.store(ins2)

        edges = self.graph._get_edges(ins2["id"], "entity")
        assert len(edges) >= 1

    def test_semantic_edges_created(self) -> None:
        ins1 = self._make_insight(
            "SQLite is used for graph storage backend",
            tags=["sqlite", "graph", "storage"],
        )
        ins2 = self._make_insight(
            "The graph storage uses SQLite with WAL mode",
            tags=["sqlite", "graph"],
        )
        self.graph.store(ins1)
        self.graph.store(ins2)

        edges = self.graph._get_edges(ins2["id"], "semantic")
        assert len(edges) >= 1

    def test_causal_edges_created(self) -> None:
        ins1 = self._make_insight("SQLite provides ACID transactions and zero config setup")
        self.graph.store(ins1)

        # Small delay so IDs differ
        ins2 = self._make_insight(
            "Chose SQLite because it provides ACID transactions and zero config"
        )
        self.graph.store(ins2)

        edges = self.graph._get_edges(ins2["id"], "causal")
        assert len(edges) >= 1

    def test_delete_removes_edges(self) -> None:
        ins1 = self._make_insight("Node A", tags=["shared"])
        ins2 = self._make_insight("Node B", tags=["shared"])
        self.graph.store(ins1)
        self.graph.store(ins2)

        self.graph.delete_node(ins1["id"])
        edges = self.graph._get_edges(ins2["id"])
        # No edges should reference deleted node
        for edge in edges:
            assert edge["source_id"] != ins1["id"]
            assert edge["target_id"] != ins1["id"]


# ── Query / Traversal ─────────────────────────────────────────────────


class TestGraphMemoryQuery:
    def setup_method(self) -> None:
        self.graph = GraphMemory(db_path=":memory:")

    def teardown_method(self) -> None:
        self.graph.close()

    def _store_insights(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        insights = [
            {
                "id": content_hash(f"insight-{i}" + now.isoformat()),
                "content": content,
                "summary": "",
                "category": category,
                "importance": importance,
                "effective_importance": 0.5,
                "tags": tags,
                "entities": [],
                "project": "testproj",
                "session": "",
                "token_count": estimate_tokens(content),
                "access_count": 0,
                "last_accessed_at": None,
                "created_at": (now + timedelta(seconds=i)).isoformat(),
            }
            for i, (content, category, importance, tags) in enumerate(
                [
                    (
                        "SQLite is used for the graph backend",
                        "decision",
                        "critical",
                        ["sqlite", "architecture"],
                    ),
                    ("Redis is used for caching", "decision", "high", ["redis", "caching"]),
                    ("Found bug in the file writer", "finding", "high", ["bug", "fileutil"]),
                    ("Client prefers 500ml bottles", "preference", "medium", ["client"]),
                    ("TODO: Add pagination", "todo", "low", ["search", "ux"]),
                ]
            )
        ]
        for ins in insights:
            self.graph.store(ins)
        return insights

    def test_query_all(self) -> None:
        self._store_insights()
        results = self.graph.query(scope="all")
        assert len(results) == 5

    def test_query_by_category(self) -> None:
        self._store_insights()
        results = self.graph.query(category="decision", scope="all")
        assert len(results) == 2

    def test_query_by_importance(self) -> None:
        self._store_insights()
        results = self.graph.query(importance="critical", scope="all")
        assert len(results) == 1

    def test_query_with_keyword(self) -> None:
        self._store_insights()
        results = self.graph.query(query="SQLite", scope="all")
        assert len(results) >= 1
        assert "SQLite" in results[0]["content"]

    def test_query_with_limit(self) -> None:
        self._store_insights()
        results = self.graph.query(limit=2, scope="all")
        assert len(results) == 2

    def test_query_with_max_tokens(self) -> None:
        self._store_insights()
        results = self.graph.query(max_tokens=20, scope="all")
        total = sum(r.get("token_count", 0) for r in results)
        assert total <= 20 or len(results) == 1

    def test_query_by_project(self) -> None:
        self._store_insights()
        results = self.graph.query(project="testproj", scope="project")
        assert len(results) == 5
        results = self.graph.query(project="other", scope="project")
        assert len(results) == 0

    def test_intent_detection_why(self) -> None:
        assert self.graph._detect_intent("why did we choose SQLite?") == "why"

    def test_intent_detection_when(self) -> None:
        assert self.graph._detect_intent("when was the bug found?") == "when"

    def test_intent_detection_who(self) -> None:
        assert self.graph._detect_intent("who reported this?") == "who"

    def test_intent_detection_default(self) -> None:
        assert self.graph._detect_intent("SQLite graph storage") == "what"


# ── Get Related (Traversal) ──────────────────────────────────────────


class TestGraphMemoryRelated:
    def setup_method(self) -> None:
        self.graph = GraphMemory(db_path=":memory:")

    def teardown_method(self) -> None:
        self.graph.close()

    def test_get_related_basic(self) -> None:
        now = datetime.now(timezone.utc)
        ins1 = {
            "id": "node-a",
            "content": "SQLite for storage backend",
            "category": "decision",
            "importance": "high",
            "effective_importance": 0.75,
            "tags": ["sqlite", "storage"],
            "entities": [],
            "project": "default",
            "session": "",
            "token_count": 6,
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": now.isoformat(),
        }
        ins2 = {
            "id": "node-b",
            "content": "SQLite supports WAL mode for concurrency",
            "category": "fact",
            "importance": "medium",
            "effective_importance": 0.5,
            "tags": ["sqlite", "concurrency"],
            "entities": [],
            "project": "default",
            "session": "",
            "token_count": 8,
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": (now + timedelta(seconds=1)).isoformat(),
        }
        self.graph.store(ins1)
        self.graph.store(ins2)

        result = self.graph.get_related("node-a")
        assert result["center"]["id"] == "node-a"
        # Should have at least one related node (temporal + semantic)
        assert len(result["related"]) >= 1 or len(result["edges"]) >= 1

    def test_get_related_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            self.graph.get_related("nonexistent")

    def test_get_related_filter_by_type(self) -> None:
        now = datetime.now(timezone.utc)
        ins1 = {
            "id": "a1",
            "content": "Node A",
            "category": "general",
            "importance": "medium",
            "effective_importance": 0.5,
            "tags": ["shared"],
            "entities": ["SharedEntity"],
            "project": "default",
            "session": "",
            "token_count": 3,
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": now.isoformat(),
        }
        ins2 = {
            "id": "a2",
            "content": "Node B shared things",
            "category": "general",
            "importance": "medium",
            "effective_importance": 0.5,
            "tags": ["shared"],
            "entities": ["SharedEntity"],
            "project": "default",
            "session": "",
            "token_count": 4,
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": (now + timedelta(seconds=1)).isoformat(),
        }
        self.graph.store(ins1)
        self.graph.store(ins2)

        result_entity = self.graph.get_related("a1", edge_type="entity")
        result_causal = self.graph.get_related("a1", edge_type="causal")

        # Entity edges should exist (shared entity)
        assert len(result_entity["edges"]) >= 1
        # Causal edges should not exist
        assert len(result_causal["edges"]) == 0

    def test_get_related_depth_2(self) -> None:
        now = datetime.now(timezone.utc)
        # Create chain: A -> B -> C (via semantic edges)
        for i, (nid, content, tags) in enumerate(
            [
                ("c1", "Alpha topic database storage", ["database", "storage"]),
                ("c2", "Beta topic database optimization", ["database", "optimization"]),
                ("c3", "Gamma topic optimization and caching", ["optimization", "caching"]),
            ]
        ):
            self.graph.store(
                {
                    "id": nid,
                    "content": content,
                    "category": "general",
                    "importance": "medium",
                    "effective_importance": 0.5,
                    "tags": tags,
                    "entities": [],
                    "project": "default",
                    "session": "",
                    "token_count": estimate_tokens(content),
                    "access_count": 0,
                    "last_accessed_at": None,
                    "created_at": (now + timedelta(seconds=i)).isoformat(),
                }
            )

        # Depth 1 from c1
        result1 = self.graph.get_related("c1", depth=1)
        ids_depth1 = {n["id"] for n in result1["related"]}

        # Depth 2 from c1 should find more
        result2 = self.graph.get_related("c1", depth=2)
        ids_depth2 = {n["id"] for n in result2["related"]}
        assert len(ids_depth2) >= len(ids_depth1)


# ── Stats ─────────────────────────────────────────────────────────────


class TestGraphMemoryStats:
    def setup_method(self) -> None:
        self.graph = GraphMemory(db_path=":memory:")

    def teardown_method(self) -> None:
        self.graph.close()

    def test_empty_stats(self) -> None:
        stats = self.graph.stats()
        assert stats["node_count"] == 0
        assert stats["total_edges"] == 0

    def test_stats_after_inserts(self) -> None:
        now = datetime.now(timezone.utc)
        for i in range(3):
            self.graph.store(
                {
                    "id": f"s{i}",
                    "content": f"Insight about SQLite topic number {i}",
                    "category": "general",
                    "importance": "medium",
                    "effective_importance": 0.5,
                    "tags": ["sqlite"],
                    "entities": [],
                    "project": "myproj",
                    "session": "",
                    "token_count": 8,
                    "access_count": 0,
                    "last_accessed_at": None,
                    "created_at": (now + timedelta(seconds=i)).isoformat(),
                }
            )

        stats = self.graph.stats()
        assert stats["node_count"] == 3
        assert stats["total_edges"] >= 0

    def test_stats_filter_by_project(self) -> None:
        now = datetime.now(timezone.utc)
        self.graph.store(
            {
                "id": "p1",
                "content": "Project A insight",
                "category": "general",
                "importance": "medium",
                "effective_importance": 0.5,
                "tags": [],
                "entities": [],
                "project": "projA",
                "session": "",
                "token_count": 4,
                "access_count": 0,
                "last_accessed_at": None,
                "created_at": now.isoformat(),
            }
        )
        self.graph.store(
            {
                "id": "p2",
                "content": "Project B insight",
                "category": "general",
                "importance": "medium",
                "effective_importance": 0.5,
                "tags": [],
                "entities": [],
                "project": "projB",
                "session": "",
                "token_count": 4,
                "access_count": 0,
                "last_accessed_at": None,
                "created_at": (now + timedelta(seconds=1)).isoformat(),
            }
        )

        stats_a = self.graph.stats(project="projA")
        assert stats_a["node_count"] == 1

        stats_all = self.graph.stats()
        assert stats_all["node_count"] == 2


# ── Migration ─────────────────────────────────────────────────────────


class TestGraphMemoryMigration:
    def setup_method(self) -> None:
        self.graph = GraphMemory(db_path=":memory:")

    def teardown_method(self) -> None:
        self.graph.close()

    def test_migrate_from_json(self) -> None:
        now = datetime.now(timezone.utc)
        memory = {
            "version": "0.1.0",
            "insights": [
                {
                    "id": "legacy-1",
                    "content": "Legacy insight about SQLite",
                    "summary": "",
                    "category": "decision",
                    "importance": "high",
                    "effective_importance": 0.75,
                    "tags": ["sqlite"],
                    "entities": [],
                    "project": "default",
                    "session": "",
                    "token_count": 6,
                    "access_count": 3,
                    "last_accessed_at": None,
                    "created_at": now.isoformat(),
                },
                {
                    "id": "legacy-2",
                    "content": "Legacy insight about Redis",
                    "summary": "",
                    "category": "fact",
                    "importance": "medium",
                    "effective_importance": 0.5,
                    "tags": ["redis"],
                    "entities": [],
                    "project": "default",
                    "session": "",
                    "token_count": 5,
                    "access_count": 0,
                    "last_accessed_at": None,
                    "created_at": now.isoformat(),
                },
            ],
        }

        imported = self.graph.migrate_from_json(memory)
        assert imported == 2

        node = self.graph.get_node("legacy-1")
        assert node is not None
        assert node["content"] == "Legacy insight about SQLite"

    def test_migrate_skips_existing(self) -> None:
        now = datetime.now(timezone.utc)
        self.graph.store(
            {
                "id": "existing-1",
                "content": "Already in graph",
                "category": "general",
                "importance": "medium",
                "effective_importance": 0.5,
                "tags": [],
                "entities": [],
                "project": "default",
                "session": "",
                "token_count": 4,
                "access_count": 0,
                "last_accessed_at": None,
                "created_at": now.isoformat(),
            }
        )

        memory = {
            "insights": [
                {
                    "id": "existing-1",
                    "content": "Already in graph",
                    "category": "general",
                    "importance": "medium",
                    "effective_importance": 0.5,
                    "tags": [],
                    "entities": [],
                    "project": "default",
                    "session": "",
                    "token_count": 4,
                    "access_count": 0,
                    "last_accessed_at": None,
                    "created_at": now.isoformat(),
                },
            ],
        }

        imported = self.graph.migrate_from_json(memory)
        assert imported == 0

    def test_migrate_empty_memory(self) -> None:
        memory = {"insights": []}
        imported = self.graph.migrate_from_json(memory)
        assert imported == 0
