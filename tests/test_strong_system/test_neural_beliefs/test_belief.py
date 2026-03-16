"""Tests for NeuralBelief class."""

from datetime import UTC

import numpy as np
import pytest
from src.strong_system.belief_embeddings import BeliefVector, ValidationError
from src.strong_system.neural_beliefs import GradientHistory, NeuralBelief


class TestGradientHistory:
    """Test cases for GradientHistory."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        history = GradientHistory()
        assert history.max_history == 100
        assert len(history.gradients) == 0
        assert len(history.timestamps) == 0

    def test_init_custom_max(self) -> None:
        """Test initialization with custom max_history."""
        history = GradientHistory(max_history=50)
        assert history.max_history == 50

    def test_init_invalid_max(self) -> None:
        """Test initialization with invalid max_history."""
        with pytest.raises(ValidationError):
            GradientHistory(max_history=0)

    def test_add_gradient(self) -> None:
        """Test adding gradients."""
        history = GradientHistory()
        grad = np.array([0.1, 0.2, 0.3])

        history.add_gradient(grad, step_number=1)

        assert len(history.gradients) == 1
        assert len(history.timestamps) == 1
        assert len(history.step_numbers) == 1
        assert history.step_numbers[0] == 1

    def test_max_history_trimming(self) -> None:
        """Test that old gradients are trimmed."""
        history = GradientHistory(max_history=3)

        for i in range(5):
            history.add_gradient(np.array([float(i)]), step_number=i)

        assert len(history.gradients) == 3
        assert history.step_numbers == [2, 3, 4]

    def test_get_recent_gradients(self) -> None:
        """Test retrieving recent gradients."""
        history = GradientHistory()

        for i in range(5):
            history.add_gradient(np.array([float(i)]), step_number=i)

        recent = history.get_recent_gradients(3)
        assert len(recent) == 3
        assert np.allclose(recent[0], np.array([2.0]))
        assert np.allclose(recent[2], np.array([4.0]))

    def test_compute_average_magnitude(self) -> None:
        """Test computing average gradient magnitude."""
        history = GradientHistory()

        history.add_gradient(np.array([3.0, 4.0]), step_number=1)  # magnitude = 5
        history.add_gradient(np.array([6.0, 8.0]), step_number=2)  # magnitude = 10

        avg = history.compute_average_magnitude()
        assert avg == 7.5

    def test_compute_average_magnitude_empty(self) -> None:
        """Test computing average magnitude with no gradients."""
        history = GradientHistory()
        assert history.compute_average_magnitude() == 0.0

    def test_compute_direction_consistency(self) -> None:
        """Test computing direction consistency."""
        history = GradientHistory()

        # Same direction
        history.add_gradient(np.array([1.0, 0.0]), step_number=1)
        history.add_gradient(np.array([1.0, 0.0]), step_number=2)

        consistency = history.compute_direction_consistency()
        assert consistency == pytest.approx(1.0, abs=1e-6)

    def test_compute_direction_consistency_opposite(self) -> None:
        """Test direction consistency with opposite directions."""
        history = GradientHistory()

        history.add_gradient(np.array([1.0, 0.0]), step_number=1)
        history.add_gradient(np.array([-1.0, 0.0]), step_number=2)

        consistency = history.compute_direction_consistency()
        assert consistency == pytest.approx(-1.0, abs=1e-6)

    def test_to_dict_from_dict(self) -> None:
        """Test serialization roundtrip."""
        history = GradientHistory(max_history=50)
        history.add_gradient(np.array([0.1, 0.2]), step_number=1)

        data = history.to_dict()
        restored = GradientHistory.from_dict(data)

        assert restored.max_history == 50
        assert len(restored.gradients) == 1


class TestNeuralBelief:
    """Test cases for NeuralBelief."""

    def test_init_from_array(self) -> None:
        """Test initialization from numpy array."""
        vector = np.array([0.1, 0.2, 0.3])
        belief = NeuralBelief(vector=vector, confidence=0.8)

        assert belief.dimension == 3
        assert belief.confidence == 0.8
        assert belief.requires_grad is True
        assert belief.gradient is None

    def test_init_from_belief_vector(self) -> None:
        """Test initialization from BeliefVector."""
        bv = BeliefVector(vector=np.array([0.1, 0.2, 0.3]))
        belief = NeuralBelief(vector=bv)

        assert belief.dimension == 3
        assert belief.belief_id == bv.belief_id

    def test_init_with_custom_id(self) -> None:
        """Test initialization with custom belief_id."""
        vector = np.array([0.1, 0.2])
        belief = NeuralBelief(vector=vector, belief_id="custom_id")

        assert belief.belief_id == "custom_id"

    def test_init_without_grad(self) -> None:
        """Test initialization without gradient tracking."""
        vector = np.array([0.1, 0.2])
        belief = NeuralBelief(vector=vector, requires_grad=False)

        assert belief.requires_grad is False
        assert belief.computation_node is None

    def test_vector_property(self) -> None:
        """Test vector getter and setter."""
        vector = np.array([0.1, 0.2, 0.3])
        belief = NeuralBelief(vector=vector)

        assert np.allclose(belief.vector, vector)

        new_vector = np.array([0.4, 0.5, 0.6])
        belief.vector = new_vector

        assert np.allclose(belief.vector, new_vector)

    def test_confidence_property(self) -> None:
        """Test confidence getter and setter."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2]), confidence=0.5)

        assert belief.confidence == 0.5

        belief.confidence = 0.8
        assert belief.confidence == 0.8

    def test_confidence_validation(self) -> None:
        """Test confidence validation."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2]))

        with pytest.raises(ValidationError):
            belief.confidence = 1.5

        with pytest.raises(ValidationError):
            belief.confidence = -0.1

    def test_zero_grad(self) -> None:
        """Test zeroing gradients."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2]))
        belief.set_gradient(np.array([0.01, 0.02]))

        assert belief.gradient is not None

        belief.zero_grad()

        assert belief.gradient is None

    def test_set_gradient(self) -> None:
        """Test setting gradient."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2, 0.3]))
        grad = np.array([0.01, 0.02, 0.03])

        belief.set_gradient(grad)

        assert np.allclose(belief.gradient, grad)
        assert belief.revision_count == 1
        assert len(belief.gradient_history.gradients) == 1

    def test_set_gradient_scalar(self) -> None:
        """Test setting scalar gradient."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2, 0.3]))

        belief.set_gradient(0.5)

        expected = np.array([0.5, 0.5, 0.5])
        assert np.allclose(belief.gradient, expected)

    def test_set_gradient_wrong_shape(self) -> None:
        """Test setting gradient with wrong shape."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2]))

        with pytest.raises(ValidationError):
            belief.set_gradient(np.array([0.01, 0.02, 0.03]))

    def test_apply_update(self) -> None:
        """Test applying update."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2, 0.3]))
        delta = np.array([0.01, 0.02, 0.03])

        belief.apply_update(delta)

        expected = np.array([0.11, 0.22, 0.33])
        assert np.allclose(belief.vector, expected)
        assert belief.revision_count == 1

    def test_apply_update_wrong_shape(self) -> None:
        """Test applying update with wrong shape."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2]))

        with pytest.raises(ValidationError):
            belief.apply_update(np.array([0.01, 0.02, 0.03]))

    def test_cosine_similarity(self) -> None:
        """Test cosine similarity computation."""
        belief1 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([0.0, 1.0, 0.0]))
        belief3 = NeuralBelief(vector=np.array([1.0, 0.0, 0.0]))

        # Orthogonal vectors
        sim_ortho = belief1.cosine_similarity(belief2)
        assert sim_ortho == pytest.approx(0.0, abs=1e-6)

        # Same vectors
        sim_same = belief1.cosine_similarity(belief3)
        assert sim_same == pytest.approx(1.0, abs=1e-6)

    def test_euclidean_distance(self) -> None:
        """Test Euclidean distance computation."""
        belief1 = NeuralBelief(vector=np.array([0.0, 0.0]))
        belief2 = NeuralBelief(vector=np.array([3.0, 4.0]))

        distance = belief1.euclidean_distance(belief2)
        assert distance == pytest.approx(5.0, abs=1e-6)

    def test_to_dict_from_dict(self) -> None:
        """Test serialization roundtrip."""
        belief = NeuralBelief(
            vector=np.array([0.1, 0.2, 0.3]),
            confidence=0.8,
            belief_id="test_id",
            requires_grad=True,
        )
        belief.set_gradient(np.array([0.01, 0.02, 0.03]))

        data = belief.to_dict()
        restored = NeuralBelief.from_dict(data)

        assert restored.belief_id == "test_id"
        assert restored.confidence == 0.8
        assert restored.requires_grad is True
        assert np.allclose(restored.vector, belief.vector)
        assert np.allclose(restored.gradient, belief.gradient)

    def test_repr(self) -> None:
        """Test string representation."""
        belief = NeuralBelief(vector=np.array([0.1, 0.2]), belief_id="test")

        repr_str = repr(belief)

        assert "NeuralBelief" in repr_str
        assert "test" in repr_str
        assert "dim=2" in repr_str

    def test_equality(self) -> None:
        """Test equality comparison."""
        from datetime import datetime

        from src.strong_system.belief_embeddings import BeliefMetadata, BeliefVector

        # Create a shared BeliefVector to ensure proper equality
        v = np.array([0.1, 0.2])
        metadata = BeliefMetadata(
            confidence=0.8,
            source="neural",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        )
        bv = BeliefVector(vector=v, metadata=metadata, belief_id="id1")

        belief1 = NeuralBelief(vector=bv)
        belief2 = NeuralBelief(vector=bv)  # Same BeliefVector instance

        # Different confidence
        metadata3 = BeliefMetadata(
            confidence=0.9,
            source="neural",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        )
        bv3 = BeliefVector(vector=v, metadata=metadata3, belief_id="id1")
        belief3 = NeuralBelief(vector=bv3)

        assert belief1 == belief2
        assert belief1 != belief3
        assert belief1 != "not a belief"
