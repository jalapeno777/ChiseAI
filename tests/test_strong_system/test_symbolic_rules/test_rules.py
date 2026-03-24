"""Tests for core symbolic rules functionality."""

from src.strong_system.symbolic_rules import (
    RuleEngine,
    RuleSet,
    SymbolicRule,
)
from src.strong_system.symbolic_rules.differentiable import (
    DifferentiableAction,
    DifferentiablePredicate,
    soft_predicate,
)
from src.strong_system.symbolic_rules.types import Rule, RuleEvaluation


class TestSymbolicRule:
    """Test suite for SymbolicRule class."""

    def test_basic_rule_creation(self):
        """Test creating a basic symbolic rule."""

        def simple_pred(inputs, steepness=1.0):
            return soft_predicate(inputs["x"], 0.5, steepness)

        rule = SymbolicRule(
            name="test_rule",
            predicate=simple_pred,
            confidence=0.8,
        )

        assert rule.name == "test_rule"
        assert rule.confidence == 0.8
        assert rule.action is None

    def test_rule_with_action(self):
        """Test creating a rule with an action."""

        def pred(inputs, steepness=1.0):
            return soft_predicate(inputs["x"], 0.5, steepness)

        def action_fn(inputs, confidence):
            return f"action_with_confidence_{confidence}"

        rule = SymbolicRule(
            name="rule_with_action",
            predicate=pred,
            action=action_fn,
            confidence=1.0,
        )

        assert rule.action is not None
        result = rule.action.execute({"x": 1.0}, 0.9)
        assert "0.9" in result

    def test_rule_evaluation(self):
        """Test rule evaluation."""

        def pred(inputs, steepness=1.0):
            return soft_predicate(inputs["price"], inputs["threshold"], steepness)

        rule = SymbolicRule(
            name="price_check",
            predicate=pred,
            confidence=0.9,
        )

        # Test with value above threshold
        result = rule.evaluate({"price": 110.0, "threshold": 100.0})
        assert isinstance(result, RuleEvaluation)
        assert result.activated > 0.5  # Should activate
        assert result.confidence == 0.9
        assert result.rule_name == "price_check"

    def test_rule_evaluation_below_threshold(self):
        """Test rule evaluation when condition is not met."""

        def pred(inputs, steepness=1.0):
            return soft_predicate(inputs["price"], inputs["threshold"], steepness)

        rule = SymbolicRule(
            name="price_check",
            predicate=pred,
            confidence=0.9,
        )

        # Test with value below threshold
        result = rule.evaluate({"price": 90.0, "threshold": 100.0})
        assert result.activated < 0.5  # Should not activate

    def test_confidence_clipping(self):
        """Test that confidence is clipped to [0, 1]."""

        def pred(inputs, steepness=1.0):
            return 1.0

        rule_high = SymbolicRule(name="test", predicate=pred, confidence=1.5)
        assert rule_high.confidence == 1.0

        rule_low = SymbolicRule(name="test", predicate=pred, confidence=-0.5)
        assert rule_low.confidence == 0.0

    def test_confidence_node_creation(self):
        """Test that confidence node is created lazily."""

        def pred(inputs, steepness=1.0):
            return 1.0

        rule = SymbolicRule(name="test", predicate=pred, confidence=0.7)
        assert rule._confidence_node is None

        node = rule.confidence_node
        assert node is not None
        assert node.value == 0.7

    def test_rule_with_differentiable_predicate(self):
        """Test rule with explicit DifferentiablePredicate."""
        pred = DifferentiablePredicate(
            "test_pred",
            lambda inputs, s: soft_predicate(inputs["x"], 0.5, s),
        )

        rule = SymbolicRule(name="test", predicate=pred)
        result = rule.evaluate({"x": 0.7})
        assert result.activated > 0

    def test_rule_with_differentiable_action(self):
        """Test rule with explicit DifferentiableAction."""

        def pred(inputs, steepness=1.0):
            return 1.0

        action = DifferentiableAction(
            "test_action",
            lambda inputs, conf: {"result": conf * 100},
        )

        rule = SymbolicRule(name="test", predicate=pred, action=action)
        result = rule.action.execute({}, 0.5)
        assert result["result"] == 50.0

    def test_rule_to_rule_conversion(self):
        """Test conversion to Rule dataclass."""

        def pred(inputs, steepness=1.0):
            return 1.0

        rule = SymbolicRule(
            name="test",
            predicate=pred,
            description="Test rule",
            metadata={"key": "value"},
        )

        rule_dataclass = rule.to_rule()
        assert isinstance(rule_dataclass, Rule)
        assert rule_dataclass.name == "test"
        assert rule_dataclass.description == "Test rule"

    def test_rule_repr(self):
        """Test rule string representation."""
        rule = SymbolicRule(name="my_rule", predicate=lambda i, s: 1.0)
        repr_str = repr(rule)
        assert "my_rule" in repr_str
        assert "SymbolicRule" in repr_str


