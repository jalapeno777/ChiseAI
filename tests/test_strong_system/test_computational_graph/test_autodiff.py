"""Tests for the auto-differentiation engine.

This module tests the backward() function and related autodiff utilities
for computing gradients through the computational graph.
"""

import numpy as np
import pytest

from src.strong_system.computational_graph import (
    Add,
    Graph,
    MatMul,
    Multiply,
    Node,
    ReLU,
    Sum,
    backward,
    clear_gradients,
    compute_gradients,
)


class TestBackwardBasic:
    """Test basic backward pass functionality."""

    def test_backward_scalar_simple(self):
        """Test simple scalar gradient: y = x^2."""
        x = Node(3.0, name="x")
        y = x * x  # y = x^2

        backward(y)

        # dy/dx = 2*x = 6
        assert x.gradient is not None
        assert x.gradient.shape == ()
        assert np.isclose(x.gradient, 6.0)

    def test_backward_scalar_with_addition(self):
        """Test scalar gradient with addition: z = x + y."""
        x = Node(2.0, name="x")
        y = Node(3.0, name="y")
        z = x + y  # z = x + y

        backward(z)

        # dz/dx = 1, dz/dy = 1
        assert np.isclose(x.gradient, 1.0)
        assert np.isclose(y.gradient, 1.0)

    def test_backward_scalar_chain_rule(self):
        """Test chain rule with multiple operations: z = (x + 1) * 2."""
        x = Node(3.0, name="x")
        temp = x + 1.0  # temp = x + 1
        z = temp * 2.0  # z = (x + 1) * 2 = 2x + 2

        backward(z)

        # dz/dx = 2
        assert np.isclose(x.gradient, 2.0)

    def test_backward_with_custom_grad_output(self):
        """Test backward with custom grad_output."""
        x = Node(3.0, name="x")
        y = x * x  # y = x^2

        # dL/dy = 2.0 (some external loss gradient)
        backward(y, grad_output=2.0)

        # dL/dx = dL/dy * dy/dx = 2 * 2*x = 12
        assert np.isclose(x.gradient, 12.0)


class TestBackwardVector:
    """Test backward pass with vector values."""

    def test_backward_vector_element_wise(self):
        """Test element-wise gradient for vectors."""
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        y = x * x  # y = x^2 element-wise

        backward(y)

        # dy/dx = 2*x = [2, 4, 6]
        expected = np.array([2.0, 4.0, 6.0])
        assert np.allclose(x.gradient, expected)

    def test_backward_vector_addition(self):
        """Test gradient for vector addition."""
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        y = Node(np.array([4.0, 5.0, 6.0]), name="y")
        z = x + y

        backward(z)

        # dz/dx = [1, 1, 1], dz/dy = [1, 1, 1]
        assert np.allclose(x.gradient, np.ones(3))
        assert np.allclose(y.gradient, np.ones(3))

    def test_backward_vector_scalar_broadcast(self):
        """Test gradient with scalar broadcasting."""
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        y = x * 2.0  # Broadcast 2.0 to all elements

        backward(y)

        # dy/dx = [2, 2, 2]
        assert np.allclose(x.gradient, np.array([2.0, 2.0, 2.0]))


