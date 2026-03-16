"""Serialization module for belief vectors.

Provides JSON serialization and deserialization for BeliefVector,
BeliefMetadata, and BeliefSchema objects.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from .vector import BeliefMetadata, BeliefSchema, BeliefVector, ValidationError

T = TypeVar("T", BeliefVector, BeliefMetadata, BeliefSchema)


def to_dict(obj: T) -> dict[str, Any]:
    """Convert a belief object to dictionary.

    Args:
        obj: A BeliefVector, BeliefMetadata, or BeliefSchema instance

    Returns:
        Dictionary representation of the object

    Raises:
        TypeError: If obj is not a supported type
    """
    if isinstance(obj, BeliefVector):
        return obj.to_dict()
    elif isinstance(obj, BeliefMetadata):
        return obj.to_dict()
    elif isinstance(obj, BeliefSchema):
        return obj.to_dict()
    else:
        raise TypeError(f"Cannot serialize object of type {type(obj)}")


def from_dict(data: dict[str, Any], obj_type: type[T]) -> T:
    """Create a belief object from dictionary.

    Args:
        data: Dictionary containing the object's data
        obj_type: The type of object to create (BeliefVector, BeliefMetadata, or BeliefSchema)

    Returns:
        Instance of the specified type

    Raises:
        TypeError: If obj_type is not a supported type
        ValidationError: If the data is invalid
    """
    if obj_type is BeliefVector:
        return BeliefVector.from_dict(data)  # type: ignore[return-value]
    elif obj_type is BeliefMetadata:
        return BeliefMetadata.from_dict(data)  # type: ignore[return-value]
    elif obj_type is BeliefSchema:
        return BeliefSchema.from_dict(data)  # type: ignore[return-value]
    else:
        raise TypeError(f"Cannot deserialize object of type {obj_type}")


def to_json(obj: T, **json_kwargs: Any) -> str:
    """Serialize a belief object to JSON string.

    Args:
        obj: A BeliefVector, BeliefMetadata, or BeliefSchema instance
        **json_kwargs: Additional arguments passed to json.dumps

    Returns:
        JSON string representation

    Raises:
        TypeError: If obj is not a supported type
    """
    data = to_dict(obj)
    return json.dumps(data, **json_kwargs)


def from_json(json_str: str, obj_type: type[T], **json_kwargs: Any) -> T:
    """Deserialize a belief object from JSON string.

    Args:
        json_str: JSON string to deserialize
        obj_type: The type of object to create
        **json_kwargs: Additional arguments passed to json.loads

    Returns:
        Instance of the specified type

    Raises:
        json.JSONDecodeError: If json_str is not valid JSON
        TypeError: If obj_type is not a supported type
        ValidationError: If the data is invalid
    """
    data = json.loads(json_str, **json_kwargs)
    return from_dict(data, obj_type)


def save_to_file(obj: T, filepath: str, **json_kwargs: Any) -> None:
    """Save a belief object to a JSON file.

    Args:
        obj: A BeliefVector, BeliefMetadata, or BeliefSchema instance
        filepath: Path to the output file
        **json_kwargs: Additional arguments passed to json.dumps

    Raises:
        TypeError: If obj is not a supported type
        IOError: If file cannot be written
    """
    json_str = to_json(obj, **json_kwargs)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json_str)


def load_from_file(filepath: str, obj_type: type[T], **json_kwargs: Any) -> T:
    """Load a belief object from a JSON file.

    Args:
        filepath: Path to the input file
        obj_type: The type of object to create
        **json_kwargs: Additional arguments passed to json.loads

    Returns:
        Instance of the specified type

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file contains invalid JSON
        TypeError: If obj_type is not a supported type
        ValidationError: If the data is invalid
    """
    with open(filepath, encoding="utf-8") as f:
        json_str = f.read()
    return from_json(json_str, obj_type, **json_kwargs)


class BeliefSerializer:
    """Convenience class for serializing/deserializing belief objects.

    Provides a unified interface for all serialization operations
    with optional default schema for validation.
    """

    def __init__(self, default_schema: BeliefSchema | None = None):
        """Initialize the serializer.

        Args:
            default_schema: Optional default schema for validation
        """
        self.default_schema = default_schema

    def serialize(self, belief: BeliefVector, **json_kwargs: Any) -> str:
        """Serialize a belief vector to JSON.

        Args:
            belief: The BeliefVector to serialize
            **json_kwargs: Additional arguments for json.dumps

        Returns:
            JSON string representation
        """
        if self.default_schema:
            self.default_schema.validate(belief)
        return to_json(belief, **json_kwargs)

    def deserialize(self, json_str: str, **json_kwargs: Any) -> BeliefVector:
        """Deserialize a belief vector from JSON.

        Args:
            json_str: JSON string to deserialize
            **json_kwargs: Additional arguments for json.loads

        Returns:
            Deserialized BeliefVector

        Raises:
            ValidationError: If default_schema is set and validation fails
        """
        belief = from_json(json_str, BeliefVector, **json_kwargs)
        if self.default_schema:
            self.default_schema.validate(belief)
        return belief

    def serialize_batch(self, beliefs: list[BeliefVector], **json_kwargs: Any) -> str:
        """Serialize a batch of belief vectors to JSON.

        Args:
            beliefs: List of BeliefVector objects
            **json_kwargs: Additional arguments for json.dumps

        Returns:
            JSON string containing array of beliefs
        """
        data = [to_dict(b) for b in beliefs]
        return json.dumps(data, **json_kwargs)

    def deserialize_batch(
        self, json_str: str, **json_kwargs: Any
    ) -> list[BeliefVector]:
        """Deserialize a batch of belief vectors from JSON.

        Args:
            json_str: JSON string containing array of beliefs
            **json_kwargs: Additional arguments for json.loads

        Returns:
            List of deserialized BeliefVector objects
        """
        data = json.loads(json_str, **json_kwargs)
        if not isinstance(data, list):
            raise ValidationError("Expected JSON array for batch deserialization")

        beliefs = [from_dict(item, BeliefVector) for item in data]

        if self.default_schema:
            for belief in beliefs:
                self.default_schema.validate(belief)

        return beliefs
