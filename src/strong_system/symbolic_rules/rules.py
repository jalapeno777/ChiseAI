"""Core symbolic rules implementation.

Provides SymbolicRule and RuleEngine classes for defining and
managing symbolic rules with differentiable evaluation.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.strong_system.computational_graph.node import Node
from src.strong_system.symbolic_rules.differentiable import (
    DifferentiableAction,
    DifferentiablePredicate,
    fuzzy_and,
    fuzzy_not,
    fuzzy_or,
    soft_predicate,
)
from src.strong_system.symbolic_rules.types import (
    Rule,
    RuleEvaluation,
    RuleSet,
)

# Type aliases for predicate and action
type Predicate = Any
type Action = Any


class SymbolicRule:
    """A symbolic rule with differentiable evaluation.

    Symbolic rules combine predicates (conditions) with actions (consequences)
    and support learning rule confidence through gradient descent.

    Attributes:
        name: Unique rule identifier
        predicate: Condition to evaluate
        action: Action to take when rule activates
        confidence: Learnable confidence parameter (0.0 to 1.0)
        confidence_node: Computational graph node for confidence (for autodiff)
        description: Human-readable description
        metadata: Additional rule metadata

    Example:
        >>> # Define a simple predicate
        >>> def price_above_ma(inputs, steepness=1.0):
        ...     return soft_predicate(inputs['price'], inputs['ma'], steepness)
        >>> pred = DifferentiablePredicate("price_above_ma", price_above_ma)
        >>> rule = SymbolicRule("bullish_signal", pred)
        >>> result = rule.evaluate({"price": 110.0, "ma": 100.0})
        >>> print(result.activated)  # High probability
    """

    def __init__(
        self,
        name: str,
        predicate: Predicate | DifferentiablePredicate | callable,
        action: Action | DifferentiableAction | None = None,
        confidence: float = 1.0,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize a symbolic rule.

        Args:
            name: Unique rule identifier
            predicate: Condition to evaluate (can be Predicate, callable, or function)
            action: Action to take when rule activates
            confidence: Initial rule confidence (0.0 to 1.0)
            description: Human-readable description
            metadata: Additional rule metadata
        """
        self.name = name
        self.description = description
        self.metadata = metadata or {}

        # Wrap callable in DifferentiablePredicate if needed
        if callable(predicate) and not isinstance(predicate, DifferentiablePredicate):
            self.predicate = DifferentiablePredicate(f"{name}_pred", predicate)
        else:
            self.predicate = predicate

        # Wrap callable in DifferentiableAction if needed
        if callable(action) and not isinstance(action, DifferentiableAction):
            self.action = DifferentiableAction(f"{name}_action", action)
        else:
            self.action = action

        # Initialize confidence
        self._confidence = float(np.clip(confidence, 0.0, 1.0))
        self._confidence_node: Node | None = None

    @property
    def confidence(self) -> float:
        """Get the current rule confidence."""
        return self._confidence

    @confidence.setter
    def confidence(self, value: float) -> None:
        """Set the rule confidence."""
        self._confidence = float(np.clip(value, 0.0, 1.0))
        # Invalidate confidence node if confidence changes
        self._confidence_node = None

    @property
    def confidence_node(self) -> Node:
        """Get or create the confidence as a computational graph node."""
        if self._confidence_node is None:
            self._confidence_node = Node(
                self._confidence, name=f"{self.name}_confidence"
            )
        return self._confidence_node

    def evaluate(self, inputs: dict[str, Any]) -> RuleEvaluation:
        """Evaluate the rule on input data.

        Performs differentiable evaluation of the predicate and returns
        the activation probability along with rule confidence.

        Args:
            inputs: Dictionary of input values

        Returns:
            RuleEvaluation containing activation probability and confidence
        """
        # Evaluate predicate
        if isinstance(self.predicate, DifferentiablePredicate):
            predicate_value = self.predicate.evaluate(inputs)
        elif hasattr(self.predicate, "evaluate"):
            predicate_value = self.predicate.evaluate(inputs)
        else:
            # Assume it's a callable
            predicate_value = self.predicate(inputs)

        # Ensure predicate value is float
        if isinstance(predicate_value, Node):
            pred_val = float(predicate_value.value)
        else:
            pred_val = float(predicate_value)

        # Activation = predicate_value * confidence
        # This allows learning confidence via gradient descent
        activated = pred_val * self._confidence

        return RuleEvaluation(
            activated=activated,
            confidence=self._confidence,
            action=self.action,
            predicate_value=pred_val,
            rule_name=self.name,
        )

    def evaluate_differentiable(self, inputs: dict[str, Node]) -> RuleEvaluation:
        """Evaluate the rule with differentiable inputs.

        This version returns Nodes for integration with the computational graph.

        Args:
            inputs: Dictionary of input nodes

        Returns:
            RuleEvaluation with Node values for differentiation
        """
        # For differentiable evaluation, we need to handle Node inputs
        # This is a simplified version - full implementation would build
        # a computational graph subgraph for the rule

        # Get input values for predicate evaluation
        input_values = {
            k: float(v.value) if isinstance(v, Node) else v for k, v in inputs.items()
        }

        # Evaluate predicate
        if isinstance(self.predicate, DifferentiablePredicate):
            predicate_value = self.predicate.evaluate(input_values)
        elif hasattr(self.predicate, "evaluate"):
            predicate_value = self.predicate.evaluate(input_values)
        else:
            predicate_value = self.predicate(input_values)

        # Create node for predicate value
        pred_node = Node(predicate_value, name=f"{self.name}_predicate")

        # Activation = predicate * confidence (element-wise multiply)
        from src.strong_system.computational_graph.operations import Multiply

        confidence_node = self.confidence_node
        activated_node = Multiply.forward(pred_node, confidence_node)
        activated_node.name = f"{self.name}_activated"

        return RuleEvaluation(
            activated=activated_node,
            confidence=confidence_node,
            action=self.action,
            predicate_value=pred_node,
            rule_name=self.name,
        )

    def compose_and(
        self, other: SymbolicRule, name: str | None = None
    ) -> CompositeRule:
        """Compose this rule with another using AND.

        Args:
            other: Rule to compose with
            name: Name for the composite rule (defaults to combined names)

        Returns:
            New composite rule representing (self AND other)
        """
        composite_name = name or f"{self.name}_AND_{other.name}"
        return CompositeRule(
            composite_name,
            [self, other],
            "AND",
            description=f"Composite rule: ({self.name} AND {other.name})",
        )

    def compose_or(self, other: SymbolicRule, name: str | None = None) -> CompositeRule:
        """Compose this rule with another using OR.

        Args:
            other: Rule to compose with
            name: Name for the composite rule (defaults to combined names)

        Returns:
            New composite rule representing (self OR other)
        """
        composite_name = name or f"{self.name}_OR_{other.name}"
        return CompositeRule(
            composite_name,
            [self, other],
            "OR",
            description=f"Composite rule: ({self.name} OR {other.name})",
        )

    def compose_not(self, name: str | None = None) -> CompositeRule:
        """Negate this rule.

        Args:
            name: Name for the negated rule

        Returns:
            New composite rule representing (NOT self)
        """
        composite_name = name or f"NOT_{self.name}"
        return CompositeRule(
            composite_name,
            [self],
            "NOT",
            description=f"Composite rule: (NOT {self.name})",
        )

    def to_rule(self) -> Rule:
        """Convert to a Rule dataclass instance.

        Returns:
            Rule dataclass representation
        """
        return Rule(
            name=self.name,
            predicate=self.predicate,
            action=self.action,
            description=self.description,
            metadata={**self.metadata, "confidence": self._confidence},
        )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SymbolicRule(name='{self.name}', confidence={self._confidence:.3f})"