class TestMatrixGradients:
    """Test backward pass with matrix values."""

    def test_backward_matmul_simple(self):
        """Test matrix multiplication gradient."""
        A = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="A")
        B = Node(np.array([[5.0, 6.0], [7.0, 8.0]]), name="B")
        C = A @ B  # Matrix multiplication

        backward(C)

        # C = A @ B
        # dC/dA = grad_output @ B.T
        # dC/dB = A.T @ grad_output
        # With grad_output = [[1, 1], [1, 1]] (ones)
        expected_A_grad = np.array([[11.0, 15.0], [11.0, 15.0]])
        expected_B_grad = np.array([[4.0, 4.0], [6.0, 6.0]])

        assert np.allclose(A.gradient, expected_A_grad)
        assert np.allclose(B.gradient, expected_B_grad)

    def test_backward_matmul_with_sum(self):
        """Test matrix multiplication followed by sum."""
        A = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="A")
        B = Node(np.array([[5.0, 6.0], [7.0, 8.0]]), name="B")
        C = A @ B
        s = Sum.forward(C)  # Sum all elements

        backward(s)

        # Sum of C = sum(A @ B)
        # d(s)/dA = d(s)/dC @ dC/dA = ones @ B.T
        # d(s)/dB = d(s)/dC @ dC/dB = A.T @ ones
        expected_A_grad = np.array([[11.0, 15.0], [11.0, 15.0]])
        expected_B_grad = np.array([[4.0, 4.0], [6.0, 6.0]])

        assert np.allclose(A.gradient, expected_A_grad)
        assert np.allclose(B.gradient, expected_B_grad)

    def test_backward_matrix_element_wise(self):
        """Test element-wise operations on matrices."""
        A = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="A")
        B = A * A  # Element-wise square

        backward(B)

        # dB/dA = 2*A = [[2, 4], [6, 8]]
        expected = np.array([[2.0, 4.0], [6.0, 8.0]])
        assert np.allclose(A.gradient, expected)


class TestChainRule:
    """Test chain rule with multiple operations."""

    def test_chain_rule_add_multiply(self):
        """Test chain rule: z = (x + y) * x."""
        x = Node(2.0, name="x")
        y = Node(3.0, name="y")
        temp = x + y  # temp = 5
        z = temp * x  # z = 5 * 2 = 10

        backward(z)

        # z = (x + y) * x = x^2 + xy
        # dz/dx = 2x + y = 4 + 3 = 7
        # dz/dy = x = 2
        assert np.isclose(x.gradient, 7.0)
        assert np.isclose(y.gradient, 2.0)

    def test_chain_rule_complex(self):
        """Test complex chain: z = (x * y + x) * y."""
        x = Node(2.0, name="x")
        y = Node(3.0, name="y")
        temp1 = x * y  # temp1 = 6
        temp2 = temp1 + x  # temp2 = 8
        z = temp2 * y  # z = 24

        backward(z)

        # z = (xy + x) * y = xy^2 + xy
        # dz/dx = y^2 + y = 9 + 3 = 12
        # dz/dy = 2xy + x = 12 + 2 = 14
        assert np.isclose(x.gradient, 12.0)
        assert np.isclose(y.gradient, 14.0)

    def test_chain_rule_relu(self):
        """Test chain rule with ReLU: y = ReLU(x * 2 - 3)."""
        x = Node(3.0, name="x")
        temp = x * 2.0 - 3.0  # temp = 3
        y = ReLU.forward(temp)  # ReLU(3) = 3

        backward(y)

        # y = ReLU(2x - 3)
        # For x = 3: 2*3 - 3 = 3 > 0, so dy/dx = 2
        assert np.isclose(x.gradient, 2.0)

    def test_chain_rule_relu_negative(self):
        """Test ReLU with negative input (gradient should be 0)."""
        x = Node(1.0, name="x")
        temp = x * 2.0 - 5.0  # temp = -3
        y = ReLU.forward(temp)  # ReLU(-3) = 0

        backward(y)

        # y = ReLU(2x - 5)
        # For x = 1: 2*1 - 5 = -3 < 0, so dy/dx = 0
        assert np.isclose(x.gradient, 0.0)


