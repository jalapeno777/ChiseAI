"""Tests for the computational graph module.

Tests cover:
    - Node creation and basic operations
    - Graph management
    - Operations (Add, Multiply, ReLU)
    - Topological sorting
    - Edge cases and error handling
"""

import numpy as np
import pytest

from src.strong_system.computational_graph import (
    Add,
    Graph,
    MatMul,
    Multiply,
    Node,
    Operation,
    ReLU,
    Sum,
)


class TestNode:
    """Tests for the Node class."""

    def test_node_creation_with_scalar(self):
        """Test creating a node with a scalar value."""
        node = Node(5.0, name="scalar")
        assert node.value == np.array(5.0)
        assert node.name == "scalar"
        assert node.gradient is None
        assert node.is_leaf

    def test_node_creation_with_array(self):
        """Test creating a node with a numpy array."""
        arr = np.array([1.0, 2.0, 3.0])
        node = Node(arr, name="array")
        np.testing.assert_array_equal(node.value, arr)
        assert node.shape == (3,)

    def test_node_creation_with_2d_array(self):
        """Test creating a node with a 2D array."""
        arr = np.array([[1.0, 2.0], [3.0, 4.0]])
        node = Node(arr)
        assert node.shape == (2, 2)
        assert node.ndim == 2

    def test_node_is_leaf(self):
        """Test leaf node detection."""
        leaf = Node(1.0)
        assert leaf.is_leaf

        # Non-leaf node created by operation
        result = Add.forward(Node(1.0), Node(2.0))
        assert not result.is_leaf

    def test_node_repr(self):
        """Test string representation of nodes."""
        node = Node(np.array([1.0, 2.0]), name="test")
        repr_str = repr(node)
        assert "Node" in repr_str
        assert "test" in repr_str
        assert "shape=" in repr_str

    def test_node_zero_grad(self):
        """Test zeroing gradients."""
        node = Node(np.array([1.0, 2.0, 3.0]))
        node.zero_grad()
        assert node.gradient is not None
        np.testing.assert_array_equal(node.gradient, np.array([0.0, 0.0, 0.0]))

    def test_node_set_grad(self):
        """Test setting gradients."""
        node = Node(1.0)
        node.set_grad(2.0)
        assert node.gradient == np.array(2.0)

        # Test accumulation
        node.set_grad(3.0)
        assert node.gradient == np.array(5.0)

    def test_node_shape_property(self):
        """Test shape property."""
        node = Node(np.array([[1, 2, 3], [4, 5, 6]]))
        assert node.shape == (2, 3)

    def test_node_ndim_property(self):
        """Test ndim property."""
        node1 = Node(1.0)
        node2 = Node([1, 2, 3])
        node3 = Node([[1, 2], [3, 4]])

        assert node1.ndim == 0
        assert node2.ndim == 1
        assert node3.ndim == 2


