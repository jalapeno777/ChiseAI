"""Integration tests for symbolic rules with computational graph."""

import numpy as np
from src.strong_system.computational_graph import Node, backward
from src.strong_system.symbolic_rules import (
    RuleEngine,
    SymbolicRule,
    fuzzy_and,
    fuzzy_or,
    rule_loss,
    soft_predicate,
)


class TestSymbolicRuleIntegration:
    """Integration tests for symbolic rules."""

    def test_rule_with_computational_graph(self):
        """Test that rules integrate with computational graph."""
        rule = SymbolicRule(
            name="price_rule",
            predicate=lambda i, s: soft_predicate(i["price"], 100.0, s, "greater"),
            confidence=0.9,
        )

        # Evaluate rule
        result = rule.evaluate({"price": 110.0})
        assert result.activated > 0.5

        # Get differentiable evaluation
        inputs = {"price": Node(110.0, name="price")}
        diff_result = rule.evaluate_differentiable(inputs)
        assert isinstance(diff_result.activated, Node)

    def test_rule_gradient_flow(self):
        """Test that gradients flow through rule evaluation."""
        rule = SymbolicRule(
            name="grad_rule",
            predicate=lambda i, s: 1.0,  # Always true
            confidence=0.5,
        )

        # Get differentiable evaluation
        inputs = {"x": Node(1.0, name="x")}
        result = rule.evaluate_differentiable(inputs)

        # Run backward pass
        activated_node = result.activated
        backward(activated_node)

        # Confidence node should have gradient
        assert result.confidence.gradient is not None

    def test_multiple_rules_shared_graph(self):
        """Test multiple rules in same computational graph."""
        engine = RuleEngine()

        # Add multiple rules
        engine.add_rule(
            SymbolicRule(
                name="rule1",
                predicate=lambda i, s: soft_predicate(i["x"], 0.5, s),
                confidence=0.8,
            )
        )
        engine.add_rule(
            SymbolicRule(
                name="rule2",
                predicate=lambda i, s: soft_predicate(i.get("y", 0.5), 0.5, s),
                confidence=0.7,
            )
        )

        # Compile all rules
        compiled = engine.compile_all()
        assert len(compiled) == 2
        assert "rule1" in compiled
        assert "rule2" in compiled

    def test_composite_rule_with_graph(self):
        """Test composite rules with computational graph."""
        rule1 = SymbolicRule(
            name="r1",
            predicate=lambda i, s: 1.0,
            confidence=0.9,
        )
        rule2 = SymbolicRule(
            name="r2",
            predicate=lambda i, s: 1.0,
            confidence=0.8,
        )

        # Create AND composition
        composite = rule1.compose_and(rule2, name="and_comp")

        # Compile to graph
        from src.strong_system.symbolic_rules import RuleCompiler

        compiler = RuleCompiler()
        node = compiler.compile_rule(composite)

        assert isinstance(node, Node)
        # Both rules true with high confidence, AND should be high
        assert node.value > 0.5


class TestRuleEngineIntegration:
    """Integration tests for RuleEngine."""

    def test_engine_evaluate_all_with_graph(self):
        """Test engine evaluate_all with graph integration."""
        engine = RuleEngine()

        # Add rules
        for i in range(3):
            threshold = 0.3 + i * 0.2
            engine.add_rule(
                SymbolicRule(
                    name=f"rule_{i}",
                    predicate=lambda inputs, s, t=threshold: soft_predicate(
                        inputs.get("x", 0), t, s
                    ),
                    confidence=0.8,
                )
            )

        # Evaluate with value that should activate at least one rule
        results = engine.evaluate_all({"x": 1.0})
        assert len(results) == 3

        # Some should activate, some not depending on thresholds
        activations = [r.activated for r in results.values()]
        assert any(a > 0.5 for a in activations)

    def test_get_activated_rules_integration(self):
        """Test getting activated rules with real data."""
        engine = RuleEngine()

        # Add rules with different conditions
        engine.add_rule(
            SymbolicRule(
                name="high_price",
                predicate=lambda i, s: soft_predicate(
                    i.get("price", 0), 100.0, s, "greater"
                ),
                confidence=0.9,
            )
        )
        engine.add_rule(
            SymbolicRule(
                name="high_volume",
                predicate=lambda i, s: soft_predicate(
                    i.get("volume", 0), 1000.0, s, "greater"
                ),
                confidence=0.8,
            )
        )
        engine.add_rule(
            SymbolicRule(
                name="low_price",
                predicate=lambda i, s: soft_predicate(
                    i.get("price", 0), 50.0, s, "less"
                ),
                confidence=0.7,
            )
        )

        # Test with data that activates some rules
        inputs = {"price": 110.0, "volume": 500.0}
        activated = engine.get_activated_rules(inputs, threshold=0.5)

        # high_price should activate, high_volume should not
        rule_names = [name for name, _ in activated]
        assert "high_price" in rule_names
        assert "high_volume" not in rule_names

    def test_compile_all_rules(self):
        """Test compiling all rules to graph."""
        engine = RuleEngine()

        for i in range(3):
            engine.add_rule(
                SymbolicRule(
                    name=f"rule_{i}",
                    predicate=lambda i, s: 0.5,
                    confidence=0.8,
                )
            )

        compiled = engine.compile_all()

        # All rules should be compiled
        assert len(compiled) == 3
        for i in range(3):
            assert f"rule_{i}" in compiled
            assert isinstance(compiled[f"rule_{i}"], Node)


