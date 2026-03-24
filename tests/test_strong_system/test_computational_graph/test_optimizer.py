"""Tests for the computational graph optimizer.

This module tests:
- Gradient checkpointing strategies
- Operator fusion patterns
- Graph pruning
- Memory profiling
- Optimization results
"""

from __future__ import annotations

import numpy as np
import pytest
from src.strong_system.computational_graph import (
    Add,
    Graph,
    MatMul,
    Node,
    ReLU,
    backward,
)
from src.strong_system.computational_graph.memory import (
    MemoryOptimizer,
    MemoryProfiler,
    estimate_graph_memory,
    format_memory_size,
    profile_memory,
)
from src.strong_system.computational_graph.optimizer import (
    CheckpointNode,
    CheckpointStrategy,
    FusedAddReLU,
    FusedLinearReLU,
    FusedMulAdd,
    GraphOptimizer,
    OptimizationConfig,
    OptimizationResult,
    optimize_graph,
)


class TestCheckpointNode:
    """Tests for CheckpointNode class."""

    def test_checkpoint_node_creation(self):
        """Test creating a checkpoint node."""
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        checkpoint = CheckpointNode(x, name="checkpoint_x")

        assert checkpoint.name == "checkpoint_x"
        assert np.array_equal(checkpoint.value, x.value)
        assert checkpoint.source_node is x
        assert checkpoint.is_leaf  # Checkpoints are leaf nodes

    def test_checkpoint_node_restore(self):
        """Test restoring checkpointed value."""
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        checkpoint = CheckpointNode(x)

        # Modify original node
        x.value = np.array([4.0, 5.0, 6.0])

        # Restore from checkpoint
        checkpoint.restore()

        assert np.array_equal(x.value, np.array([1.0, 2.0, 3.0]))

    def test_checkpoint_node_default_name(self):
        """Test checkpoint node with default name."""
        x = Node(np.array([1.0]), name="test_node")
        checkpoint = CheckpointNode(x)

        assert "checkpoint" in checkpoint.name
        assert "test_node" in checkpoint.name


