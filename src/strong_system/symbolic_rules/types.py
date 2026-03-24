"""Type definitions for symbolic rules module.

Provides type hints and data structures for symbolic rule definitions,
evaluation results, and rule sets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np

if TYPE_CHECKING:
    from src.strong_system.computational_graph.node import Node


@runtime_checkable
class Predicate(Protocol):
    """Protocol for rule predicates.

    A predicate evaluates a condition on input data and returns
    a probability (0.0 to 1.0) representing the degree to which
    the condition is satisfied.
    """

    def evaluate(self, inputs: dict[str, Any]) -> float | Node:
        """Evaluate the predicate on input data.

        Args:
            inputs: Dictionary of input values

        Returns:
            Probability (0.0 to 1.0) or Node for differentiable evaluation
        """
        ...

    @property
    def name(self) -> str:
        """Return the predicate name."""
        ...


@runtime_checkable
class Action(Protocol):
    """Protocol for rule actions.

    An action defines what to do when a rule is activated.
    """

    def execute(self, inputs: dict[str, Any], confidence: float) -> Any:
        """Execute the action.

        Args:
            inputs: Dictionary of input values
            confidence: Rule confidence (0.0 to 1.0)

        Returns:
            Action result
        """
        ...

    @property
    def name(self) -> str:
        """Return the action name."""
        ...


@dataclass
class RuleEvaluation:
    """Result of evaluating a symbolic rule.

    Attributes:
        activated: Probability that the rule activated (0.0 to 1.0)
        confidence: Rule confidence parameter (learnable)
        action: The action associated with this rule
        predicate_value: The raw predicate evaluation result
        rule_name: Name of the evaluated rule
    """

    activated: float | Node
    confidence: float | Node
    action: Action | None = None
    predicate_value: float | Node = 0.0
    rule_name: str = ""

    def __post_init__(self):
        """Validate evaluation values."""
        # Ensure values are in valid range if they're floats
        if isinstance(self.activated, (int, float)):
            self.activated = float(np.clip(self.activated, 0.0, 1.0))
        if isinstance(self.confidence, (int, float)):
            self.confidence = float(np.clip(self.confidence, 0.0, 1.0))


@dataclass
class Rule:
    """Definition of a symbolic rule.

    Attributes:
        name: Unique rule identifier
        predicate: Condition to evaluate
        action: Action to take when rule activates
        description: Human-readable description
        metadata: Additional rule metadata
    """

    name: str
    predicate: Predicate
    action: Action | None = None
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleSet:
    """A collection of related rules.

    Attributes:
        name: Name of the rule set
        rules: List of rules in the set
        description: Description of what this rule set does
        metadata: Additional metadata
    """

    name: str
    rules: list[Rule] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_rule(self, rule: Rule) -> None:
        """Add a rule to the set.

        Args:
            rule: Rule to add
        """
        self.rules.append(rule)

    def remove_rule(self, rule_name: str) -> bool:
        """Remove a rule by name.

        Args:
            rule_name: Name of rule to remove

        Returns:
            True if rule was found and removed, False otherwise
        """
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                return True
        return False

    def get_rule(self, rule_name: str) -> Rule | None:
        """Get a rule by name.

        Args:
            rule_name: Name of rule to find

        Returns:
            Rule if found, None otherwise
        """
        for rule in self.rules:
            if rule.name == rule_name:
                return rule
        return None


# Type aliases for rule composition
# Note: These use string annotations to avoid circular imports
RuleCompositionOperator = Callable[[list[float]], float]
PredicateFunction = Callable[[dict[str, Any]], float]
ActionFunction = Callable[[dict[str, Any], float], Any]


@dataclass
class CompiledRule:
    """A rule compiled to a computational graph node.

    Attributes:
        rule: Original rule definition
        node: Computational graph node representing the rule
        input_nodes: Mapping of input names to nodes
        confidence_node: Learnable confidence parameter node
    """

    rule: Rule
    node: Node
    input_nodes: dict[str, Node] = field(default_factory=dict)
    confidence_node: Node | None = None
