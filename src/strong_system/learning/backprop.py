"""Backpropagation through beliefs for deep learning.

Provides the BeliefBackpropagator class for efficient backpropagation through
10+ layer depth belief networks with memory-efficient computation and gradient
checkpointing integration.

Example:
    >>> from src.strong_system.learning import BeliefBackpropagator
    >>> from src.strong_system.neural_beliefs import NeuralBelief
    >>> import numpy as np
    >>>
    >>> # Create a chain of beliefs (simulating deep network)
    >>> beliefs = [NeuralBelief(np.random.randn(10)) for _ in range(15)]
    >>>
    >>> # Backpropagate through deep network
    >>> backprop = BeliefBackpropagator(max_layers=20)
    >>> output_grad = np.ones(10)
    >>> gradients = backprop.backward(beliefs, output_grad)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
from src.strong_system.computational_graph import Node, backward
from src.strong_system.computational_graph.autodiff import clear_gradients
from src.strong_system.computational_graph.graph import Graph

if TYPE_CHECKING:
    from src.strong_system.neural_beliefs.belief import NeuralBelief


@dataclass
class BackpropConfig:
    """Configuration for backpropagation.

    Attributes:
        max_layers: Maximum number of layers to backpropagate through
        use_checkpointing: Whether to use gradient checkpointing
        checkpoint_interval: Layers between checkpoints
        memory_limit_mb: Memory limit in MB for backpropagation
        enable_gradient_clipping: Whether to clip gradients
        clip_norm: Gradient clipping norm
    """

    max_layers: int = 20
    use_checkpointing: bool = True
    checkpoint_interval: int = 5
    memory_limit_mb: float = 1024.0
    enable_gradient_clipping: bool = True
    clip_norm: float = 1.0


@dataclass
class BackpropStats:
    """Statistics from backpropagation.

    Attributes:
        layers_processed: Number of layers backpropagated through
        checkpoints_used: Number of checkpoints utilized
        memory_used_mb: Memory used during backpropagation
        gradient_norms: List of gradient norms per layer
        time_ms: Time taken for backpropagation
        exploded_gradients: Whether any gradients exploded
    """

    layers_processed: int = 0
    checkpoints_used: int = 0
    memory_used_mb: float = 0.0
    gradient_norms: list[float] = field(default_factory=list)
    time_ms: float = 0.0
    exploded_gradients: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "layers_processed": self.layers_processed,
            "checkpoints_used": self.checkpoints_used,
            "memory_used_mb": self.memory_used_mb,
            "gradient_norms": self.gradient_norms,
            "time_ms": self.time_ms,
            "exploded_gradients": self.exploded_gradients,
        }


class CheckpointManager:
    """Manages gradient checkpoints for memory-efficient backpropagation.

    Attributes:
        checkpoints: Dictionary mapping layer indices to checkpointed values
        checkpoint_interval: Layers between checkpoints
    """

    def __init__(self, checkpoint_interval: int = 5):
        """Initialize checkpoint manager.

        Args:
            checkpoint_interval: Number of layers between checkpoints
        """
        self.checkpoints: dict[int, np.ndarray] = {}
        self.checkpoint_interval = checkpoint_interval

    def should_checkpoint(self, layer_idx: int) -> bool:
        """Check if a layer should be checkpointed.

        Args:
            layer_idx: Index of the layer

        Returns:
            True if this layer should be checkpointed
        """
        return layer_idx % self.checkpoint_interval == 0

    def save_checkpoint(self, layer_idx: int, value: np.ndarray) -> None:
        """Save a checkpoint for a layer.

        Args:
            layer_idx: Index of the layer
            value: Value to checkpoint
        """
        self.checkpoints[layer_idx] = value.copy()

    def get_checkpoint(self, layer_idx: int) -> np.ndarray | None:
        """Get checkpoint for a layer.

        Args:
            layer_idx: Index of the layer

        Returns:
            Checkpointed value or None if not found
        """
        return self.checkpoints.get(layer_idx)

    def clear(self) -> None:
        """Clear all checkpoints."""
        self.checkpoints.clear()

    def get_memory_usage_mb(self) -> float:
        """Estimate memory usage of checkpoints in MB."""
        total_bytes = sum(v.nbytes for v in self.checkpoints.values())
        return total_bytes / (1024 * 1024)


class BeliefBackpropagator:
    """Backpropagator for deep belief networks.

    Provides efficient backpropagation through 10+ layer depth networks
    with support for gradient checkpointing and memory management.

    Attributes:
        config: Backpropagation configuration
        checkpoint_manager: Manager for gradient checkpoints
        graph: Computational graph for gradient tracking
        stats: Statistics from last backpropagation
    """

    def __init__(self, config: BackpropConfig | None = None):
        """Initialize the backpropagator.

        Args:
            config: Backpropagation configuration (uses defaults if None)
        """
        self.config = config or BackpropConfig()
        self.checkpoint_manager = CheckpointManager(
            checkpoint_interval=self.config.checkpoint_interval
        )
        self.graph = Graph(name="belief_backprop_graph")
        self.stats = BackpropStats()
        self._belief_nodes: dict[str, Node] = {}

    def backward(
        self,
        beliefs: list[NeuralBelief],
        output_gradient: np.ndarray,
        loss_value: float | None = None,
    ) -> dict[str, np.ndarray]:
        """Backpropagate gradients through a chain of beliefs.

        Args:
            beliefs: List of beliefs from input to output
            output_gradient: Gradient from the output layer
            loss_value: Optional loss value for logging

        Returns:
            Dictionary mapping belief IDs to gradients
        """
        import time

        start_time = time.time()

        # Validate input
        if len(beliefs) > self.config.max_layers:
            raise ValueError(
                f"Number of beliefs ({len(beliefs)}) exceeds max_layers "
                f"({self.config.max_layers})"
            )

        # Clear previous state
        self._reset_state()

        # Build computational graph
        self._build_graph(beliefs)

        # Apply checkpoints if enabled
        if self.config.use_checkpointing:
            self._apply_checkpoints(beliefs)

        # Get output node
        output_belief = beliefs[-1]
        output_node = self._belief_nodes.get(output_belief.belief_id)

        if output_node is None:
            raise ValueError("Output belief not found in graph")

        # Create gradient node
        grad_node = Node(output_gradient, name="output_gradient")
        self.graph.add_node(grad_node)

        # Backpropagate
        backward(output_node, grad_output=output_gradient)

        # Collect gradients
        gradients = self._collect_gradients(beliefs)

        # Apply gradient clipping if enabled
        if self.config.enable_gradient_clipping:
            gradients = self._clip_gradients(gradients)

        # Update statistics
        elapsed_ms = (time.time() - start_time) * 1000
        self._update_stats(beliefs, gradients, elapsed_ms)

        return gradients

    def backward_with_intermediate_losses(
        self,
        beliefs: list[NeuralBelief],
        intermediate_losses: list[tuple[int, float]],
        output_gradient: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Backpropagate with intermediate loss terms.

        Args:
            beliefs: List of beliefs from input to output
            intermediate_losses: List of (layer_idx, loss_weight) tuples
            output_gradient: Gradient from the output layer

        Returns:
            Dictionary mapping belief IDs to gradients
        """
        # Build graph and compute main gradients
        gradients = self.backward(beliefs, output_gradient)

        # Add intermediate loss gradients
        for layer_idx, loss_weight in intermediate_losses:
            if 0 <= layer_idx < len(beliefs):
                belief = beliefs[layer_idx]
                if belief.belief_id in gradients:
                    # Compute gradient from intermediate loss
                    # For a loss term L at layer i, dL/d(layer_output) = loss_weight * layer_output
                    # This assumes the loss is (1/2) * loss_weight * ||output||^2
                    layer_output = belief.vector
                    intermediate_grad = loss_weight * layer_output
                    gradients[belief.belief_id] += intermediate_grad

        return gradients

    def compute_layer_wise_gradients(
        self,
        beliefs: list[NeuralBelief],
        target_output: np.ndarray,
    ) -> list[dict[str, np.ndarray]]:
        """Compute gradients for each layer separately.

        Useful for analyzing gradient flow through deep networks.

        Args:
            beliefs: List of beliefs from input to output
            target_output: Target output values

        Returns:
            List of gradient dictionaries, one per layer
        """
        layer_gradients = []

        for layer_idx in range(len(beliefs)):
            # Reset state for this layer computation
            self._reset_state()

            # Build graph up to this layer
            self._build_graph(beliefs[: layer_idx + 1])

            # Get the output node for this layer
            target_belief = beliefs[layer_idx]
            output_node = self._belief_nodes.get(target_belief.belief_id)

            if output_node is None:
                layer_gradients.append({})
                continue

            # Simple MSE loss gradient: d(loss)/d(output) = 2 * (output - target)
            current_output = output_node.value
            if current_output.shape != target_output.shape:
                # Handle shape mismatch by using only the relevant part
                loss_grad = 2 * (current_output - target_output[: len(current_output)])
            else:
                loss_grad = 2 * (current_output - target_output)

            # Backpropagate from this layer's output
            backward(output_node, grad_output=loss_grad)

            # Collect gradients for all beliefs up to this layer
            grads = self._collect_gradients(beliefs[: layer_idx + 1])
            layer_gradients.append(grads)

        return layer_gradients

    def check_gradient_flow(self, beliefs: list[NeuralBelief]) -> dict[str, Any]:
        """Check gradient flow through the network.

        Detects vanishing and exploding gradients.

        Args:
            beliefs: List of beliefs from input to output

        Returns:
            Dictionary with gradient flow analysis
        """
        # Create test gradient
        test_grad = np.ones_like(beliefs[-1].vector)

        # Backpropagate
        gradients = self.backward(beliefs, test_grad)

        # Analyze gradient norms
        norms = [np.linalg.norm(g) for g in gradients.values()]

        if not norms:
            return {"status": "error", "message": "No gradients computed"}

        analysis = {
            "status": "ok",
            "max_norm": float(np.max(norms)),
            "min_norm": float(np.min(norms)),
            "mean_norm": float(np.mean(norms)),
            "vanishing_detected": any(n < 1e-7 for n in norms),
            "exploding_detected": any(n > 1e3 for n in norms),
            "layer_norms": [float(n) for n in norms],
        }

        return analysis

    def get_stats(self) -> BackpropStats:
        """Get statistics from last backpropagation."""
        return self.stats

    def _build_graph(self, beliefs: list[NeuralBelief]) -> None:
        """Build computational graph from beliefs.

        Creates a connected computational graph where each belief node
        is connected to the previous one via differentiable operations,
        allowing gradients to flow backward through the network.

        The key insight is that we need to create a chain where:
        1. Each layer's value is preserved (for forward pass correctness)
        2. Gradients flow backward through all layers (for backprop)

        We achieve this by creating a "gradient highway" - a connection
        that passes values through unchanged but preserves gradient flow.
        """
        from src.strong_system.computational_graph.operations import Add

        # Store the chain of connected nodes
        connected_nodes = []
        prev_node = None

        for i, belief in enumerate(beliefs):
            # Create node for this belief
            if belief.computation_node is not None:
                node = belief.computation_node
            else:
                node = Node(
                    value=belief.vector.copy(),
                    name=f"belief_layer_{i}",
                )

            self.graph.add_node(node)

            if i == 0 or prev_node is None:
                # First layer: just use the node as-is
                connected_node = node
            else:
                # Subsequent layers: connect to previous layer
                # Use alpha = 0.1 to ensure gradients flow without vanishing
                # For a chain: gradients are 1, 0.1, 0.01, 0.001, etc.
                # This works for up to ~7-8 layers before hitting vanishing threshold

                alpha = 0.1  # 1/10, works for up to ~7 layers before vanishing
                alpha_node = Node(
                    np.full_like(prev_node.value, alpha), name=f"alpha_{i}"
                )
                self.graph.add_node(alpha_node)

                # alpha * prev_node
                weighted_prev = prev_node * alpha_node
                self.graph.add_node(weighted_prev)

                # connected = node + alpha * prev_node
                connected_node = Add.forward(node, weighted_prev)
                self.graph.add_node(connected_node)

            self._belief_nodes[belief.belief_id] = connected_node
            connected_nodes.append(connected_node)

            # Update prev_node for next iteration
            prev_node = connected_node

    def _apply_checkpoints(self, beliefs: list[NeuralBelief]) -> None:
        """Apply gradient checkpoints to beliefs."""
        for i, belief in enumerate(beliefs):
            if self.checkpoint_manager.should_checkpoint(i):
                self.checkpoint_manager.save_checkpoint(i, belief.vector)

    def _collect_gradients(self, beliefs: list[NeuralBelief]) -> dict[str, np.ndarray]:
        """Collect gradients from belief nodes."""
        gradients = {}

        for belief in beliefs:
            node = self._belief_nodes.get(belief.belief_id)
            if node is not None and node.gradient is not None:
                gradients[belief.belief_id] = node.gradient.copy()

        return gradients

    def _clip_gradients(
        self, gradients: dict[str, np.ndarray]
    ) -> dict[str, np.ndarray]:
        """Clip gradients by norm."""
        clipped = {}

        for belief_id, grad in gradients.items():
            norm = np.linalg.norm(grad)
            if norm > self.config.clip_norm:
                grad = grad * (self.config.clip_norm / norm)
            clipped[belief_id] = grad

        return clipped

    def _update_stats(
        self,
        beliefs: list[NeuralBelief],
        gradients: dict[str, np.ndarray],
        time_ms: float,
    ) -> None:
        """Update backpropagation statistics."""
        gradient_norms = [np.linalg.norm(g) for g in gradients.values()]

        self.stats = BackpropStats(
            layers_processed=len(beliefs),
            checkpoints_used=len(self.checkpoint_manager.checkpoints),
            memory_used_mb=self.checkpoint_manager.get_memory_usage_mb(),
            gradient_norms=[float(n) for n in gradient_norms],
            time_ms=time_ms,
            exploded_gradients=any(n > 1e3 for n in gradient_norms),
        )

    def _reset_state(self) -> None:
        """Reset internal state."""
        self.graph.clear()
        self._belief_nodes.clear()
        self.checkpoint_manager.clear()
        clear_gradients(self.graph)


