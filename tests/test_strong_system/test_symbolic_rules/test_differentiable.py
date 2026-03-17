"""Tests for differentiable operations in symbolic rules."""

import numpy as np
import pytest

from src.strong_system.symbolic_rules.differentiable import (
    DifferentiableAction,
    DifferentiablePredicate,
    fuzzy_and,
    fuzzy_not,
    fuzzy_or,
    rule_loss,
    rule_loss_gradient,
    sigmoid,
    soft_predicate,
)


class TestSigmoid:
    """Test suite for sigmoid function."""

    def test_sigmoid_zero(self):
        """Test sigmoid at zero."""
        result = sigmoid(0.0)
        assert np.isclose(result, 0.5, atol=1e-6)

    def test_sigmoid_positive(self):
        """Test sigmoid with positive input."""
        result = sigmoid(2.0)
        assert result > 0.5
        assert result < 1.0

    def test_sigmoid_negative(self):
        """Test sigmoid with negative input."""
        result = sigmoid(-2.0)
        assert result < 0.5
        assert result > 0.0

    def test_sigmoid_steepness(self):
        """Test sigmoid with different steepness values."""
        # Higher steepness should give more extreme values
        result_steep = sigmoid(1.0, steepness=5.0)
        result_shallow = sigmoid(1.0, steepness=0.5)
        assert result_steep > result_shallow

    def test_sigmoid_array(self):
        """Test sigmoid with array input."""
        arr = np.array([-1.0, 0.0, 1.0])
        result = sigmoid(arr)
        assert len(result) == 3
        assert np.all(result >= 0) and np.all(result <= 1)

    def test_sigmoid_extreme_values(self):
        """Test sigmoid with extreme values."""
        # Should not overflow
        result_large = sigmoid(1000.0)
        assert result_large <= 1.0

        result_small = sigmoid(-1000.0)
        assert result_small >= 0.0


class TestSoftPredicate:
    """Test suite for soft_predicate function."""

    def test_greater_mode(self):
        """Test soft_predicate in greater mode."""
        # Value well above threshold
        result = soft_predicate(10.0, 5.0, mode="greater")
        assert result > 0.5

        # Value well below threshold
        result = soft_predicate(0.0, 5.0, mode="greater")
        assert result < 0.5

    def test_less_mode(self):
        """Test soft_predicate in less mode."""
        # Value well below threshold
        result = soft_predicate(0.0, 5.0, mode="less")
        assert result > 0.5

        # Value well above threshold
        result = soft_predicate(10.0, 5.0, mode="less")
        assert result < 0.5

    def test_equal_mode(self):
        """Test soft_predicate in equal mode."""
        # Value exactly at threshold
        result = soft_predicate(5.0, 5.0, steepness=1.0, mode="equal")
        assert np.isclose(result, 1.0, atol=1e-6)

        # Value far from threshold
        result = soft_predicate(10.0, 5.0, steepness=1.0, mode="equal")
        assert result < 0.5

    def test_not_equal_mode(self):
        """Test soft_predicate in not_equal mode."""
        # Value exactly at threshold
        result = soft_predicate(5.0, 5.0, mode="not_equal")
        assert np.isclose(result, 0.0, atol=1e-6)

        # Value far from threshold
        result = soft_predicate(10.0, 5.0, mode="not_equal")
        assert result > 0.5

    def test_steepness_parameter(self):
        """Test effect of steepness parameter."""
        value = 6.0
        threshold = 5.0

        steep = soft_predicate(value, threshold, steepness=5.0, mode="greater")
        shallow = soft_predicate(value, threshold, steepness=0.5, mode="greater")

        # Steeper should give more confident result
        assert steep > shallow

    def test_invalid_mode(self):
        """Test that invalid mode raises error."""
        with pytest.raises(ValueError, match="Unknown mode"):
            soft_predicate(5.0, 5.0, mode="invalid")


class TestFuzzyAnd:
    """Test suite for fuzzy_and function."""

    def test_product_method(self):
        """Test AND with product method."""
        result = fuzzy_and([0.5, 0.5], method="product")
        assert np.isclose(result, 0.25)

    def test_min_method(self):
        """Test AND with min method."""
        result = fuzzy_and([0.3, 0.8], method="min")
        assert result == 0.3

    def test_mean_method(self):
        """Test AND with mean method."""
        result = fuzzy_and([0.3, 0.7], method="mean")
        assert np.isclose(result, 0.5)

    def test_empty_list(self):
        """Test AND with empty list."""
        result = fuzzy_and([], method="product")
        assert result == 1.0  # Empty conjunction is true

    def test_single_element(self):
        """Test AND with single element."""
        result = fuzzy_and([0.7], method="product")
        assert result == 0.7

    def test_multiple_elements(self):
        """Test AND with multiple elements."""
        result = fuzzy_and([0.9, 0.9, 0.9], method="product")
        assert result < 0.9  # Should decrease with more elements
        assert result > 0


class TestFuzzyOr:
    """Test suite for fuzzy_or function."""

    def test_probabilistic_method(self):
        """Test OR with probabilistic method."""
        result = fuzzy_or([0.5, 0.5], method="probabilistic")
        # P(A or B) = 0.5 + 0.5 - 0.5*0.5 = 0.75
        assert np.isclose(result, 0.75)

    def test_max_method(self):
        """Test OR with max method."""
        result = fuzzy_or([0.3, 0.8], method="max")
        assert result == 0.8

    def test_mean_method(self):
        """Test OR with mean method."""
        result = fuzzy_or([0.3, 0.7], method="mean")
        assert np.isclose(result, 0.5)

    def test_empty_list(self):
        """Test OR with empty list."""
        result = fuzzy_or([], method="probabilistic")
        assert result == 0.0  # Empty disjunction is false

    def test_single_element(self):
        """Test OR with single element."""
        result = fuzzy_or([0.7], method="probabilistic")
        assert result == 0.7

    def test_multiple_elements(self):
        """Test OR with multiple elements."""
        result = fuzzy_or([0.5, 0.5, 0.5], method="probabilistic")
        assert result > 0.5  # Should increase with more elements
        assert result <= 1.0


