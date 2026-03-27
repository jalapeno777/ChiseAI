"""Tests for belief graph and contradiction resolution.

Tests cover:
- BeliefGraph construction and traversal
- Relationship management
- Contradiction detection
- Resolution suggestion generation
- Resolution application
- Graph persistence round-trip
- Performance with 100+ beliefs
"""

from __future__ import annotations

from datetime import UTC, datetime

from autonomous_cognition.beliefs.graph import BeliefGraph
from autonomous_cognition.beliefs.models import (
    Belief,
    BeliefConflict,
    BeliefRelationship,
    RelationshipType,
)
from autonomous_cognition.contradiction_resolver import (
    AppliedResolution,
    ContradictionResolver,
    ResolutionSuggestion,
    ResolutionType,
)


class TestBeliefGraphConstruction:
    """Test BeliefGraph node and edge management."""

    def test_add_belief(self) -> None:
        """Should add belief as node in graph."""
        graph = BeliefGraph()
        belief = Belief(
            belief_id="b1",
            statement="Test statement",
            domain="test",
            confidence=0.8,
        )
        graph.add_belief(belief)

        assert graph.belief_count() == 1
        assert graph.get_belief("b1") == belief

    def test_add_relationship(self) -> None:
        """Should add relationship as edge in graph."""
        graph = BeliefGraph()
        b1 = Belief(belief_id="b1", statement="S1", domain="test", confidence=0.8)
        b2 = Belief(belief_id="b2", statement="S2", domain="test", confidence=0.6)
        graph.add_belief(b1)
        graph.add_belief(b2)

        rel = BeliefRelationship(
            relationship_id="r1",
            source_belief_id="b1",
            target_belief_id="b2",
            relationship_type=RelationshipType.SUPPORTS.value,
            strength=0.9,
        )
        graph.add_relationship(rel)

        assert graph.relationship_count() == 1
        assert graph.get_relationship("r1") == rel

    def test_add_relationship_auto_creates_nodes(self) -> None:
        """Should create placeholder nodes if not present."""
        graph = BeliefGraph()
        rel = BeliefRelationship(
            relationship_id="r1",
            source_belief_id="b1",
            target_belief_id="b2",
            relationship_type=RelationshipType.SUPPORTS.value,
        )
        graph.add_relationship(rel)

        # Should have placeholder nodes
        assert graph.belief_count() == 2
        assert graph.get_belief("b1") is not None
        assert graph.get_belief("b2") is not None


