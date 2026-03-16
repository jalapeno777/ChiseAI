"""NeuralBelief class with gradient tracking.

Extends BeliefVector with gradient tracking capabilities for neural
belief revision and backpropagation through belief operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

import numpy as np
from src.strong_system.belief_embeddings import (
    BeliefMetadata,
    BeliefVector,
    ValidationError,
)
from src.strong_system.computational_graph import Node, backward


@dataclass
class GradientHistory:
    """History of gradient updates for a neural belief.

    Tracks gradient magnitudes and update directions over time
    to enable adaptive optimization and convergence detection.

    Attributes:
        gradients: List of gradient vectors from each update step
        timestamps: List of timestamps for each gradient update
        step_numbers: List of step numbers corresponding to gradients
        max_history: Maximum number of gradients to retain
    """

    gradients: list[np.ndarray] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    step_numbers: list[int] = field(default_factory=list)
    max_history: int = 100

    def __post_init__(self) -> None:
        """Validate history configuration."""
        if self.max_history < 1:
            raise ValidationError("max_history must be at least 1")

    def add_gradient(
        self, gradient: np.ndarray, step_number: int, timestamp: datetime | None = None
    ) -> None:
        """Add a gradient to the history.

        Args:
            gradient: The gradient vector to record
            step_number: The optimization step number
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        self.gradients.append(np.array(gradient, dtype=np.float64))
        self.timestamps.append(timestamp)
        self.step_numbers.append(step_number)

        # Trim history if exceeding max
        if len(self.gradients) > self.max_history:
            self.gradients.pop(0)
            self.timestamps.pop(0)
            self.step_numbers.pop(0)

    def get_recent_gradients(self, n: int = 10) -> list[np.ndarray]:
        """Get the n most recent gradients.

        Args:
            n: Number of recent gradients to retrieve

        Returns:
            List of the n most recent gradient vectors
        """
        return self.gradients[-n:] if n < len(self.gradients) else self.gradients.copy()

    def compute_average_magnitude(self, n: int = 10) -> float:
        """Compute average gradient magnitude over recent steps.

        Args:
            n: Number of recent gradients to consider

        Returns:
            Average L2 norm of recent gradients
        """
        recent = self.get_recent_gradients(n)
        if not recent:
            return 0.0
        return float(np.mean([np.linalg.norm(g) for g in recent]))

    def compute_direction_consistency(self, n: int = 10) -> float:
        """Compute consistency of gradient directions.

        Measures how consistently gradients point in similar directions.
        A value of 1.0 means all gradients are identical, 0.0 means
        orthogonal on average, negative means opposing directions.

        Args:
            n: Number of recent gradients to consider

        Returns:
            Direction consistency score between -1 and 1
        """
        recent = self.get_recent_gradients(n)
        if len(recent) < 2:
            return 1.0

        # Normalize gradients
        normalized = []
        for g in recent:
            norm = np.linalg.norm(g)
            if norm > 1e-10:
                normalized.append(g / norm)
            else:
                normalized.append(g)

        # Compute pairwise cosine similarities
        similarities = []
        for i in range(len(normalized)):
            for j in range(i + 1, len(normalized)):
                sim = np.dot(normalized[i], normalized[j])
                similarities.append(sim)

        return float(np.mean(similarities)) if similarities else 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert gradient history to dictionary."""
        return {
            "gradients": [g.tolist() for g in self.gradients],
            "timestamps": [t.isoformat() for t in self.timestamps],
            "step_numbers": self.step_numbers,
            "max_history": self.max_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create gradient history from dictionary."""
        history = cls(max_history=int(data.get("max_history", 100)))

        gradients = data.get("gradients", [])
        timestamps = data.get("timestamps", [])
        step_numbers = data.get("step_numbers", [])

        for g, t, s in zip(gradients, timestamps, step_numbers, strict=False):
            ts = datetime.fromisoformat(t) if isinstance(t, str) else datetime.now(UTC)
            history.add_gradient(np.array(g), int(s), ts)

        return history


