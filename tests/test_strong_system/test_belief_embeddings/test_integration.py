"""Integration tests for Belief Embeddings module."""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.strong_system.belief_embeddings import (
    BeliefMetadata,
    BeliefSchema,
    BeliefSerializer,
    BeliefVector,
    ValidationError,
)


class TestEndToEndWorkflow:
    """End-to-end integration tests."""

    def test_create_validate_serialize_deserialize(self) -> None:
        """Test complete workflow: create → validate → serialize → deserialize."""
        # 1. Create belief vectors
        belief1 = BeliefVector(
            vector=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
            metadata=BeliefMetadata(
                confidence=0.95,
                source="inference",
                custom={"model": "gpt-4", "temperature": 0.7},
            ),
            belief_id="belief_001",
        )
        belief2 = BeliefVector(
            vector=np.array([1.1, 2.1, 2.9, 4.2, 4.8]),
            metadata=BeliefMetadata(
                confidence=0.87,
                source="inference",
                custom={"model": "gpt-4", "temperature": 0.7},
            ),
            belief_id="belief_002",
        )

        # 2. Create and apply schema
        schema = BeliefSchema(
            expected_dimension=5,
            min_confidence=0.5,
            max_confidence=1.0,
            allowed_sources=["inference", "training"],
        )

        assert schema.is_valid(belief1)
        assert schema.is_valid(belief2)

        # 3. Compute similarity
        similarity = belief1.cosine_similarity(belief2)
        assert 0.99 < similarity <= 1.0  # Vectors are very similar

        # 4. Serialize
        serializer = BeliefSerializer(default_schema=schema)
        json_str1 = serializer.serialize(belief1)
        json_str2 = serializer.serialize(belief2)

        # 5. Deserialize
        restored1 = serializer.deserialize(json_str1)
        restored2 = serializer.deserialize(json_str2)

        # 6. Verify
        assert restored1.belief_id == belief1.belief_id
        assert np.allclose(restored1.vector, belief1.vector)
        assert restored1.metadata.confidence == belief1.metadata.confidence
        assert restored1.metadata.custom == belief1.metadata.custom

        # 7. Verify similarity preserved
        restored_similarity = restored1.cosine_similarity(restored2)
        assert np.allclose(similarity, restored_similarity)

    def test_batch_workflow(self) -> None:
        """Test batch processing workflow."""
        # Create multiple beliefs
        beliefs = [
            BeliefVector(
                vector=np.random.randn(384),
                metadata=BeliefMetadata(confidence=0.9, source="training"),
                belief_id=f"belief_{i}",
            )
            for i in range(10)
        ]

        # Apply schema
        schema = BeliefSchema(
            expected_dimension=384,
            min_confidence=0.5,
            allowed_sources=["training"],
        )

        for belief in beliefs:
            assert schema.is_valid(belief)

        # Serialize batch
        serializer = BeliefSerializer(default_schema=schema)
        batch_json = serializer.serialize_batch(beliefs)

        # Deserialize batch
        restored = serializer.deserialize_batch(batch_json)

        assert len(restored) == 10
        for i, belief in enumerate(restored):
            assert belief.belief_id == f"belief_{i}"
            assert belief.dimension == 384

    def test_normalization_workflow(self) -> None:
        """Test normalization in workflow."""
        # Create unnormalized belief
        raw_belief = BeliefVector(
            vector=np.array([3.0, 4.0]),
            metadata=BeliefMetadata(confidence=1.0, source="raw"),
        )

        # Verify it's not normalized
        assert raw_belief.magnitude == 5.0

        # Normalize
        normalized = raw_belief.normalize()

        # Verify normalization
        assert np.allclose(normalized.magnitude, 1.0)
        assert np.allclose(normalized.vector, np.array([0.6, 0.8]))

        # Verify metadata preserved
        assert normalized.metadata.confidence == raw_belief.metadata.confidence
        assert normalized.metadata.source == raw_belief.metadata.source

    def test_schema_enforcement_pipeline(self) -> None:
        """Test schema enforcement in processing pipeline."""
        # Define strict schema
        strict_schema = BeliefSchema(
            expected_dimension=3,
            min_confidence=0.8,
            max_confidence=1.0,
            allowed_sources=["expert"],
            max_magnitude=10.0,
        )

        serializer = BeliefSerializer(default_schema=strict_schema)

        # Valid belief
        valid = BeliefVector(
            vector=np.array([1.0, 2.0, 2.0]),  # magnitude = 3
            metadata=BeliefMetadata(confidence=0.9, source="expert"),
        )

        # Invalid beliefs
        wrong_dim = BeliefVector(
            vector=np.array([1.0, 2.0]),
            metadata=BeliefMetadata(confidence=0.9, source="expert"),
        )
        low_confidence = BeliefVector(
            vector=np.array([1.0, 2.0, 2.0]),
            metadata=BeliefMetadata(confidence=0.5, source="expert"),
        )
        wrong_source = BeliefVector(
            vector=np.array([1.0, 2.0, 2.0]),
            metadata=BeliefMetadata(confidence=0.9, source="user"),
        )
        too_large = BeliefVector(
            vector=np.array([10.0, 10.0, 10.0]),  # magnitude ≈ 17.3
            metadata=BeliefMetadata(confidence=0.9, source="expert"),
        )

        # Valid belief passes
        serializer.serialize(valid)  # Should not raise

        # Invalid beliefs fail
        with pytest.raises(ValidationError, match="Expected dimension"):
            serializer.serialize(wrong_dim)

        with pytest.raises(ValidationError, match="not in range"):
            serializer.serialize(low_confidence)

        with pytest.raises(ValidationError, match="not in allowed sources"):
            serializer.serialize(wrong_source)

        with pytest.raises(ValidationError, match="exceeds maximum"):
            serializer.serialize(too_large)