class TestBeliefGraphTraversal:
    """Test graph traversal operations."""

    def setup_method(self) -> None:
        """Set up a test graph with known structure."""
        self.graph = BeliefGraph()

        # Create beliefs
        beliefs = [
            Belief(belief_id="b1", statement="S1", domain="test", confidence=0.9),
            Belief(belief_id="b2", statement="S2", domain="test", confidence=0.7),
            Belief(belief_id="b3", statement="S3", domain="test", confidence=0.6),
            Belief(belief_id="b4", statement="S4", domain="other", confidence=0.5),
        ]
        for b in beliefs:
            self.graph.add_belief(b)

        # Create relationships: b1 -> b2 -> b3 (chain), b2 -> b4 (cross)
        self.graph.add_relationship(
            BeliefRelationship(
                relationship_id="r1",
                source_belief_id="b1",
                target_belief_id="b2",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )
        self.graph.add_relationship(
            BeliefRelationship(
                relationship_id="r2",
                source_belief_id="b2",
                target_belief_id="b3",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )
        self.graph.add_relationship(
            BeliefRelationship(
                relationship_id="r3",
                source_belief_id="b2",
                target_belief_id="b4",
                relationship_type=RelationshipType.RELATED.value,
            )
        )

    def test_get_neighbors(self) -> None:
        """Should return directly connected beliefs."""
        neighbors = self.graph.get_neighbors("b1")
        neighbor_ids = {n.belief_id for n in neighbors}

        assert "b2" in neighbor_ids
        assert len(neighbor_ids) == 1

    def test_get_neighbors_b2(self) -> None:
        """b2 should be connected to b1, b3, and b4."""
        neighbors = self.graph.get_neighbors("b2")
        neighbor_ids = {n.belief_id for n in neighbors}

        assert "b1" in neighbor_ids
        assert "b3" in neighbor_ids
        assert "b4" in neighbor_ids
        assert len(neighbor_ids) == 3

    def test_get_transitive_closure(self) -> None:
        """Should return all reachable beliefs from starting node."""
        closure = self.graph.get_transitive_closure("b1")

        assert "b2" in closure
        assert "b3" in closure
        assert "b4" in closure  # reachable via b2

    def test_get_transitive_closure_max_depth(self) -> None:
        """Should respect max_depth parameter."""
        closure = self.graph.get_transitive_closure("b1", max_depth=1)

        assert "b2" in closure
        assert "b3" not in closure  # depth 2
        assert "b4" not in closure  # depth 2

    def test_find_paths(self) -> None:
        """Should find all paths between two beliefs."""
        paths = self.graph.find_paths("b1", "b3")

        assert len(paths) >= 1
        assert all(p[0] == "b1" and p[-1] == "b3" for p in paths)

    def test_find_paths_no_connection(self) -> None:
        """Should return empty list for unconnected beliefs."""
        # Create isolated belief
        self.graph.add_belief(
            Belief(
                belief_id="isolated",
                statement="isolated",
                domain="test",
                confidence=0.5,
            )
        )

        paths = self.graph.find_paths("isolated", "b1")
        assert len(paths) == 0

    def test_find_paths_with_cycle(self) -> None:
        """Should handle cycles without infinite loops."""
        # Create a graph with a cycle: b1 -> b2 -> b3 -> b1
        graph = BeliefGraph()
        graph.add_belief(
            Belief(belief_id="b1", statement="S1", domain="test", confidence=0.8)
        )
        graph.add_belief(
            Belief(belief_id="b2", statement="S2", domain="test", confidence=0.8)
        )
        graph.add_belief(
            Belief(belief_id="b3", statement="S3", domain="test", confidence=0.8)
        )

        graph.add_relationship(
            BeliefRelationship(
                relationship_id="r1",
                source_belief_id="b1",
                target_belief_id="b2",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )
        graph.add_relationship(
            BeliefRelationship(
                relationship_id="r2",
                source_belief_id="b2",
                target_belief_id="b3",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )
        graph.add_relationship(
            BeliefRelationship(
                relationship_id="r3",
                source_belief_id="b3",
                target_belief_id="b1",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )

        # find_paths should not infinite loop on cycles
        paths = graph.find_paths("b1", "b1", max_length=5)
        # Should find paths that don't revisit nodes
        assert isinstance(paths, list)

    def test_transitive_closure_with_cycle(self) -> None:
        """Should handle cycles in transitive closure without infinite loops."""
        graph = BeliefGraph()
        graph.add_belief(
            Belief(belief_id="b1", statement="S1", domain="test", confidence=0.8)
        )
        graph.add_belief(
            Belief(belief_id="b2", statement="S2", domain="test", confidence=0.8)
        )

        # Create two-way edge (cycle of depth 1)
        graph.add_relationship(
            BeliefRelationship(
                relationship_id="r1",
                source_belief_id="b1",
                target_belief_id="b2",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )
        graph.add_relationship(
            BeliefRelationship(
                relationship_id="r2",
                source_belief_id="b2",
                target_belief_id="b1",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )

        # Should complete without infinite loop
        closure = graph.get_transitive_closure("b1")
        assert "b2" in closure

    def test_get_subgraph(self) -> None:
        """Should return beliefs and relationships within a domain."""
        subgraph = self.graph.get_subgraph("test")

        assert subgraph.belief_count() == 3
        assert subgraph.get_belief("b4") is None  # different domain

    def test_get_subgraph_includes_relationships(self) -> None:
        """Subgraph should include relationships between domain beliefs."""
        subgraph = self.graph.get_subgraph("test")

        # b1-b2 and b2-b3 should be included
        assert subgraph.relationship_count() == 2


class TestBeliefGraphPersistence:
    """Test graph persistence operations."""

    def test_save_and_load_empty_graph(self) -> None:
        """Should handle empty graph persistence."""
        # Clear Redis keys for isolation using proper hdel
        from tools.redis_state import redis_state_hdel, redis_state_hgetall

        graph_index_key = "bmad:chiseai:autocog:belief_graph:index"
        graph_rel_key = "bmad:chiseai:autocog:belief_graph:relationships"

        try:
            # Delete all belief entries from the graph index hash
            belief_data = redis_state_hgetall(graph_index_key) or {}
            for field_name in list(belief_data.keys()):
                redis_state_hdel(graph_index_key, field_name)

            # Delete all relationship entries from the relationships hash
            rel_data = redis_state_hgetall(graph_rel_key) or {}
            for field_name in list(rel_data.keys()):
                redis_state_hdel(graph_rel_key, field_name)
        except Exception:
            pass  # Ignore if Redis not available

        graph = BeliefGraph()
        # Should not raise
        graph.save_to_redis()

        graph2 = BeliefGraph()
        graph2.load_from_redis()

        assert graph2.belief_count() == 0
        assert graph2.relationship_count() == 0

    def test_save_and_load_graph(self) -> None:
        """Should persist and reconstruct graph correctly."""
        graph = BeliefGraph()
        graph.add_belief(
            Belief(belief_id="b1", statement="S1", domain="test", confidence=0.8)
        )
        graph.add_belief(
            Belief(belief_id="b2", statement="S2", domain="test", confidence=0.6)
        )
        graph.add_relationship(
            BeliefRelationship(
                relationship_id="r1",
                source_belief_id="b1",
                target_belief_id="b2",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )

        graph.save_to_redis()

        graph2 = BeliefGraph()
        graph2.load_from_redis()

        assert graph2.belief_count() == 2
        assert graph2.relationship_count() == 1
        assert graph2.get_belief("b1") is not None
        assert graph2.get_relationship("r1") is not None


class TestBeliefGraphNetworkX:
    """Test networkx export functionality."""

    def test_to_networkx_no_library(self) -> None:
        """Should handle missing networkx gracefully."""
        graph = BeliefGraph()
        graph.add_belief(
            Belief(belief_id="b1", statement="S1", domain="test", confidence=0.8)
        )

        # Even without networkx, should return None without crashing
        result = graph.to_networkx()
        # Result depends on whether networkx is installed


class TestRelationshipTypes:
    """Test RelationshipType enum values."""

    def test_relationship_type_values(self) -> None:
        """Should have correct enum values."""
        assert RelationshipType.SUPPORTS.value == "supports"
        assert RelationshipType.CONTRADICTS.value == "contradicts"
        assert RelationshipType.SUPERSEDES.value == "supersedes"
        assert RelationshipType.RELATED.value == "related"


class TestContradictionResolverDetection:
    """Test contradiction detection."""

    def setup_method(self) -> None:
        """Set up resolver with test graph."""
        self.graph = BeliefGraph()

        # Create conflicting beliefs
        self.graph.add_belief(
            Belief(
                belief_id="b1",
                statement="System is healthy",
                domain="health",
                confidence=0.9,
                evidence_refs=["ev1"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="b2",
                statement="System is failing",
                domain="health",
                confidence=0.7,
                evidence_refs=["ev2"],
            )
        )

        # Add contradicts relationship
        self.graph.add_relationship(
            BeliefRelationship(
                relationship_id="r1",
                source_belief_id="b1",
                target_belief_id="b2",
                relationship_type=RelationshipType.CONTRADICTS.value,
                strength=1.0,
            )
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_detect_direct_contradictions(self) -> None:
        """Should detect contradictions from CONTRADICTS edges."""
        conflicts = self.resolver.detect_contradictions()

        assert len(conflicts) >= 1
        conflict_ids = {c.conflict_id for c in conflicts}

        # Should find b1-b2 conflict
        found = any(
            (c.belief_id_a == "b1" and c.belief_id_b == "b2")
            or (c.belief_id_a == "b2" and c.belief_id_b == "b1")
            for c in conflicts
        )
        assert found


class TestResolutionSuggestionGeneration:
    """Test resolution suggestion generation."""

    def setup_method(self) -> None:
        """Set up resolver with conflicting beliefs."""
        self.graph = BeliefGraph()

        self.graph.add_belief(
            Belief(
                belief_id="b1",
                statement="Market is bullish",
                domain="market",
                confidence=0.85,
                evidence_refs=["ev1", "ev2"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="b2",
                statement="Market is bearish",
                domain="market",
                confidence=0.6,
                evidence_refs=["ev3"],
            )
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_generate_suggestions_for_conflict(self) -> None:
        """Should generate multiple resolution suggestions."""
        conflict = BeliefConflict(
            conflict_id="c1",
            belief_id_a="b1",
            belief_id_b="b2",
            similarity=0.3,
            severity="high",
            reason="Direct contradiction",
        )

        suggestions = self.resolver.generate_resolution_suggestions(conflict)

        assert len(suggestions) >= 3
        suggestion_types = {s.resolution_type for s in suggestions}
        assert ResolutionType.CONFIDENCE_ADJUSTMENT in suggestion_types
        assert ResolutionType.EVIDENCE_REVIEW in suggestion_types
        assert ResolutionType.ARCHIVE_BELIEF in suggestion_types

    def test_suggestion_has_confidence_adjustment(self) -> None:
        """Confidence adjustment suggestion should have valid adjustment."""
        conflict = BeliefConflict(
            conflict_id="c1",
            belief_id_a="b1",
            belief_id_b="b2",
            similarity=0.3,
            severity="high",
            reason="Test",
        )

        suggestions = self.resolver.generate_resolution_suggestions(conflict)

        conf_adj = next(
            s
            for s in suggestions
            if s.resolution_type == ResolutionType.CONFIDENCE_ADJUSTMENT
        )

        assert conf_adj.confidence_adjustment is not None
        assert 0.0 <= conf_adj.confidence_adjustment <= 1.0

    def test_high_similarity_triggers_merge_suggestion(self) -> None:
        """High similarity conflict should suggest merge."""
        conflict = BeliefConflict(
            conflict_id="c1",
            belief_id_a="b1",
            belief_id_b="b2",
            similarity=0.85,  # High similarity
            severity="medium",
            reason="Similar statements",
        )

        suggestions = self.resolver.generate_resolution_suggestions(conflict)

        merge_suggestions = [
            s for s in suggestions if s.resolution_type == ResolutionType.MERGE_BELIEFS
        ]
        assert len(merge_suggestions) == 1


class TestResolutionApplication:
    """Test resolution application."""

    def setup_method(self) -> None:
        """Set up resolver and store."""
        self.graph = BeliefGraph()
        self.graph.add_belief(
            Belief(
                belief_id="b1",
                statement="System is healthy",
                domain="health",
                confidence=0.9,
                evidence_refs=["ev1"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="b2",
                statement="System is unhealthy",
                domain="health",
                confidence=0.5,
                evidence_refs=["ev2"],
            )
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_apply_confidence_adjustment(self) -> None:
        """Should adjust belief confidence."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.CONFIDENCE_ADJUSTMENT,
            target_belief_id="b2",
            source_belief_id="b1",
            confidence_adjustment=0.3,
            reason="Lower confidence",
        )

        resolution = self.resolver.apply_resolution(suggestion)

        assert resolution is not None
        assert resolution.resolution_type == ResolutionType.CONFIDENCE_ADJUSTMENT
        assert self.graph.get_belief("b2").confidence == 0.3

    def test_apply_archive(self) -> None:
        """Should archive belief."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.ARCHIVE_BELIEF,
            target_belief_id="b2",
            source_belief_id="b1",
            archive=True,
            reason="Archive outdated belief",
        )

        resolution = self.resolver.apply_resolution(suggestion)

        assert resolution is not None
        assert resolution.archived is True
        assert self.graph.get_belief("b2").status == "archived"

    def test_resolution_history_tracked(self) -> None:
        """Should track applied resolutions."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.EVIDENCE_REVIEW,
            target_belief_id="b1",
            source_belief_id="b2",
            reason="Flag for review",
        )

        self.resolver.apply_resolution(suggestion)

        history = self.resolver.get_resolution_history()
        assert len(history) == 1
        assert history[0].conflict_id == "c1"


class TestResolutionExplanation:
    """Test resolution explanation generation."""

    def test_explain_resolution(self) -> None:
        """Should generate human-readable explanation."""
        resolution = AppliedResolution(
            resolution_id="r1",
            conflict_id="c1",
            resolution_type=ResolutionType.CONFIDENCE_ADJUSTMENT,
            belief_id="b1",
            previous_confidence=0.8,
            new_confidence=0.5,
        )

        resolver = ContradictionResolver()
        explanation = resolver.explain_resolution(resolution)

        assert "r1" in explanation
        assert "0.80" in explanation
        assert "0.50" in explanation


class TestBeliefGraphPerformance:
    """Test performance with larger graphs."""

    def test_graph_with_100_beliefs(self) -> None:
        """Should handle 100+ beliefs efficiently."""
        graph = BeliefGraph()

        # Create 100 beliefs
        for i in range(100):
            graph.add_belief(
                Belief(
                    belief_id=f"b{i}",
                    statement=f"Statement {i}",
                    domain=f"domain{i % 5}",
                    confidence=0.5 + (i % 50) / 100,
                )
            )

        # Create some relationships
        for i in range(50):
            graph.add_relationship(
                BeliefRelationship(
                    relationship_id=f"r{i}",
                    source_belief_id=f"b{i}",
                    target_belief_id=f"b{i + 1}",
                    relationship_type=RelationshipType.RELATED.value,
                )
            )

        assert graph.belief_count() == 100
        assert graph.relationship_count() == 50

        # Traversal should be fast
        closure = graph.get_transitive_closure("b0")
        assert len(closure) > 0

    def test_transitive_closure_performance(self) -> None:
        """Transitive closure should complete in reasonable time."""
        import time

        graph = BeliefGraph()

        # Create chain of 100 beliefs
        for i in range(100):
            graph.add_belief(
                Belief(
                    belief_id=f"b{i}",
                    statement=f"Statement {i}",
                    domain="test",
                    confidence=0.8,
                )
            )
            if i > 0:
                graph.add_relationship(
                    BeliefRelationship(
                        relationship_id=f"r{i}",
                        source_belief_id=f"b{i - 1}",
                        target_belief_id=f"b{i}",
                        relationship_type=RelationshipType.SUPPORTS.value,
                    )
                )

        start = time.time()
        closure = graph.get_transitive_closure("b0", max_depth=50)
        elapsed = time.time() - start

        assert elapsed < 1.0  # Should complete in under 1 second
        assert len(closure) > 0


class TestBeliefRelationshipModel:
    """Test BeliefRelationship model serialization."""

    def test_to_dict(self) -> None:
        """Should serialize correctly."""
        rel = BeliefRelationship(
            relationship_id="r1",
            source_belief_id="b1",
            target_belief_id="b2",
            relationship_type="supports",
            strength=0.9,
            evidence_refs=["ev1"],
        )

        data = rel.to_dict()

        assert data["relationship_id"] == "r1"
        assert data["source_belief_id"] == "b1"
        assert data["target_belief_id"] == "b2"
        assert data["relationship_type"] == "supports"
        assert data["strength"] == 0.9

    def test_from_dict(self) -> None:
        """Should deserialize correctly."""
        data = {
            "relationship_id": "r1",
            "source_belief_id": "b1",
            "target_belief_id": "b2",
            "relationship_type": "contradicts",
            "strength": 0.8,
            "evidence_refs": ["ev1", "ev2"],
            "created_at": datetime.now(UTC).isoformat(),
        }

        rel = BeliefRelationship.from_dict(data)

        assert rel.relationship_id == "r1"
        assert rel.relationship_type == "contradicts"
        assert rel.strength == 0.8
        assert rel.evidence_refs == ["ev1", "ev2"]


class TestConflictResolutionStatus:
    """Test conflict resolution status updates."""

    def test_conflict_to_dict_includes_resolution(self) -> None:
        """BeliefConflict.to_dict should include resolution fields."""
        conflict = BeliefConflict(
            conflict_id="c1",
            belief_id_a="b1",
            belief_id_b="b2",
            similarity=0.5,
            severity="high",
            reason="Test",
            resolution_type="confidence_adjustment",
            resolution_status="applied",
        )

        data = conflict.to_dict()

        assert data["resolution_type"] == "confidence_adjustment"
        assert data["resolution_status"] == "applied"

    def test_conflict_from_dict_parses_resolution(self) -> None:
        """BeliefConflict.from_dict should parse resolution fields."""
        data = {
            "conflict_id": "c1",
            "belief_id_a": "b1",
            "belief_id_b": "b2",
            "similarity": 0.5,
            "severity": "high",
            "reason": "Test",
            "resolution_type": "archive",
            "resolution_status": "pending",
        }

        conflict = BeliefConflict.from_dict(data)

        assert conflict.resolution_type == "archive"
        assert conflict.resolution_status == "pending"
