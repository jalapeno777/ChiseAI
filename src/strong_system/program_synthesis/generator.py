"""Safe program generator for program synthesis.

Provides safe generation with constraints, template-based generation,
and search-based generation with integration to the belief system.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

from src.strong_system.program_synthesis.dsl import (
    DSLBuilder,
    ProgramDSL,
    create_safe_schema,
)
from src.strong_system.program_synthesis.types import (
    ASTNode,
    ASTNodeType,
    BinaryOp,
    BinaryOperator,
    CallExpression,
    FunctionDef,
    NumberLiteral,
    ParameterRef,
    Program,
    ProgramSchema,
    ProgramType,
    Sequence,
    StringLiteral,
    TypeAnnotation,
    UnaryOp,
    UnaryOperator,
    VariableDecl,
    VariableRef,
)
from src.strong_system.program_synthesis.validator import (
    ValidationResult,
    validate_program,
)


class GenerationStrategy(Enum):
    """Strategies for program generation."""

    TEMPLATE = auto()
    SEARCH = auto()
    GRAMMAR = auto()
    NEURAL = auto()
    HYBRID = auto()


@dataclass
class GenerationConstraints:
    """Constraints for safe program generation.

    Attributes:
        max_depth: Maximum AST depth
        max_nodes: Maximum number of AST nodes
        max_parameters: Maximum function parameters
        allowed_node_types: Set of allowed AST node types
        allowed_operators: Set of allowed operators
        forbidden_patterns: List of forbidden code patterns
        timeout_seconds: Generation timeout
    """

    max_depth: int = 10
    max_nodes: int = 100
    max_parameters: int = 5
    allowed_node_types: set[ASTNodeType] = field(
        default_factory=lambda: {
            ASTNodeType.NUMBER,
            ASTNodeType.STRING,
            ASTNodeType.BOOLEAN,
            ASTNodeType.VARIABLE,
            ASTNodeType.PARAMETER,
            ASTNodeType.BINARY_OP,
            ASTNodeType.UNARY_OP,
            ASTNodeType.CALL,
            ASTNodeType.SEQUENCE,
            ASTNodeType.FUNCTION_DEF,
            ASTNodeType.VARIABLE_DECL,
        }
    )
    allowed_operators: set[str] = field(
        default_factory=lambda: {
            "+",
            "-",
            "*",
            "/",
            "==",
            "!=",
            "<",
            "<=",
            ">",
            ">=",
        }
    )
    forbidden_patterns: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0

    def __post_init__(self):
        """Validate constraints."""
        if self.max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        if self.max_nodes < 1:
            raise ValueError("max_nodes must be at least 1")


@dataclass
class GenerationConfig:
    """Configuration for program generation.

    Attributes:
        strategy: Generation strategy
        schema: Program schema for validation
        constraints: Generation constraints
        random_seed: Random seed for reproducibility
        belief_context: Belief IDs to use for generation context
        temperature: Generation temperature (0.0-1.0)
    """

    strategy: GenerationStrategy = GenerationStrategy.TEMPLATE
    schema: ProgramSchema = field(default_factory=lambda: create_safe_schema("safe"))
    constraints: GenerationConstraints = field(default_factory=GenerationConstraints)
    random_seed: int | None = None
    belief_context: list[str] = field(default_factory=list)
    temperature: float = 0.7

    def __post_init__(self):
        """Validate configuration."""
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("temperature must be between 0.0 and 1.0")


@dataclass
class GenerationContext:
    """Context for program generation.

    Attributes:
        variables: Available variables
        functions: Available functions
        beliefs: Belief references from belief system
        hypotheses: Hypothesis references
        target_type: Target program type
        description: Generation description/requirements
    """

    variables: dict[str, TypeAnnotation] = field(default_factory=dict)
    functions: dict[str, Callable] = field(default_factory=dict)
    beliefs: dict[str, Any] = field(default_factory=dict)
    hypotheses: list[str] = field(default_factory=list)
    target_type: ProgramType = ProgramType.FUNCTION
    description: str = ""


class ProgramGenerator(ABC):
    """Abstract base class for program generators.

    Provides common functionality for safe program generation
    with constraints and validation.
    """

    def __init__(self, config: GenerationConfig | None = None):
        """Initialize generator.

        Args:
            config: Generation configuration
        """
        self.config = config or GenerationConfig()
        self.constraints = self.config.constraints
        self._builder = DSLBuilder()
        self._node_count = 0

        # Set random seed if provided
        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)

    @abstractmethod
    def generate(
        self,
        context: GenerationContext,
    ) -> Program | None:
        """Generate a program.

        Args:
            context: Generation context

        Returns:
            Generated program or None if generation failed
        """
        pass

    def validate_generation(self, program: Program) -> ValidationResult:
        """Validate a generated program.

        Args:
            program: Program to validate

        Returns:
            Validation result
        """
        return validate_program(
            program,
            schema=self.config.schema,
            check_types=True,
            check_semantics=True,
        )

    def is_valid_node_type(self, node_type: ASTNodeType) -> bool:
        """Check if a node type is allowed.

        Args:
            node_type: Node type to check

        Returns:
            True if allowed
        """
        return node_type in self.constraints.allowed_node_types

    def is_valid_operator(self, operator: str) -> bool:
        """Check if an operator is allowed.

        Args:
            operator: Operator to check

        Returns:
            True if allowed
        """
        return operator in self.constraints.allowed_operators

    def check_node_count(self) -> bool:
        """Check if we can add more nodes.

        Returns:
            True if within limits
        """
        return self._node_count < self.constraints.max_nodes

    def increment_node_count(self) -> None:
        """Increment the node count."""
        self._node_count += 1

    def reset_node_count(self) -> None:
        """Reset the node count."""
        self._node_count = 0


class TemplateBasedGenerator(ProgramGenerator):
    """Template-based program generator.

    Generates programs by filling in predefined templates
    with context-specific values.
    """

    def __init__(self, config: GenerationConfig | None = None):
        """Initialize template generator.

        Args:
            config: Generation configuration
        """
        super().__init__(config)
        self._templates: dict[str, Callable[[GenerationContext], Program]] = {}
        self._register_default_templates()

    def _register_default_templates(self) -> None:
        """Register default program templates."""
        self._templates["simple_function"] = self._template_simple_function
        self._templates["arithmetic_expr"] = self._template_arithmetic_expr
        self._templates["conditional"] = self._template_conditional

    def register_template(
        self,
        name: str,
        template_fn: Callable[[GenerationContext], Program],
    ) -> None:
        """Register a new template.

        Args:
            name: Template name
            template_fn: Template function
        """
        self._templates[name] = template_fn

    def generate(
        self,
        context: GenerationContext,
    ) -> Program | None:
        """Generate a program using templates.

        Args:
            context: Generation context

        Returns:
            Generated program or None
        """
        self.reset_node_count()

        # Select template based on context
        template_name = self._select_template(context)
        template_fn = self._templates.get(template_name)

        if template_fn is None:
            return None

        # Generate using template
        program = template_fn(context)

        if program is None:
            return None

        # Validate
        result = self.validate_generation(program)
        if not result.valid:
            return None

        return program

    def _select_template(self, context: GenerationContext) -> str:
        """Select appropriate template for context.

        Args:
            context: Generation context

        Returns:
            Template name
        """
        # Simple selection based on context
        if "condition" in context.description.lower():
            return "conditional"
        elif "arithmetic" in context.description.lower():
            return "arithmetic_expr"
        else:
            return "simple_function"

    def _template_simple_function(self, context: GenerationContext) -> Program | None:
        """Template for simple function.

        Args:
            context: Generation context

        Returns:
            Generated program
        """
        dsl = ProgramDSL("simple_function", context.target_type)
        dsl.with_description("Auto-generated simple function")

        # Create a parameter
        param = self._builder.param(
            "x",
            TypeAnnotation(base_type="float"),
        )

        # Create function body
        body = self._builder.sequence(
            [self._builder.add(self._builder.var("x"), self._builder.number(1.0))]
        )

        dsl.define_function(
            "compute",
            parameters=[param],
            body=body,
            return_type=TypeAnnotation(base_type="float"),
        )

        return dsl.build()

    def _template_arithmetic_expr(self, context: GenerationContext) -> Program | None:
        """Template for arithmetic expression.

        Args:
            context: Generation context

        Returns:
            Generated program
        """
        dsl = ProgramDSL("arithmetic_expr", context.target_type)
        dsl.with_description("Auto-generated arithmetic expression")

        # Create variables
        dsl.declare_variable("a", self._builder.number(10.0))
        dsl.declare_variable("b", self._builder.number(5.0))

        # Create arithmetic expression: (a + b) * 2
        expr = self._builder.mul(
            self._builder.add(
                self._builder.var("a"),
                self._builder.var("b"),
            ),
            self._builder.number(2.0),
        )

        dsl.add_statement(expr)

        return dsl.build()

    def _template_conditional(self, context: GenerationContext) -> Program | None:
        """Template for conditional.

        Args:
            context: Generation context

        Returns:
            Generated program
        """
        dsl = ProgramDSL("conditional", context.target_type)
        dsl.with_description("Auto-generated conditional")

        # Create a simple if-then
        from src.strong_system.program_synthesis.types import Conditional

        condition = self._builder.lt(
            self._builder.var("x"),
            self._builder.number(0.0),
        )

        then_branch = self._builder.sequence(
            [
                self._builder.call("print", [self._builder.string("negative")]),
            ]
        )

        else_branch = self._builder.sequence(
            [
                self._builder.call("print", [self._builder.string("non-negative")]),
            ]
        )

        cond = Conditional(
            condition=condition,
            then_branch=then_branch,
            else_branch=else_branch,
        )

        dsl.add_statement(cond)

        return dsl.build()


class SearchBasedGenerator(ProgramGenerator):
    """Search-based program generator.

    Generates programs using search algorithms (random, beam search, etc.)
    with constraint satisfaction.

    NOTE: This is a skeleton implementation for Phase 3.
    Full search implementation will come in Phase 4.
    """

    def __init__(self, config: GenerationConfig | None = None):
        """Initialize search generator.

        Args:
            config: Generation configuration
        """
        super().__init__(config)
        self._max_attempts = 10

    def generate(
        self,
        context: GenerationContext,
    ) -> Program | None:
        """Generate a program using search.

        Args:
            context: Generation context

        Returns:
            Generated program or None
        """
        self.reset_node_count()

        # Skeleton: try random generation up to max_attempts
        for attempt in range(self._max_attempts):
            program = self._try_generate(context)
            if program is not None:
                result = self.validate_generation(program)
                if result.valid:
                    return program

        return None

    def _try_generate(self, context: GenerationContext) -> Program | None:
        """Try to generate a valid program (skeleton).

        Args:
            context: Generation context

        Returns:
            Program or None
        """
        # Skeleton: generate simple arithmetic expression
        dsl = ProgramDSL("search_generated", context.target_type)

        # Generate random arithmetic operation
        ops = [BinaryOperator.ADD, BinaryOperator.SUB, BinaryOperator.MUL]
        op = random.choice(ops)

        left = self._builder.number(random.uniform(-10, 10))
        right = self._builder.number(random.uniform(-10, 10))

        expr = BinaryOp(operator=op, left=left, right=right)
        dsl.add_statement(expr)

        return dsl.build()


class GrammarBasedGenerator(ProgramGenerator):
    """Grammar-based program generator.

    Generates programs using a formal grammar.

    NOTE: This is a skeleton implementation for Phase 3.
    Full grammar implementation will come in Phase 4.
    """

    def __init__(self, config: GenerationConfig | None = None):
        """Initialize grammar generator.

        Args:
            config: Generation configuration
        """
        super().__init__(config)

    def generate(
        self,
        context: GenerationContext,
    ) -> Program | None:
        """Generate a program using grammar rules.

        Args:
            context: Generation context

        Returns:
            Generated program or None
        """
        self.reset_node_count()

        # Skeleton: generate simple expression using basic grammar
        dsl = ProgramDSL("grammar_generated", context.target_type)

        # Generate: var = expr
        value = self._generate_expression(0)
        if value is None:
            return None

        dsl.declare_variable("result", value)

        program = dsl.build()
        result = self.validate_generation(program)

        if result.valid:
            return program
        return None

    def _generate_expression(self, depth: int) -> ASTNode | None:
        """Generate an expression using grammar rules.

        Args:
            depth: Current recursion depth

        Returns:
            Expression node or None
        """
        if depth >= self.constraints.max_depth:
            # Generate terminal
            return self._builder.number(random.uniform(-100, 100))

        if not self.check_node_count():
            return None

        self.increment_node_count()

        # 50% chance of terminal, 50% chance of binary op
        if random.random() < 0.5 or depth >= 3:
            return self._builder.number(random.uniform(-100, 100))

        # Generate binary operation
        ops = [BinaryOperator.ADD, BinaryOperator.SUB, BinaryOperator.MUL]
        op = random.choice(ops)

        left = self._generate_expression(depth + 1)
        right = self._generate_expression(depth + 1)

        if left is None or right is None:
            return None

        return BinaryOp(operator=op, left=left, right=right)


class HybridGenerator(ProgramGenerator):
    """Hybrid program generator combining multiple strategies.

    Uses a combination of template-based, search-based, and grammar-based
    generation for maximum flexibility.

    NOTE: This is a skeleton implementation for Phase 3.
    """

    def __init__(self, config: GenerationConfig | None = None):
        """Initialize hybrid generator.

        Args:
            config: Generation configuration
        """
        super().__init__(config)
        self._template_gen = TemplateBasedGenerator(config)
        self._search_gen = SearchBasedGenerator(config)
        self._grammar_gen = GrammarBasedGenerator(config)

    def generate(
        self,
        context: GenerationContext,
    ) -> Program | None:
        """Generate a program using hybrid approach.

        Args:
            context: Generation context

        Returns:
            Generated program or None
        """
        # Try different generators based on strategy preference
        strategy = self.config.strategy

        if strategy == GenerationStrategy.TEMPLATE:
            return self._template_gen.generate(context)
        elif strategy == GenerationStrategy.SEARCH:
            return self._search_gen.generate(context)
        elif strategy == GenerationStrategy.GRAMMAR:
            return self._grammar_gen.generate(context)
        else:
            # HYBRID: try all and pick best
            programs: list[Program] = []

            template_program = self._template_gen.generate(context)
            if template_program:
                programs.append(template_program)

            search_program = self._search_gen.generate(context)
            if search_program:
                programs.append(search_program)

            grammar_program = self._grammar_gen.generate(context)
            if grammar_program:
                programs.append(grammar_program)

            if programs:
                # Pick first valid one (could be improved with scoring)
                return programs[0]

        return None


class SafeGenerator:
    """Safe program generator with comprehensive safety checks.

    Wraps any generator with additional safety constraints and
    comprehensive validation.
    """

    def __init__(self, generator: ProgramGenerator):
        """Initialize safe generator.

        Args:
            generator: Base generator to wrap
        """
        self._generator = generator
        self._constraints = generator.constraints

    def generate(
        self,
        context: GenerationContext,
    ) -> Program | None:
        """Generate a program safely.

        Args:
            context: Generation context

        Returns:
            Generated program or None
        """
        # Pre-generation safety checks
        if not self._pre_generation_checks(context):
            return None

        # Generate
        program = self._generator.generate(context)

        if program is None:
            return None

        # Post-generation safety checks
        if not self._post_generation_checks(program):
            return None

        return program

    def _pre_generation_checks(self, context: GenerationContext) -> bool:
        """Perform pre-generation safety checks.

        Args:
            context: Generation context

        Returns:
            True if checks pass
        """
        # Check context doesn't contain forbidden patterns
        for pattern in self._constraints.forbidden_patterns:
            if pattern in context.description:
                return False

        return True

    def _post_generation_checks(self, program: Program) -> bool:
        """Perform post-generation safety checks.

        Args:
            program: Generated program

        Returns:
            True if checks pass
        """
        # Validate program
        result = self._generator.validate_generation(program)
        return result.valid


def create_generator(
    strategy: GenerationStrategy = GenerationStrategy.TEMPLATE,
    config: GenerationConfig | None = None,
) -> ProgramGenerator:
    """Factory function to create appropriate generator.

    Args:
        strategy: Generation strategy
        config: Generation configuration

    Returns:
        Configured program generator
    """
    if config is None:
        config = GenerationConfig(strategy=strategy)

    if strategy == GenerationStrategy.TEMPLATE:
        return TemplateBasedGenerator(config)
    elif strategy == GenerationStrategy.SEARCH:
        return SearchBasedGenerator(config)
    elif strategy == GenerationStrategy.GRAMMAR:
        return GrammarBasedGenerator(config)
    elif strategy == GenerationStrategy.HYBRID:
        return HybridGenerator(config)
    else:
        # Default to template
        return TemplateBasedGenerator(config)


def generate_program(
    description: str,
    target_type: ProgramType = ProgramType.FUNCTION,
    strategy: GenerationStrategy = GenerationStrategy.TEMPLATE,
    constraints: GenerationConstraints | None = None,
) -> Program | None:
    """Convenience function for program generation.

    Args:
        description: Generation description
        target_type: Target program type
        strategy: Generation strategy
        constraints: Generation constraints

    Returns:
        Generated program or None
    """
    config = GenerationConfig(
        strategy=strategy,
        constraints=constraints or GenerationConstraints(),
    )

    generator = create_generator(strategy, config)

    context = GenerationContext(
        description=description,
        target_type=target_type,
    )

    return generator.generate(context)
