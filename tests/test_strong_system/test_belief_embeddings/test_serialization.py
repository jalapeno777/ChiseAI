"""Tests for serialization module."""

from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import pytest
from src.strong_system.belief_embeddings import (
    BeliefMetadata,
    BeliefSchema,
    BeliefSerializer,
    BeliefVector,
    ValidationError,
    from_dict,
    from_json,
    load_from_file,
    save_to_file,
    to_dict,
    to_json,
)


class TestToDict:
    """Tests for to_dict function."""

    def test_belief_vector_to_dict(self) -> None:
        """Test converting BeliefVector to dict."""
        belief = BeliefVector(
            vector=np.array([1.0, 2.0, 3.0]),
            metadata=BeliefMetadata(confidence=0.9, source="test"),
            belief_id="test_001",
        )
        data = to_dict(belief)
        assert data["belief_id"] == "test_001"
        assert data["vector"] == [1.0, 2.0, 3.0]
        assert data["metadata"]["confidence"] == 0.9

    def test_belief_metadata_to_dict(self) -> None:
        """Test converting BeliefMetadata to dict."""
        metadata = BeliefMetadata(confidence=0.8, source="inference")
        data = to_dict(metadata)
        assert data["confidence"] == 0.8
        assert data["source"] == "inference"

    def test_belief_schema_to_dict(self) -> None:
        """Test converting BeliefSchema to dict."""
        schema = BeliefSchema(expected_dimension=384, min_confidence=0.5)
        data = to_dict(schema)
        assert data["expected_dimension"] == 384
        assert data["min_confidence"] == 0.5

    def test_to_dict_unsupported_type(self) -> None:
        """Test that unsupported type raises TypeError."""
        with pytest.raises(TypeError, match="Cannot serialize"):
            to_dict("not a belief object")


class TestFromDict:
    """Tests for from_dict function."""

    def test_dict_to_belief_vector(self) -> None:
        """Test creating BeliefVector from dict."""
        data = {
            "belief_id": "test_001",
            "vector": [1.0, 2.0, 3.0],
            "metadata": {"confidence": 0.9, "source": "test"},
        }
        belief = from_dict(data, BeliefVector)
        assert belief.belief_id == "test_001"
        assert np.allclose(belief.vector, np.array([1.0, 2.0, 3.0]))
        assert belief.metadata.confidence == 0.9

    def test_dict_to_belief_metadata(self) -> None:
        """Test creating BeliefMetadata from dict."""
        data = {"confidence": 0.8, "source": "inference"}
        metadata = from_dict(data, BeliefMetadata)
        assert metadata.confidence == 0.8
        assert metadata.source == "inference"

    def test_dict_to_belief_schema(self) -> None:
        """Test creating BeliefSchema from dict."""
        data = {"expected_dimension": 384, "min_confidence": 0.5}
        schema = from_dict(data, BeliefSchema)
        assert schema.expected_dimension == 384
        assert schema.min_confidence == 0.5

    def test_from_dict_unsupported_type(self) -> None:
        """Test that unsupported type raises TypeError."""
        with pytest.raises(TypeError, match="Cannot deserialize"):
            from_dict({}, str)  # type: ignore[type-var]


class TestToJson:
    """Tests for to_json function."""

    def test_belief_vector_to_json(self) -> None:
        """Test converting BeliefVector to JSON."""
        belief = BeliefVector(
            vector=np.array([1.0, 2.0, 3.0]),
            metadata=BeliefMetadata(confidence=0.9, source="test"),
            belief_id="test_001",
        )
        json_str = to_json(belief)
        data = json.loads(json_str)
        assert data["belief_id"] == "test_001"
        assert data["vector"] == [1.0, 2.0, 3.0]
        assert data["metadata"]["confidence"] == 0.9

    def test_belief_metadata_to_json(self) -> None:
        """Test converting BeliefMetadata to JSON."""
        metadata = BeliefMetadata(confidence=0.8, source="inference")
        json_str = to_json(metadata)
        data = json.loads(json_str)
        assert data["confidence"] == 0.8
        assert data["source"] == "inference"

    def test_to_json_with_kwargs(self) -> None:
        """Test to_json with additional kwargs."""
        belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))
        json_str = to_json(belief, indent=2)
        assert "\n" in json_str  # Should be formatted with newlines