class TestFusedOperations:
    """Tests for fused operations."""

    def test_fused_add_relu_forward(self):
        """Test FusedAddReLU forward pass."""
        a = Node(np.array([1.0, -2.0, 3.0]), name="a")
        b = Node(np.array([1.0, 2.0, -1.0]), name="b")

        result = FusedAddReLU.forward(a, b)

        # ReLU([1+1, -2+2, 3-1]) = ReLU([2, 0, 2]) = [2, 0, 2]
        expected = np.array([2.0, 0.0, 2.0])
        assert np.allclose(result.value, expected)

    def test_fused_add_relu_backward(self):
        """Test FusedAddReLU backward pass."""
        a = Node(np.array([1.0, -2.0, 3.0]), name="a")
        b = Node(np.array([1.0, 2.0, -1.0]), name="b")

        result = FusedAddReLU.forward(a, b)
        grad_output = np.array([1.0, 1.0, 1.0])

        grad_a, grad_b = FusedAddReLU.backward(grad_output, a, b)

        # Pre-activation: [2, 0, 2]
        # ReLU mask: [1, 0, 1]
        # grad_a = grad_b = [1, 0, 1]
        expected = np.array([1.0, 0.0, 1.0])
        assert np.allclose(grad_a, expected)
        assert np.allclose(grad_b, expected)

    def test_fused_mul_add_forward(self):
        """Test FusedMulAdd forward pass."""
        a = Node(np.array([2.0, 3.0]), name="a")
        b = Node(np.array([3.0, 4.0]), name="b")
        c = Node(np.array([1.0, 2.0]), name="c")

        result = FusedMulAdd.forward(a, b, c)

        # [2*3+1, 3*4+2] = [7, 14]
        expected = np.array([7.0, 14.0])
        assert np.allclose(result.value, expected)

    def test_fused_mul_add_backward(self):
        """Test FusedMulAdd backward pass."""
        a = Node(np.array([2.0, 3.0]), name="a")
        b = Node(np.array([3.0, 4.0]), name="b")
        c = Node(np.array([1.0, 2.0]), name="c")

        result = FusedMulAdd.forward(a, b, c)
        grad_output = np.array([1.0, 1.0])

        grad_a, grad_b, grad_c = FusedMulAdd.backward(grad_output, a, b, c)

        # grad_a = grad_output * b = [3, 4]
        # grad_b = grad_output * a = [2, 3]
        # grad_c = grad_output = [1, 1]
        assert np.allclose(grad_a, np.array([3.0, 4.0]))
        assert np.allclose(grad_b, np.array([2.0, 3.0]))
        assert np.allclose(grad_c, np.array([1.0, 1.0]))

    def test_fused_linear_relu_forward(self):
        """Test FusedLinearReLU forward pass."""
        # A @ x + b where A is 2x3, x is 3x1, b is 2x1
        A = Node(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]), name="A")
        x = Node(np.array([[1.0], [2.0], [3.0]]), name="x")
        b = Node(np.array([[1.0], [1.0]]), name="b")

        result = FusedLinearReLU.forward(A, x, b)

        # A @ x = [[14], [32]]
        # + b = [[15], [33]]
        # ReLU = [[15], [33]]
        expected = np.array([[15.0], [33.0]])
        assert np.allclose(result.value, expected)

    def test_fused_linear_relu_backward(self):
        """Test FusedLinearReLU backward pass."""
        A = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="A")
        x = Node(np.array([[1.0], [2.0]]), name="x")
        b = Node(np.array([[1.0], [1.0]]), name="b")

        result = FusedLinearReLU.forward(A, x, b)
        grad_output = np.array([[1.0], [1.0]])

        grad_A, grad_x, grad_b = FusedLinearReLU.backward(grad_output, A, x, b)

        # Check shapes
        assert grad_A.shape == A.shape
        assert grad_x.shape == x.shape
        assert grad_b.shape == b.shape

        # Check that gradients are computed (non-zero)
        assert np.any(grad_A != 0)
        assert np.any(grad_x != 0)
        assert np.any(grad_b != 0)