class TestCompositeRule:
    """Test suite for CompositeRule class."""

    def test_and_composition(self):
        """Test AND composition of rules."""
        rule1 = SymbolicRule(
            name="rule1",
            predicate=lambda i, s: soft_predicate(i.get("x", 0), 0.5, s),
            confidence=1.0,
        )
        rule2 = SymbolicRule(
            name="rule2",
            predicate=lambda i, s: soft_predicate(i.get("x", 0), 0.3, s),
            confidence=1.0,
        )

        composite = rule1.compose_and(rule2, name="and_rule")
        assert composite.name == "and_rule"
        assert composite.composition == "AND"

        # Both conditions met (value well above both thresholds)
        result = composite.evaluate({"x": 1.5})
        assert result.activated > 0.5

        # One condition not met (value below one threshold)
        result = composite.evaluate({"x": 0.2})
        assert result.activated < 0.5

    def test_or_composition(self):
        """Test OR composition of rules."""
        rule1 = SymbolicRule(
            name="rule1",
            predicate=lambda i, s: soft_predicate(i.get("x", 0), 0.5, s),
            confidence=1.0,
        )
        rule2 = SymbolicRule(
            name="rule2",
            predicate=lambda i, s: soft_predicate(i.get("x", 0), 0.5, s, "less"),
            confidence=1.0,
        )

        composite = rule1.compose_or(rule2, name="or_rule")
        assert composite.composition == "OR"

        # One condition met (x > 0.5)
        result = composite.evaluate({"x": 0.8})
        assert result.activated > 0.5

        # Other condition met (x < 0.5)
        result = composite.evaluate({"x": 0.2})
        assert result.activated > 0.5

    def test_not_composition(self):
        """Test NOT composition."""
        rule = SymbolicRule(
            name="base_rule",
            predicate=lambda i, s: soft_predicate(i["x"], 0.5, s),
            confidence=1.0,
        )

        negated = rule.compose_not(name="not_rule")
        assert negated.composition == "NOT"

        # When base rule activates, negated should not
        result_base = rule.evaluate({"x": 0.8})
        result_neg = negated.evaluate({"x": 0.8})
        assert result_base.activated > 0.5
        assert result_neg.activated < 0.5

    def test_composite_rule_repr(self):
        """Test composite rule string representation."""
        rule1 = SymbolicRule(name="r1", predicate=lambda i, s: 1.0)
        rule2 = SymbolicRule(name="r2", predicate=lambda i, s: 1.0)
        composite = rule1.compose_and(rule2)

        repr_str = repr(composite)
        assert "CompositeRule" in repr_str
        assert "AND" in repr_str