class TestGradientAccumulation:
    """Test gradient accumulation behavior."""

    def test_gradient_accumulation_single_use(self):
        """Test gradient accumulation when node is used once."""
        x = Node(2.0, name="x")
        y = x * 3.0  # y = 6

        backward(y)

        # dy/dx = 3
        assert np.isclose(x.gradient, 3.0)

    def test_gradient_accumulation_multiple_uses(self):
        """Test gradient accumulation when node is used multiple times."""
        x = Node(2.0, name="x")
        y1 = x * 3.0  # y1 = 6
        y2 = x * 4.0  # y2 = 8
        z = y1 + y2  # z = 14

        backward(z)

        # z = 3x + 4x = 7x
        # dz/dx = 7
        assert np.isclose(x.gradient, 7.0)

    def test_gradient_accumulation_shared_subgraph(self):
        """Test gradient with shared subgraph."""
        x = Node(2.0, name="x")
        shared = x * x  # shared = 4
        y = shared * 2.0  # y = 8
        z = shared * 3.0  # z = 12
        result = y + z  # result = 20

        backward(result)

        # result = 2*x^2 + 3*x^2 = 5*x^2
        # d(result)/dx = 10*x = 20
        assert np.isclose(x.gradient, 20.0)

    def test_set_grad_accumulation(self):
        """Test that set_grad properly accumulates."""
        x = Node(2.0, name="x")
        x.set_grad(1.0)
        x.set_grad(2.0)
        x.set_grad(3.0)

        assert np.isclose(x.gradient, 6.0)


class TestOperationsBackward:
    """Test backward pass for each operation type."""

    def test_add_backward(self):
        """Test Add operation backward pass."""
        a = Node(2.0, name="a")
        b = Node(3.0, name="b")
        c = Add.forward(a, b)

        backward(c)

        assert np.isclose(a.gradient, 1.0)
        assert np.isclose(b.gradient, 1.0)

    def test_multiply_backward(self):
        """Test Multiply operation backward pass."""
        a = Node(2.0, name="a")
        b = Node(3.0, name="b")
        c = Multiply.forward(a, b)

        backward(c)

        # dc/da = b = 3, dc/db = a = 2
        assert np.isclose(a.gradient, 3.0)
        assert np.isclose(b.gradient, 2.0)

    def test_relu_backward_positive(self):
        """Test ReLU backward with positive input."""
        x = Node(2.0, name="x")
        y = ReLU.forward(x)

        backward(y)

        assert np.isclose(x.gradient, 1.0)

    def test_relu_backward_negative(self):
        """Test ReLU backward with negative input."""
        x = Node(-2.0, name="x")
        y = ReLU.forward(x)

        backward(y)

        assert np.isclose(x.gradient, 0.0)

    def test_relu_backward_zero(self):
        """Test ReLU backward with zero input."""
        x = Node(0.0, name="x")
        y = ReLU.forward(x)

        backward(y)

        # ReLU'(0) = 0 (by our implementation)
        assert np.isclose(x.gradient, 0.0)

    def test_sum_backward_all_axes(self):
        """Test Sum backward with all axes."""
        x = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="x")
        s = Sum.forward(x)  # Sum all elements = 10

        backward(s)

        # Each element contributes 1 to the sum
        expected = np.ones((2, 2))
        assert np.allclose(x.gradient, expected)

    def test_sum_backward_axis(self):
        """Test Sum backward with specific axis."""
        x = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="x")
        s = Sum.forward(x, axis=0, keepdims=True)  # Sum over rows

        backward(s)

        # Gradient should be broadcast back
        expected = np.ones((2, 2))
        assert np.allclose(x.gradient, expected)

    def test_matmul_backward_2d(self):
        """Test MatMul backward with 2D matrices."""
        A = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="A")
        B = Node(np.array([[5.0, 6.0], [7.0, 8.0]]), name="B")
        C = MatMul.forward(A, B)

        backward(C)

        # Check shapes
        assert A.gradient.shape == A.value.shape
        assert B.gradient.shape == B.value.shape