class CompositeRule(SymbolicRule):
    """A rule composed from multiple sub-rules.

    Supports AND, OR, and NOT compositions with differentiable evaluation.
    """

    def __init__(
        self,
        name: str,
        sub_rules: list[SymbolicRule],
        composition: str,
        confidence: float = 1.0,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize a composite rule.

        Args:
            name: Rule name
            sub_rules: List of sub-rules to compose
            composition: Composition type - "AND", "OR", or "NOT"
            confidence: Rule confidence
            description: Rule description
            metadata: Additional metadata
        """
        self.sub_rules = sub_rules
        self.composition = composition.upper()

        # Create a predicate that evaluates the composition
        def composite_predicate(inputs: dict, steepness: float = 1.0) -> float:
            return self._evaluate_composition(inputs)

        super().__init__(
            name=name,
            predicate=DifferentiablePredicate(name, composite_predicate),
            confidence=confidence,
            description=description
            or f"Composite rule: {composition} of {[r.name for r in sub_rules]}",
            metadata=metadata,
        )

    def _evaluate_composition(self, inputs: dict[str, Any]) -> float:
        """Evaluate the rule composition.

        Args:
            inputs: Input values

        Returns:
            Composed activation probability
        """
        if self.composition == "NOT":
            if len(self.sub_rules) != 1:
                raise ValueError("NOT composition requires exactly 1 sub-rule")
            result = self.sub_rules[0].evaluate(inputs)
            return fuzzy_not(result.activated)

        # Evaluate all sub-rules
        activations = [rule.evaluate(inputs).activated for rule in self.sub_rules]

        if self.composition == "AND":
            return fuzzy_and(activations)
        elif self.composition == "OR":
            return fuzzy_or(activations)
        else:
            raise ValueError(f"Unknown composition: {self.composition}")

    def evaluate(self, inputs: dict[str, Any]) -> RuleEvaluation:
        """Evaluate the composite rule."""
        # Get base evaluation from parent class
        result = super().evaluate(inputs)

        # Add sub-rule results to metadata
        sub_results = {
            rule.name: rule.evaluate(inputs).activated for rule in self.sub_rules
        }
        result.metadata = {"sub_rules": sub_results}

        return result

    def __repr__(self) -> str:
        """Return string representation."""
        return f"CompositeRule(name='{self.name}', composition='{self.composition}', sub_rules={len(self.sub_rules)})"


class RuleEngine:
    """Engine for managing and evaluating symbolic rule sets.

    The RuleEngine manages collections of rules, evaluates them against
    inputs, and supports rule compilation to computational graphs.

    Attributes:
        rules: Dictionary of rules by name
        rule_sets: Dictionary of rule sets by name

    Example:
        >>> engine = RuleEngine()
        >>> engine.add_rule(SymbolicRule("rule1", predicate1))
        >>> engine.add_rule(SymbolicRule("rule2", predicate2))
        >>> results = engine.evaluate_all({"price": 100.0, "volume": 1000})
    """

    def __init__(self):
        """Initialize the rule engine."""
        self.rules: dict[str, SymbolicRule] = {}
        self.rule_sets: dict[str, RuleSet] = {}

    def add_rule(self, rule: SymbolicRule) -> None:
        """Add a rule to the engine.

        Args:
            rule: Rule to add
        """
        self.rules[rule.name] = rule

    def remove_rule(self, rule_name: str) -> bool:
        """Remove a rule by name.

        Args:
            rule_name: Name of rule to remove

        Returns:
            True if rule was found and removed
        """
        if rule_name in self.rules:
            del self.rules[rule_name]
            return True
        return False

    def get_rule(self, rule_name: str) -> SymbolicRule | None:
        """Get a rule by name.

        Args:
            rule_name: Name of rule to retrieve

        Returns:
            Rule if found, None otherwise
        """
        return self.rules.get(rule_name)

    def add_rule_set(self, rule_set: RuleSet) -> None:
        """Add a rule set to the engine.

        Args:
            rule_set: Rule set to add
        """
        self.rule_sets[rule_set.name] = rule_set

        # Also add individual rules
        for rule in rule_set.rules:
            if isinstance(rule, Rule):
                # Convert Rule to SymbolicRule
                sym_rule = SymbolicRule(
                    name=rule.name,
                    predicate=rule.predicate,
                    action=rule.action,
                    description=rule.description,
                    metadata=rule.metadata,
                )
                self.rules[rule.name] = sym_rule

    def evaluate_rule(
        self, rule_name: str, inputs: dict[str, Any]
    ) -> RuleEvaluation | None:
        """Evaluate a single rule.

        Args:
            rule_name: Name of rule to evaluate
            inputs: Input values

        Returns:
            Rule evaluation result, or None if rule not found
        """
        rule = self.rules.get(rule_name)
        if rule is None:
            return None
        return rule.evaluate(inputs)

    def evaluate_all(self, inputs: dict[str, Any]) -> dict[str, RuleEvaluation]:
        """Evaluate all rules against inputs.

        Args:
            inputs: Input values

        Returns:
            Dictionary mapping rule names to evaluation results
        """
        results = {}
        for name, rule in self.rules.items():
            results[name] = rule.evaluate(inputs)
        return results

    def get_activated_rules(
        self,
        inputs: dict[str, Any],
        threshold: float = 0.5,
    ) -> list[tuple[str, RuleEvaluation]]:
        """Get rules that activate above a threshold.

        Args:
            inputs: Input values
            threshold: Activation threshold (0.0 to 1.0)

        Returns:
            List of (rule_name, evaluation) tuples for activated rules
        """
        results = self.evaluate_all(inputs)
        activated = [
            (name, eval_result)
            for name, eval_result in results.items()
            if eval_result.activated >= threshold
        ]
        # Sort by activation strength (descending)
        activated.sort(key=lambda x: x[1].activated, reverse=True)
        return activated

    def compile_rule(self, rule_name: str) -> Node | None:
        """Compile a rule to a computational graph node.

        Args:
            rule_name: Name of rule to compile

        Returns:
            Computational graph node, or None if rule not found
        """
        from src.strong_system.symbolic_rules.compiler import RuleCompiler

        rule = self.rules.get(rule_name)
        if rule is None:
            return None

        compiler = RuleCompiler()
        return compiler.compile_rule(rule)

    def compile_all(self) -> dict[str, Node]:
        """Compile all rules to computational graph nodes.

        Returns:
            Dictionary mapping rule names to compiled nodes
        """
        from src.strong_system.symbolic_rules.compiler import RuleCompiler

        compiler = RuleCompiler()
        compiled = {}
        for name, rule in self.rules.items():
            compiled[name] = compiler.compile_rule(rule)
        return compiled

    def list_rules(self) -> list[str]:
        """List all rule names.

        Returns:
            List of rule names
        """
        return list(self.rules.keys())

    def list_rule_sets(self) -> list[str]:
        """List all rule set names.

        Returns:
            List of rule set names
        """
        return list(self.rule_sets.keys())

    def __len__(self) -> int:
        """Return number of rules."""
        return len(self.rules)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"RuleEngine(rules={len(self.rules)}, rule_sets={len(self.rule_sets)})"
