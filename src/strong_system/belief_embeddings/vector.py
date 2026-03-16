"""Belief Vector Module for Strong AI System.

Provides the BeliefVector class for representing belief embeddings with metadata,
and BeliefSchema for validation and constraint enforcement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

import numpy as np


class ValidationError(ValueError):
    """Raised when belief vector validation fails."""


@dataclass
class BeliefMetadata:
    """Metadata for a belief vector.

    Attributes:
        confidence: Confidence score (0.0 to 1.0)
        source: Source identifier (e.g., "inference", "training", "user")
        timestamp: UTC timestamp when the belief was created
        version: Version identifier for the belief format
        custom: Additional custom metadata
    """

    confidence: float = 1.0
    source: str = "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: str = "1.0.0"
    custom: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate metadata fields."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValidationError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        if not self.source or not isinstance(self.source, str):
            raise ValidationError("Source must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValidationError("Timestamp must be a datetime object")

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "confidence": self.confidence,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "custom": self.custom,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create metadata from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now(UTC)

        return cls(
            confidence=float(data.get("confidence", 1.0)),
            source=str(data.get("source", "unknown")),
            timestamp=timestamp,
            version=str(data.get("version", "1.0.0")),
            custom=dict(data.get("custom", {})),
        )


@dataclass
class BeliefVector:
    """A belief vector with associated metadata.

    Represents an embedding vector with confidence, source, and temporal
    information. Supports normalization, validation, and serialization.

    Attributes:
        vector: The embedding vector as a numpy array
        metadata: Associated metadata for the belief
        belief_id: Unique identifier for this belief
    """

    vector: np.ndarray
    metadata: BeliefMetadata = field(default_factory=BeliefMetadata)
    belief_id: str = field(
        default_factory=lambda: f"belief_{datetime.now(UTC).timestamp()}"
    )

    def __post_init__(self) -> None:
        """Validate the belief vector."""
        self._validate_vector()

    def _validate_vector(self) -> None:
        """Validate the vector data."""
        if not isinstance(self.vector, np.ndarray):
            raise ValidationError(
                f"Vector must be numpy.ndarray, got {type(self.vector)}"
            )

        if self.vector.ndim != 1:
            raise ValidationError(
                f"Vector must be 1-dimensional, got {self.vector.ndim} dimensions"
            )

        if len(self.vector) == 0:
            raise ValidationError("Vector cannot be empty")

        if not np.all(np.isfinite(self.vector)):
            raise ValidationError("Vector contains non-finite values (NaN or Inf)")

    @property
    def dimension(self) -> int:
        """Return the dimension of the vector."""
        return len(self.vector)

    @property
    def magnitude(self) -> float:
        """Return the L2 norm (magnitude) of the vector."""
        return float(np.linalg.norm(self.vector))

    def normalize(self, method: str = "l2") -> BeliefVector:
        """Create a normalized copy of this belief vector.

        Args:
            method: Normalization method ("l2" or "unit")

        Returns:
            A new BeliefVector with normalized vector data

        Raises:
            ValidationError: If normalization fails (e.g., zero vector)
        """
        if method not in ("l2", "unit"):
            raise ValidationError(f"Unknown normalization method: {method}")

        norm = np.linalg.norm(self.vector)
        if norm == 0:
            raise ValidationError("Cannot normalize zero vector")

        normalized = self.vector / norm
        return BeliefVector(
            vector=normalized,
            metadata=self.metadata,
            belief_id=f"{self.belief_id}_norm",
        )

    def cosine_similarity(self, other: BeliefVector) -> float:
        """Compute cosine similarity with another belief vector.

        Args:
            other: Another BeliefVector to compare with

        Returns:
            Cosine similarity score between -1 and 1

        Raises:
            ValidationError: If vectors have different dimensions
        """
        if self.dimension != other.dimension:
            raise ValidationError(
                f"Dimension mismatch: {self.dimension} vs {other.dimension}"
            )

        dot_product = np.dot(self.vector, other.vector)
        magnitude_product = self.magnitude * other.magnitude

        if magnitude_product == 0:
            raise ValidationError("Cannot compute similarity with zero vector")

        return float(dot_product / magnitude_product)

    def euclidean_distance(self, other: BeliefVector) -> float:
        """Compute Euclidean distance to another belief vector.

        Args:
            other: Another BeliefVector to compare with

        Returns:
            Euclidean distance

        Raises:
            ValidationError: If vectors have different dimensions
        """
        if self.dimension != other.dimension:
            raise ValidationError(
                f"Dimension mismatch: {self.dimension} vs {other.dimension}"
            )

        return float(np.linalg.norm(self.vector - other.vector))

    def to_dict(self) -> dict[str, Any]:
        """Convert belief vector to dictionary."""
        return {
            "belief_id": self.belief_id,
            "vector": self.vector.tolist(),
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create belief vector from dictionary."""
        vector_data = data.get("vector", [])
        if isinstance(vector_data, str):
            vector_data = json.loads(vector_data)

        return cls(
            belief_id=str(data.get("belief_id", "")),
            vector=np.array(vector_data, dtype=np.float64),
            metadata=BeliefMetadata.from_dict(data.get("metadata", {})),
        )

    def __len__(self) -> int:
        """Return the dimension of the vector."""
        return self.dimension

    def __eq__(self, other: object) -> bool:
        """Check equality with another belief vector."""
        if not isinstance(other, BeliefVector):
            return NotImplemented
        return (
            np.allclose(self.vector, other.vector)
            and self.metadata == other.metadata
            and self.belief_id == other.belief_id
        )


