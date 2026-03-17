"""Rule compiler for converting symbolic rules to computational graphs.

Provides compilation of symbolic rules to computational graph nodes
for integration with automatic differentiation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from src.strong_system.computational_graph.node import Node
from src.strong_system.symbolic_rules.differentiable import (
    DifferentiablePredicate,
    fuzzy_and,
    fuzzy_not,
    fuzzy_or,
    soft_predicate,
)
from src.strong_system.symbolic_rules.types import CompiledRule, Rule

if TYPE_CHECKING:
    from src.strong_system.symbolic_rules.rules import CompositeRule, SymbolicRule


class RuleCompiler:
    """Compiler for converting rules to computational graph nodes.

    The RuleCompiler transforms symbolic rules into computational graph
    representations that can be differentiated and optimized.

    Example:
        >>> compiler = RuleCompiler()
        >>> rule = SymbolicRule("price_check", predicate)
        >>> compiled = compiler.compile_rule(rule)
        >>> # compiled is a Node that can be used in the computational graph
    """

    def __init__(self):
        """Initialize the rule compiler."""
        self.compiled_rules: dict[str, CompiledRule] = {}
        self._input_nodes: dict[str, Node] = {}

    def compile_rule(
        self, rule: SymbolicRule | Rule, input_nodes: dict[str, Node] | None = None
    ) -> Node:
        """Compile a rule to a computational graph node.

        Args:
            rule: Rule to compile
            input_nodes: Optional mapping of input names to nodes

        Returns:
            Computational graph node representing the rule
        """
        if hasattr(rule, "sub_rules"):
            # Handle composite rules
            return self._compile_composite(rule, input_nodes)

        # Create input nodes if not provided
        if input_nodes is None:
            input_nodes = self._create_input_nodes(rule)

        # Compile the predicate to a node
        predicate_node = self._compile_predicate(rule.predicate, input_nodes)

        # Get or create confidence node
        if hasattr(rule, "confidence_node"):
            confidence_node = rule.confidence_node
        else:
            confidence = getattr(rule, "confidence", 1.0)
            confidence_node = Node(confidence, name=f"{rule.name}_confidence")

        # Activation = predicate * confidence
        from src.strong_system.computational_graph.operations import Multiply

        activation_node = Multiply.forward(predicate_node, confidence_node)
        activation_node.name = f"{rule.name}_activation"

        # Store compiled rule info
        compiled = CompiledRule(
            rule=rule if isinstance(rule, Rule) else rule.to_rule(),
            node=activation_node,
            input_nodes=input_nodes,
            confidence_node=confidence_node,
        )
        self.compiled_rules[rule.name] = compiled

        return activation_node

    def _compile_composite(
        self,
        rule: CompositeRule,
        input_nodes: dict[str, Node] | None = None,
    ) -> Node:
        """Compile a composite rule.

        Args:
            rule: Composite rule to compile
            input_nodes: Optional input nodes

        Returns:
            Compiled node
        """
        # Compile sub-rules
        sub_nodes = []
        for sub_rule in rule.sub_rules:
            sub_node = self.compile_rule(sub_rule, input_nodes)
            sub_nodes.append(sub_node)

        # Apply composition
        if rule.composition == "NOT":
            result = self._compile_not(sub_nodes[0])
        elif rule.composition == "AND":
            result = self._compile_and(sub_nodes)
        elif rule.composition == "OR":
            result = self._compile_or(sub_nodes)
        else:
            raise ValueError(f"Unknown composition: {rule.composition}")

        result.name = f"{rule.name}_composite"
        return result

    def _compile_predicate(
        self,
        predicate: Any,
        input_nodes: dict[str, Node],
    ) -> Node:
        """Compile a predicate to a computational graph node.

        Args:
            predicate: Predicate to compile
            input_nodes: Input nodes

        Returns:
            Predicate node
        """
        # For now, create a simple node based on predicate evaluation
        # Full implementation would build a subgraph for the predicate

        if isinstance(predicate, DifferentiablePredicate):
            # Evaluate with current input values
            input_values = {k: float(v.value) for k, v in input_nodes.items()}
            pred_value = predicate.evaluate(input_values)
        elif hasattr(predicate, "evaluate"):
            input_values = {k: float(v.value) for k, v in input_nodes.items()}
            pred_value = predicate.evaluate(input_values)
        else:
            # Assume callable
            input_values = {k: float(v.value) for k, v in input_nodes.items()}
            pred_value = predicate(input_values)

        return Node(pred_value, name="predicate_output")

    def _compile_and(self, nodes: list[Node]) -> Node:
        """Compile AND composition of nodes.

        Uses product t-norm: P(A and B) = P(A) * P(B)

        Args:
            nodes: Nodes to combine

        Returns:
            Combined node
        """
        from src.strong_system.computational_graph.operations import Multiply

        if len(nodes) == 0:
            return Node(1.0, name="empty_and")

        if len(nodes) == 1:
            return nodes[0]

        # Chain multiplications
        result = Multiply.forward(nodes[0], nodes[1])
        for node in nodes[2:]:
            result = Multiply.forward(result, node)

        return result

    def _compile_or(self, nodes: list[Node]) -> Node:
        """Compile OR composition of nodes.

        Uses probabilistic sum: P(A or B) = P(A) + P(B) - P(A)*P(B)

        Args:
            nodes: Nodes to combine

        Returns:
            Combined node
        """
        from src.strong_system.computational_graph.operations import Add, Multiply

        if len(nodes) == 0:
            return Node(0.0, name="empty_or")

        if len(nodes) == 1:
            return nodes[0]

        # P(A or B) = P(A) + P(B) - P(A)*P(B)
        # Chain the operation
        result = nodes[0]
        for node in nodes[1:]:
            sum_node = Add.forward(result, node)
            prod_node = Multiply.forward(result, node)
            # Subtract: sum - prod
            neg_prod = Multiply.forward(prod_node, Node(-1.0))
            result = Add.forward(sum_node, neg_prod)

        return result

    def _compile_not(self, node: Node) -> Node:
        """Compile NOT operation on a node.

        P(NOT A) = 1 - P(A)

        Args:
            node: Node to negate

        Returns:
            Negated node
        """
        from src.strong_system.computational_graph.operations import Add, Multiply

        # 1 - node = 1 + (-1 * node)
        neg_node = Multiply.forward(node, Node(-1.0))
        one_node = Node(1.0)
        return Add.forward(one_node, neg_node)

    def _create_input_nodes(self, rule: SymbolicRule | Rule) -> dict[str, Node]:
        """Create default input nodes for a rule.

        Args:
            rule: Rule to create inputs for

        Returns:
            Dictionary of input nodes
        """
        # Extract input names from rule metadata or use defaults
        metadata = getattr(rule, "metadata", {})
        input_names = metadata.get("inputs", ["x"])

        nodes = {}
        for name in input_names:
            nodes[name] = Node(0.0, name=f"input_{name}")

        return nodes

    def create_soft_predicate_node(
        self,
        input_node: Node,
        threshold: float,
        steepness: float = 1.0,
        mode: str = "greater",
    ) -> Node:
        """Create a soft predicate as a computational graph node.

        This creates a differentiable soft threshold operation.

        Args:
            input_node: Input value node
            threshold: Threshold value
            steepness: Steepness of the transition
            mode: Comparison mode

        Returns:
            Node representing soft predicate output
        """
        # For now, evaluate and create a constant node
        # Full implementation would create a custom operation
        value = soft_predicate(
            float(input_node.value),
            threshold,
            steepness,
            mode,
        )
        return Node(value, name=f"soft_pred_{mode}")

    def get_compiled_rule(self, rule_name: str) -> CompiledRule | None:
        """Get a compiled rule by name.

        Args:
            rule_name: Name of compiled rule

        Returns:
            CompiledRule if found, None otherwise
        """
        return self.compiled_rules.get(rule_name)

    def list_compiled_rules(self) -> list[str]:
        """List all compiled rule names.

        Returns:
            List of rule names
        """
        return list(self.compiled_rules.keys())

    def clear(self) -> None:
        """Clear all compiled rules."""
        self.compiled_rules.clear()
        self._input_nodes.clear()