class TestFuzzyLogicIntegration:
    """Integration tests for fuzzy logic operations."""

    def test_fuzzy_and_with_real_values(self):
        """Test fuzzy AND with realistic values."""
        # Simulate two rule activations
        activation1 = 0.8
        activation2 = 0.6

        result = fuzzy_and([activation1, activation2], method="product")
        # 0.8 * 0.6 = 0.48
        assert np.isclose(result, 0.48)

        result_min = fuzzy_and([activation1, activation2], method="min")
        assert result_min == 0.6

    def test_fuzzy_or_with_real_values(self):
        """Test fuzzy OR with realistic values."""
        activation1 = 0.8
        activation2 = 0.6

        result = fuzzy_or([activation1, activation2], method="probabilistic")
        # 0.8 + 0.6 - 0.8*0.6 = 0.92
        expected = 0.8 + 0.6 - 0.8 * 0.6
        assert np.isclose(result, expected)

    def test_composite_rule_fuzzy_logic(self):
        """Test composite rules use fuzzy logic correctly."""
        rule1 = SymbolicRule(
            name="r1",
            predicate=lambda i, s: 0.8,  # 80% activation
            confidence=1.0,
        )
        rule2 = SymbolicRule(
            name="r2",
            predicate=lambda i, s: 0.6,  # 60% activation
            confidence=1.0,
        )

        # AND should give lower activation than either individually
        and_result = rule1.compose_and(rule2, name="and_test").evaluate({})
        assert and_result.activated <= 0.8
        assert and_result.activated <= 0.6

        # OR should give higher activation than either individually
        or_result = rule1.compose_or(rule2, name="or_test").evaluate({})
        assert or_result.activated >= 0.8


class TestRuleLossIntegration:
    """Integration tests for rule loss functions."""

    def test_loss_with_perfect_prediction(self):
        """Test loss when prediction matches target."""
        # Perfect prediction should give zero loss
        loss = rule_loss(1.0, 1.0, loss_type="mse")
        assert loss == 0.0

        loss = rule_loss(0.0, 0.0, loss_type="mse")
        assert loss == 0.0

    def test_loss_with_imperfect_prediction(self):
        """Test loss when prediction differs from target."""
        # MSE loss
        mse = rule_loss(0.7, 1.0, loss_type="mse")
        assert mse > 0

        # L1 loss
        l1 = rule_loss(0.7, 1.0, loss_type="l1")
        assert l1 > 0

        # BCE loss
        bce = rule_loss(0.7, 1.0, loss_type="bce")
        assert bce > 0

    def test_loss_types_differ(self):
        """Test that different loss types give different values."""
        pred = 0.7
        target = 1.0

        mse = rule_loss(pred, target, loss_type="mse")
        l1 = rule_loss(pred, target, loss_type="l1")
        bce = rule_loss(pred, target, loss_type="bce")

        # All should be different
        assert mse != l1
        assert mse != bce
        assert l1 != bce


