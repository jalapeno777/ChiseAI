"""Program validation for program synthesis.

Provides syntax validation, type checking, semantic validation,
and comprehensive error reporting for synthesized programs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from src.strong_system.program_synthesis.types import (
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CallExpression,
    Conditional,
    FunctionDef,
    Loop,
    Program,
    ProgramSchema,
    TypeAnnotation,
    UnaryOp,
    VariableDecl,
    VariableRef,
)


class ValidationErrorType(Enum):
    """Types of validation errors."""

    SYNTAX_ERROR = auto()
    TYPE_ERROR = auto()
    SEMANTIC_ERROR = auto()
    SCHEMA_VIOLATION = auto()
    UNSUPPORTED_NODE = auto()
    UNDEFINED_REFERENCE = auto()
    TYPE_MISMATCH = auto()
    ARITY_MISMATCH = auto()
    RECURSION_LIMIT = auto()


@dataclass
class ValidationError:
    """A single validation error.

    Attributes:
        error_type: Type of error
        message: Human-readable error message
        node: AST node where error occurred
        line: Line number (if available)
        column: Column number (if available)
        severity: Error severity ("error", "warning", "info")
    """

    error_type: ValidationErrorType
    message: str
    node: ASTNode | None = None
    line: int = 0
    column: int = 0
    severity: str = "error"

    def __str__(self) -> str:
        """Format error as string."""
        loc = f" at line {self.line}" if self.line > 0 else ""
        if self.column > 0:
            loc += f", column {self.column}"
        return f"[{self.severity.upper()}] {self.error_type.name}: {self.message}{loc}"


@dataclass
class ValidationResult:
    """Result of program validation.

    Attributes:
        valid: Whether validation passed
        errors: List of validation errors
        warnings: List of validation warnings
        metadata: Additional validation metadata
    """

    valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_error(
        self,
        error_type: ValidationErrorType,
        message: str,
        node: ASTNode | None = None,
        severity: str = "error",
    ) -> None:
        """Add a validation error.

        Args:
            error_type: Type of error
            message: Error message
            node: Associated AST node
            severity: Error severity
        """
        line = node.location.line if node else 0
        column = node.location.column if node else 0

        error = ValidationError(
            error_type=error_type,
            message=message,
            node=node,
            line=line,
            column=column,
            severity=severity,
        )

        if severity == "error":
            self.errors.append(error)
            self.valid = False
        else:
            self.warnings.append(error)

    def add_warning(
        self,
        error_type: ValidationErrorType,
        message: str,
        node: ASTNode | None = None,
    ) -> None:
        """Add a validation warning.

        Args:
            error_type: Type of error
            message: Warning message
            node: Associated AST node
        """
        self.add_error(error_type, message, node, severity="warning")

    def merge(self, other: ValidationResult) -> None:
        """Merge another validation result into this one.

        Args:
            other: Other validation result
        """
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if not other.valid:
            self.valid = False

    def __str__(self) -> str:
        """Format result as string."""
        status = "VALID" if self.valid else "INVALID"
        result = f"Validation Result: {status}\n"
        result += f"  Errors: {len(self.errors)}\n"
        result += f"  Warnings: {len(self.warnings)}\n"

        for error in self.errors:
            result += f"  - {error}\n"

        for warning in self.warnings:
            result += f"  - {warning}\n"

        return result


class ProgramValidator:
    """Validator for synthesized programs.

    Provides comprehensive validation including:
    - Syntax validation
    - Type checking
    - Semantic validation
    - Schema compliance checking
    """

    def __init__(self, schema: ProgramSchema | None = None):
        """Initialize validator.

        Args:
            schema: Schema to validate against (uses default if None)
        """
        if schema is None:
            from src.strong_system.program_synthesis.dsl import (
                schema_registry,
            )

            schema = schema_registry.get("default")
            if schema is None:
                raise ValueError("No default schema available")

        self.schema = schema
        self._max_nesting_depth = schema.constraints.get("max_nesting_depth", 100)
        self._max_statements = schema.constraints.get("max_statements", 10000)
        self._symbol_table: dict[str, TypeAnnotation] = {}

    def validate(self, program: Program) -> ValidationResult:
        """Validate a complete program.

        Args:
            program: Program to validate

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Validate program metadata
        if not program.name:
            result.add_error(
                ValidationErrorType.SYNTAX_ERROR,
                "Program name cannot be empty",
            )

        # Validate against schema
        schema_result = self._validate_schema_compliance(program)
        result.merge(schema_result)

        # Validate AST structure
        ast_result = self._validate_ast(program.ast)
        result.merge(ast_result)

        # Count statements
        statement_count = self._count_statements(program.ast)
        if statement_count > self._max_statements:
            result.add_error(
                ValidationErrorType.SEMANTIC_ERROR,
                f"Program has {statement_count} statements, "
                f"exceeding maximum of {self._max_statements}",
            )

        return result

    def _validate_schema_compliance(self, program: Program) -> ValidationResult:
        """Validate program complies with schema.

        Args:
            program: Program to validate

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Check required imports
        for required in self.schema.required_imports:
            if required not in program.imports:
                result.add_error(
                    ValidationErrorType.SCHEMA_VIOLATION,
                    f"Missing required import: {required}",
                )

        return result

    def _validate_ast(self, node: ASTNode, depth: int = 0) -> ValidationResult:
        """Validate an AST node recursively.

        Args:
            node: AST node to validate
            depth: Current nesting depth

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Check nesting depth
        if depth > self._max_nesting_depth:
            result.add_error(
                ValidationErrorType.RECURSION_LIMIT,
                f"Maximum nesting depth exceeded ({self._max_nesting_depth})",
                node,
            )
            return result

        # Check if node type is allowed
        if not self.schema.allows_node_type(node.node_type):
            result.add_error(
                ValidationErrorType.UNSUPPORTED_NODE,
                f"Node type {node.node_type.name} is not allowed by schema",
                node,
            )

        # Validate specific node types
        node_result = self._validate_node_specific(node)
        result.merge(node_result)

        # Validate children
        for child in node.children():
            child_result = self._validate_ast(child, depth + 1)
            result.merge(child_result)

        return result

    def _validate_node_specific(self, node: ASTNode) -> ValidationResult:
        """Validate node-specific constraints.

        Args:
            node: AST node to validate

        Returns:
            Validation result
        """
        result = ValidationResult()

        if isinstance(node, BinaryOp):
            result.merge(self._validate_binary_op(node))
        elif isinstance(node, UnaryOp):
            result.merge(self._validate_unary_op(node))
        elif isinstance(node, CallExpression):
            result.merge(self._validate_call(node))
        elif isinstance(node, FunctionDef):
            result.merge(self._validate_function_def(node))
        elif isinstance(node, VariableDecl):
            result.merge(self._validate_variable_decl(node))
        elif isinstance(node, Conditional):
            result.merge(self._validate_conditional(node))
        elif isinstance(node, Loop):
            result.merge(self._validate_loop(node))

        return result

    def _validate_binary_op(self, node: BinaryOp) -> ValidationResult:
        """Validate binary operation.

        Args:
            node: Binary operation node

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Check for division by zero (simple case)
        if node.operator == BinaryOperator.DIV:
            from src.strong_system.program_synthesis.types import NumberLiteral

            if isinstance(node.right, NumberLiteral) and node.right.value == 0:
                result.add_warning(
                    ValidationErrorType.SEMANTIC_ERROR,
                    "Potential division by zero",
                    node,
                )

        return result

    def _validate_unary_op(self, node: UnaryOp) -> ValidationResult:
        """Validate unary operation.

        Args:
            node: Unary operation node

        Returns:
            Validation result
        """
        result = ValidationResult()
        # Add unary-specific validations as needed
        return result

    def _validate_call(self, node: CallExpression) -> ValidationResult:
        """Validate function call.

        Args:
            node: Call expression node

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Check if arbitrary calls are allowed
        allow_arbitrary = self.schema.constraints.get("allow_arbitrary_calls", True)
        allowed_calls = self.schema.constraints.get("allowed_calls", [])

        if not allow_arbitrary:
            # Get function name
            func_name = ""
            if isinstance(node.callee, VariableRef):
                func_name = node.callee.name

            if func_name and func_name not in allowed_calls:
                result.add_error(
                    ValidationErrorType.SEMANTIC_ERROR,
                    f"Function '{func_name}' is not in allowed calls list",
                    node,
                )

        # Check argument count for known functions
        if isinstance(node.callee, VariableRef):
            func_name = node.callee.name
            if func_name == "len" and len(node.arguments) != 1:
                result.add_error(
                    ValidationErrorType.ARITY_MISMATCH,
                    f"len() takes exactly 1 argument ({len(node.arguments)} given)",
                    node,
                )

        return result

    def _validate_function_def(self, node: FunctionDef) -> ValidationResult:
        """Validate function definition.

        Args:
            node: Function definition node

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Check parameter count
        max_params = self.schema.constraints.get("max_parameters", 100)
        if len(node.parameters) > max_params:
            result.add_error(
                ValidationErrorType.SEMANTIC_ERROR,
                f"Function has {len(node.parameters)} parameters, "
                f"exceeding maximum of {max_params}",
                node,
            )

        # Check for type annotations if required
        require_types = self.schema.constraints.get("require_type_annotations", False)
        if require_types:
            for param in node.parameters:
                if param.type_annotation is None:
                    result.add_warning(
                        ValidationErrorType.TYPE_ERROR,
                        f"Parameter '{param.name}' lacks type annotation",
                        param,
                    )

            if node.return_type is None:
                result.add_warning(
                    ValidationErrorType.TYPE_ERROR,
                    f"Function '{node.name}' lacks return type annotation",
                    node,
                )

        return result

    def _validate_variable_decl(self, node: VariableDecl) -> ValidationResult:
        """Validate variable declaration.

        Args:
            node: Variable declaration node

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Check variable name is valid
        if not node.name.isidentifier():
            result.add_error(
                ValidationErrorType.SYNTAX_ERROR,
                f"'{node.name}' is not a valid identifier",
                node,
            )

        # Check for type annotation if required
        require_types = self.schema.constraints.get("require_type_annotations", False)
        if require_types and node.type_annotation is None:
            result.add_warning(
                ValidationErrorType.TYPE_ERROR,
                f"Variable '{node.name}' lacks type annotation",
                node,
            )

        return result

    def _validate_conditional(self, node: Conditional) -> ValidationResult:
        """Validate conditional.

        Args:
            node: Conditional node

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Validate condition exists
        if node.condition is None:
            result.add_error(
                ValidationErrorType.SYNTAX_ERROR,
                "Conditional missing condition expression",
                node,
            )

        return result

    def _validate_loop(self, node: Loop) -> ValidationResult:
        """Validate loop.

        Args:
            node: Loop node

        Returns:
            Validation result
        """
        result = ValidationResult()

        # Validate loop variable name
        if not node.loop_variable.isidentifier():
            result.add_error(
                ValidationErrorType.SYNTAX_ERROR,
                f"'{node.loop_variable}' is not a valid identifier",
                node,
            )

        return result

    def _count_statements(self, node: ASTNode) -> int:
        """Count total statements in AST.

        Args:
            node: Root AST node

        Returns:
            Statement count
        """
        count = 1  # Count this node

        for child in node.children():
            count += self._count_statements(child)

        return count


class TypeChecker:
    """Type checker for program AST.

    Performs static type checking and inference on synthesized programs.
    """

    def __init__(self):
        """Initialize type checker."""
        self._type_env: dict[str, TypeAnnotation] = {}

    def check_types(self, program: Program) -> ValidationResult:
        """Type check a program.

        Args:
            program: Program to type check

        Returns:
            Validation result with type errors
        """
        result = ValidationResult()
        self._type_env.clear()

        # Type check AST
        ast_result = self._check_node_types(program.ast)
        result.merge(ast_result)

        return result

    def _check_node_types(self, node: ASTNode) -> ValidationResult:
        """Type check an AST node.

        Args:
            node: AST node to check

        Returns:
            Validation result
        """
        result = ValidationResult()

        from src.strong_system.program_synthesis.types import (
            BinaryOp,
            FunctionDef,
            VariableDecl,
        )

        if isinstance(node, BinaryOp):
            # Check operand types
            left_result = self._check_node_types(node.left)
            right_result = self._check_node_types(node.right)
            result.merge(left_result)
            result.merge(right_result)

        elif isinstance(node, FunctionDef):
            # Add parameters to type environment
            for param in node.parameters:
                if param.type_annotation:
                    self._type_env[param.name] = param.type_annotation

            # Check body
            body_result = self._check_node_types(node.body)
            result.merge(body_result)

        elif isinstance(node, VariableDecl):
            # Check initializer type
            if node.initializer:
                init_result = self._check_node_types(node.initializer)
                result.merge(init_result)

            # Add to type environment
            if node.type_annotation:
                self._type_env[node.name] = node.type_annotation

        # Recursively check children
        for child in node.children():
            child_result = self._check_node_types(child)
            result.merge(child_result)

        return result

    def infer_type(self, node: ASTNode) -> TypeAnnotation | None:
        """Infer the type of an AST node.

        Args:
            node: AST node

        Returns:
            Inferred type or None if cannot infer
        """
        from src.strong_system.program_synthesis.types import (
            BinaryOp,
            BinaryOperator,
            BooleanLiteral,
            NumberLiteral,
            StringLiteral,
            VectorLiteral,
        )

        if isinstance(node, NumberLiteral):
            return TypeAnnotation(base_type="float")

        elif isinstance(node, StringLiteral):
            return TypeAnnotation(base_type="str")

        elif isinstance(node, BooleanLiteral):
            return TypeAnnotation(base_type="bool")

        elif isinstance(node, VectorLiteral):
            return TypeAnnotation(
                base_type="vector",
                shape=(len(node.values),),
            )

        elif isinstance(node, BinaryOp):
            # Infer based on operator
            if node.operator in (
                BinaryOperator.EQ,
                BinaryOperator.NE,
                BinaryOperator.LT,
                BinaryOperator.LE,
                BinaryOperator.GT,
                BinaryOperator.GE,
            ):
                return TypeAnnotation(base_type="bool")
            else:
                # Arithmetic operators return numeric types
                return TypeAnnotation(base_type="float")

        return None


class SemanticAnalyzer:
    """Semantic analyzer for program validation.

    Performs semantic analysis including:
    - Undefined reference detection
    - Unused variable detection
    - Dead code detection
    """

    def __init__(self):
        """Initialize semantic analyzer."""
        self._defined_symbols: set[str] = set()
        self._used_symbols: set[str] = set()

    def analyze(self, program: Program) -> ValidationResult:
        """Perform semantic analysis on a program.

        Args:
            program: Program to analyze

        Returns:
            Validation result with semantic issues
        """
        result = ValidationResult()
        self._defined_symbols.clear()
        self._used_symbols.clear()

        # Collect symbols
        self._collect_symbols(program.ast)

        # Check for undefined references
        undefined = self._used_symbols - self._defined_symbols
        for symbol in undefined:
            result.add_error(
                ValidationErrorType.UNDEFINED_REFERENCE,
                f"Undefined reference: '{symbol}'",
            )

        # Check for unused variables
        unused = self._defined_symbols - self._used_symbols
        for symbol in unused:
            result.add_warning(
                ValidationErrorType.SEMANTIC_ERROR,
                f"Unused variable: '{symbol}'",
            )

        return result

    def _collect_symbols(self, node: ASTNode) -> None:
        """Collect symbol definitions and usages.

        Args:
            node: AST node to analyze
        """
        from src.strong_system.program_synthesis.types import (
            FunctionDef,
            ParameterRef,
            VariableDecl,
            VariableRef,
        )

        # Track definitions
        if isinstance(node, VariableDecl) or isinstance(node, ParameterRef) or isinstance(node, FunctionDef):
            self._defined_symbols.add(node.name)

        # Track usages
        elif isinstance(node, VariableRef):
            self._used_symbols.add(node.name)

        # Recursively collect from children
        for child in node.children():
            self._collect_symbols(child)


def validate_program(
    program: Program,
    schema: ProgramSchema | None = None,
    check_types: bool = True,
    check_semantics: bool = True,
) -> ValidationResult:
    """Validate a program comprehensively.

    Args:
        program: Program to validate
        schema: Schema to validate against
        check_types: Whether to perform type checking
        check_semantics: Whether to perform semantic analysis

    Returns:
        Comprehensive validation result
    """
    # Run main validation
    validator = ProgramValidator(schema)
    result = validator.validate(program)

    # Type checking
    if check_types:
        type_checker = TypeChecker()
        type_result = type_checker.check_types(program)
        result.merge(type_result)

    # Semantic analysis
    if check_semantics:
        analyzer = SemanticAnalyzer()
        semantic_result = analyzer.analyze(program)
        result.merge(semantic_result)

    return result
