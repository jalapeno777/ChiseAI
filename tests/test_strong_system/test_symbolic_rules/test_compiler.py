"""Tests for rule compiler functionality."""

import numpy as np
import pytest

from src.strong_system.computational_graph import Node, backward
from src.strong_system.symbolic_rules import RuleCompiler, SymbolicRule
from src.strong_system.symbolic_rules.differentiable import soft_predicate
from src.strong_system.symbolic_rules.types import Rule


class TestRuleCompiler:
    """Test suite for RuleCompiler class."""

    def test_compiler_creation(self):
        """Test creating a rule compiler."""
        compiler = RuleCompiler()
        assert len(compiler.list_compiled_rules()) == 0

    def test_compile_simple_rule(self):
        """Test compiling a simple rule."""
        compiler = RuleCompiler()
        rule = SymbolicRule(
            name="test_rule",
            predicate=lambda i, s: soft_predicate(i["x"], 0.5, s),
            confidence=0.8,
        )

        node = compiler.compile_rule(rule)
        assert isinstance(node, Node)
        assert node.name == "test_rule_activation"

    def test_compile_with_input_nodes(self):
        """Test compiling with provided input nodes."""
        compiler = RuleCompiler()
        rule = SymbolicRule(
            name="test_rule",
            predicate=lambda i, s: soft_predicate(i["x"], 0.5, s),
        )

        input_nodes = {"x": Node(0.8, name="input_x")}
        node = compiler.compile_rule(rule, input_nodes)
        assert isinstance(node, Node)

    def test_get_compiled_rule(self):
        """Test retrieving a compiled rule."""
        compiler = RuleCompiler()
        rule = SymbolicRule(name="test_rule", predicate=lambda i, s: 1.0)

        compiler.compile_rule(rule)
        compiled = compiler.get_compiled_rule("test_rule")

        assert compiled is not None
        assert compiled.rule.name == "test_rule"
        assert compiled.node is not None

    def test_get_nonexistent_compiled_rule(self):
        """Test retrieving a non-existent compiled rule."""
        compiler = RuleCompiler()
        compiled = compiler.get_compiled_rule("nonexistent")
        assert compiled is None

    def test_list_compiled_rules(self):
        """Test listing compiled rules."""
        compiler = RuleCompiler()
        compiler.compile_rule(SymbolicRule(name="r1", predicate=lambda i, s: 1.0))
        compiler.compile_rule(SymbolicRule(name="r2", predicate=lambda i, s: 1.0))

        rules = compiler.list_compiled_rules()
        assert len(rules) == 2
        assert "r1" in rules
        assert "r2" in rules

    def test_clear_compiled_rules(self):
        """Test clearing all compiled rules."""
        compiler = RuleCompiler()
        compiler.compile_rule(SymbolicRule(name="test", predicate=lambda i, s: 1.0))

        compiler.clear()
        assert len(compiler.list_compiled_rules()) == 0

    def test_compile_rule_dataclass(self):
        """Test compiling a Rule dataclass."""
        compiler = RuleCompiler()
        rule = Rule(
            name="dataclass_rule",
            predicate=lambda i: 1.0,
        )

        node = compiler.compile_rule(rule)
        assert isinstance(node, Node)


class TestCompositeRuleCompilation:
    """Test suite for compiling composite rules."""

    def test_compile_and_composition(self):
        """Test compiling AND composition."""
        compiler = RuleCompiler()

        rule1 = SymbolicRule(name="r1", predicate=lambda i, s: 1.0, confidence=1.0)
        rule2 = SymbolicRule(name="r2", predicate=lambda i, s: 1.0, confidence=1.0)
        composite = rule1.compose_and(rule2, name="and_rule")

        node = compiler.compile_rule(composite)
        assert isinstance(node, Node)
        assert node.name == "and_rule_composite"

    def test_compile_or_composition(self):
        """Test compiling OR composition."""
        compiler = RuleCompiler()

        rule1 = SymbolicRule(name="r1", predicate=lambda i, s: 1.0, confidence=1.0)
        rule2 = SymbolicRule(name="r2", predicate=lambda i, s: 0.0, confidence=1.0)
        composite = rule1.compose_or(rule2, name="or_rule")

        node = compiler.compile_rule(composite)
        assert isinstance(node, Node)
        assert node.name == "or_rule_composite"

    def test_compile_not_composition(self):
        """Test compiling NOT composition."""
        compiler = RuleCompiler()

        rule = SymbolicRule(name="base", predicate=lambda i, s: 1.0, confidence=1.0)
        negated = rule.compose_not(name="not_rule")

        node = compiler.compile_rule(negated)
        assert isinstance(node, Node)
        assert node.name == "not_rule_composite"

    def test_compile_empty_and(self):
        """Test compiling empty AND."""
        compiler = RuleCompiler()

        # Create composite with no sub-rules manually
        from src.strong_system.symbolic_rules.rules import CompositeRule

        composite = CompositeRule(
            name="empty_and",
            sub_rules=[],
            composition="AND",
        )

        node = compiler.compile_rule(composite)
        assert isinstance(node, Node)
        # Empty AND should return 1.0 (true)
        assert node.value == 1.0

    def test_compile_empty_or(self):
        """Test compiling empty OR."""
        compiler = RuleCompiler()

        from src.strong_system.symbolic_rules.rules import CompositeRule

        composite = CompositeRule(
            name="empty_or",
            sub_rules=[],
            composition="OR",
        )

        node = compiler.compile_rule(composite)
        assert isinstance(node, Node)
        # Empty OR should return 0.0 (false)
        assert node.value == 0.0