class TestEndToEndScenario:
    """End-to-end integration scenarios."""

    def test_trading_signal_rules(self):
        """Test a realistic trading signal scenario."""
        engine = RuleEngine()

        # Define trading rules
        engine.add_rule(
            SymbolicRule(
                name="price_above_ma",
                predicate=lambda i, s: soft_predicate(
                    i.get("price", 0), i.get("ma20", 0), s, "greater"
                ),
                confidence=0.85,
                description="Price above 20-period moving average",
            )
        )

        engine.add_rule(
            SymbolicRule(
                name="rsi_not_overbought",
                predicate=lambda i, s: soft_predicate(
                    i.get("rsi", 50), 70.0, s, "less"
                ),
                confidence=0.75,
                description="RSI not in overbought territory",
            )
        )

        engine.add_rule(
            SymbolicRule(
                name="volume_above_average",
                predicate=lambda i, s: soft_predicate(
                    i.get("volume", 0), i.get("avg_volume", 0), s, "greater"
                ),
                confidence=0.80,
                description="Volume above average",
            )
        )

        # Test with bullish data
        bullish_data = {
            "price": 110.0,
            "ma20": 100.0,
            "rsi": 55.0,
            "volume": 1500.0,
            "avg_volume": 1000.0,
        }

        results = engine.evaluate_all(bullish_data)

        # All rules should activate for bullish data
        for name, result in results.items():
            assert result.activated > 0.5, f"Rule {name} should activate"

        # Test with bearish data
        bearish_data = {
            "price": 90.0,
            "ma20": 100.0,
            "rsi": 75.0,
            "volume": 500.0,
            "avg_volume": 1000.0,
        }

        activated = engine.get_activated_rules(bearish_data, threshold=0.5)
        # Should have fewer or no activated rules
        assert len(activated) < len(results)

    def test_composite_trading_signal(self):
        """Test composite rule for complex trading signal."""
        engine = RuleEngine()

        # Individual rules
        trend_rule = SymbolicRule(
            name="uptrend",
            predicate=lambda i, s: soft_predicate(
                i.get("price", 0), i.get("ma50", 0), s, "greater"
            ),
            confidence=0.8,
        )

        momentum_rule = SymbolicRule(
            name="momentum",
            predicate=lambda i, s: soft_predicate(i.get("rsi", 50), 50.0, s, "greater"),
            confidence=0.7,
        )

        volume_rule = SymbolicRule(
            name="volume",
            predicate=lambda i, s: soft_predicate(
                i.get("volume", 0), i.get("avg_volume", 0), s, "greater"
            ),
            confidence=0.75,
        )

        # Create composite: (uptrend AND momentum) OR volume_spike
        trend_and_momentum = trend_rule.compose_and(
            momentum_rule, name="trend_and_momentum"
        )
        full_signal = trend_and_momentum.compose_or(volume_rule, name="full_signal")

        engine.add_rule(full_signal)

        # Test with strong trend and momentum
        data1 = {
            "price": 110.0,
            "ma50": 100.0,
            "rsi": 65.0,
            "volume": 800.0,
            "avg_volume": 1000.0,
        }

        result1 = engine.evaluate_rule("full_signal", data1)
        assert result1.activated > 0.5

        # Test with just volume spike
        data2 = {
            "price": 95.0,
            "ma50": 100.0,
            "rsi": 45.0,
            "volume": 2000.0,
            "avg_volume": 1000.0,
        }

        result2 = engine.evaluate_rule("full_signal", data2)
        assert result2.activated > 0.5

    def test_rule_learning_simulation(self):
        """Simulate learning rule confidence through gradient descent."""
        rule = SymbolicRule(
            name="learnable_rule",
            predicate=lambda i, s: 1.0,  # Always fires
            confidence=0.5,  # Start with medium confidence
        )

        # Simulate training: we want rule to activate when target is 1.0
        learning_rate = 0.1
        num_iterations = 10

        initial_confidence = rule.confidence

        for _ in range(num_iterations):
            # Forward pass
            result = rule.evaluate({})
            activated = result.activated

            # Compute loss (target is 1.0)
            loss = rule_loss(activated, 1.0, loss_type="mse")

            # Simple gradient update simulation
            # d_loss/d_confidence = 2 * (activated - target) * predicate
            grad = 2 * (activated - 1.0) * 1.0

            # Update confidence (gradient descent)
            new_confidence = rule.confidence - learning_rate * grad
            rule.confidence = min(1.0, max(0.0, new_confidence))

        # Confidence should have increased toward 1.0
        assert rule.confidence >= initial_confidence
