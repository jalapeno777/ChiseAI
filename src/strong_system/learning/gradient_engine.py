"""Gradient Engine for belief-based learning.

Provides the GradientEngine class for computing gradients through belief operations
with support for automatic differentiation, gradient clipping, and memory-efficient
computation. Integrates with the existing computational graph infrastructure.

Example:
    >>> from src.strong_system.learning import GradientEngine
    >>> from src.strong_system.neural_beliefs import NeuralBelief
    >>> import numpy as np
    >>>
    >>> # Create beliefs
    >>> belief1 = NeuralBelief(np.array([1.0, 2.0, 3.0]))
    >>> belief2 = NeuralBelief(np.array([0.5, 1.5, 2.5]))
    >>>
    >>> # Compute gradient of similarity
    >>> engine = GradientEngine()
    >>> loss = engine.compute_similarity_loss(belief1, belief2)
    >>> gradients = engine.compute_gradients(loss)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from src.strong_system.computational_graph import Node, backward
from src.strong_system.computational_graph.autodiff import clear_gradients
from src.strong_system.computational_graph.graph import Graph

if TYPE_CHECKING:
    from src.strong_system.neural_beliefs.belief import NeuralBelief


@dataclass
class GradientConfig:
    """Configuration for gradient computation.

    Attributes:
        clip_norm: Maximum gradient norm for clipping (None = no clipping)
        clip_value: Maximum absolute gradient value (None = no clipping)
        accumulate_gradients: Whether to accumulate gradients across calls
        zero_grad_before_compute: Whether to zero gradients before computation
    """

    clip_norm: float | None = 1.0
    clip_value: float | None = None
    accumulate_gradients: bool = False
    zero_grad_before_compute: bool = True


@dataclass
class GradientStats:
    """Statistics from gradient computation.

    Attributes:
        mean_magnitude: Mean gradient magnitude across all parameters
        max_magnitude: Maximum gradient magnitude
        min_magnitude: Minimum gradient magnitude
        std_magnitude: Standard deviation of gradient magnitudes
        clipped_count: Number of gradients that were clipped
        total_params: Total number of parameters
        has_nans: Whether any NaN values were detected
        has_infs: Whether any Inf values were detected
    """

    mean_magnitude: float = 0.0
    max_magnitude: float = 0.0
    min_magnitude: float = 0.0
    std_magnitude: float = 0.0
    clipped_count: int = 0
    total_params: int = 0
    has_nans: bool = False
    has_infs: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "mean_magnitude": self.mean_magnitude,
            "max_magnitude": self.max_magnitude,
            "min_magnitude": self.min_magnitude,
            "std_magnitude": self.std_magnitude,
            "clipped_count": self.clipped_count,
            "total_params": self.total_params,
            "has_nans": self.has_nans,
            "has_infs": self.has_infs,
        }


class GradientEngine:
    """Engine for computing gradients through belief operations.

    Provides high-level interface for gradient computation with support for:
    - Automatic differentiation through belief operations
    - Gradient clipping (norm-based and value-based)
    - Gradient statistics and monitoring
    - Integration with computational graph

    Attributes:
        config: Gradient computation configuration
        graph: Computational graph for gradient tracking
        stats: Statistics from last gradient computation
    """

    def __init__(self, config: GradientConfig | None = None):
        """Initialize the gradient engine.

        Args:
            config: Gradient configuration (uses defaults if None)
        """
        self.config = config or GradientConfig()
        self.graph = Graph(name="belief_gradient_graph")
        self.stats = GradientStats()
        self._belief_nodes: dict[str, Node] = {}
        self._loss_node: Node | None = None

    def register_belief(self, belief: NeuralBelief, name: str | None = None) -> Node:
        """Register a belief for gradient tracking.

        Args:
            belief: The neural belief to register
            name: Optional name for the node

        Returns:
            The computational graph node for this belief
        """
        belief_id = name or belief.belief_id

        if belief_id in self._belief_nodes:
            return self._belief_nodes[belief_id]

        # Create or use existing computation node
        if belief.computation_node is not None:
            node = belief.computation_node
        else:
            node = Node(
                value=belief.vector,
                name=f"belief_{belief_id}",
            )

        self._belief_nodes[belief_id] = node
        self.graph.add_node(node)

        return node

    def compute_similarity_loss(
        self,
        belief1: NeuralBelief,
        belief2: NeuralBelief,
        target_similarity: float = 1.0,
    ) -> Node:
        """Compute loss based on cosine similarity between beliefs.

        Args:
            belief1: First belief
            belief2: Second belief
            target_similarity: Target similarity score (default 1.0 for identical)

        Returns:
            Loss node for gradient computation
        """
        node1 = self.register_belief(belief1, belief1.belief_id)
        node2 = self.register_belief(belief2, belief2.belief_id)

        # Compute cosine similarity using differentiable operations
        # dot_product = sum(node1 * node2)
        dot_product_node = node1 * node2
        from src.strong_system.computational_graph.operations import Divide, Power, Sum

        dot_product = Sum.forward(dot_product_node)

        # norm1 = sqrt(sum(node1 * node1))
        norm1_squared_node = node1 * node1
        norm1_squared = Sum.forward(norm1_squared_node)
        half = Node(np.array(0.5), name="half")
        norm1 = Power.forward(norm1_squared, half)

        # norm2 = sqrt(sum(node2 * node2))
        norm2_squared_node = node2 * node2
        norm2_squared = Sum.forward(norm2_squared_node)
        norm2 = Power.forward(norm2_squared, half)

        # Similarity = dot / (norm1 * norm2)
        norm_product = norm1 * norm2
        similarity = Divide.forward(dot_product, norm_product)

        # Loss = (target - similarity)^2
        target_node = Node(np.array(target_similarity), name="target")
        diff = target_node - similarity
        loss = diff * diff

        self.graph.add_node(target_node)
        self.graph.add_node(similarity)
        self._loss_node = loss

        return loss

    def compute_mse_loss(
        self,
        belief: NeuralBelief,
        target: np.ndarray,
    ) -> Node:
        """Compute mean squared error loss between belief and target.

        Args:
            belief: The belief to compare
            target: Target values

        Returns:
            Loss node for gradient computation
        """
        node = self.register_belief(belief)
        target_node = Node(np.array(target), name="target")

        diff = node - target_node
        squared = diff * diff

        # Mean across dimensions using Sum operation for differentiability
        from src.strong_system.computational_graph.operations import Sum

        loss_sum = Sum.forward(squared)
        # Scale by 1/n to get mean
        n = float(squared.value.size)
        scale_node = Node(np.array(1.0 / n), name="scale")
        loss = loss_sum * scale_node

        self.graph.add_node(target_node)
        self.graph.add_node(scale_node)
        self._loss_node = loss

        return loss

    def compute_contrastive_loss(
        self,
        anchor: NeuralBelief,
        positive: NeuralBelief,
        negative: NeuralBelief,
        margin: float = 1.0,
    ) -> Node:
        """Compute contrastive loss for belief embeddings.

        Args:
            anchor: Anchor belief
            positive: Positive example (should be similar to anchor)
            negative: Negative example (should be different from anchor)
            margin: Margin for contrastive loss

        Returns:
            Loss node for gradient computation
        """
        from src.strong_system.computational_graph.operations import ReLU

        anchor_node = self.register_belief(anchor, "anchor")
        positive_node = self.register_belief(positive, "positive")
        negative_node = self.register_belief(negative, "negative")

        # Compute distances using differentiable operations
        pos_dist = self._compute_euclidean_distance(anchor_node, positive_node)
        neg_dist = self._compute_euclidean_distance(anchor_node, negative_node)

        # Contrastive loss: max(0, pos_dist - neg_dist + margin)
        # Use differentiable operations:
        # 1. Compute pos_dist - neg_dist using subtraction
        diff = pos_dist - neg_dist

        # 2. Add margin using Add operation
        margin_node = Node(np.array(margin), name="margin")
        margin_node_diff = diff + margin_node

        # 3. Apply ReLU for max(0, ...)
        loss = ReLU.forward(margin_node_diff)

        self.graph.add_node(margin_node)
        self.graph.add_node(loss)
        self._loss_node = loss

        return loss

    def compute_gradients(
        self,
        loss_node: Node | None = None,
        beliefs: list[NeuralBelief] | None = None,
    ) -> dict[str, np.ndarray]:
        """Compute gradients for registered beliefs.

        Args:
            loss_node: Loss node to compute gradients from (uses last computed if None)
            beliefs: Specific beliefs to compute gradients for (all if None)

        Returns:
            Dictionary mapping belief IDs to gradient arrays
        """
        loss = loss_node or self._loss_node
        if loss is None:
            raise ValueError("No loss node provided or computed")

        # Clear gradients if configured
        if (
            self.config.zero_grad_before_compute
            and not self.config.accumulate_gradients
        ):
            clear_gradients(self.graph)

        # Compute gradients via backpropagation
        backward(loss)

        # Collect gradients
        gradients = {}
        belief_ids = list(self._belief_nodes.keys())

        for belief_id in belief_ids:
            node = self._belief_nodes[belief_id]
            if node.gradient is not None:
                gradient = node.gradient.copy()

                # Apply clipping
                gradient, was_clipped = self._clip_gradient(gradient)

                gradients[belief_id] = gradient

        # Update statistics
        self._update_stats(gradients)

        return gradients

    def apply_gradients(
        self,
        gradients: dict[str, np.ndarray],
        beliefs: dict[str, NeuralBelief],
        learning_rate: float = 0.01,
    ) -> None:
        """Apply computed gradients to beliefs.

        Args:
            gradients: Dictionary of gradients by belief ID
            beliefs: Dictionary of beliefs by ID
            learning_rate: Learning rate for updates
        """
        for belief_id, gradient in gradients.items():
            if belief_id in beliefs:
                belief = beliefs[belief_id]
                update = -learning_rate * gradient
                belief.apply_update(update)

    def zero_grad(self) -> None:
        """Zero all gradients in the graph."""
        clear_gradients(self.graph)
        for node in self._belief_nodes.values():
            node.gradient = None

    def get_gradient_stats(self) -> GradientStats:
        """Get statistics from last gradient computation."""
        return self.stats

    def _compute_dot_product(self, node1: Node, node2: Node) -> Node:
        """Compute dot product between two nodes using differentiable operations."""
        from src.strong_system.computational_graph.operations import Sum

        # Element-wise multiplication then sum using differentiable Sum operation
        product = node1 * node2
        result = Sum.forward(product)
        return result

    def _compute_norm(self, node: Node) -> Node:
        """Compute L2 norm of a node using differentiable operations."""
        from src.strong_system.computational_graph.operations import Power, Sum

        # Compute sqrt(sum(x^2)) using differentiable operations
        squared = node * node
        sum_squared = Sum.forward(squared)
        # Use Power with exponent 0.5 for square root
        half = Node(np.array(0.5), name="half")
        norm = Power.forward(sum_squared, half)
        return norm

    def _compute_euclidean_distance(self, node1: Node, node2: Node) -> Node:
        """Compute Euclidean distance between two nodes using differentiable operations."""
        from src.strong_system.computational_graph.operations import Power, Sum

        # Compute sqrt(sum((node1 - node2)^2)) using differentiable operations
        diff = node1 - node2
        squared = diff * diff
        sum_squared = Sum.forward(squared)
        # Use Power with exponent 0.5 for square root
        half = Node(np.array(0.5), name="half")
        distance = Power.forward(sum_squared, half)
        return distance

    def _clip_gradient(self, gradient: np.ndarray) -> tuple[np.ndarray, bool]:
        """Clip gradient based on configuration.

        Args:
            gradient: The gradient to clip

        Returns:
            Tuple of (clipped_gradient, was_clipped)
        """
        was_clipped = False

        # Check for NaN/Inf
        if np.any(np.isnan(gradient)):
            self.stats.has_nans = True
            gradient = np.nan_to_num(gradient, nan=0.0)
            was_clipped = True

        if np.any(np.isinf(gradient)):
            self.stats.has_infs = True
            gradient = np.nan_to_num(gradient, posinf=1e10, neginf=-1e10)
            was_clipped = True

        # Clip by value
        if self.config.clip_value is not None:
            clipped = np.clip(gradient, -self.config.clip_value, self.config.clip_value)
            if not np.array_equal(clipped, gradient):
                was_clipped = True
            gradient = clipped

        # Clip by norm
        if self.config.clip_norm is not None:
            norm = np.linalg.norm(gradient)
            if norm > self.config.clip_norm:
                gradient = gradient * (self.config.clip_norm / norm)
                was_clipped = True

        return gradient, was_clipped

    def _update_stats(self, gradients: dict[str, np.ndarray]) -> None:
        """Update gradient statistics."""
        if not gradients:
            self.stats = GradientStats()
            return

        all_grads = list(gradients.values())
        magnitudes = [np.linalg.norm(g) for g in all_grads]

        self.stats = GradientStats(
            mean_magnitude=float(np.mean(magnitudes)),
            max_magnitude=float(np.max(magnitudes)),
            min_magnitude=float(np.min(magnitudes)),
            std_magnitude=float(np.std(magnitudes)),
            total_params=sum(g.size for g in all_grads),
            has_nans=any(np.any(np.isnan(g)) for g in all_grads),
            has_infs=any(np.any(np.isinf(g)) for g in all_grads),
        )

    def reset(self) -> None:
        """Reset the engine state."""
        self.graph.clear()
        self._belief_nodes.clear()
        self._loss_node = None
        self.stats = GradientStats()


class BeliefGradientFunction:
    """Wrapper for gradient-based functions on beliefs.

    Allows defining custom gradient functions that can be composed
    and differentiated through.

    Example:
        >>> def similarity_fn(b1, b2):
        ...     return np.dot(b1.vector, b2.vector)
        ...
        >>> grad_fn = BeliefGradientFunction(similarity_fn)
        >>> gradients = grad_fn.compute_gradients(belief1, belief2)
    """

    def __init__(
        self,
        func: Callable[..., np.ndarray],
        name: str | None = None,
    ):
        """Initialize gradient function.

        Args:
            func: Function to wrap (takes beliefs, returns array)
            name: Optional name for this function
        """
        self.func = func
        self.name = name or func.__name__
        self.engine = GradientEngine()

    def __call__(self, *beliefs: NeuralBelief) -> np.ndarray:
        """Execute the function.

        Args:
            *beliefs: Variable number of beliefs

        Returns:
            Function output
        """
        return self.func(*beliefs)

    def compute_gradients(
        self,
        *beliefs: NeuralBelief,
        target: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        """Compute gradients through this function.

        Args:
            *beliefs: Input beliefs
            target: Optional target for computing loss

        Returns:
            Dictionary of gradients by belief ID
        """
        # Register beliefs
        for i, belief in enumerate(beliefs):
            self.engine.register_belief(belief, name=f"input_{i}")

        # Compute output
        output = self.func(*beliefs)

        # If target provided, compute MSE loss
        if target is not None:
            # Create a temporary belief from output
            from src.strong_system.neural_beliefs import NeuralBelief

            temp_belief = NeuralBelief(output, requires_grad=True)
            loss_node = self.engine.compute_mse_loss(temp_belief, target)
        else:
            # Use output as loss (for scalar outputs)
            loss_node = Node(float(np.sum(output)), name="output_loss")

        return self.engine.compute_gradients(loss_node)