class TestNodeArithmetic:
    """Tests for node arithmetic operations."""

    def test_add_nodes(self):
        """Test adding two nodes."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        b = Node(np.array([4.0, 5.0, 6.0]))
        result = a + b

        expected = np.array([5.0, 7.0, 9.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_add_node_and_scalar(self):
        """Test adding a node and a scalar."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        result = a + 5.0

        expected = np.array([6.0, 7.0, 8.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_radd_scalar_and_node(self):
        """Test adding a scalar and a node (reverse add)."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        result = 5.0 + a

        expected = np.array([6.0, 7.0, 8.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_subtract_nodes(self):
        """Test subtracting two nodes."""
        a = Node(np.array([5.0, 6.0, 7.0]))
        b = Node(np.array([1.0, 2.0, 3.0]))
        result = a - b

        expected = np.array([4.0, 4.0, 4.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_subtract_scalar_from_node(self):
        """Test subtracting a scalar from a node."""
        a = Node(np.array([5.0, 6.0, 7.0]))
        result = a - 2.0

        expected = np.array([3.0, 4.0, 5.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_rsubtract_node_from_scalar(self):
        """Test subtracting a node from a scalar."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        result = 10.0 - a

        expected = np.array([9.0, 8.0, 7.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_multiply_nodes(self):
        """Test multiplying two nodes."""
        a = Node(np.array([2.0, 3.0, 4.0]))
        b = Node(np.array([3.0, 2.0, 1.0]))
        result = a * b

        expected = np.array([6.0, 6.0, 4.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_multiply_node_and_scalar(self):
        """Test multiplying a node by a scalar."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        result = a * 3.0

        expected = np.array([3.0, 6.0, 9.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_rmultiply_scalar_and_node(self):
        """Test multiplying a scalar by a node."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        result = 3.0 * a

        expected = np.array([3.0, 6.0, 9.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_chained_operations(self):
        """Test chained arithmetic operations."""
        x = Node(np.array([1.0, 2.0, 3.0]))
        y = Node(np.array([4.0, 5.0, 6.0]))

        # z = (x + y) * 2
        z = (x + y) * 2

        expected = np.array([10.0, 14.0, 18.0])
        np.testing.assert_array_equal(z.value, expected)


class TestGraph:
    """Tests for the Graph class."""

    def test_graph_creation(self):
        """Test creating an empty graph."""
        graph = Graph(name="test_graph")
        assert graph.name == "test_graph"
        assert len(graph) == 0

    def test_add_node(self):
        """Test adding nodes to the graph."""
        graph = Graph()
        node = Node(1.0)
        node_id = graph.add_node(node)

        assert len(graph) == 1
        assert graph.get_node(node_id) is node

    def test_get_node_nonexistent(self):
        """Test getting a non-existent node."""
        graph = Graph()
        assert graph.get_node(999) is None

    def test_remove_node(self):
        """Test removing a node from the graph."""
        graph = Graph()
        node = Node(1.0)
        node_id = graph.add_node(node)

        removed = graph.remove_node(node_id)
        assert removed is node
        assert len(graph) == 0

    def test_remove_nonexistent_node(self):
        """Test removing a non-existent node."""
        graph = Graph()
        assert graph.remove_node(999) is None

    def test_contains_node(self):
        """Test checking if a node is in the graph."""
        graph = Graph()
        node = Node(1.0)

        assert node not in graph
        graph.add_node(node)
        assert node in graph

    def test_connect_nodes(self):
        """Test connecting nodes in the graph."""
        graph = Graph()
        parent = Node(1.0)
        child = Node(2.0)

        graph.add_node(parent)
        graph.add_node(child)
        graph.connect(parent, child)

        assert parent in child.parents
        assert child in parent.children

    def test_connect_node_not_in_graph(self):
        """Test connecting a node not in the graph raises error."""
        graph = Graph()
        parent = Node(1.0)
        child = Node(2.0)

        graph.add_node(parent)

        with pytest.raises(ValueError, match="to_node must be added"):
            graph.connect(parent, child)

    def test_topological_sort_linear(self):
        """Test topological sort on a linear chain."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)
        c = Node(3.0)

        id_a = graph.add_node(a)
        id_b = graph.add_node(b)
        id_c = graph.add_node(c)

        graph.connect(a, b)
        graph.connect(b, c)

        order = graph.topological_sort()
        assert order == [a, b, c]

    def test_topological_sort_diamond(self):
        """Test topological sort on a diamond-shaped graph."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)
        c = Node(3.0)
        d = Node(4.0)

        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)
        graph.add_node(d)

        # Diamond: a -> b, a -> c, b -> d, c -> d
        graph.connect(a, b)
        graph.connect(a, c)
        graph.connect(b, d)
        graph.connect(c, d)

        order = graph.topological_sort()
        assert order[0] == a  # a must be first
        assert order[-1] == d  # d must be last
        # b and c can be in either order
        assert order.index(b) < order.index(d)
        assert order.index(c) < order.index(d)

    def test_topological_sort_cycle_detection(self):
        """Test that cycles are detected in topological sort."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)
        c = Node(3.0)

        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)

        # Create cycle: a -> b -> c -> a
        graph.connect(a, b)
        graph.connect(b, c)
        graph.connect(c, a)

        with pytest.raises(ValueError, match="cycle"):
            graph.topological_sort()

    def test_get_leaf_nodes(self):
        """Test getting leaf nodes."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)
        c = Node(3.0)

        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)

        graph.connect(a, b)
        graph.connect(a, c)

        leaves = graph.get_leaf_nodes()
        assert a in leaves
        assert b not in leaves
        assert c not in leaves

    def test_get_output_nodes(self):
        """Test getting output nodes."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)
        c = Node(3.0)

        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)

        graph.connect(a, b)
        graph.connect(a, c)

        outputs = graph.get_output_nodes()
        assert a not in outputs
        assert b in outputs
        assert c in outputs

    def test_clear(self):
        """Test clearing the graph."""
        graph = Graph()
        node = Node(1.0)
        graph.add_node(node)

        graph.clear()
        assert len(graph) == 0
        assert graph.get_node(0) is None

    def test_to_dict(self):
        """Test converting graph to dictionary."""
        graph = Graph(name="test")
        node = Node(np.array([1.0, 2.0]), name="node1")
        graph.add_node(node)

        result = graph.to_dict()
        assert result["name"] == "test"
        assert result["node_count"] == 1

    def test_get_execution_order(self):
        """Test getting execution order."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)

        graph.add_node(a)
        graph.add_node(b)
        graph.connect(a, b)

        order = graph.get_execution_order()
        assert order == [a, b]

    def test_validate_empty_graph(self):
        """Test validating an empty graph."""
        graph = Graph()
        errors = graph.validate()
        assert errors == []

    def test_validate_valid_graph(self):
        """Test validating a valid graph."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)

        graph.add_node(a)
        graph.add_node(b)
        graph.connect(a, b)

        errors = graph.validate()
        assert errors == []

    def test_validate_cycle(self):
        """Test validating a graph with a cycle."""
        graph = Graph()
        a = Node(1.0)
        b = Node(2.0)

        graph.add_node(a)
        graph.add_node(b)
        graph.connect(a, b)
        graph.connect(b, a)

        errors = graph.validate()
        assert len(errors) > 0
        assert any("cycle" in error.lower() for error in errors)


class TestOperations:
    """Tests for operation classes."""

    def test_add_operation(self):
        """Test Add operation."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        b = Node(np.array([4.0, 5.0, 6.0]))
        result = Add.forward(a, b)

        expected = np.array([5.0, 7.0, 9.0])
        np.testing.assert_array_equal(result.value, expected)
        assert result.operation is not None

    def test_add_backward(self):
        """Test Add backward pass."""
        a = Node(np.array([1.0, 2.0, 3.0]))
        b = Node(np.array([4.0, 5.0, 6.0]))
        grad_output = np.array([1.0, 1.0, 1.0])

        grad_a, grad_b = Add.backward(grad_output, a, b)

        np.testing.assert_array_equal(grad_a, grad_output)
        np.testing.assert_array_equal(grad_b, grad_output)

    def test_multiply_operation(self):
        """Test Multiply operation."""
        a = Node(np.array([2.0, 3.0, 4.0]))
        b = Node(np.array([3.0, 2.0, 1.0]))
        result = Multiply.forward(a, b)

        expected = np.array([6.0, 6.0, 4.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_multiply_backward(self):
        """Test Multiply backward pass."""
        a = Node(np.array([2.0, 3.0]))
        b = Node(np.array([4.0, 5.0]))
        grad_output = np.array([1.0, 1.0])

        grad_a, grad_b = Multiply.backward(grad_output, a, b)

        np.testing.assert_array_equal(grad_a, np.array([4.0, 5.0]))
        np.testing.assert_array_equal(grad_b, np.array([2.0, 3.0]))

    def test_relu_operation_positive(self):
        """Test ReLU on positive values."""
        x = Node(np.array([1.0, 2.0, 3.0]))
        result = ReLU.forward(x)

        expected = np.array([1.0, 2.0, 3.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_relu_operation_negative(self):
        """Test ReLU on negative values."""
        x = Node(np.array([-1.0, -2.0, -3.0]))
        result = ReLU.forward(x)

        expected = np.array([0.0, 0.0, 0.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_relu_operation_mixed(self):
        """Test ReLU on mixed values."""
        x = Node(np.array([-1.0, 0.0, 1.0]))
        result = ReLU.forward(x)

        expected = np.array([0.0, 0.0, 1.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_relu_backward(self):
        """Test ReLU backward pass."""
        x = Node(np.array([-1.0, 0.0, 1.0, 2.0]))
        grad_output = np.array([1.0, 1.0, 1.0, 1.0])

        (grad_x,) = ReLU.backward(grad_output, x)

        expected = np.array([0.0, 0.0, 1.0, 1.0])
        np.testing.assert_array_equal(grad_x, expected)

    def test_matmul_operation(self):
        """Test MatMul operation."""
        a = Node(np.array([[1.0, 2.0], [3.0, 4.0]]))
        b = Node(np.array([[5.0, 6.0], [7.0, 8.0]]))
        result = MatMul.forward(a, b)

        expected = np.array([[19.0, 22.0], [43.0, 50.0]])
        np.testing.assert_array_equal(result.value, expected)

    def test_matmul_backward(self):
        """Test MatMul backward pass."""
        a = Node(np.array([[1.0, 2.0], [3.0, 4.0]]))
        b = Node(np.array([[5.0, 6.0], [7.0, 8.0]]))
        grad_output = np.array([[1.0, 0.0], [0.0, 1.0]])

        grad_a, grad_b = MatMul.backward(grad_output, a, b)

        # grad_a = grad_output @ b.T
        expected_grad_a = np.array([[5.0, 7.0], [6.0, 8.0]])
        np.testing.assert_array_equal(grad_a, expected_grad_a)

    def test_matmul_shape_mismatch(self):
        """Test MatMul with incompatible shapes."""
        a = Node(np.array([[1.0, 2.0, 3.0]]))  # Shape (1, 3)
        b = Node(np.array([[1.0, 2.0]]))  # Shape (1, 2)

        with pytest.raises(ValueError, match="shape mismatch"):
            MatMul.forward(a, b)

    def test_sum_operation_all(self):
        """Test Sum operation over all elements."""
        x = Node(np.array([[1.0, 2.0], [3.0, 4.0]]))
        result = Sum.forward(x)

        assert result.value == 10.0

    def test_sum_operation_axis(self):
        """Test Sum operation over specific axis."""
        x = Node(np.array([[1.0, 2.0], [3.0, 4.0]]))
        result = Sum.forward(x, axis=0)

        expected = np.array([4.0, 6.0])
        np.testing.assert_array_equal(result.value, expected)

    def test_sum_operation_keepdims(self):
        """Test Sum operation with keepdims."""
        x = Node(np.array([[1.0, 2.0], [3.0, 4.0]]))
        result = Sum.forward(x, axis=0, keepdims=True)

        expected = np.array([[4.0, 6.0]])
        np.testing.assert_array_equal(result.value, expected)

    def test_sum_backward(self):
        """Test Sum backward pass."""
        x = Node(np.array([[1.0, 2.0], [3.0, 4.0]]))
        grad_output = np.array(5.0)

        (grad_x,) = Sum.backward(grad_output, x)

        expected = np.array([[5.0, 5.0], [5.0, 5.0]])
        np.testing.assert_array_equal(grad_x, expected)


class TestOperationBase:
    """Tests for the Operation base class."""

    def test_operation_creation(self):
        """Test creating an operation."""
        op = Operation(name="test_op")
        assert op.name == "test_op"

    def test_operation_default_name(self):
        """Test operation default name."""
        op = Operation()
        assert op.name == "Operation"

    def test_operation_repr(self):
        """Test operation string representation."""
        op = Operation(name="test")
        assert "Operation" in repr(op)
        assert "test" in repr(op)

    def test_forward_not_implemented(self):
        """Test that base Operation forward raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            Operation.forward()

    def test_backward_not_implemented(self):
        """Test that base Operation backward raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            Operation.backward(np.array([1.0]))


class TestIntegration:
    """Integration tests for the computational graph."""

    def test_simple_neural_network_forward(self):
        """Test a simple neural network forward pass."""
        # Create input
        x = Node(np.array([1.0, 2.0, 3.0]), name="input")

        # Create weights
        W = Node(
            np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]),
            name="weights",
        )
        b = Node(np.array([0.1, 0.2, 0.3]), name="bias")

        # Forward pass: z = ReLU(x @ W + b)
        hidden = MatMul.forward(x, W)
        biased = Add.forward(hidden, b)
        output = ReLU.forward(biased)

        # Verify output shape
        assert output.shape == (3,)
        # Verify all values are non-negative (ReLU)
        assert np.all(output.value >= 0)

    def test_graph_with_operations(self):
        """Test building a graph with operations."""
        graph = Graph()

        # Create computation: z = (x + y) * 2
        x = Node(np.array([1.0, 2.0]), name="x")
        y = Node(np.array([3.0, 4.0]), name="y")

        graph.add_node(x)
        graph.add_node(y)

        # Perform operations
        sum_node = Add.forward(x, y)
        two = Node(np.array([2.0, 2.0]), name="two")
        graph.add_node(two)

        z = Multiply.forward(sum_node, two)
        graph.add_node(z)

        # Verify graph structure
        assert len(graph) == 4
        assert x in z.parents[0].parents  # x is grandparent of z

    def test_complex_computation_graph(self):
        """Test a more complex computation graph."""
        # Build: a = 2, b = 3, c = 4
        # f = (a + b) * (b + c)
        # Expected: (2 + 3) * (3 + 4) = 5 * 7 = 35

        a = Node(np.array([2.0]))
        b = Node(np.array([3.0]))
        c = Node(np.array([4.0]))

        ab_sum = Add.forward(a, b)  # 5
        bc_sum = Add.forward(b, c)  # 7
        result = Multiply.forward(ab_sum, bc_sum)  # 35

        assert result.value[0] == 35.0