class TestRuleEngine:
    """Test suite for RuleEngine class."""

    def test_engine_creation(self):
        """Test creating a rule engine."""
        engine = RuleEngine()
        assert len(engine) == 0
        assert engine.list_rules() == []

    def test_add_rule(self):
        """Test adding rules to engine."""
        engine = RuleEngine()
        rule = SymbolicRule(name="test", predicate=lambda i, s: 1.0)

        engine.add_rule(rule)
        assert len(engine) == 1
        assert "test" in engine.list_rules()

    def test_remove_rule(self):
        """Test removing rules from engine."""
        engine = RuleEngine()
        rule = SymbolicRule(name="test", predicate=lambda i, s: 1.0)

        engine.add_rule(rule)
        assert engine.remove_rule("test") is True
        assert len(engine) == 0
        assert engine.remove_rule("nonexistent") is False

    def test_get_rule(self):
        """Test retrieving rules by name."""
        engine = RuleEngine()
        rule = SymbolicRule(name="test", predicate=lambda i, s: 1.0)

        engine.add_rule(rule)
        retrieved = engine.get_rule("test")
        assert retrieved is not None
        assert retrieved.name == "test"

        assert engine.get_rule("nonexistent") is None

    def test_evaluate_rule(self):
        """Test evaluating a single rule."""
        engine = RuleEngine()
        rule = SymbolicRule(
            name="price_check",
            predicate=lambda i, s: soft_predicate(i["price"], 100.0, s),
        )

        engine.add_rule(rule)
        result = engine.evaluate_rule("price_check", {"price": 110.0})
        assert result is not None
        assert result.activated > 0.5

    def test_evaluate_all(self):
        """Test evaluating all rules."""
        engine = RuleEngine()
        engine.add_rule(
            SymbolicRule(
                name="rule1",
                predicate=lambda i, s: soft_predicate(i["x"], 0.5, s),
            )
        )
        engine.add_rule(
            SymbolicRule(
                name="rule2",
                predicate=lambda i, s: soft_predicate(i["y"], 0.5, s),
            )
        )

        results = engine.evaluate_all({"x": 0.8, "y": 0.3})
        assert len(results) == 2
        assert "rule1" in results
        assert "rule2" in results
        assert results["rule1"].activated > 0.5
        assert results["rule2"].activated < 0.5

    def test_get_activated_rules(self):
        """Test getting activated rules above threshold."""
        engine = RuleEngine()
        engine.add_rule(
            SymbolicRule(
                name="high_confidence",
                predicate=lambda i, s: 0.9,
                confidence=1.0,
            )
        )
        engine.add_rule(
            SymbolicRule(
                name="low_confidence",
                predicate=lambda i, s: 0.3,
                confidence=1.0,
            )
        )

        activated = engine.get_activated_rules({}, threshold=0.5)
        assert len(activated) == 1
        assert activated[0][0] == "high_confidence"

    def test_add_rule_set(self):
        """Test adding a rule set."""
        engine = RuleEngine()
        rule_set = RuleSet(
            name="my_set",
            rules=[
                Rule(name="r1", predicate=lambda i: 1.0),
                Rule(name="r2", predicate=lambda i: 1.0),
            ],
        )

        engine.add_rule_set(rule_set)
        assert "my_set" in engine.list_rule_sets()
        assert "r1" in engine.list_rules()
        assert "r2" in engine.list_rules()

    def test_engine_repr(self):
        """Test engine string representation."""
        engine = RuleEngine()
        engine.add_rule(SymbolicRule(name="r1", predicate=lambda i, s: 1.0))

        repr_str = repr(engine)
        assert "RuleEngine" in repr_str
        assert "rules=1" in repr_str


class TestRuleSet:
    """Test suite for RuleSet class."""

    def test_rule_set_creation(self):
        """Test creating a rule set."""
        rule_set = RuleSet(name="test_set")
        assert rule_set.name == "test_set"
        assert len(rule_set.rules) == 0

    def test_add_rule(self):
        """Test adding rules to a set."""
        rule_set = RuleSet(name="test_set")
        rule = Rule(name="r1", predicate=lambda i: 1.0)

        rule_set.add_rule(rule)
        assert len(rule_set.rules) == 1

    def test_remove_rule(self):
        """Test removing rules from a set."""
        rule_set = RuleSet(name="test_set")
        rule_set.add_rule(Rule(name="r1", predicate=lambda i: 1.0))
        rule_set.add_rule(Rule(name="r2", predicate=lambda i: 1.0))

        assert rule_set.remove_rule("r1") is True
        assert len(rule_set.rules) == 1
        assert rule_set.remove_rule("nonexistent") is False

    def test_get_rule(self):
        """Test getting rules by name."""
        rule_set = RuleSet(name="test_set")
        rule_set.add_rule(Rule(name="r1", predicate=lambda i: 1.0))

        rule = rule_set.get_rule("r1")
        assert rule is not None
        assert rule.name == "r1"
        assert rule_set.get_rule("nonexistent") is None