@dataclass
class BeliefSchema:
    """Schema for validating belief vectors.

    Defines constraints and validation rules for belief vectors,
    including dimension requirements, value constraints, and
    metadata validation.

    Attributes:
        expected_dimension: Expected vector dimension (None for any)
        min_confidence: Minimum allowed confidence value
        max_confidence: Maximum allowed confidence value
        allowed_sources: List of allowed source identifiers (empty = any)
        require_finite: Whether to require all vector values to be finite
        max_magnitude: Maximum allowed vector magnitude (None = unlimited)
    """

    expected_dimension: int | None = None
    min_confidence: float = 0.0
    max_confidence: float = 1.0
    allowed_sources: list[str] = field(default_factory=list)
    require_finite: bool = True
    max_magnitude: float | None = None

    def validate(self, belief: BeliefVector) -> None:
        """Validate a belief vector against this schema.

        Args:
            belief: The BeliefVector to validate

        Raises:
            ValidationError: If validation fails
        """
        # Validate dimension
        if self.expected_dimension is not None:
            if belief.dimension != self.expected_dimension:
                raise ValidationError(
                    f"Expected dimension {self.expected_dimension}, "
                    f"got {belief.dimension}"
                )

        # Validate confidence range
        confidence = belief.metadata.confidence
        if not (self.min_confidence <= confidence <= self.max_confidence):
            raise ValidationError(
                f"Confidence {confidence} not in range "
                f"[{self.min_confidence}, {self.max_confidence}]"
            )

        # Validate source
        if self.allowed_sources:
            if belief.metadata.source not in self.allowed_sources:
                raise ValidationError(
                    f"Source '{belief.metadata.source}' not in allowed sources: "
                    f"{self.allowed_sources}"
                )

        # Validate finite values
        if self.require_finite:
            if not np.all(np.isfinite(belief.vector)):
                raise ValidationError("Vector contains non-finite values")

        # Validate magnitude
        if self.max_magnitude is not None:
            if belief.magnitude > self.max_magnitude:
                raise ValidationError(
                    f"Vector magnitude {belief.magnitude} exceeds "
                    f"maximum {self.max_magnitude}"
                )

    def is_valid(self, belief: BeliefVector) -> bool:
        """Check if a belief vector is valid according to this schema.

        Args:
            belief: The BeliefVector to check

        Returns:
            True if valid, False otherwise
        """
        try:
            self.validate(belief)
            return True
        except ValidationError:
            return False

    def to_dict(self) -> dict[str, Any]:
        """Convert schema to dictionary."""
        return {
            "expected_dimension": self.expected_dimension,
            "min_confidence": self.min_confidence,
            "max_confidence": self.max_confidence,
            "allowed_sources": self.allowed_sources,
            "require_finite": self.require_finite,
            "max_magnitude": self.max_magnitude,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create schema from dictionary."""
        return cls(
            expected_dimension=data.get("expected_dimension"),
            min_confidence=float(data.get("min_confidence", 0.0)),
            max_confidence=float(data.get("max_confidence", 1.0)),
            allowed_sources=list(data.get("allowed_sources", [])),
            require_finite=bool(data.get("require_finite", True)),
            max_magnitude=data.get("max_magnitude"),
        )