class TestFuzzyNot:
    """Test suite for fuzzy_not function."""

    def test_basic_negation(self):
        """Test basic fuzzy negation."""
        assert np.isclose(fuzzy_not(0.8), 0.2)
        assert np.isclose(fuzzy_not(0.2), 0.8)

    def test_boundary_values(self):
        """Test negation at boundaries."""
        assert fuzzy_not(0.0) == 1.0
        assert fuzzy_not(1.0) == 0.0

    def test_middle_value(self):
        """Test negation at 0.5."""
        assert fuzzy_not(0.5) == 0.5


class TestRuleLoss:
    """Test suite for rule_loss function."""

    def test_mse_loss(self):
        """Test MSE loss."""
        result = rule_loss(0.8, 1.0, loss_type="mse")
        assert np.isclose(result, 0.04)  # (0.8 - 1.0)^2

    def test_l1_loss(self):
        """Test L1 loss."""
        result = rule_loss(0.8, 1.0, loss_type="l1")
        assert np.isclose(result, 0.2)  # |0.8 - 1.0|

    def test_bce_loss(self):
        """Test binary cross-entropy loss."""
        result = rule_loss(0.8, 1.0, loss_type="bce")
        # -log(0.8) ≈ 0.223
        assert result > 0

    def test_bce_with_zero_prediction(self):
        """Test BCE handles zero predictions safely."""
        result = rule_loss(0.0, 1.0, loss_type="bce")
        # Should be clipped to avoid log(0)
        assert result > 0

    def test_perfect_prediction(self):
        """Test loss with perfect prediction."""
        mse = rule_loss(1.0, 1.0, loss_type="mse")
        assert mse == 0.0

        l1 = rule_loss(1.0, 1.0, loss_type="l1")
        assert l1 == 0.0

    def test_invalid_loss_type(self):
        """Test that invalid loss type raises error."""
        with pytest.raises(ValueError, match="Unknown loss type"):
            rule_loss(0.5, 1.0, loss_type="invalid")


class TestRuleLossGradient:
    """Test suite for rule_loss_gradient function."""

    def test_mse_gradient(self):
        """Test MSE gradient."""
        grad = rule_loss_gradient(0.8, 1.0, loss_type="mse")
        # 2 * (0.8 - 1.0) = -0.4
        assert np.isclose(grad, -0.4)

    def test_l1_gradient(self):
        """Test L1 gradient."""
        grad = rule_loss_gradient(0.8, 1.0, loss_type="l1")
        # sign(0.8 - 1.0) = -1
        assert grad == -1.0

    def test_bce_gradient(self):
        """Test BCE gradient."""
        grad = rule_loss_gradient(0.8, 1.0, loss_type="bce")
        # -1/0.8 = -1.25
        assert grad < 0

    def test_gradient_direction(self):
        """Test that gradient points in correct direction."""
        # When prediction < target, gradient should be negative
        # (we need to increase prediction)
        grad = rule_loss_gradient(0.3, 1.0, loss_type="mse")
        assert grad < 0

        # When prediction > target, gradient should be positive
        grad = rule_loss_gradient(0.8, 0.0, loss_type="mse")
        assert grad > 0


class TestDifferentiablePredicate:
    """Test suite for DifferentiablePredicate class."""

    def test_predicate_creation(self):
        """Test creating a differentiable predicate."""
        pred = DifferentiablePredicate(
            "test_pred",
            lambda inputs, s: soft_predicate(inputs["x"], 0.5, s),
        )
        assert pred.name == "test_pred"

    def test_predicate_evaluation(self):
        """Test predicate evaluation."""
        pred = DifferentiablePredicate(
            "test_pred",
            lambda inputs, s: soft_predicate(inputs["x"], 0.5, s),
        )
        result = pred.evaluate({"x": 0.8})
        assert result > 0.5

    def test_predicate_call(self):
        """Test predicate can be called directly."""
        pred = DifferentiablePredicate(
            "test_pred",
            lambda inputs, s: inputs["x"] > 0.5,
        )
        result = pred({"x": 0.8})
        assert result is True

    def test_steepness_parameter(self):
        """Test steepness parameter is passed."""
        received_steepness = [None]

        def capture_steepness(inputs, s):
            received_steepness[0] = s
            return 1.0

        pred = DifferentiablePredicate("test", capture_steepness, steepness=2.5)
        pred.evaluate({})
        assert received_steepness[0] == 2.5


class TestDifferentiableAction:
    """Test suite for DifferentiableAction class."""

    def test_action_creation(self):
        """Test creating a differentiable action."""
        action = DifferentiableAction(
            "test_action",
            lambda inputs, conf: {"confidence": conf},
        )
        assert action.name == "test_action"

    def test_action_execution(self):
        """Test action execution."""
        action = DifferentiableAction(
            "test_action",
            lambda inputs, conf: inputs["value"] * conf,
        )
        result = action.execute({"value": 10.0}, 0.5)
        assert result == 5.0

    def test_action_call(self):
        """Test action can be called directly."""
        action = DifferentiableAction(
            "test_action",
            lambda inputs, conf: conf,
        )
        result = action({}, 0.7)
        assert result == 0.7

    def test_default_confidence(self):
        """Test default confidence value."""
        action = DifferentiableAction(
            "test_action",
            lambda inputs, conf: conf,
        )
        result = action({})
        assert result == 1.0