class TestCompiledRuleGradients:
    """Test suite for gradients in compiled rules."""

    def test_simple_rule_gradient(self):
        """Test that compiled rule supports gradient computation."""
        compiler = RuleCompiler()
        rule = SymbolicRule(
            name="grad_test",
            predicate=lambda i, s: 1.0,
            confidence=0.5,
        )

        node = compiler.compile_rule(rule)

        # Should be able to run backward
        backward(node)

        # Confidence node should have gradient
        compiled = compiler.get_compiled_rule("grad_test")
        assert compiled.confidence_node is not None

    def test_and_composition_gradient(self):
        """Test gradients through AND composition."""
        compiler = RuleCompiler()

        rule1 = SymbolicRule(name="r1", predicate=lambda i, s: 1.0, confidence=0.8)
        rule2 = SymbolicRule(name="r2", predicate=lambda i, s: 1.0, confidence=0.9)
        composite = rule1.compose_and(rule2, name="and_grad")

        node = compiler.compile_rule(composite)
        backward(node)

        # Should complete without error
        assert node.gradient is not None

    def test_or_composition_gradient(self):
        """Test gradients through OR composition."""
        compiler = RuleCompiler()

        rule1 = SymbolicRule(name="r1", predicate=lambda i, s: 1.0, confidence=0.8)
        rule2 = SymbolicRule(name="r2", predicate=lambda i, s: 0.0, confidence=0.9)
        composite = rule1.compose_or(rule2, name="or_grad")

        node = compiler.compile_rule(composite)
        backward(node)

        # Should complete without error
        assert node.gradient is not None


class TestSoftPredicateNode:
    """Test suite for soft predicate node creation."""

    def test_create_soft_predicate_node(self):
        """Test creating a soft predicate node."""
        compiler = RuleCompiler()
        input_node = Node(0.8, name="input")

        node = compiler.create_soft_predicate_node(
            input_node,
            threshold=0.5,
            steepness=2.0,
            mode="greater",
        )

        assert isinstance(node, Node)
        # Value should be > 0.5 since input > threshold
        assert node.value > 0.5

    def test_soft_predicate_less_mode(self):
        """Test soft predicate with less mode."""
        compiler = RuleCompiler()
        input_node = Node(0.3, name="input")

        node = compiler.create_soft_predicate_node(
            input_node,
            threshold=0.5,
            mode="less",
        )

        # Value should be > 0.5 since input < threshold
        assert node.value > 0.5


class TestCompilerIntegration:
    """Integration tests for the compiler."""

    def test_compile_multiple_rules(self):
        """Test compiling multiple rules."""
        compiler = RuleCompiler()

        rules = [
            SymbolicRule(name=f"rule_{i}", predicate=lambda i, s: 0.5, confidence=0.8)
            for i in range(5)
        ]

        for rule in rules:
            compiler.compile_rule(rule)

        assert len(compiler.list_compiled_rules()) == 5

    def test_rule_with_complex_predicate(self):
        """Test compiling rule with complex predicate."""
        compiler = RuleCompiler()

        def complex_pred(inputs, steepness):
            x = soft_predicate(inputs.get("x", 0), 0.5, steepness, "greater")
            y = soft_predicate(inputs.get("y", 0), 0.5, steepness, "less")
            return x * y  # Both conditions

        rule = SymbolicRule(
            name="complex",
            predicate=complex_pred,
            confidence=0.9,
        )

        node = compiler.compile_rule(rule)
        assert isinstance(node, Node)

    def test_compiled_rule_has_parents(self):
        """Test that compiled rule node has parents."""
        compiler = RuleCompiler()
        rule = SymbolicRule(
            name="parent_test",
            predicate=lambda i, s: 1.0,
            confidence=0.5,
        )

        node = compiler.compile_rule(rule)
        # Node should have parents (predicate and confidence)
        assert len(node.parents) >= 1