class TestImportIntegration:
    """Test module imports work correctly."""

    def test_import_belief_vector(self) -> None:
        """Test importing BeliefVector from module."""
        from src.strong_system.belief_embeddings import BeliefVector as ImportedVector
        from src.strong_system.belief_embeddings.vector import (
            BeliefVector as DirectVector,
        )

        assert ImportedVector is DirectVector

    def test_import_validation_error(self) -> None:
        """Test importing ValidationError from module."""
        from src.strong_system.belief_embeddings import ValidationError as ImportedError
        from src.strong_system.belief_embeddings.vector import (
            ValidationError as DirectError,
        )

        assert ImportedError is DirectError

    def test_create_from_import(self) -> None:
        """Test creating instances from imports."""
        from src.strong_system.belief_embeddings import (
            BeliefMetadata,
            BeliefSchema,
            BeliefVector,
        )

        # Should be able to create instances
        metadata = BeliefMetadata(confidence=0.9, source="test")
        vector = BeliefVector(vector=np.array([1.0, 2.0, 3.0]), metadata=metadata)
        schema = BeliefSchema(expected_dimension=3)

        assert schema.is_valid(vector)

    def test_round_trip_json(self) -> None:
        """Test full round-trip through JSON."""
        # Create complex belief with metadata
        original = BeliefVector(
            vector=np.array([0.1, 0.2, 0.3, 0.4, 0.5]),
            metadata=BeliefMetadata(
                confidence=0.85,
                source="inference",
                custom={
                    "model_version": "2.1.0",
                    "inference_time_ms": 45.2,
                    "batch_id": "batch_12345",
                    "tags": ["important", "reviewed"],
                },
            ),
            belief_id="complex_belief_001",
        )

        # Convert to dict
        data = original.to_dict()

        # Convert to JSON and back
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)

        # Restore belief
        restored = BeliefVector.from_dict(restored_data)

        # Verify all fields
        assert restored.belief_id == original.belief_id
        assert np.allclose(restored.vector, original.vector)
        assert restored.metadata.confidence == original.metadata.confidence
        assert restored.metadata.source == original.metadata.source
        assert restored.metadata.custom == original.metadata.custom


class TestErrorHandling:
    """Test error handling in integration scenarios."""

    def test_invalid_vector_data_in_dict(self) -> None:
        """Test handling invalid vector data when loading from dict."""
        invalid_data = {
            "belief_id": "test",
            "vector": [],  # Empty vector
            "metadata": {},
        }

        with pytest.raises(ValidationError, match="Vector cannot be empty"):
            BeliefVector.from_dict(invalid_data)

    def test_malformed_metadata_in_dict(self) -> None:
        """Test handling malformed metadata when loading from dict."""
        data = {
            "belief_id": "test",
            "vector": [1.0, 2.0, 3.0],
            "metadata": {
                "confidence": 2.0,  # Invalid confidence
            },
        }

        with pytest.raises(ValidationError, match="Confidence must be between"):
            BeliefVector.from_dict(data)

    def test_dimension_mismatch_in_comparison(self) -> None:
        """Test error when comparing vectors of different dimensions."""
        belief1 = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        belief2 = BeliefVector(vector=np.array([1.0, 2.0]))

        with pytest.raises(ValidationError, match="Dimension mismatch"):
            belief1.cosine_similarity(belief2)

        with pytest.raises(ValidationError, match="Dimension mismatch"):
            belief1.euclidean_distance(belief2)

    def test_schema_validation_with_multiple_constraints(self) -> None:
        """Test schema catches first validation error."""
        schema = BeliefSchema(
            expected_dimension=5,
            min_confidence=0.5,
            allowed_sources=["expert"],
        )

        # This fails on dimension first
        invalid = BeliefVector(
            vector=np.array([1.0, 2.0]),  # Wrong dimension
            metadata=BeliefMetadata(
                confidence=0.3,  # Also too low
                source="user",  # Also wrong source
            ),
        )

        with pytest.raises(ValidationError, match="Expected dimension"):
            schema.validate(invalid)
