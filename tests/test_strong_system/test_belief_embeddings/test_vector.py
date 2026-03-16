"""Tests for BeliefVector and BeliefSchema classes."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest

from src.strong_system.belief_embeddings import (
    BeliefMetadata,
    BeliefSchema,
    BeliefVector,
    ValidationError,
)


class TestBeliefMetadata:
    """Tests for BeliefMetadata class."""

    def test_default_creation(self) -> None:
        """Test creating metadata with default values."""
        metadata = BeliefMetadata()
        assert metadata.confidence == 1.0
        assert metadata.source == "unknown"
        assert isinstance(metadata.timestamp, datetime)
        assert metadata.version == "1.0.0"
        assert metadata.custom == {}

    def test_custom_creation(self) -> None:
        """Test creating metadata with custom values."""
        now = datetime.now(UTC)
        metadata = BeliefMetadata(
            confidence=0.85,
            source="inference",
            timestamp=now,
            version="2.0.0",
            custom={"model": "test-model"},
        )
        assert metadata.confidence == 0.85
        assert metadata.source == "inference"
        assert metadata.timestamp == now
        assert metadata.version == "2.0.0"
        assert metadata.custom == {"model": "test-model"}

    def test_confidence_validation_low(self) -> None:
        """Test that confidence below 0.0 raises error."""
        with pytest.raises(ValidationError, match="Confidence must be between"):
            BeliefMetadata(confidence=-0.1)

    def test_confidence_validation_high(self) -> None:
        """Test that confidence above 1.0 raises error."""
        with pytest.raises(ValidationError, match="Confidence must be between"):
            BeliefMetadata(confidence=1.1)

    def test_source_validation_empty(self) -> None:
        """Test that empty source raises error."""
        with pytest.raises(ValidationError, match="Source must be a non-empty string"):
            BeliefMetadata(source="")

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(UTC)
        metadata = BeliefMetadata(
            confidence=0.75,
            source="training",
            timestamp=now,
            custom={"epoch": 10},
        )
        data = metadata.to_dict()
        assert data["confidence"] == 0.75
        assert data["source"] == "training"
        assert data["timestamp"] == now.isoformat()
        assert data["custom"] == {"epoch": 10}

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        now = datetime.now(UTC)
        data = {
            "confidence": 0.9,
            "source": "user",
            "timestamp": now.isoformat(),
            "version": "1.5.0",
            "custom": {"validated": True},
        }
        metadata = BeliefMetadata.from_dict(data)
        assert metadata.confidence == 0.9
        assert metadata.source == "user"
        assert metadata.timestamp == now
        assert metadata.version == "1.5.0"
        assert metadata.custom == {"validated": True}

    def test_from_dict_with_string_timestamp(self) -> None:
        """Test creation from dict with string timestamp."""
        data = {
            "confidence": 0.5,
            "source": "test",
            "timestamp": "2024-01-15T10:30:00+00:00",
        }
        metadata = BeliefMetadata.from_dict(data)
        assert metadata.timestamp == datetime.fromisoformat("2024-01-15T10:30:00+00:00")

    def test_from_dict_defaults(self) -> None:
        """Test that from_dict provides defaults for missing fields."""
        data = {}
        metadata = BeliefMetadata.from_dict(data)
        assert metadata.confidence == 1.0
        assert metadata.source == "unknown"
        assert metadata.version == "1.0.0"


class TestBeliefVector:
    """Tests for BeliefVector class."""

    def test_default_creation(self) -> None:
        """Test creating belief vector with defaults."""
        vector = np.array([1.0, 2.0, 3.0])
        belief = BeliefVector(vector=vector)
        assert np.array_equal(belief.vector, vector)
        assert isinstance(belief.metadata, BeliefMetadata)
        assert belief.belief_id.startswith("belief_")

    def test_custom_creation(self) -> None:
        """Test creating belief vector with custom values."""
        vector = np.array([0.5, 0.5, 0.5])
        metadata = BeliefMetadata(confidence=0.9, source="test")
        belief = BeliefVector(vector=vector, metadata=metadata, belief_id="test_001")
        assert np.array_equal(belief.vector, vector)
        assert belief.metadata.confidence == 0.9
        assert belief.metadata.source == "test"
        assert belief.belief_id == "test_001"

    def test_vector_validation_not_array(self) -> None:
        """Test that non-array vector raises error."""
        with pytest.raises(ValidationError, match="Vector must be numpy.ndarray"):
            BeliefVector(vector=[1, 2, 3])  # type: ignore[arg-type]

    def test_vector_validation_wrong_dimensions(self) -> None:
        """Test that multi-dimensional array raises error."""
        vector = np.array([[1.0, 2.0], [3.0, 4.0]])
        with pytest.raises(ValidationError, match="Vector must be 1-dimensional"):
            BeliefVector(vector=vector)

    def test_vector_validation_empty(self) -> None:
        """Test that empty vector raises error."""
        vector = np.array([])
        with pytest.raises(ValidationError, match="Vector cannot be empty"):
            BeliefVector(vector=vector)

    def test_vector_validation_nan_values(self) -> None:
        """Test that NaN values raise error."""
        vector = np.array([1.0, float("nan"), 3.0])
        with pytest.raises(ValidationError, match="non-finite values"):
            BeliefVector(vector=vector)

    def test_vector_validation_inf_values(self) -> None:
        """Test that Inf values raise error."""
        vector = np.array([1.0, float("inf"), 3.0])
        with pytest.raises(ValidationError, match="non-finite values"):
            BeliefVector(vector=vector)

    def test_dimension_property(self) -> None:
        """Test dimension property."""
        belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        assert belief.dimension == 5
        assert len(belief) == 5

    def test_magnitude_property(self) -> None:
        """Test magnitude property."""
        belief = BeliefVector(vector=np.array([3.0, 4.0]))
        assert belief.magnitude == 5.0

    def test_normalize_l2(self) -> None:
        """Test L2 normalization."""
        vector = np.array([3.0, 4.0])
        belief = BeliefVector(vector=vector)
        normalized = belief.normalize(method="l2")
        assert np.allclose(normalized.magnitude, 1.0)
        assert np.allclose(normalized.vector, np.array([0.6, 0.8]))

    def test_normalize_zero_vector(self) -> None:
        """Test that normalizing zero vector raises error."""
        belief = BeliefVector(vector=np.array([0.0, 0.0, 0.0]))
        with pytest.raises(ValidationError, match="Cannot normalize zero vector"):
            belief.normalize()

    def test_normalize_unknown_method(self) -> None:
        """Test that unknown normalization method raises error."""
        belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        with pytest.raises(ValidationError, match="Unknown normalization method"):
            belief.normalize(method="unknown")

    def test_cosine_similarity_identical(self) -> None:
        """Test cosine similarity with identical vectors."""
        vector = np.array([1.0, 2.0, 3.0])
        belief1 = BeliefVector(vector=vector)
        belief2 = BeliefVector(vector=vector.copy())
        similarity = belief1.cosine_similarity(belief2)
        assert np.allclose(similarity, 1.0)

    def test_cosine_similarity_opposite(self) -> None:
        """Test cosine similarity with opposite vectors."""
        belief1 = BeliefVector(vector=np.array([1.0, 0.0, 0.0]))
        belief2 = BeliefVector(vector=np.array([-1.0, 0.0, 0.0]))
        similarity = belief1.cosine_similarity(belief2)
        assert np.allclose(similarity, -1.0)

    def test_cosine_similarity_dimension_mismatch(self) -> None:
        """Test that dimension mismatch raises error."""
        belief1 = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        belief2 = BeliefVector(vector=np.array([1.0, 2.0]))
        with pytest.raises(ValidationError, match="Dimension mismatch"):
            belief1.cosine_similarity(belief2)

    def test_cosine_similarity_zero_vector(self) -> None:
        """Test that zero vector in similarity raises error."""
        belief1 = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        belief2 = BeliefVector(vector=np.array([0.0, 0.0, 0.0]))
        with pytest.raises(ValidationError, match="zero vector"):
            belief1.cosine_similarity(belief2)

    def test_euclidean_distance(self) -> None:
        """Test Euclidean distance calculation."""
        belief1 = BeliefVector(vector=np.array([0.0, 0.0]))
        belief2 = BeliefVector(vector=np.array([3.0, 4.0]))
        distance = belief1.euclidean_distance(belief2)
        assert distance == 5.0

    def test_euclidean_distance_dimension_mismatch(self) -> None:
        """Test that dimension mismatch in distance raises error."""
        belief1 = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        belief2 = BeliefVector(vector=np.array([1.0, 2.0]))
        with pytest.raises(ValidationError, match="Dimension mismatch"):
            belief1.euclidean_distance(belief2)

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        vector = np.array([1.0, 2.0, 3.0])
        metadata = BeliefMetadata(confidence=0.8, source="test")
        belief = BeliefVector(vector=vector, metadata=metadata, belief_id="test_001")
        data = belief.to_dict()
        assert data["belief_id"] == "test_001"
        assert data["vector"] == [1.0, 2.0, 3.0]
        assert data["metadata"]["confidence"] == 0.8
        assert data["metadata"]["source"] == "test"

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "belief_id": "test_002",
            "vector": [0.5, 1.5, 2.5],
            "metadata": {
                "confidence": 0.75,
                "source": "inference",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }
        belief = BeliefVector.from_dict(data)
        assert belief.belief_id == "test_002"
        assert np.allclose(belief.vector, np.array([0.5, 1.5, 2.5]))
        assert belief.metadata.confidence == 0.75
        assert belief.metadata.source == "inference"

    def test_from_dict_with_json_string_vector(self) -> None:
        """Test creation from dict with JSON string vector."""
        data = {
            "belief_id": "test_003",
            "vector": json.dumps([1.0, 2.0, 3.0]),
            "metadata": {},
        }
        belief = BeliefVector.from_dict(data)
        assert np.allclose(belief.vector, np.array([1.0, 2.0, 3.0]))

    def test_equality(self) -> None:
        """Test equality comparison."""
        vector = np.array([1.0, 2.0, 3.0])
        metadata = BeliefMetadata(confidence=0.9)
        belief1 = BeliefVector(vector=vector, metadata=metadata, belief_id="id1")
        belief2 = BeliefVector(vector=vector.copy(), metadata=metadata, belief_id="id1")
        belief3 = BeliefVector(
            vector=np.array([1.0, 2.0, 3.1]), metadata=metadata, belief_id="id1"
        )
        assert belief1 == belief2
        assert belief1 != belief3

    def test_equality_different_types(self) -> None:
        """Test equality with different types."""
        belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        assert belief != "not a belief"
        assert belief != 123
        assert belief is not None


class TestBeliefSchema:
    """Tests for BeliefSchema class."""

    def test_default_creation(self) -> None:
        """Test creating schema with defaults."""
        schema = BeliefSchema()
        assert schema.expected_dimension is None
        assert schema.min_confidence == 0.0
        assert schema.max_confidence == 1.0
        assert schema.allowed_sources == []
        assert schema.require_finite is True
        assert schema.max_magnitude is None

    def test_custom_creation(self) -> None:
        """Test creating schema with custom values."""
        schema = BeliefSchema(
            expected_dimension=384,
            min_confidence=0.5,
            max_confidence=0.95,
            allowed_sources=["inference", "training"],
            require_finite=True,
            max_magnitude=10.0,
        )
        assert schema.expected_dimension == 384
        assert schema.min_confidence == 0.5
        assert schema.max_confidence == 0.95
        assert schema.allowed_sources == ["inference", "training"]
        assert schema.require_finite is True
        assert schema.max_magnitude == 10.0

    def test_validate_dimension(self) -> None:
        """Test dimension validation."""
        schema = BeliefSchema(expected_dimension=3)
        valid_belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        invalid_belief = BeliefVector(vector=np.array([1.0, 2.0]))

        schema.validate(valid_belief)  # Should not raise

        with pytest.raises(ValidationError, match="Expected dimension 3"):
            schema.validate(invalid_belief)

    def test_validate_confidence_range(self) -> None:
        """Test confidence range validation."""
        schema = BeliefSchema(min_confidence=0.3, max_confidence=0.8)
        valid_belief = BeliefVector(
            vector=np.array([1.0, 2.0]),
            metadata=BeliefMetadata(confidence=0.5),
        )
        low_belief = BeliefVector(
            vector=np.array([1.0, 2.0]),
            metadata=BeliefMetadata(confidence=0.1),
        )
        high_belief = BeliefVector(
            vector=np.array([1.0, 2.0]),
            metadata=BeliefMetadata(confidence=0.9),
        )

        schema.validate(valid_belief)  # Should not raise

        with pytest.raises(ValidationError, match="not in range"):
            schema.validate(low_belief)

        with pytest.raises(ValidationError, match="not in range"):
            schema.validate(high_belief)

    def test_validate_source(self) -> None:
        """Test source validation."""
        schema = BeliefSchema(allowed_sources=["inference", "training"])
        valid_belief = BeliefVector(
            vector=np.array([1.0, 2.0]),
            metadata=BeliefMetadata(source="inference"),
        )
        invalid_belief = BeliefVector(
            vector=np.array([1.0, 2.0]),
            metadata=BeliefMetadata(source="user"),
        )

        schema.validate(valid_belief)  # Should not raise

        with pytest.raises(ValidationError, match="not in allowed sources"):
            schema.validate(invalid_belief)

    def test_validate_magnitude(self) -> None:
        """Test magnitude validation."""
        schema = BeliefSchema(max_magnitude=5.0)
        valid_belief = BeliefVector(vector=np.array([3.0, 4.0]))  # magnitude = 5
        invalid_belief = BeliefVector(vector=np.array([6.0, 8.0]))  # magnitude = 10

        schema.validate(valid_belief)  # Should not raise

        with pytest.raises(ValidationError, match="exceeds maximum"):
            schema.validate(invalid_belief)

    def test_is_valid(self) -> None:
        """Test is_valid convenience method."""
        schema = BeliefSchema(expected_dimension=3)
        valid_belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        invalid_belief = BeliefVector(vector=np.array([1.0, 2.0]))

        assert schema.is_valid(valid_belief) is True
        assert schema.is_valid(invalid_belief) is False

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        schema = BeliefSchema(
            expected_dimension=384,
            min_confidence=0.5,
            allowed_sources=["inference"],
        )
        data = schema.to_dict()
        assert data["expected_dimension"] == 384
        assert data["min_confidence"] == 0.5
        assert data["max_confidence"] == 1.0
        assert data["allowed_sources"] == ["inference"]
        assert data["require_finite"] is True
        assert data["max_magnitude"] is None

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "expected_dimension": 768,
            "min_confidence": 0.2,
            "max_confidence": 0.9,
            "allowed_sources": ["training", "inference"],
            "require_finite": False,
            "max_magnitude": 100.0,
        }
        schema = BeliefSchema.from_dict(data)
        assert schema.expected_dimension == 768
        assert schema.min_confidence == 0.2
        assert schema.max_confidence == 0.9
        assert schema.allowed_sources == ["training", "inference"]
        assert schema.require_finite is False
        assert schema.max_magnitude == 100.0

    def test_from_dict_defaults(self) -> None:
        """Test that from_dict provides defaults."""
        data = {}
        schema = BeliefSchema.from_dict(data)
        assert schema.expected_dimension is None
        assert schema.min_confidence == 0.0
        assert schema.max_confidence == 1.0
        assert schema.allowed_sources == []
        assert schema.require_finite is True
        assert schema.max_magnitude is None