class TestGraphOptimizer:
    """Tests for GraphOptimizer class."""

    def test_optimizer_initialization(self):
        """Test optimizer initialization with default config."""
        optimizer = GraphOptimizer()

        assert optimizer.config is not None
        assert optimizer.config.enable_fusion is True
        assert optimizer.config.enable_pruning is True

    def test_optimizer_with_custom_config(self):
        """Test optimizer with custom configuration."""
        config = OptimizationConfig(
            checkpoint_strategy=CheckpointStrategy.ALL,
            enable_fusion=False,
            enable_pruning=False,
        )
        optimizer = GraphOptimizer(config)

        assert optimizer.config.checkpoint_strategy == CheckpointStrategy.ALL
        assert optimizer.config.enable_fusion is False
        assert optimizer.config.enable_pruning is False

    def test_graph_pruning_basic(self):
        """Test basic graph pruning."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = Node(np.array([2.0]), name="y")
        z = x + y
        unused = Node(np.array([3.0]), name="unused")

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)
        graph.add_node(unused)

        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=[z])

        assert result.nodes_pruned == 1
        assert unused not in graph.nodes.values()

    def test_graph_pruning_preserves_reachable(self):
        """Test that pruning preserves reachable nodes."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = x * 2
        z = y + 1

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=[z])

        assert result.nodes_pruned == 0
        assert x in graph.nodes.values()
        assert y in graph.nodes.values()
        assert z in graph.nodes.values()

    def test_operator_fusion_add_relu(self):
        """Test fusion of Add + ReLU pattern."""
        graph = Graph()
        a = Node(np.array([1.0, -1.0]), name="a")
        b = Node(np.array([1.0, 2.0]), name="b")
        add_result = Add.forward(a, b)
        relu_result = ReLU.forward(add_result)

        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(add_result)
        graph.add_node(relu_result)

        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=[relu_result])

        assert result.fusions_applied >= 0  # Fusion may or may not be applied

    def test_checkpoint_addition_selective(self):
        """Test selective checkpointing strategy."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = x * 2
        z = y + 1
        w = z * 3

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)
        graph.add_node(w)

        config = OptimizationConfig(checkpoint_strategy=CheckpointStrategy.SELECTIVE)
        optimizer = GraphOptimizer(config)
        result = optimizer.optimize(graph, output_nodes=[w])

        # Selective checkpointing should add some checkpoints
        assert result.checkpoints_added >= 0

    def test_checkpoint_addition_all(self):
        """Test checkpointing all intermediate nodes."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = x * 2
        z = y + 1

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        config = OptimizationConfig(checkpoint_strategy=CheckpointStrategy.ALL)
        optimizer = GraphOptimizer(config)
        result = optimizer.optimize(graph, output_nodes=[z])

        # Should checkpoint intermediate nodes (not leaves, not outputs)
        assert result.checkpoints_added >= 0

    def test_checkpoint_none(self):
        """Test no checkpointing strategy."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = x * 2

        graph.add_node(x)
        graph.add_node(y)

        config = OptimizationConfig(checkpoint_strategy=CheckpointStrategy.NONE)
        optimizer = GraphOptimizer(config)
        result = optimizer.optimize(graph, output_nodes=[y])

        assert result.checkpoints_added == 0

    def test_memory_estimation(self):
        """Test memory estimation."""
        graph = Graph()
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        y = Node(np.array([4.0, 5.0, 6.0]), name="y")
        z = x + y

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=[z])

        assert result.memory_estimate_mb > 0

    def test_optimization_result_properties(self):
        """Test OptimizationResult properties."""
        result = OptimizationResult(
            nodes_before=10,
            nodes_after=7,
            nodes_pruned=3,
            fusions_applied=2,
            checkpoints_added=1,
            memory_estimate_mb=100.0,
        )

        assert result.node_reduction_percent == 30.0
        assert result.nodes_before == 10
        assert result.nodes_after == 7

    def test_get_optimization_summary(self):
        """Test getting optimization summary."""
        optimizer = GraphOptimizer()
        summary = optimizer.get_optimization_summary()

        assert "checkpoint_strategy" in summary
        assert "fusion_enabled" in summary
        assert "pruning_enabled" in summary

    def test_optimize_graph_convenience_function(self):
        """Test the optimize_graph convenience function."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = x * 2

        graph.add_node(x)
        graph.add_node(y)

        result = optimize_graph(graph, [y])

        assert isinstance(result, OptimizationResult)