class TestFromJson:
    """Tests for from_json function."""

    def test_json_to_belief_vector(self) -> None:
        """Test creating BeliefVector from JSON."""
        json_str = json.dumps(
            {
                "belief_id": "test_001",
                "vector": [1.0, 2.0, 3.0],
                "metadata": {"confidence": 0.9, "source": "test"},
            }
        )
        belief = from_json(json_str, BeliefVector)
        assert belief.belief_id == "test_001"
        assert np.allclose(belief.vector, np.array([1.0, 2.0, 3.0]))
        assert belief.metadata.confidence == 0.9

    def test_json_to_belief_metadata(self) -> None:
        """Test creating BeliefMetadata from JSON."""
        json_str = json.dumps({"confidence": 0.8, "source": "inference"})
        metadata = from_json(json_str, BeliefMetadata)
        assert metadata.confidence == 0.8
        assert metadata.source == "inference"

    def test_from_json_invalid_json(self) -> None:
        """Test that invalid JSON raises error."""
        with pytest.raises(json.JSONDecodeError):
            from_json("not valid json", BeliefVector)


class TestSaveLoadFile:
    """Tests for save_to_file and load_from_file functions."""

    def test_save_and_load_belief_vector(self) -> None:
        """Test saving and loading BeliefVector to/from file."""
        belief = BeliefVector(
            vector=np.array([1.0, 2.0, 3.0]),
            metadata=BeliefMetadata(confidence=0.9, source="test"),
            belief_id="test_001",
        )

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            filepath = f.name

        try:
            save_to_file(belief, filepath)
            loaded = load_from_file(filepath, BeliefVector)

            assert loaded.belief_id == belief.belief_id
            assert np.allclose(loaded.vector, belief.vector)
            assert loaded.metadata.confidence == belief.metadata.confidence
        finally:
            os.unlink(filepath)

    def test_load_file_not_found(self) -> None:
        """Test that loading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_from_file("/nonexistent/path/file.json", BeliefVector)

    def test_save_belief_metadata(self) -> None:
        """Test saving BeliefMetadata to file."""
        metadata = BeliefMetadata(confidence=0.8, source="inference")

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            filepath = f.name

        try:
            save_to_file(metadata, filepath)
            loaded = load_from_file(filepath, BeliefMetadata)

            assert loaded.confidence == metadata.confidence
            assert loaded.source == metadata.source
        finally:
            os.unlink(filepath)


class TestBeliefSerializer:
    """Tests for BeliefSerializer class."""

    def test_serialize(self) -> None:
        """Test serializing a belief vector."""
        serializer = BeliefSerializer()
        belief = BeliefVector(
            vector=np.array([1.0, 2.0, 3.0]),
            metadata=BeliefMetadata(confidence=0.9),
        )
        json_str = serializer.serialize(belief)
        data = json.loads(json_str)
        assert data["vector"] == [1.0, 2.0, 3.0]

    def test_serialize_with_validation(self) -> None:
        """Test serialization with schema validation."""
        schema = BeliefSchema(expected_dimension=3, min_confidence=0.5)
        serializer = BeliefSerializer(default_schema=schema)

        valid_belief = BeliefVector(
            vector=np.array([1.0, 2.0, 3.0]),
            metadata=BeliefMetadata(confidence=0.9),
        )
        serializer.serialize(valid_belief)  # Should not raise

    def test_serialize_validation_failure(self) -> None:
        """Test that serialization fails when validation fails."""
        schema = BeliefSchema(expected_dimension=2)
        serializer = BeliefSerializer(default_schema=schema)

        invalid_belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0]))

        with pytest.raises(ValidationError):
            serializer.serialize(invalid_belief)

    def test_deserialize(self) -> None:
        """Test deserializing a belief vector."""
        serializer = BeliefSerializer()
        json_str = json.dumps(
            {
                "belief_id": "test_001",
                "vector": [1.0, 2.0, 3.0],
                "metadata": {"confidence": 0.9, "source": "test"},
            }
        )
        belief = serializer.deserialize(json_str)
        assert belief.belief_id == "test_001"
        assert np.allclose(belief.vector, np.array([1.0, 2.0, 3.0]))

    def test_deserialize_with_validation(self) -> None:
        """Test deserialization with schema validation."""
        schema = BeliefSchema(expected_dimension=3)
        serializer = BeliefSerializer(default_schema=schema)

        json_str = json.dumps(
            {
                "belief_id": "test_001",
                "vector": [1.0, 2.0, 3.0],
                "metadata": {"confidence": 0.9},
            }
        )
        belief = serializer.deserialize(json_str)
        assert belief.dimension == 3

    def test_deserialize_validation_failure(self) -> None:
        """Test that deserialization fails when validation fails."""
        schema = BeliefSchema(expected_dimension=2)
        serializer = BeliefSerializer(default_schema=schema)

        json_str = json.dumps(
            {
                "belief_id": "test_001",
                "vector": [1.0, 2.0, 3.0],
                "metadata": {"confidence": 0.9},
            }
        )

        with pytest.raises(ValidationError):
            serializer.deserialize(json_str)

    def test_serialize_batch(self) -> None:
        """Test serializing a batch of beliefs."""
        serializer = BeliefSerializer()
        beliefs = [
            BeliefVector(vector=np.array([1.0, 2.0]), belief_id="b1"),
            BeliefVector(vector=np.array([3.0, 4.0]), belief_id="b2"),
        ]
        json_str = serializer.serialize_batch(beliefs)
        data = json.loads(json_str)
        assert len(data) == 2
        assert data[0]["belief_id"] == "b1"
        assert data[1]["belief_id"] == "b2"

    def test_deserialize_batch(self) -> None:
        """Test deserializing a batch of beliefs."""
        serializer = BeliefSerializer()
        json_str = json.dumps(
            [
                {"belief_id": "b1", "vector": [1.0, 2.0], "metadata": {}},
                {"belief_id": "b2", "vector": [3.0, 4.0], "metadata": {}},
            ]
        )
        beliefs = serializer.deserialize_batch(json_str)
        assert len(beliefs) == 2
        assert beliefs[0].belief_id == "b1"
        assert beliefs[1].belief_id == "b2"

    def test_deserialize_batch_not_array(self) -> None:
        """Test that deserializing non-array raises error."""
        serializer = BeliefSerializer()
        json_str = json.dumps({"not": "an array"})

        with pytest.raises(ValidationError, match="Expected JSON array"):
            serializer.deserialize_batch(json_str)

    def test_deserialize_batch_with_validation(self) -> None:
        """Test batch deserialization with validation."""
        schema = BeliefSchema(expected_dimension=2)
        serializer = BeliefSerializer(default_schema=schema)

        json_str = json.dumps(
            [
                {"belief_id": "b1", "vector": [1.0, 2.0], "metadata": {}},
                {"belief_id": "b2", "vector": [3.0, 4.0], "metadata": {}},
            ]
        )
        beliefs = serializer.deserialize_batch(json_str)
        assert len(beliefs) == 2

    def test_deserialize_batch_validation_failure(self) -> None:
        """Test that batch deserialization fails when validation fails."""
        schema = BeliefSchema(expected_dimension=2)
        serializer = BeliefSerializer(default_schema=schema)

        json_str = json.dumps(
            [
                {"belief_id": "b1", "vector": [1.0, 2.0], "metadata": {}},
                {
                    "belief_id": "b2",
                    "vector": [1.0, 2.0, 3.0],
                    "metadata": {},
                },  # Wrong dimension
            ]
        )

        with pytest.raises(ValidationError):
            serializer.deserialize_batch(json_str)
