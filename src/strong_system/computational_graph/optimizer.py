"""Computational graph optimizer.

Provides optimization strategies for computational graphs including:
- Gradient checkpointing for memory-efficient backpropagation
- Operator fusion for common patterns
- Graph pruning for unused nodes

Example:
    >>> from src.strong_system.computational_graph import Graph, Node, backward
    >>> from src.strong_system.computational_graph.optimizer import GraphOptimizer
    >>> import numpy as np
    >>>
    >>> # Create a graph
    >>> graph = Graph()
    >>> x = Node(np.array([1.0, 2.0, 3.0]), name="x")
    >>> y = x * 2 + 1
    >>> graph.add_node(x)
    >>> graph.add_node(y)
    >>>
    >>> # Optimize the graph
    >>> optimizer = GraphOptimizer()
    >>> optimizer.optimize(graph, output_nodes=[y])
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

import numpy as np

from src.strong_system.computational_graph.node import Node, Operation

if TYPE_CHECKING:
    from src.strong_system.computational_graph.graph import Graph


class CheckpointStrategy(Enum):
    """Strategy for gradient checkpointing."""

    NONE = auto()  # No checkpointing
    ALL = auto()  # Checkpoint all intermediate activations
    SELECTIVE = auto()  # Checkpoint based on heuristics
    MEMORY_BOUND = auto()  # Checkpoint when memory exceeds threshold


@dataclass
class OptimizationConfig:
    """Configuration for graph optimization.

    Attributes:
        checkpoint_strategy: Strategy for gradient checkpointing
        enable_fusion: Whether to enable operator fusion
        enable_pruning: Whether to enable graph pruning
        memory_threshold_mb: Memory threshold for MEMORY_BOUND strategy
        fuse_patterns: List of operator patterns to fuse
    """

    checkpoint_strategy: CheckpointStrategy = CheckpointStrategy.SELECTIVE
    enable_fusion: bool = True
    enable_pruning: bool = True
    memory_threshold_mb: float = 1024.0  # 1GB default
    fuse_patterns: list[str] = field(default_factory=lambda: ["all"])


@dataclass
class OptimizationResult:
    """Result of graph optimization.

    Attributes:
        nodes_before: Number of nodes before optimization
        nodes_after: Number of nodes after optimization
        nodes_pruned: Number of nodes removed by pruning
        fusions_applied: Number of operator fusions applied
        checkpoints_added: Number of checkpoint nodes added
        memory_estimate_mb: Estimated memory usage in MB
    """

    nodes_before: int
    nodes_after: int
    nodes_pruned: int
    fusions_applied: int
    checkpoints_added: int
    memory_estimate_mb: float

    @property
    def node_reduction_percent(self) -> float:
        """Calculate percentage of nodes reduced."""
        if self.nodes_before == 0:
            return 0.0
        return (self.nodes_pruned / self.nodes_before) * 100


class FusedOperation(Operation):
    """Base class for fused operations."""

    def __init__(self, name: str, fused_ops: list[type[Operation]]):
        """Initialize fused operation.

        Args:
            name: Name of the fused operation
            fused_ops: List of operations being fused
        """
        super().__init__(name=name)
        self.fused_ops = fused_ops


class FusedLinearReLU(FusedOperation):
    """Fused Linear + ReLU operation.

    Computes: output = ReLU(A @ x + b)
    """

    def __init__(self):
        """Initialize fused Linear+ReLU operation."""
        from src.strong_system.computational_graph.operations import Add, MatMul, ReLU

        super().__init__("FusedLinearReLU", [MatMul, Add, ReLU])

    @classmethod
    def forward(cls, *inputs: Node, **kwargs: Any) -> Node:
        """Compute the forward pass.

        Args:
            *inputs: Input nodes (A, x, b)
            **kwargs: Additional keyword arguments

        Returns:
            A new node containing ReLU(A @ x + b)
        """

        A, x, b = inputs[0], inputs[1], inputs[2]

        # Compute A @ x
        matmul_result = np.matmul(A.value, x.value)
        # Add bias
        add_result = matmul_result + b.value
        # Apply ReLU
        result_value = np.maximum(0, add_result)

        return Node(
            value=result_value,
            operation=cls(),
            parents=[A, x, b],
            name=f"fused_linear_relu({A.name or 'A'}, {x.name or 'x'}, {b.name or 'b'})",
        )

    @classmethod
    def backward(cls, grad_output: np.ndarray, *inputs: Node) -> tuple[np.ndarray, ...]:
        """Compute the backward pass for fused Linear+ReLU.

        Args:
            grad_output: Gradient of the loss with respect to the output
            *inputs: Input nodes (A, x, b)

        Returns:
            Tuple of (grad_A, grad_x, grad_b)
        """
        A, x, b = inputs[0], inputs[1], inputs[2]

        # ReLU backward: mask where pre-activation > 0
        matmul_result = np.matmul(A.value, x.value)
        pre_activation = matmul_result + b.value
        relu_mask = (pre_activation > 0).astype(np.float64)
        grad_pre_relu = grad_output * relu_mask

        # Add backward (broadcast to bias shape)
        grad_b = grad_pre_relu.sum(axis=tuple(range(grad_pre_relu.ndim - b.value.ndim)))
        if grad_b.ndim < b.value.ndim:
            grad_b = np.expand_dims(
                grad_b, axis=tuple(range(b.value.ndim - grad_b.ndim))
            )

        # MatMul backward
        grad_A = np.matmul(grad_pre_relu, x.value.T)
        grad_x = np.matmul(A.value.T, grad_pre_relu)

        return grad_A, grad_x, grad_b


class FusedAddReLU(FusedOperation):
    """Fused Add + ReLU operation.

    Computes: output = ReLU(a + b)
    """

    def __init__(self):
        """Initialize fused Add+ReLU operation."""
        from src.strong_system.computational_graph.operations import Add, ReLU

        super().__init__("FusedAddReLU", [Add, ReLU])

    @classmethod
    def forward(cls, *inputs: Node, **kwargs: Any) -> Node:
        """Compute the forward pass.

        Args:
            *inputs: Input nodes (a, b)
            **kwargs: Additional keyword arguments

        Returns:
            A new node containing ReLU(a + b)
        """
        a, b = inputs[0], inputs[1]

        # Compute a + b, then ReLU
        add_result = a.value + b.value
        result_value = np.maximum(0, add_result)

        return Node(
            value=result_value,
            operation=cls(),
            parents=[a, b],
            name=f"fused_add_relu({a.name or 'a'}, {b.name or 'b'})",
        )

    @classmethod
    def backward(cls, grad_output: np.ndarray, *inputs: Node) -> tuple[np.ndarray, ...]:
        """Compute the backward pass for fused Add+ReLU.

        Args:
            grad_output: Gradient of the loss with respect to the output
            *inputs: Input nodes (a, b)

        Returns:
            Tuple of (grad_a, grad_b)
        """
        a, b = inputs[0], inputs[1]

        # ReLU backward: mask where (a + b) > 0
        pre_activation = a.value + b.value
        relu_mask = (pre_activation > 0).astype(np.float64)
        grad_pre_relu = grad_output * relu_mask

        # Add backward
        grad_a = grad_pre_relu
        grad_b = grad_pre_relu

        # Reduce if broadcasting occurred
        from src.strong_system.computational_graph.operations import Add

        grad_a = Add._reduce_grad(grad_a, a.value.shape)
        grad_b = Add._reduce_grad(grad_b, b.value.shape)

        return grad_a, grad_b


class FusedMulAdd(FusedOperation):
    """Fused Multiply + Add operation.

    Computes: output = a * b + c
    """

    def __init__(self):
        """Initialize fused Mul+Add operation."""
        from src.strong_system.computational_graph.operations import Add, Multiply

        super().__init__("FusedMulAdd", [Multiply, Add])

    @classmethod
    def forward(cls, *inputs: Node, **kwargs: Any) -> Node:
        """Compute the forward pass.

        Args:
            *inputs: Input nodes (a, b, c)
            **kwargs: Additional keyword arguments

        Returns:
            A new node containing a * b + c
        """
        a, b, c = inputs[0], inputs[1], inputs[2]

        # Compute a * b + c
        mul_result = a.value * b.value
        result_value = mul_result + c.value

        return Node(
            value=result_value,
            operation=cls(),
            parents=[a, b, c],
            name=f"fused_mul_add({a.name or 'a'}, {b.name or 'b'}, {c.name or 'c'})",
        )

    @classmethod
    def backward(cls, grad_output: np.ndarray, *inputs: Node) -> tuple[np.ndarray, ...]:
        """Compute the backward pass for fused Mul+Add.

        Args:
            grad_output: Gradient of the loss with respect to the output
            *inputs: Input nodes (a, b, c)

        Returns:
            Tuple of (grad_a, grad_b, grad_c)
        """
        a, b, c = inputs[0], inputs[1], inputs[2]

        from src.strong_system.computational_graph.operations import Add

        # Add backward (c branch)
        grad_c = grad_output
        grad_c = Add._reduce_grad(grad_c, c.value.shape)

        # Multiply backward (a and b branches)
        grad_a = grad_output * b.value
        grad_b = grad_output * a.value

        # Reduce if broadcasting occurred
        grad_a = Add._reduce_grad(grad_a, a.value.shape)
        grad_b = Add._reduce_grad(grad_b, b.value.shape)

        return grad_a, grad_b, grad_c


class CheckpointNode(Node):
    """A node that saves its value for checkpointing.

    Checkpoint nodes store their values during forward pass to avoid
    recomputation during backward pass.
    """

    def __init__(self, source_node: Node, name: str | None = None):
        """Initialize a checkpoint node.

        Args:
            source_node: The node whose value to checkpoint
            name: Optional name for the checkpoint
        """
        super().__init__(
            value=source_node.value.copy(),
            operation=None,  # Checkpoint is a leaf node
            parents=[],
            name=name or f"checkpoint({source_node.name or 'node'})",
        )
        self.source_node = source_node
        self.checkpoint_value = self.value.copy()

    def restore(self) -> None:
        """Restore the checkpointed value to the source node."""
        self.source_node.value = self.checkpoint_value.copy()


class GraphOptimizer:
    """Optimizer for computational graphs.

    Provides optimization strategies including:
    - Gradient checkpointing for memory efficiency
    - Operator fusion for performance
    - Graph pruning for removing unused nodes

    Attributes:
        config: Optimization configuration
        checkpoint_nodes: List of checkpoint nodes created
        fused_operations: List of fused operations applied
    """

    def __init__(self, config: OptimizationConfig | None = None):
        """Initialize the graph optimizer.

        Args:
            config: Optimization configuration. Uses defaults if None.
        """
        self.config = config or OptimizationConfig()
        self.checkpoint_nodes: list[CheckpointNode] = []
        self.fused_operations: list[Operation] = []

    def optimize(
        self,
        graph: Graph,
        output_nodes: list[Node] | None = None,
        input_nodes: list[Node] | None = None,
    ) -> OptimizationResult:
        """Optimize a computational graph.

        Applies optimizations in the following order:
        1. Graph pruning (remove unreachable nodes)
        2. Operator fusion (combine common patterns)
        3. Gradient checkpointing (if enabled)

        Args:
            graph: The computational graph to optimize
            output_nodes: List of output nodes to preserve
            input_nodes: List of input nodes (for checkpointing strategy)

        Returns:
            OptimizationResult with statistics about the optimization
        """
        nodes_before = len(graph.nodes)
        nodes_pruned = 0
        fusions_applied = 0
        checkpoints_added = 0

        # Step 1: Graph pruning
        if self.config.enable_pruning and output_nodes:
            nodes_pruned = self._prune_graph(graph, output_nodes)

        # Step 2: Operator fusion
        if self.config.enable_fusion:
            fusions_applied = self._fuse_operators(graph)

        # Step 3: Gradient checkpointing
        if self.config.checkpoint_strategy != CheckpointStrategy.NONE:
            checkpoints_added = self._add_checkpoints(graph, output_nodes, input_nodes)

        nodes_after = len(graph.nodes)
        memory_estimate = self._estimate_memory(graph)

        return OptimizationResult(
            nodes_before=nodes_before,
            nodes_after=nodes_after,
            nodes_pruned=nodes_pruned,
            fusions_applied=fusions_applied,
            checkpoints_added=checkpoints_added,
            memory_estimate_mb=memory_estimate,
        )

    def _prune_graph(self, graph: Graph, output_nodes: list[Node]) -> int:
        """Remove nodes that are not reachable from output nodes.

        Args:
            graph: The computational graph
            output_nodes: List of output nodes to preserve

        Returns:
            Number of nodes pruned
        """
        # Find all nodes reachable from outputs (backward BFS)
        reachable: set[int] = set()
        queue: deque[Node] = deque(output_nodes)

        while queue:
            node = queue.popleft()
            node_id = id(node)

            if node_id in reachable:
                continue

            reachable.add(node_id)

            # Add parents to queue (they contribute to this node)
            for parent in node.parents:
                queue.append(parent)

        # Find nodes to remove (not in reachable set)
        nodes_to_remove: list[int] = []
        for node_id, node in list(graph.nodes.items()):
            if id(node) not in reachable:
                nodes_to_remove.append(node_id)

        # Remove unreachable nodes
        for node_id in nodes_to_remove:
            graph.remove_node(node_id)

        return len(nodes_to_remove)

    def _fuse_operators(self, graph: Graph) -> int:
        """Fuse common operator patterns.

        Currently supported fusions:
        - Linear + ReLU (MatMul + Add + ReLU)
        - Add + ReLU
        - Mul + Add

        Args:
            graph: The computational graph

        Returns:
            Number of fusions applied
        """
        fusions_applied = 0

        # Get nodes in topological order for consistent processing
        try:
            sorted_nodes = graph.topological_sort()
        except ValueError:
            # Graph has cycles, can't fuse
            return 0

        # Track which nodes have been fused (to avoid double-processing)
        fused_nodes: set[int] = set()

        for node in sorted_nodes:
            node_id = id(node)
            if node_id in fused_nodes:
                continue

            # Check for fusion patterns
            fusion_result = self._try_fusion(node, fused_nodes)
            if fusion_result:
                fusions_applied += 1

        return fusions_applied

    def _try_fusion(self, node: Node, fused_nodes: set[int]) -> bool:
        """Try to fuse a node with its parents.

        Args:
            node: The node to check for fusion
            fused_nodes: Set of node IDs that have been fused

        Returns:
            True if fusion was applied, False otherwise
        """
        from src.strong_system.computational_graph.operations import (
            Add,
            MatMul,
            Multiply,
            ReLU,
        )

        # Pattern 1: ReLU(Add(...)) -> FusedAddReLU
        if (
            node.operation
            and isinstance(node.operation, ReLU)
            and len(node.parents) == 1
        ):
            parent = node.parents[0]
            if (
                parent.operation
                and isinstance(parent.operation, Add)
                and len(parent.parents) == 2
                and id(parent) not in fused_nodes
            ):
                # Apply FusedAddReLU
                a, b = parent.parents
                fused_node = FusedAddReLU.forward(a, b)

                # Replace the chain with fused node
                self._replace_node_chain(node, [parent, node], fused_node)
                fused_nodes.add(id(parent))
                fused_nodes.add(id(node))
                if fused_node.operation is not None:
                    self.fused_operations.append(fused_node.operation)
                return True

        # Pattern 2: Add(Mul(a, b), c) -> FusedMulAdd
        if (
            node.operation
            and isinstance(node.operation, Add)
            and len(node.parents) == 2
        ):
            left, right = node.parents

            # Check left side for Mul
            if (
                left.operation
                and isinstance(left.operation, Multiply)
                and len(left.parents) == 2
                and id(left) not in fused_nodes
            ):
                a, b = left.parents
                c = right
                fused_node = FusedMulAdd.forward(a, b, c)

                self._replace_node_chain(node, [left, node], fused_node)
                fused_nodes.add(id(left))
                fused_nodes.add(id(node))
                if fused_node.operation is not None:
                    self.fused_operations.append(fused_node.operation)
                return True

            # Check right side for Mul
            if (
                right.operation
                and isinstance(right.operation, Multiply)
                and len(right.parents) == 2
                and id(right) not in fused_nodes
            ):
                a, b = right.parents
                c = left
                fused_node = FusedMulAdd.forward(a, b, c)

                self._replace_node_chain(node, [right, node], fused_node)
                fused_nodes.add(id(right))
                fused_nodes.add(id(node))
                if fused_node.operation is not None:
                    self.fused_operations.append(fused_node.operation)
                return True

        # Pattern 3: ReLU(Add(MatMul(A, x), b)) -> FusedLinearReLU
        if (
            node.operation
            and isinstance(node.operation, ReLU)
            and len(node.parents) == 1
        ):
            add_node = node.parents[0]
            if (
                add_node.operation
                and isinstance(add_node.operation, Add)
                and len(add_node.parents) == 2
                and id(add_node) not in fused_nodes
            ):
                # Check if one parent is MatMul
                for i, parent in enumerate(add_node.parents):
                    if (
                        parent.operation
                        and isinstance(parent.operation, MatMul)
                        and len(parent.parents) == 2
                        and id(parent) not in fused_nodes
                    ):
                        A, x = parent.parents
                        b = add_node.parents[1 - i]  # The other parent

                        fused_node = FusedLinearReLU.forward(A, x, b)

                        self._replace_node_chain(
                            node, [parent, add_node, node], fused_node
                        )
                        fused_nodes.add(id(parent))
                        fused_nodes.add(id(add_node))
                        fused_nodes.add(id(node))
                        if fused_node.operation is not None:
                            self.fused_operations.append(fused_node.operation)
                        return True

        return False

    def _replace_node_chain(
        self, original_output: Node, chain: list[Node], fused_node: Node
    ) -> None:
        """Replace a chain of nodes with a fused node.

        This updates the children of the original output to point to the
        fused node instead.

        Args:
            original_output: The original output node of the chain
            chain: List of nodes in the chain being replaced
            fused_node: The new fused node
        """
        # Transfer children from original output to fused node
        for child in original_output.children:
            if child not in chain:  # Don't add chain nodes as children
                fused_node.children.append(child)
                # Update child's parents
                for i, parent in enumerate(child.parents):
                    if parent is original_output:
                        child.parents[i] = fused_node

    def _add_checkpoints(
        self,
        graph: Graph,
        output_nodes: list[Node] | None,
        input_nodes: list[Node] | None,
    ) -> int:
        """Add gradient checkpointing to the graph.

        Args:
            graph: The computational graph
            output_nodes: List of output nodes
            input_nodes: List of input nodes

        Returns:
            Number of checkpoints added
        """
        if self.config.checkpoint_strategy == CheckpointStrategy.NONE:
            return 0

        checkpoints_added = 0

        # Get all nodes in topological order
        try:
            sorted_nodes = graph.topological_sort()
        except ValueError:
            return 0

        if self.config.checkpoint_strategy == CheckpointStrategy.ALL:
            # Checkpoint all intermediate nodes
            for node in sorted_nodes:
                if not node.is_leaf and node not in (output_nodes or []):
                    checkpoint = CheckpointNode(node)
                    self.checkpoint_nodes.append(checkpoint)
                    checkpoints_added += 1

        elif self.config.checkpoint_strategy == CheckpointStrategy.SELECTIVE:
            # Checkpoint based on heuristics
            checkpoints_added = self._add_selective_checkpoints(
                graph, sorted_nodes, output_nodes, input_nodes
            )

        elif self.config.checkpoint_strategy == CheckpointStrategy.MEMORY_BOUND:
            # Checkpoint when memory would exceed threshold
            checkpoints_added = self._add_memory_bound_checkpoints(
                graph, sorted_nodes, output_nodes
            )

        return checkpoints_added

    def _add_selective_checkpoints(
        self,
        graph: Graph,
        sorted_nodes: list[Node],
        output_nodes: list[Node] | None,
        input_nodes: list[Node] | None,
    ) -> int:
        """Add checkpoints selectively based on heuristics.

        Heuristics:
        - Checkpoint nodes with high fan-out (many children)
        - Checkpoint expensive operations (MatMul)
        - Checkpoint at regular intervals

        Args:
            graph: The computational graph
            sorted_nodes: Nodes in topological order
            output_nodes: List of output nodes
            input_nodes: List of input nodes

        Returns:
            Number of checkpoints added
        """
        from src.strong_system.computational_graph.operations import MatMul

        checkpoints_added = 0
        checkpoint_interval = max(1, len(sorted_nodes) // 4)  # Checkpoint ~25% of nodes

        for i, node in enumerate(sorted_nodes):
            # Skip leaf nodes and output nodes
            if node.is_leaf or (output_nodes and node in output_nodes):
                continue

            should_checkpoint = False

            # Heuristic 1: High fan-out (many children depend on this)
            if len(node.children) >= 3:
                should_checkpoint = True

            # Heuristic 2: Expensive operation (MatMul)
            if node.operation and isinstance(node.operation, MatMul):
                should_checkpoint = True

            # Heuristic 3: Regular interval
            if i % checkpoint_interval == 0 and i > 0:
                should_checkpoint = True

            if should_checkpoint:
                checkpoint = CheckpointNode(node)
                self.checkpoint_nodes.append(checkpoint)
                checkpoints_added += 1

        return checkpoints_added

    def _add_memory_bound_checkpoints(
        self,
        graph: Graph,
        sorted_nodes: list[Node],
        output_nodes: list[Node] | None,
    ) -> int:
        """Add checkpoints when memory usage would exceed threshold.

        Args:
            graph: The computational graph
            sorted_nodes: Nodes in topological order
            output_nodes: List of output nodes

        Returns:
            Number of checkpoints added
        """
        checkpoints_added = 0
        current_memory = 0.0
        threshold_bytes = self.config.memory_threshold_mb * 1024 * 1024

        for node in sorted_nodes:
            # Skip leaf nodes and output nodes
            if node.is_leaf or (output_nodes and node in output_nodes):
                continue

            # Estimate memory for this node
            node_memory = node.value.nbytes if hasattr(node.value, "nbytes") else 8
            current_memory += node_memory

            # If memory exceeds threshold, add checkpoint and reset
            if current_memory > threshold_bytes:
                checkpoint = CheckpointNode(node)
                self.checkpoint_nodes.append(checkpoint)
                checkpoints_added += 1
                current_memory = node_memory  # Reset but keep current node

        return checkpoints_added

    def _estimate_memory(self, graph: Graph) -> float:
        """Estimate memory usage of the graph in MB.

        Args:
            graph: The computational graph

        Returns:
            Estimated memory usage in MB
        """
        total_bytes = 0

        for node in graph.nodes.values():
            if hasattr(node.value, "nbytes"):
                total_bytes += node.value.nbytes
            else:
                # Assume scalar (8 bytes for float64)
                total_bytes += 8

            if node.gradient is not None and hasattr(node.gradient, "nbytes"):
                total_bytes += node.gradient.nbytes
            elif node.gradient is not None:
                total_bytes += 8

        return total_bytes / (1024 * 1024)

    def get_optimization_summary(self) -> dict[str, Any]:
        """Get a summary of optimizations applied.

        Returns:
            Dictionary with optimization summary
        """
        return {
            "checkpoint_strategy": self.config.checkpoint_strategy.name,
            "fusion_enabled": self.config.enable_fusion,
            "pruning_enabled": self.config.enable_pruning,
            "checkpoint_nodes": len(self.checkpoint_nodes),
            "fused_operations": len(self.fused_operations),
            "fused_op_types": [op.__class__.__name__ for op in self.fused_operations],
        }


def optimize_graph(
    graph: Graph,
    output_nodes: list[Node] | None = None,
    checkpoint_strategy: CheckpointStrategy = CheckpointStrategy.SELECTIVE,
    enable_fusion: bool = True,
    enable_pruning: bool = True,
) -> OptimizationResult:
    """Convenience function to optimize a graph.

    Args:
        graph: The computational graph to optimize
        output_nodes: List of output nodes to preserve
        checkpoint_strategy: Strategy for gradient checkpointing
        enable_fusion: Whether to enable operator fusion
        enable_pruning: Whether to enable graph pruning

    Returns:
        OptimizationResult with statistics

    Example:
        >>> graph = Graph()
        >>> x = Node([1.0, 2.0], name="x")
        >>> y = x * 2
        >>> graph.add_node(x)
        >>> graph.add_node(y)
        >>> result = optimize_graph(graph, [y])
        >>> print(f"Nodes pruned: {result.nodes_pruned}")
    """
    config = OptimizationConfig(
        checkpoint_strategy=checkpoint_strategy,
        enable_fusion=enable_fusion,
        enable_pruning=enable_pruning,
    )
    optimizer = GraphOptimizer(config)
    return optimizer.optimize(graph, output_nodes)