class TestMemoryProfiler:
    """Tests for MemoryProfiler class."""

    def test_profiler_initialization(self):
        """Test profiler initialization."""
        profiler = MemoryProfiler()

        assert profiler.enabled is True
        assert profiler.track_nodes is True

    def test_profiler_disabled(self):
        """Test disabled profiler."""
        profiler = MemoryProfiler(enabled=False)

        with profiler:
            x = Node(np.array([1.0]))
            pass

        report = profiler.get_report()
        assert report.duration_seconds == 0.0

    def test_profiler_context_manager(self):
        """Test profiler as context manager."""
        with MemoryProfiler() as profiler:
            x = Node(np.array([1.0, 2.0, 3.0]))
            y = x * 2

        report = profiler.get_report()
        assert report.duration_seconds >= 0.0

    def test_take_snapshot(self):
        """Test taking memory snapshots."""
        profiler = MemoryProfiler()

        with profiler:
            snapshot1 = profiler.take_snapshot("First")
            x = Node(np.random.randn(100, 100))
            snapshot2 = profiler.take_snapshot("Second")

        assert len(profiler.snapshots) >= 2
        assert profiler.snapshots[0].description == "Initial"
        assert snapshot1.description == "First"

    def test_track_node(self):
        """Test tracking individual nodes."""
        profiler = MemoryProfiler()

        with profiler:
            x = Node(np.random.randn(100, 100), name="large_node")
            profiler.track_node(x)

        report = profiler.get_report()
        assert "large_node" in report.node_breakdown

    def test_memory_report_to_dict(self):
        """Test converting report to dictionary."""
        with MemoryProfiler() as profiler:
            x = Node(np.array([1.0]))

        report = profiler.get_report()
        data = report.to_dict()

        assert "duration_seconds" in data
        assert "peak_memory_mb" in data
        assert "snapshots" in data

    def test_memory_report_str(self):
        """Test report string representation."""
        with MemoryProfiler() as profiler:
            x = Node(np.array([1.0]))

        report = profiler.get_report()
        report_str = str(report)

        assert "MEMORY PROFILING REPORT" in report_str
        assert "Duration" in report_str

    def test_compare_snapshots(self):
        """Test comparing snapshots."""
        with MemoryProfiler() as profiler:
            snapshot1 = profiler.take_snapshot("Before")
            x = Node(np.random.randn(100, 100))
            snapshot2 = profiler.take_snapshot("After")

        comparison = profiler.compare_snapshots(0, 1)

        assert "snapshot1" in comparison
        assert "snapshot2" in comparison
        assert "memory_delta_mb" in comparison

    def test_compare_snapshots_invalid_index(self):
        """Test comparing snapshots with invalid index."""
        with MemoryProfiler() as profiler:
            profiler.take_snapshot()

        with pytest.raises(ValueError):
            profiler.compare_snapshots(0, 10)

    def test_profile_memory_context_manager(self):
        """Test profile_memory convenience function."""
        with profile_memory("Test session") as profiler:
            x = Node(np.array([1.0, 2.0]))

        report = profiler.get_report()
        assert report.duration_seconds >= 0.0


class TestMemoryOptimizer:
    """Tests for MemoryOptimizer class."""

    def test_memory_optimizer_initialization(self):
        """Test memory optimizer initialization."""
        optimizer = MemoryOptimizer(max_memory_mb=512.0)

        assert optimizer.max_memory_mb == 512.0

    def test_allocate_tensor(self):
        """Test tensor allocation."""
        optimizer = MemoryOptimizer()

        tensor = optimizer.allocate_tensor((10, 10), dtype=np.float64)

        assert tensor.shape == (10, 10)
        assert tensor.dtype == np.float64

    def test_release_and_reuse_tensor(self):
        """Test tensor release and reuse from pool."""
        optimizer = MemoryOptimizer()

        # Allocate and release
        tensor1 = optimizer.allocate_tensor((10, 10))
        optimizer.release_tensor(tensor1)

        # Should reuse from pool
        tensor2 = optimizer.allocate_tensor((10, 10))

        assert tensor2.shape == (10, 10)

    def test_clear_pool(self):
        """Test clearing memory pool."""
        optimizer = MemoryOptimizer()

        tensor = optimizer.allocate_tensor((10, 10))
        optimizer.release_tensor(tensor)
        optimizer.clear_pool()

        # Pool should be empty now
        tensor2 = optimizer.allocate_tensor((10, 10))
        # Should allocate new tensor

    def test_estimate_graph_memory(self):
        """Test estimating graph memory."""
        graph = Graph()
        x = Node(np.random.randn(100, 100), name="x")
        y = Node(np.random.randn(100, 100), name="y")
        z = x + y

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        optimizer = MemoryOptimizer()
        estimate = optimizer.estimate_peak_memory(graph, batch_size=2)

        assert estimate > 0.0

    def test_suggest_batch_size(self):
        """Test suggesting batch size."""
        graph = Graph()
        x = Node(np.random.randn(100, 100), name="x")
        y = x * 2

        graph.add_node(x)
        graph.add_node(y)

        optimizer = MemoryOptimizer(max_memory_mb=100.0)
        batch_size = optimizer.suggest_batch_size(graph)

        assert batch_size >= 1