class TestGraphUtilities:
    """Test graph utility functions."""

    def test_clear_gradients(self):
        """Test clear_gradients resets all gradients."""
        graph = Graph()
        x = Node(2.0, name="x")
        y = Node(3.0, name="y")
        z = x * y

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        backward(z)
        assert x.gradient is not None
        assert y.gradient is not None

        clear_gradients(graph)
        assert x.gradient is None
        assert y.gradient is None
        assert z.gradient is None

    def test_compute_gradients(self):
        """Test compute_gradients returns gradient dictionary."""
        graph = Graph()
        x = Node(2.0, name="x")
        y = Node(3.0, name="y")
        z = x * y + x

        graph.add_node(x)
        graph.add_node(y)
        graph.add_node(z)

        gradients = compute_gradients(graph, z)

        # z = xy + x
        # dz/dx = y + 1 = 4
        # dz/dy = x = 2
        assert np.isclose(gradients[x], 4.0)
        assert np.isclose(gradients[y], 2.0)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_backward_leaf_node(self):
        """Test backward on a leaf node (no operation)."""
        x = Node(2.0, name="x")

        backward(x)

        # Gradient of x w.r.t. itself is 1
        assert np.isclose(x.gradient, 1.0)

    def test_backward_single_node(self):
        """Test backward with single node computation."""
        x = Node(5.0, name="x")

        backward(x)

        assert np.isclose(x.gradient, 1.0)

    def test_backward_vector_with_sum(self):
        """Test backward through vector with sum."""
        x = Node(np.array([1.0, 2.0, 3.0]), name="x")
        y = x * x  # [1, 4, 9]
        s = Sum.forward(y)  # 14

        backward(s)

        # ds/dx = 2*x = [2, 4, 6]
        expected = np.array([2.0, 4.0, 6.0])
        assert np.allclose(x.gradient, expected)

    def test_backward_deep_graph(self):
        """Test backward through deep computation graph."""
        x = Node(1.0, name="x")

        # Build deep chain: (((((x + 1) * 2 + 1) * 2 + 1) * 2 + 1) * 2)
        y = x
        for _ in range(5):
            y = (y + 1) * 2

        backward(y)

        # Each iteration: y_new = (y + 1) * 2 = 2*y + 2
        # dy_new/dy = 2
        # After 5 iterations: dy/dx = 2^5 = 32
        assert np.isclose(x.gradient, 32.0)


class TestLiveVerification:
    """Tests that match the live verification examples from requirements."""

    def test_example_scalar_gradient(self):
        """Test the example: y = x^2 at x=3 should give 6."""
        from src.strong_system.computational_graph import backward

        x = Node(3.0, name="x")
        y = x * x  # Uses Multiply operation

        backward(y)

        assert x.gradient == 6.0  # dy/dx = 2*x = 6

    def test_example_matrix_multiplication(self):
        """Test matrix multiplication gradient."""
        A = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="A")
        B = Node(np.array([[5.0, 6.0], [7.0, 8.0]]), name="B")
        C = A @ B

        backward(C)

        # Verify gradients exist and have correct shapes
        assert A.gradient is not None
        assert B.gradient is not None
        assert A.gradient.shape == (2, 2)
        assert B.gradient.shape == (2, 2)


class TestImportExports:
    """Test that all exports work correctly."""

    def test_import_backward(self):
        """Test importing backward from module."""
        from src.strong_system.computational_graph import backward

        assert callable(backward)

    def test_import_compute_gradients(self):
        """Test importing compute_gradients from module."""
        from src.strong_system.computational_graph import compute_gradients

        assert callable(compute_gradients)

    def test_import_clear_gradients(self):
        """Test importing clear_gradients from module."""
        from src.strong_system.computational_graph import clear_gradients

        assert callable(clear_gradients)

    def test_all_exports_available(self):
        """Test all expected exports are available."""
        from src.strong_system.computational_graph import __all__

        expected = [
            "Graph",
            "Node",
            "Operation",
            "Add",
            "Multiply",
            "ReLU",
            "MatMul",
            "Sum",
            "backward",
            "compute_gradients",
            "clear_gradients",
        ]

        for export in expected:
            assert export in __all__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