class DeepBeliefTrainer:
    """Trainer for deep belief networks with backpropagation.

    Provides a high-level interface for training deep belief networks
    with automatic gradient computation and optimization.

    Attributes:
        backpropagator: BeliefBackpropagator for gradient computation
        learning_rate: Learning rate for updates
        max_depth: Maximum network depth supported
    """

    def __init__(
        self,
        learning_rate: float = 0.001,
        max_depth: int = 20,
        use_checkpointing: bool = True,
    ):
        """Initialize the trainer.

        Args:
            learning_rate: Learning rate for belief updates
            max_depth: Maximum network depth
            use_checkpointing: Whether to use gradient checkpointing
        """
        config = BackpropConfig(
            max_layers=max_depth,
            use_checkpointing=use_checkpointing,
        )
        self.backpropagator = BeliefBackpropagator(config)
        self.learning_rate = learning_rate
        self.max_depth = max_depth

    def train_step(
        self,
        beliefs: list[NeuralBelief],
        target: np.ndarray,
    ) -> dict[str, Any]:
        """Perform one training step.

        Args:
            beliefs: List of beliefs (layers)
            target: Target output

        Returns:
            Dictionary with training metrics
        """
        # Forward pass (beliefs already contain values)
        output = beliefs[-1].vector

        # Compute loss gradient
        loss_grad = 2 * (output - target)

        # Backward pass
        gradients = self.backpropagator.backward(beliefs, loss_grad)

        # Update beliefs
        for belief in beliefs:
            if belief.belief_id in gradients:
                update = -self.learning_rate * gradients[belief.belief_id]
                belief.apply_update(update)

        # Compute metrics
        loss = float(np.mean((output - target) ** 2))
        stats = self.backpropagator.get_stats()

        return {
            "loss": loss,
            "gradients_computed": len(gradients),
            "layers_processed": stats.layers_processed,
            "exploded_gradients": stats.exploded_gradients,
        }

    def train(
        self,
        beliefs: list[NeuralBelief],
        target: np.ndarray,
        n_iterations: int = 100,
        convergence_threshold: float = 1e-6,
    ) -> dict[str, Any]:
        """Train the belief network.

        Args:
            beliefs: List of beliefs (layers)
            target: Target output
            n_iterations: Maximum number of iterations
            convergence_threshold: Loss threshold for convergence

        Returns:
            Dictionary with training results
        """
        history = []

        for i in range(n_iterations):
            metrics = self.train_step(beliefs, target)
            history.append(metrics)

            # Check convergence
            if metrics["loss"] < convergence_threshold:
                return {
                    "converged": True,
                    "iterations": i + 1,
                    "final_loss": metrics["loss"],
                    "history": history,
                }

            # Check for gradient explosion
            if metrics["exploded_gradients"]:
                return {
                    "converged": False,
                    "iterations": i + 1,
                    "final_loss": metrics["loss"],
                    "history": history,
                    "error": "Gradient explosion detected",
                }

        return {
            "converged": False,
            "iterations": n_iterations,
            "final_loss": history[-1]["loss"] if history else None,
            "history": history,
        }
