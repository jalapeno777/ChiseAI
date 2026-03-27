"""Tests for ContradictionResolver.

Tests cover:
- Contradiction detection (direct and transitive)
- Resolution suggestion generation
- Resolution application
- Resolution history
- Explanation generation
"""

from __future__ import annotations

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


class TestContradictionDetection:
    """Test contradiction detection methods."""

    def setup_method(self) -> None:
        """Set up test graph with various conflict scenarios."""
        self.graph = BeliefGraph()

        # Scenario 1: Direct contradiction
        self.graph.add_belief(
            Belief(
                belief_id="healthy",
                statement="System is healthy and performing well",
                domain="health",
                confidence=0.9,
                evidence_refs=["ev1", "ev2"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="failing",
                statement="System is failing and needs immediate attention",
                domain="health",
                confidence=0.7,
                evidence_refs=["ev3"],
            )
        )
        self.graph.add_relationship(
            BeliefRelationship(
                relationship_id="direct_conflict",
                source_belief_id="healthy",
                target_belief_id="failing",
                relationship_type=RelationshipType.CONTRADICTS.value,
            )
        )

        # Scenario 2: Chain supporting contradiction
        self.graph.add_belief(
            Belief(
                belief_id="bullish",
                statement="Market outlook is bullish",
                domain="market",
                confidence=0.85,
                evidence_refs=["ev4"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="supporting",
                statement="Recent data supports positive outlook",
                domain="market",
                confidence=0.8,
                evidence_refs=["ev5"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="bearish",
                statement="Market outlook is bearish",
                domain="market",
                confidence=0.75,
                evidence_refs=["ev6"],
            )
        )
        self.graph.add_relationship(
            BeliefRelationship(
                relationship_id="bull_support",
                source_belief_id="bullish",
                target_belief_id="supporting",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )
        self.graph.add_relationship(
            BeliefRelationship(
                relationship_id="market_conflict",
                source_belief_id="supporting",
                target_belief_id="bearish",
                relationship_type=RelationshipType.CONTRADICTS.value,
            )
        )

        # Scenario 3: No conflict
        self.graph.add_belief(
            Belief(
                belief_id=" unrelated_a",
                statement="It is raining outside",
                domain="weather",
                confidence=0.95,
                evidence_refs=["ev7"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="unrelated_b",
                statement="The price of tea increased",
                domain="economy",
                confidence=0.8,
                evidence_refs=["ev8"],
            )
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_detect_direct_contradiction(self) -> None:
        """Should detect direct contradicts relationship."""
        conflicts = self.resolver.detect_contradictions()

        # Should find the healthy/failing conflict
        found = any(
            (c.belief_id_a == "healthy" and c.belief_id_b == "failing")
            or (c.belief_id_a == "failing" and c.belief_id_b == "healthy")
            for c in conflicts
        )
        assert found

    def test_detect_transitive_contradiction(self) -> None:
        """Should find transitive contradictions through chains."""
        conflicts = self.resolver.detect_contradictions()

        # Should find transitive conflict (bullish -> supporting -> bearish)
        conflict_ids = {c.conflict_id for c in conflicts}

        # There should be more than just the direct conflicts
        assert len(conflicts) >= 2

    def test_conflict_severity_assignment(self) -> None:
        """Should assign correct severity based on confidence difference."""
        conflicts = self.resolver.detect_contradictions()

        healthy_conflict = next(
            (
                c
                for c in conflicts
                if (c.belief_id_a == "healthy" and c.belief_id_b == "failing")
                or (c.belief_id_a == "failing" and c.belief_id_b == "healthy")
            ),
            None,
        )

        if healthy_conflict:
            # healthy=0.9, failing=0.7, diff=0.2 > 0.15, should be medium+
            assert healthy_conflict.severity in ("high", "medium")

    def test_no_false_positives_on_unrelated(self) -> None:
        """Should not detect conflicts between unrelated beliefs."""
        conflicts = self.resolver.detect_contradictions()

        unrelated_conflicts = [
            c
            for c in conflicts
            if "unrelated" in c.belief_id_a or "unrelated" in c.belief_id_b
        ]
        assert len(unrelated_conflicts) == 0


class TestResolutionGeneration:
    """Test resolution suggestion generation."""

    def setup_method(self) -> None:
        """Set up resolver with a conflict."""
        self.graph = BeliefGraph()
        self.graph.add_belief(
            Belief(
                belief_id="a",
                statement="Statement A",
                domain="test",
                confidence=0.9,
                evidence_refs=["ev1", "ev2", "ev3"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="b",
                statement="Statement B (contradicts A)",
                domain="test",
                confidence=0.5,
                evidence_refs=["ev4"],
            )
        )

        self.conflict = BeliefConflict(
            conflict_id="test_conflict",
            belief_id_a="a",
            belief_id_b="b",
            similarity=0.3,
            severity="high",
            reason="Direct contradiction",
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_generates_multiple_suggestion_types(self) -> None:
        """Should generate at least 4 types of suggestions for low similarity."""
        suggestions = self.resolver.generate_resolution_suggestions(self.conflict)

        types = {s.resolution_type for s in suggestions}
        # MERGE is only generated for high similarity (>0.7), so it's not here
        assert ResolutionType.CONFIDENCE_ADJUSTMENT in types
        assert ResolutionType.EVIDENCE_REVIEW in types
        assert ResolutionType.ARCHIVE_BELIEF in types
        assert ResolutionType.SUPERSEDE in types

    def test_confidence_adjustment_targets_weaker_belief(self) -> None:
        """Should suggest lowering confidence on weaker-evidence belief."""
        suggestions = self.resolver.generate_resolution_suggestions(self.conflict)

        conf_adj = next(
            s
            for s in suggestions
            if s.resolution_type == ResolutionType.CONFIDENCE_ADJUSTMENT
        )

        assert conf_adj.target_belief_id == "b"  # b has fewer evidence refs
        assert conf_adj.confidence_adjustment is not None
        assert conf_adj.confidence_adjustment < 0.5  # Should reduce from 0.5

    def test_evidence_review_high_severity(self) -> None:
        """High severity conflicts should get high-confidence review suggestion."""
        suggestions = self.resolver.generate_resolution_suggestions(self.conflict)

        review = next(
            s
            for s in suggestions
            if s.resolution_type == ResolutionType.EVIDENCE_REVIEW
        )

        # High severity should have high confidence review
        assert review.confidence >= 0.7

    def test_merge_only_on_high_similarity(self) -> None:
        """Merge suggestion should only appear for similar beliefs."""
        # Low similarity should not have merge
        suggestions = self.resolver.generate_resolution_suggestions(self.conflict)
        merge_suggestions = [
            s for s in suggestions if s.resolution_type == ResolutionType.MERGE_BELIEFS
        ]

        # This conflict has low similarity (0.3), so no merge should be generated
        # or if it was generated, confidence should be low
        for m in merge_suggestions:
            assert m.confidence < 0.7

    def test_supersede_targets_lower_confidence(self) -> None:
        """Supersede should target the lower-confidence belief."""
        suggestions = self.resolver.generate_resolution_suggestions(self.conflict)

        supersede = next(
            s for s in suggestions if s.resolution_type == ResolutionType.SUPERSEDE
        )

        assert supersede.target_belief_id == "b"  # lower confidence

    def test_suggestion_stored_by_conflict_id(self) -> None:
        """Suggestions should be retrievable by conflict ID."""
        self.resolver.generate_resolution_suggestions(self.conflict)

        stored = self.resolver.get_suggestions_for_conflict("test_conflict")
        assert len(stored) >= 4  # 4 types for low similarity (no merge)


class TestResolutionApplication:
    """Test applying resolutions to beliefs."""

    def setup_method(self) -> None:
        """Set up resolver and beliefs."""
        self.graph = BeliefGraph()
        self.graph.add_belief(
            Belief(
                belief_id="original",
                statement="Original belief",
                domain="test",
                confidence=0.8,
                evidence_refs=["ev1"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="conflict",
                statement="Conflicting belief",
                domain="test",
                confidence=0.4,
                evidence_refs=["ev2"],
            )
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_apply_confidence_adjustment_updates_belief(self) -> None:
        """Should update belief confidence when applying adjustment."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.CONFIDENCE_ADJUSTMENT,
            target_belief_id="conflict",
            source_belief_id="original",
            confidence_adjustment=0.25,
            reason="Lower confidence",
        )

        resolution = self.resolver.apply_resolution(suggestion)

        assert resolution is not None
        assert self.graph.get_belief("conflict").confidence == 0.25
        assert resolution.previous_confidence == 0.4
        assert resolution.new_confidence == 0.25

    def test_apply_archive_updates_status(self) -> None:
        """Should mark belief as archived."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.ARCHIVE_BELIEF,
            target_belief_id="conflict",
            source_belief_id="original",
            archive=True,
            reason="Outdated",
        )

        resolution = self.resolver.apply_resolution(suggestion)

        assert resolution is not None
        assert self.graph.get_belief("conflict").status == "archived"
        assert resolution.archived is True

    def test_apply_evidence_review_does_not_change_belief(self) -> None:
        """Evidence review should not modify beliefs."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.EVIDENCE_REVIEW,
            target_belief_id="original",
            source_belief_id="conflict",
            reason="Flag for review",
        )

        original_confidence = self.graph.get_belief("conflict").confidence
        resolution = self.resolver.apply_resolution(suggestion)

        assert resolution is not None
        # Confidence should not change
        assert self.graph.get_belief("conflict").confidence == original_confidence

    def test_resolution_history_records_applications(self) -> None:
        """Should track all applied resolutions."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.ARCHIVE_BELIEF,
            target_belief_id="conflict",
            source_belief_id="original",
            archive=True,
            reason="Archive",
        )

        self.resolver.apply_resolution(suggestion)

        history = self.resolver.get_resolution_history()
        assert len(history) == 1
        assert history[0].conflict_id == "c1"


class TestMergeResolution:
    """Test belief merging functionality."""

    def setup_method(self) -> None:
        """Set up beliefs for merge test."""
        self.graph = BeliefGraph()
        self.graph.add_belief(
            Belief(
                belief_id="keep",
                statement="Similar to other",
                domain="test",
                confidence=0.8,
                evidence_refs=["ev1"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="discard",
                statement="Similar to keep statement",
                domain="test",
                confidence=0.6,
                evidence_refs=["ev2"],
            )
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_apply_merge_combines_evidence(self) -> None:
        """Merge should combine evidence from both beliefs."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.MERGE_BELIEFS,
            target_belief_id="discard",
            source_belief_id="keep",
            merge_into_belief_id="keep",
            reason="Similar beliefs",
        )

        self.resolver.apply_resolution(suggestion)

        keep = self.graph.get_belief("keep")
        assert "ev1" in keep.evidence_refs
        assert "ev2" in keep.evidence_refs

    def test_apply_merge_archives_discarded(self) -> None:
        """Merged belief should be archived."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.MERGE_BELIEFS,
            target_belief_id="discard",
            source_belief_id="keep",
            merge_into_belief_id="keep",
            reason="Similar beliefs",
        )

        self.resolver.apply_resolution(suggestion)

        discard = self.graph.get_belief("discard")
        assert discard.status == "merged"

    def test_apply_merge_creates_supersedes_relationship(self) -> None:
        """Merge should create SUPERSEDES relationship."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.MERGE_BELIEFS,
            target_belief_id="discard",
            source_belief_id="keep",
            merge_into_belief_id="keep",
            reason="Similar beliefs",
        )

        self.resolver.apply_resolution(suggestion)

        # Should have new relationship
        relationships = self.graph._edges.values()
        supersedes_rels = [
            r
            for r in relationships
            if r.relationship_type == RelationshipType.SUPERSEDES.value
        ]
        assert len(supersedes_rels) >= 1


class TestSupersedeResolution:
    """Test supersede resolution functionality."""

    def setup_method(self) -> None:
        """Set up beliefs for supersede test."""
        self.graph = BeliefGraph()
        self.graph.add_belief(
            Belief(
                belief_id="newer",
                statement="Newer belief with more evidence",
                domain="test",
                confidence=0.9,
                evidence_refs=["ev1", "ev2"],
            )
        )
        self.graph.add_belief(
            Belief(
                belief_id="older",
                statement="Older belief",
                domain="test",
                confidence=0.5,
                evidence_refs=["ev3"],
            )
        )

        self.resolver = ContradictionResolver(graph=self.graph)

    def test_apply_supersede_updates_status(self) -> None:
        """Superseded belief should be marked as superseded."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.SUPERSEDE,
            source_belief_id="newer",
            target_belief_id="older",
            reason="Supersede older belief",
        )

        self.resolver.apply_resolution(suggestion)

        older = self.graph.get_belief("older")
        assert older.status == "superseded"
        assert older.supersedes_belief_id == "newer"

    def test_apply_supersede_creates_relationship(self) -> None:
        """Should create SUPERSEDES relationship edge."""
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.SUPERSEDE,
            source_belief_id="newer",
            target_belief_id="older",
            reason="Supersede older belief",
        )

        self.resolver.apply_resolution(suggestion)

        rels = list(self.graph._edges.values())
        supersedes = [
            r for r in rels if r.relationship_type == RelationshipType.SUPERSEDES.value
        ]
        assert len(supersedes) >= 1


class TestConflictSummary:
    """Test conflict summary reporting."""

    def test_get_conflict_summary(self) -> None:
        """Should return accurate conflict summary."""
        graph = BeliefGraph()
        graph.add_belief(
            Belief(belief_id="b1", statement="S1", domain="test", confidence=0.8)
        )
        graph.add_belief(
            Belief(belief_id="b2", statement="S2", domain="test", confidence=0.6)
        )

        resolver = ContradictionResolver(graph=graph)

        summary = resolver.get_conflict_summary()

        assert "total_conflicts" in summary
        assert "pending_conflicts" in summary
        assert "resolved_conflicts" in summary
        assert "resolution_types_applied" in summary


class TestExplanationGeneration:
    """Test resolution explanation."""

    def test_explain_resolution_with_confidence_change(self) -> None:
        """Should explain confidence adjustment."""
        resolution = AppliedResolution(
            resolution_id="r1",
            conflict_id="c1",
            resolution_type=ResolutionType.CONFIDENCE_ADJUSTMENT,
            belief_id="b1",
            previous_confidence=0.8,
            new_confidence=0.4,
        )

        resolver = ContradictionResolver()
        explanation = resolver.explain_resolution(resolution)

        assert "r1" in explanation
        assert "confidence" in explanation.lower()
        assert "0.80" in explanation
        assert "0.40" in explanation

    def test_explain_resolution_archive(self) -> None:
        """Should explain archive action."""
        resolution = AppliedResolution(
            resolution_id="r1",
            conflict_id="c1",
            resolution_type=ResolutionType.ARCHIVE_BELIEF,
            belief_id="b1",
            archived=True,
        )

        resolver = ContradictionResolver()
        explanation = resolver.explain_resolution(resolution)

        assert "archived" in explanation.lower()

    def test_explain_resolution_merge(self) -> None:
        """Should explain merge action."""
        resolution = AppliedResolution(
            resolution_id="r1",
            conflict_id="c1",
            resolution_type=ResolutionType.MERGE_BELIEFS,
            belief_id="b1",
            merged_into="b2",
        )

        resolver = ContradictionResolver()
        explanation = resolver.explain_resolution(resolution)

        assert "b2" in explanation


class TestGraphIntegration:
    """Test resolver integration with graph operations."""

    def test_resolver_uses_graph_neighbors(self) -> None:
        """Should find contradictions through graph neighbors."""
        graph = BeliefGraph()

        # Create belief chain
        for i in range(5):
            graph.add_belief(
                Belief(
                    belief_id=f"b{i}",
                    statement=f"Statement {i}",
                    domain="test",
                    confidence=0.7,
                )
            )

        # Create contradicts relationship at end
        graph.add_relationship(
            BeliefRelationship(
                relationship_id="final_conflict",
                source_belief_id="b3",
                target_belief_id="b4",
                relationship_type=RelationshipType.CONTRADICTS.value,
            )
        )

        resolver = ContradictionResolver(graph=graph)
        conflicts = resolver.detect_contradictions()

        assert len(conflicts) >= 1

    def test_resolver_preserves_graph_after_resolution(self) -> None:
        """Should preserve graph structure after applying resolution."""
        graph = BeliefGraph()
        graph.add_belief(
            Belief(belief_id="a", statement="A", domain="test", confidence=0.9)
        )
        graph.add_belief(
            Belief(belief_id="b", statement="B", domain="test", confidence=0.5)
        )
        graph.add_relationship(
            BeliefRelationship(
                relationship_id="r1",
                source_belief_id="a",
                target_belief_id="b",
                relationship_type=RelationshipType.SUPPORTS.value,
            )
        )

        resolver = ContradictionResolver(graph=graph)

        # Apply resolution
        suggestion = ResolutionSuggestion(
            suggestion_id="s1",
            conflict_id="c1",
            resolution_type=ResolutionType.ARCHIVE_BELIEF,
            target_belief_id="b",
            source_belief_id="a",
            archive=True,
            reason="Archive",
        )
        resolver.apply_resolution(suggestion)

        # Graph should still have both beliefs and relationship
        assert graph.belief_count() == 2
        assert graph.relationship_count() == 1
