"""Symbolic rules module for the Strong AI System.

This module provides differentiable symbolic rules that integrate
symbolic reasoning with neural networks through gradient-based learning.

Components:
    - SymbolicRule: Individual symbolic rule with learnable confidence
    - RuleEngine: Engine for managing and evaluating rule sets
    - RuleCompiler: Compiles rules to computational graph nodes
    - DifferentiablePredicate: Predicate with soft thresholds
    - DifferentiableAction: Action with confidence-weighted execution
    - soft_predicate: Soft thresholding for predicates
    - fuzzy_and, fuzzy_or, fuzzy_not: Fuzzy logic operations
    - rule_loss: Differentiable loss for rule learning

Example:
    >>> from src.strong_system.symbolic_rules import SymbolicRule, RuleEngine
    >>> from src.strong_system.symbolic_rules import soft_predicate
    >>>
    >>> # Define a predicate
    >>> def price_above_ma(inputs, steepness=1.0):
    ...     return soft_predicate(inputs['price'], inputs['ma'], steepness)
    >>>
    >>> # Create a rule
    >>> rule = SymbolicRule(
    ...     name="bullish_signal",
    ...     predicate=price_above_ma,
    ...     confidence=0.8
    ... )
    >>>
    >>> # Evaluate
    >>> result = rule.evaluate({"price": 110.0, "ma": 100.0})
    >>> print(f"Activated: {result.activated:.3f}")
    >>>
    >>> # Use with RuleEngine
    >>> engine = RuleEngine()
    >>> engine.add_rule(rule)
    >>> results = engine.evaluate_all({"price": 110.0, "ma": 100.0})
"""

from src.strong_system.symbolic_rules.compiler import RuleCompiler
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
from src.strong_system.symbolic_rules.rules import (
    CompositeRule,
    RuleEngine,
    SymbolicRule,
)
from src.strong_system.symbolic_rules.types import (
    Action,
    CompiledRule,
    Predicate,
    Rule,
    RuleEvaluation,
    RuleSet,
)

__version__ = "0.1.0"

__all__ = [
    # Core classes
    "SymbolicRule",
    "CompositeRule",
    "RuleEngine",
    "RuleCompiler",
    # Types
    "Rule",
    "RuleSet",
    "RuleEvaluation",
    "Predicate",
    "Action",
    "CompiledRule",
    # Differentiable components
    "DifferentiablePredicate",
    "DifferentiableAction",
    # Operations
    "soft_predicate",
    "sigmoid",
    "fuzzy_and",
    "fuzzy_or",
    "fuzzy_not",
    "rule_loss",
    "rule_loss_gradient",
]