class NeuralBelief:
    """A belief vector with gradient tracking for neural updates.

    Extends the concept of BeliefVector with support for gradient-based
    updates, backpropagation through belief operations, and integration
    with the computational graph for automatic differentiation.

    Attributes:
        belief_vector: The underlying BeliefVector
        requires_grad: Whether to track gradients for this belief
        gradient: Current gradient (None if not computed)
        gradient_history: History of gradient updates
        computation_node: Associated computational graph node
        revision_count: Number of times this belief has been revised
    """

    def __init__(
        self,
        vector: np.ndarray | BeliefVector,
        confidence: float = 1.0,
        source: str = "neural",
        belief_id: str | None = None,
        requires_grad: bool = True,
        max_gradient_history: int = 100,
    ):
        """Initialize a neural belief.

        Args:
            vector: Either a numpy array or an existing BeliefVector
            confidence: Initial confidence score (0.0 to 1.0)
            source: Source identifier for the belief
            belief_id: Unique identifier (auto-generated if None)
            requires_grad: Whether to track gradients
            max_gradient_history: Maximum gradient history to retain
        """
        if isinstance(vector, BeliefVector):
            self.belief_vector = vector
        else:
            # Create BeliefVector from numpy array
            metadata = BeliefMetadata(
                confidence=confidence,
                source=source,
                timestamp=datetime.now(UTC),
            )
            self.belief_vector = BeliefVector(
                vector=np.array(vector, dtype=np.float64),
                metadata=metadata,
                belief_id=belief_id or f"neural_belief_{datetime.now(UTC).timestamp()}",
            )

        self.requires_grad = requires_grad
        self.gradient: np.ndarray | None = None
        self.gradient_history = GradientHistory(max_history=max_gradient_history)
        self.computation_node: Node | None = None
        self.revision_count: int = 0

        # Create computation node if gradient tracking is enabled
        if self.requires_grad:
            self._create_computation_node()

    def _create_computation_node(self) -> None:
        """Create a computational graph node for this belief."""
        self.computation_node = Node(
            value=self.belief_vector.vector,
            name=f"belief_{self.belief_vector.belief_id}",
        )

    @property
    def vector(self) -> np.ndarray:
        """Return the belief vector values."""
        return self.belief_vector.vector

    @vector.setter
    def vector(self, value: np.ndarray) -> None:
        """Update the belief vector values."""
        self.belief_vector.vector = np.array(value, dtype=np.float64)
        if self.computation_node is not None:
            self.computation_node.value = self.belief_vector.vector

    @property
    def confidence(self) -> float:
        """Return the belief confidence score."""
        return self.belief_vector.metadata.confidence

    @confidence.setter
    def confidence(self, value: float) -> None:
        """Update the belief confidence score."""
        if not 0.0 <= value <= 1.0:
            raise ValidationError(
                f"Confidence must be between 0.0 and 1.0, got {value}"
            )
        self.belief_vector.metadata.confidence = value

    @property
    def belief_id(self) -> str:
        """Return the belief identifier."""
        return self.belief_vector.belief_id

    @property
    def dimension(self) -> int:
        """Return the vector dimension."""
        return self.belief_vector.dimension

    @property
    def metadata(self) -> BeliefMetadata:
        """Return the belief metadata."""
        return self.belief_vector.metadata

    def zero_grad(self) -> None:
        """Zero out the gradient."""
        self.gradient = None
        if self.computation_node is not None:
            self.computation_node.gradient = None

    def set_gradient(self, gradient: np.ndarray | float) -> None:
        """Set the gradient manually.

        Args:
            gradient: The gradient value (numpy array or scalar)
        """
        if isinstance(gradient, (int, float)):
            gradient = np.full(self.dimension, float(gradient), dtype=np.float64)
        else:
            gradient = np.array(gradient, dtype=np.float64)

        if gradient.shape != (self.dimension,):
            raise ValidationError(
                f"Gradient shape {gradient.shape} doesn't match belief dimension {self.dimension}"
            )

        self.gradient = gradient
        self.revision_count += 1
        self.gradient_history.add_gradient(gradient, self.revision_count)

    def backward(self, grad_output: np.ndarray | float | None = None) -> None:
        """Compute gradients via backpropagation.

        Uses the computational graph to compute gradients through
        any operations that involved this belief.

        Args:
            grad_output: Optional output gradient (defaults to ones)
        """
        if not self.requires_grad or self.computation_node is None:
            return

        backward(self.computation_node, grad_output)

        # Extract gradient from computation node
        if self.computation_node.gradient is not None:
            self.set_gradient(self.computation_node.gradient)

    def apply_update(self, delta: np.ndarray) -> None:
        """Apply an update to the belief vector.

        Args:
            delta: The update to apply (added to current vector)
        """
        delta = np.array(delta, dtype=np.float64)
        if delta.shape != (self.dimension,):
            raise ValidationError(
                f"Update shape {delta.shape} doesn't match belief dimension {self.dimension}"
            )

        self.vector = self.vector + delta
        self.revision_count += 1

    def cosine_similarity(self, other: NeuralBelief) -> float:
        """Compute cosine similarity with another neural belief.

        Args:
            other: Another NeuralBelief to compare with

        Returns:
            Cosine similarity score between -1 and 1
        """
        return self.belief_vector.cosine_similarity(other.belief_vector)

    def euclidean_distance(self, other: NeuralBelief) -> float:
        """Compute Euclidean distance to another neural belief.

        Args:
            other: Another NeuralBelief to compare with

        Returns:
            Euclidean distance
        """
        return self.belief_vector.euclidean_distance(other.belief_vector)

    def to_dict(self) -> dict[str, Any]:
        """Convert neural belief to dictionary."""
        return {
            "belief_vector": self.belief_vector.to_dict(),
            "requires_grad": self.requires_grad,
            "gradient": self.gradient.tolist() if self.gradient is not None else None,
            "gradient_history": self.gradient_history.to_dict(),
            "revision_count": self.revision_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create neural belief from dictionary."""
        belief_vector = BeliefVector.from_dict(data["belief_vector"])

        neural_belief = cls(
            vector=belief_vector,
            requires_grad=data.get("requires_grad", True),
            max_gradient_history=data.get("gradient_history", {}).get(
                "max_history", 100
            ),
        )

        # Restore gradient if present
        gradient_data = data.get("gradient")
        if gradient_data is not None:
            neural_belief.gradient = np.array(gradient_data, dtype=np.float64)

        # Restore gradient history
        if "gradient_history" in data:
            neural_belief.gradient_history = GradientHistory.from_dict(
                data["gradient_history"]
            )

        neural_belief.revision_count = data.get("revision_count", 0)

        return neural_belief

    def __repr__(self) -> str:
        """Return string representation."""
        grad_str = f" grad={self.gradient is not None}"
        return f"NeuralBelief({self.belief_id} dim={self.dimension}{grad_str})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another neural belief."""
        if not isinstance(other, NeuralBelief):
            return NotImplemented
        return (
            self.belief_vector == other.belief_vector
            and self.requires_grad == other.requires_grad
            and self.revision_count == other.revision_count
        )