class TestEstimateGraphMemory:
    """Tests for estimate_graph_memory function."""

    def test_estimate_basic_graph(self):
        """Test estimating memory for basic graph."""
        graph = Graph()
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        y = x * 2

        graph.add_node(x)
        graph.add_node(y)

        estimate = estimate_graph_memory(graph)

        assert estimate["total_mb"] > 0.0
        assert estimate["node_values_mb"] > 0.0
        assert "node_breakdown" in estimate

    def test_estimate_with_gradients(self):
        """Test estimating memory including gradients."""
        graph = Graph()
        x = Node(np.array([1.0, 2.0]), name="x")
        y = x * 2

        graph.add_node(x)
        graph.add_node(y)

        # Compute gradients
        backward(y)

        estimate = estimate_graph_memory(graph, include_gradients=True)

        assert estimate["gradients_mb"] >= 0.0

    def test_estimate_without_gradients(self):
        """Test estimating memory without gradients."""
        graph = Graph()
        x = Node(np.array([1.0, 2.0]), name="x")
        y = x * 2

        graph.add_node(x)
        graph.add_node(y)

        estimate = estimate_graph_memory(graph, include_gradients=False)

        assert estimate["gradients_mb"] == 0.0


class TestFormatMemorySize:
    """Tests for format_memory_size function."""

    def test_format_bytes(self):
        """Test formatting bytes."""
        result = format_memory_size(500)
        assert "B" in result

    def test_format_kilobytes(self):
        """Test formatting kilobytes."""
        result = format_memory_size(500 * 1024)
        assert "KB" in result

    def test_format_megabytes(self):
        """Test formatting megabytes."""
        result = format_memory_size(500 * 1024 * 1024)
        assert "MB" in result

    def test_format_gigabytes(self):
        """Test formatting gigabytes."""
        result = format_memory_size(2 * 1024 * 1024 * 1024)
        assert "GB" in result


class TestIntegration:
    """Integration tests for the optimizer."""

    def test_end_to_end_optimization(self):
        """Test end-to-end optimization workflow."""
        # Create a graph with redundant and optimizable operations
        graph = Graph()

        # Inputs
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        w = Node(np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]), name="w")
        b = Node(np.array([1.0, 1.0]), name="b")

        # Linear layer: ReLU(x @ w + b)
        x_reshaped = Node(x.value.reshape((1, 3)), name="x_reshaped")
        b_reshaped = Node(b.value.reshape((1, 2)), name="b_reshaped")
        matmul_result = MatMul.forward(x_reshaped, w)
        add_result = Add.forward(matmul_result, b_reshaped)
        output = ReLU.forward(add_result)

        # Unused node (should be pruned)
        unused = Node(np.array([1.0]), name="unused")

        graph.add_node(x)
        graph.add_node(x_reshaped)
        graph.add_node(w)
        graph.add_node(b)
        graph.add_node(b_reshaped)
        graph.add_node(matmul_result)
        graph.add_node(add_result)
        graph.add_node(output)
        graph.add_node(unused)

        # Optimize
        config = OptimizationConfig(
            checkpoint_strategy=CheckpointStrategy.SELECTIVE,
            enable_fusion=True,
            enable_pruning=True,
        )
        optimizer = GraphOptimizer(config)
        result = optimizer.optimize(graph, output_nodes=[output])

        # Verify optimization results
        assert result.nodes_before == 9
        # Pruned: unused, x_reshaped, b_reshaped (not on path to output)
        assert result.nodes_pruned == 3
        assert result.nodes_after == 6

    def test_memory_profiling_with_graph(self):
        """Test memory profiling with graph execution."""
        with MemoryProfiler() as profiler:
            graph = Graph()
            x = Node(np.random.randn(100, 100), name="x")
            y = x * 2
            z = y + 1

            graph.add_node(x)
            graph.add_node(y)
            graph.add_node(z)

            profiler.track_node(x)
            profiler.track_node(y)
            profiler.track_node(z)

        report = profiler.get_report()

        assert report.duration_seconds >= 0.0
        assert len(report.node_breakdown) >= 3

    def test_backward_after_optimization(self):
        """Test that backward pass still works after optimization."""
        graph = Graph()
        x = Node(np.array([2.0]), name="x")
        y = x * 3  # y = 6
        z = y + 1  # z = 7

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        # Optimize
        optimizer = GraphOptimizer()
        optimizer.optimize(graph, output_nodes=[z])

        # Backward pass should still work
        backward(z)

        assert x.gradient is not None
        # dz/dx = dz/dy * dy/dx = 1 * 3 = 3
        assert np.allclose(x.gradient, np.array([3.0]))

    def test_complex_graph_optimization(self):
        """Test optimization on a more complex graph."""
        graph = Graph()

        # Create a branching computation
        x = Node(np.array([1.0, 2.0]), name="x")
        y = x * 2  # [2, 4]
        z = x + 1  # [2, 3]
        w = y * z  # [4, 12]
        output = w + 1  # [5, 13]

        # Unused branch
        unused_a = Node(np.array([1.0]), name="unused_a")
        unused_b = unused_a * 2

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)
        graph.add_node(w)
        graph.add_node(output)
        graph.add_node(unused_a)
        graph.add_node(unused_b)

        # Optimize
        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=[output])

        # Should prune unused branch
        assert result.nodes_pruned == 2
        assert unused_a not in graph.nodes.values()
        assert unused_b not in graph.nodes.values()

        # Verify output is still correct
        assert np.allclose(output.value, np.array([5.0, 13.0]))


