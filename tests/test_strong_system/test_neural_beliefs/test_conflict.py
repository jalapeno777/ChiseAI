"""Tests for BeliefConflictResolver."""

import numpy as np
import pytest
from src.strong_system.belief_embeddings import ValidationError
from src.strong_system.neural_beliefs import (
    BeliefConflictResolver,
    ConflictConfig,
    ConflictResolution,
    ConflictStrategy,
    NeuralBelief,
)


class TestConflictConfig:
    """Test cases for ConflictConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = ConflictConfig()

        assert config.similarity_threshold == 0.8
        assert config.conflict_threshold == 0.3
        assert config.default_strategy == ConflictStrategy.MERGE
        assert config.min_confidence_diff == 0.2
        assert config.enable_history is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = ConflictConfig(
            similarity_threshold=0.9,
            conflict_threshold=0.5,
            default_strategy=ConflictStrategy.PRIORITIZE,
        )

        assert config.similarity_threshold == 0.9
        assert config.conflict_threshold == 0.5
        assert config.default_strategy == ConflictStrategy.PRIORITIZE

    def test_invalid_similarity_threshold(self) -> None:
        """Test validation of similarity threshold."""
        with pytest.raises(ValidationError):
            ConflictConfig(similarity_threshold=1.5)

        with pytest.raises(ValidationError):
            ConflictConfig(similarity_threshold=-0.1)

    def test_invalid_conflict_threshold(self) -> None:
        """Test validation of conflict threshold."""
        with pytest.raises(ValidationError):
            ConflictConfig(conflict_threshold=1.5)

        with pytest.raises(ValidationError):
            ConflictConfig(conflict_threshold=-0.1)

    def test_threshold_order(self) -> None:
        """Test that similarity must be greater than conflict threshold."""
        with pytest.raises(ValidationError):
            ConflictConfig(similarity_threshold=0.3, conflict_threshold=0.5)

        with pytest.raises(ValidationError):
            ConflictConfig(similarity_threshold=0.5, conflict_threshold=0.5)


class TestBeliefConflictResolver:
    """Test cases for BeliefConflictResolver."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        resolver = BeliefConflictResolver()

        assert isinstance(resolver.config, ConflictConfig)
        assert len(resolver.resolution_history) == 0
        assert len(resolver.pending_conflicts) == 0

    def test_init_custom(self) -> None:
        """Test initialization with custom config."""
        config = ConflictConfig(similarity_threshold=0.9)
        resolver = BeliefConflictResolver(config=config)

        assert resolver.config.similarity_threshold == 0.9

    def test_detect_conflict_no_conflict(self) -> None:
        """Test detecting no conflict between orthogonal beliefs."""
        resolver = BeliefConflictResolver()

        # Orthogonal vectors - not similar enough to conflict
        belief1 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.0, 1.0, 0.0]))

        conflict = resolver.detect_conflict(belief1, belief2)

        assert conflict is None

    def test_detect_conflict_similar_beliefs(self) -> None:
        """Test detecting conflict between similar but different beliefs."""
        resolver = BeliefConflictResolver()

        # Similar direction but different magnitudes
        belief1 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]), confidence=0.9)
        belief2 = NeuralBelief(vector=np.array([0.8, 0.1, 0.1]), confidence=0.9)

        conflict = resolver.detect_conflict(belief1, belief2)

        assert conflict is not None
        assert "belief1_id" in conflict
        assert "belief2_id" in conflict
        assert "conflict_score" in conflict
        assert conflict["conflict_score"] > 0.0

    def test_detect_conflict_different_dimensions(self) -> None:
        """Test that different dimensions don't conflict."""
        resolver = BeliefConflictResolver()

        belief1 = NeuralBelief(vector=np.array([1.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]))

        conflict = resolver.detect_conflict(belief1, belief2)

        assert conflict is None

    def test_detect_conflict_same_belief(self) -> None:
        """Test that identical beliefs have no conflict."""
        resolver = BeliefConflictResolver()

        belief1 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]))

        conflict = resolver.detect_conflict(belief1, belief2)

        # Identical beliefs should have low conflict score
        # (distance is 0, so conflict_score should be low)
        assert conflict is None or conflict["conflict_score"] < 0.1

    def test_find_conflicts(self) -> None:
        """Test finding all conflicts in a list."""
        resolver = BeliefConflictResolver()

        target = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]), confidence=0.9)

        candidates = [
            NeuralBelief(vector=np.array([0.0, 1.0, 0.0])),  # No conflict (orthogonal)
            NeuralBelief(vector=np.array([0.8, 0.2, 0.0]), confidence=0.9),  # Conflict
            NeuralBelief(vector=np.array([0.7, 0.3, 0.0]), confidence=0.9),  # Conflict
        ]

        conflicts = resolver.find_conflicts(target, candidates)

        assert len(conflicts) == 2
        # Should be sorted by conflict score (highest first)
        assert conflicts[0]["conflict_score"] >= conflicts[1]["conflict_score"]

    def test_resolve_conflict_merge(self) -> None:
        """Test MERGE resolution strategy."""
        resolver = BeliefConflictResolver(
            config=ConflictConfig(default_strategy=ConflictStrategy.MERGE)
        )

        # Similar vectors that will conflict (similar direction but different)
        belief1 = NeuralBelief(vector=np.array([1.0, 0.5]), confidence=0.8)
        belief2 = NeuralBelief(vector=np.array([0.5, 1.0]), confidence=0.6)

        resolution = resolver.resolve_conflict(belief1, belief2)

        assert isinstance(resolution, ConflictResolution)
        assert resolution.strategy == ConflictStrategy.MERGE
        assert resolution.winner_id == belief1.belief_id
        # Belief1 should be updated (merged)
        assert not np.allclose(belief1.vector, np.array([1.0, 0.5]))

    def test_resolve_conflict_prioritize(self) -> None:
        """Test PRIORITIZE resolution strategy."""
        resolver = BeliefConflictResolver(
            config=ConflictConfig(
                default_strategy=ConflictStrategy.PRIORITIZE,
                min_confidence_diff=0.1,
            )
        )

        # Similar vectors that will conflict
        belief1 = NeuralBelief(vector=np.array([1.0, 0.5]), confidence=0.5)
        belief2 = NeuralBelief(vector=np.array([0.5, 1.0]), confidence=0.9)

        resolution = resolver.resolve_conflict(belief1, belief2)

        assert resolution.strategy == ConflictStrategy.PRIORITIZE
        # Higher confidence belief should win
        assert belief1.confidence == pytest.approx(0.9, abs=1e-6)

    def test_resolve_conflict_prioritize_falls_back_to_merge(self) -> None:
        """Test that PRIORITIZE falls back to MERGE when confidence is close."""
        resolver = BeliefConflictResolver(
            config=ConflictConfig(
                default_strategy=ConflictStrategy.PRIORITIZE,
                min_confidence_diff=0.2,
            )
        )

        # Confidence difference is only 0.1, less than min_confidence_diff
        # Similar vectors that will conflict
        belief1 = NeuralBelief(vector=np.array([1.0, 0.5]), confidence=0.5)
        belief2 = NeuralBelief(vector=np.array([0.5, 1.0]), confidence=0.6)

        resolution = resolver.resolve_conflict(belief1, belief2)

        # Should fall back to merge (vector changed from original)
        assert not np.allclose(belief1.vector, np.array([1.0, 0.5]))

    def test_resolve_conflict_contextualize(self) -> None:
        """Test CONTEXTUALIZE resolution strategy."""
        resolver = BeliefConflictResolver(
            config=ConflictConfig(default_strategy=ConflictStrategy.CONTEXTUALIZE)
        )

        # Similar vectors that will conflict
        belief1 = NeuralBelief(vector=np.array([1.0, 0.5]))
        belief2 = NeuralBelief(vector=np.array([0.5, 1.0]))

        original_vector1 = belief1.vector.copy()
        original_vector2 = belief2.vector.copy()

        resolution = resolver.resolve_conflict(belief1, belief2)

        assert resolution.strategy == ConflictStrategy.CONTEXTUALIZE
        # Vectors should not be modified
        assert np.allclose(belief1.vector, original_vector1)
        assert np.allclose(belief2.vector, original_vector2)
        # But metadata should be updated
        assert belief1.metadata.custom.get("contextual_variant") == "primary"
        assert belief2.metadata.custom.get("contextual_variant") == "secondary"

    def test_resolve_conflict_reject(self) -> None:
        """Test REJECT resolution strategy."""
        resolver = BeliefConflictResolver(
            config=ConflictConfig(default_strategy=ConflictStrategy.REJECT)
        )

        # Similar vectors that will conflict
        belief1 = NeuralBelief(vector=np.array([1.0, 0.5]), confidence=0.8)
        belief2 = NeuralBelief(vector=np.array([0.5, 1.0]), confidence=0.9)

        original_vector = belief1.vector.copy()

        resolution = resolver.resolve_conflict(belief1, belief2)

        assert resolution.strategy == ConflictStrategy.REJECT
        assert resolution.winner_id == belief1.belief_id
        # Belief1 should be unchanged
        assert np.allclose(belief1.vector, original_vector)

    def test_resolve_conflict_flag(self) -> None:
        """Test FLAG resolution strategy."""
        resolver = BeliefConflictResolver(
            config=ConflictConfig(default_strategy=ConflictStrategy.FLAG)
        )

        belief1 = NeuralBelief(vector=np.array([1.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.0, 1.0]))

        resolution = resolver.resolve_conflict(belief1, belief2)

        assert resolution.strategy == ConflictStrategy.FLAG
        assert resolution.winner_id is None  # No automatic resolution

    def test_resolve_conflict_no_actual_conflict(self) -> None:
        """Test resolving when no actual conflict exists."""
        resolver = BeliefConflictResolver()

        # Orthogonal beliefs - no conflict
        belief1 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.0, 1.0, 0.0]))

        resolution = resolver.resolve_conflict(belief1, belief2)

        assert resolution.score == 0.0
        assert resolution.metadata.get("reason") == "no_conflict_detected"

    def test_batch_resolve(self) -> None:
        """Test batch conflict resolution."""
        resolver = BeliefConflictResolver()

        beliefs = [
            NeuralBelief(vector=np.array([1.0, 0.0, 0.0]), confidence=0.9),
            NeuralBelief(
                vector=np.array([0.8, 0.2, 0.0]), confidence=0.9
            ),  # Conflicts with 1
            NeuralBelief(vector=np.array([0.0, 1.0, 0.0]), confidence=0.9),
            NeuralBelief(
                vector=np.array([0.1, 0.9, 0.0]), confidence=0.9
            ),  # Conflicts with 3
        ]

        resolutions = resolver.batch_resolve(beliefs)

        assert len(resolutions) >= 1
        for resolution in resolutions:
            assert isinstance(resolution, ConflictResolution)

    def test_batch_resolve_no_conflicts(self) -> None:
        """Test batch resolve with no conflicts."""
        resolver = BeliefConflictResolver()

        beliefs = [
            NeuralBelief(vector=np.array([1.0, 0.0, 0.0])),
            NeuralBelief(vector=np.array([0.0, 1.0, 0.0])),
            NeuralBelief(vector=np.array([0.0, 0.0, 1.0])),
        ]

        resolutions = resolver.batch_resolve(beliefs)

        # All orthogonal, no conflicts
        assert len(resolutions) == 0

    def test_history_tracking(self) -> None:
        """Test that resolutions are tracked in history."""
        resolver = BeliefConflictResolver(config=ConflictConfig(enable_history=True))

        belief1 = NeuralBelief(vector=np.array([1.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.8, 0.2]))

        resolver.resolve_conflict(belief1, belief2)

        assert len(resolver.resolution_history) == 1

    def test_history_disabled(self) -> None:
        """Test that history can be disabled."""
        resolver = BeliefConflictResolver(config=ConflictConfig(enable_history=False))

        belief1 = NeuralBelief(vector=np.array([1.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.8, 0.2]))

        resolver.resolve_conflict(belief1, belief2)

        assert len(resolver.resolution_history) == 0

    def test_get_conflict_statistics(self) -> None:
        """Test conflict statistics."""
        resolver = BeliefConflictResolver()

        # Empty stats
        stats = resolver.get_conflict_statistics()
        assert stats["total_conflicts"] == 0

        # Resolve some conflicts
        belief1 = NeuralBelief(vector=np.array([1.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.8, 0.2]))

        resolver.resolve_conflict(belief1, belief2)

        stats = resolver.get_conflict_statistics()
        assert stats["total_conflicts"] == 1
        assert "strategy_counts" in stats

    def test_clear_history(self) -> None:
        """Test clearing history."""
        resolver = BeliefConflictResolver()

        belief1 = NeuralBelief(vector=np.array([1.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.8, 0.2]))

        resolver.resolve_conflict(belief1, belief2)
        assert len(resolver.resolution_history) == 1

        resolver.clear_history()

        assert len(resolver.resolution_history) == 0

    def test_resolution_to_dict(self) -> None:
        """Test ConflictResolution serialization."""
        resolution = ConflictResolution(
            conflict_id="test_1",
            belief_ids=["b1", "b2"],
            strategy=ConflictStrategy.MERGE,
            score=0.5,
            winner_id="b1",
        )

        data = resolution.to_dict()

        assert data["conflict_id"] == "test_1"
        assert data["belief_ids"] == ["b1", "b2"]
        assert data["strategy"] == "MERGE"
        assert data["score"] == 0.5
        assert data["winner_id"] == "b1"

    def test_to_dict(self) -> None:
        """Test resolver serialization."""
        resolver = BeliefConflictResolver()

        belief1 = NeuralBelief(vector=np.array([1.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.8, 0.2]))
        resolver.resolve_conflict(belief1, belief2)

        data = resolver.to_dict()

        assert "config" in data
        assert "resolution_history" in data
        assert "statistics" in data
        assert len(data["resolution_history"]) == 1