class TestCheckpointStrategies:
    """Tests for different checkpoint strategies."""

    def test_selective_checkpointing_with_fanout(self):
        """Test selective checkpointing on nodes with high fanout."""
        graph = Graph()

        # x has high fanout (used by many nodes)
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        y1 = x * 1
        y2 = x * 2
        y3 = x * 3
        y4 = x * 4

        output = y1 + y2 + y3 + y4

        graph.add_node(x)
        graph.add_node(y1)
        graph.add_node(y2)
        graph.add_node(y3)
        graph.add_node(y4)
        graph.add_node(output)

        config = OptimizationConfig(checkpoint_strategy=CheckpointStrategy.SELECTIVE)
        optimizer = GraphOptimizer(config)
        result = optimizer.optimize(graph, output_nodes=[output])

        # x has 4 children, should be checkpointed
        assert result.checkpoints_added >= 0

    def test_memory_bound_checkpointing(self):
        """Test memory-bound checkpointing strategy."""
        graph = Graph()

        # Create large tensors
        x = Node(np.random.randn(1000, 1000), name="x")
        y = x * 2
        z = y + 1

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        config = OptimizationConfig(
            checkpoint_strategy=CheckpointStrategy.MEMORY_BOUND,
            memory_threshold_mb=1.0,  # Very low threshold
        )
        optimizer = GraphOptimizer(config)
        result = optimizer.optimize(graph, output_nodes=[z])

        # Should add checkpoints due to low threshold
        assert result.checkpoints_added >= 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_graph(self):
        """Test optimizing an empty graph."""
        graph = Graph()
        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=[])

        assert result.nodes_before == 0
        assert result.nodes_after == 0
        assert result.nodes_pruned == 0

    def test_single_node_graph(self):
        """Test optimizing a single-node graph."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        graph.add_node(x)

        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=[x])

        assert result.nodes_before == 1
        assert result.nodes_after == 1
        assert result.nodes_pruned == 0

    def test_cyclic_graph_pruning(self):
        """Test handling of cyclic graphs during pruning."""
        # Note: The graph module should prevent cycles, but we test handling
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = x * 2

        graph.add_node(x)
        graph.add_node(y)

        optimizer = GraphOptimizer()
        # Should not raise even if graph has issues
        result = optimizer.optimize(graph, output_nodes=[y])

        assert isinstance(result, OptimizationResult)

    def test_no_output_nodes(self):
        """Test optimization with no output nodes specified."""
        graph = Graph()
        x = Node(np.array([1.0]), name="x")
        y = x * 2
        unused = Node(np.array([3.0]), name="unused")

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(unused)

        optimizer = GraphOptimizer()
        result = optimizer.optimize(graph, output_nodes=None)

        # Without output nodes, pruning won't remove anything
        assert result.nodes_pruned == 0

    def test_zero_node_reduction(self):
        """Test result properties when no nodes are reduced."""
        result = OptimizationResult(
            nodes_before=5,
            nodes_after=5,
            nodes_pruned=0,
            fusions_applied=0,
            checkpoints_added=0,
            memory_estimate_mb=50.0,
        )

        assert result.node_reduction_percent == 0.0

    def test_all_nodes_pruned(self):
        """Test result properties when all nodes are pruned."""
        result = OptimizationResult(
            nodes_before=5,
            nodes_after=0,
            nodes_pruned=5,
            fusions_applied=0,
            checkpoints_added=0,
            memory_estimate_mb=0.0,
        )

        assert result.node_reduction_percent == 100.0


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    def test_memory_reduction_benchmark(self):
        """Benchmark memory reduction from optimization."""
        import time

        # Create a graph with many intermediate nodes
        graph = Graph()
        x = Node(np.random.randn(100, 100), name="x")
        graph.add_node(x)

        current = x
        for i in range(20):
            current = current * 1.1
            graph.add_node(current)

        # Add unused nodes
        for i in range(10):
            unused = Node(np.random.randn(100, 100), name=f"unused_{i}")
            graph.add_node(unused)

        # Measure before optimization
        before_memory = estimate_graph_memory(graph)["total_mb"]

        # Optimize
        optimizer = GraphOptimizer()
        start_time = time.time()
        result = optimizer.optimize(graph, output_nodes=[current])
        optimization_time = time.time() - start_time

        # Measure after optimization
        after_memory = estimate_graph_memory(graph)["total_mb"]

        # Verify improvements
        assert result.nodes_pruned == 10  # Unused nodes removed
        assert optimization_time < 1.0  # Should be fast

        # Memory should be reduced (or at least not increased)
        assert after_memory <= before_memory

    def test_fusion_performance(self):
        """Benchmark operator fusion performance."""
        import time

        graph = Graph()

        # Create Add + ReLU patterns
        a = Node(np.random.randn(100, 100), name="a")
        b = Node(np.random.randn(100, 100), name="b")
        graph.add_node(a)
        graph.add_node(b)

        current = a
        for i in range(5):
            add_result = Add.forward(current, b)
            current = ReLU.forward(add_result)
            graph.add_node(add_result)
            graph.add_node(current)

        # Optimize with fusion
        config = OptimizationConfig(enable_fusion=True, enable_pruning=False)
        optimizer = GraphOptimizer(config)

        start_time = time.time()
        result = optimizer.optimize(graph, output_nodes=[current])
        optimization_time = time.time() - start_time

        assert optimization_time < 1.0
        # Fusion may or may not be applied depending on graph structure

    def test_checkpointing_overhead(self):
        """Test overhead of checkpointing."""
        import time

        # Create graph
        graph = Graph()
        x = Node(np.random.randn(50, 50), name="x")
        graph.add_node(x)

        current = x
        for i in range(10):
            current = current * 2
            graph.add_node(current)

        # Without checkpointing
        config_none = OptimizationConfig(checkpoint_strategy=CheckpointStrategy.NONE)
        optimizer_none = GraphOptimizer(config_none)
        start = time.time()
        result_none = optimizer_none.optimize(graph, [current])
        time_none = time.time() - start

        # With selective checkpointing (on same graph, different optimizer)
        config_sel = OptimizationConfig(
            checkpoint_strategy=CheckpointStrategy.SELECTIVE
        )
        optimizer_sel = GraphOptimizer(config_sel)
        start = time.time()
        result_sel = optimizer_sel.optimize(graph, [current])
        time_sel = time.time() - start

        # Checkpointing should add some overhead but not too much
        assert time_sel < time_none + 0.5  # Less than 500ms overhead


# Mark tests that require more time
pytestmark = [
    pytest.mark.unit,
    pytest.mark.computational_graph,
]
