"""Type definitions for program synthesis module.

Provides dataclasses and type definitions for program AST nodes,
program types, and program representation classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np


class ProgramType(Enum):
    """Types of programs that can be synthesized."""

    FUNCTION = auto()
    STRATEGY = auto()
    RULE_SET = auto()
    PIPELINE = auto()
    TRANSFORM = auto()


class ASTNodeType(Enum):
    """Types of AST nodes in program representation."""

    # Literals
    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    NULL = auto()
    VECTOR = auto()

    # Variables
    VARIABLE = auto()
    PARAMETER = auto()

    # Expressions
    BINARY_OP = auto()
    UNARY_OP = auto()
    CALL = auto()
    INDEX = auto()
    ATTRIBUTE = auto()

    # Control flow
    CONDITIONAL = auto()
    LOOP = auto()
    SEQUENCE = auto()

    # Declarations
    FUNCTION_DEF = auto()
    VARIABLE_DECL = auto()

    # Special
    BELIEF_REF = auto()
    RULE_REF = auto()
    HYPOTHESIS_REF = auto()


class BinaryOperator(Enum):
    """Binary operators for expressions."""

    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    POW = "**"
    MOD = "%"
    EQ = "=="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    AND = "and"
    OR = "or"


class UnaryOperator(Enum):
    """Unary operators for expressions."""

    NEG = "-"
    NOT = "not"
    ABS = "abs"


@dataclass
class SourceLocation:
    """Source location information for AST nodes.

    Attributes:
        line: Line number (1-indexed)
        column: Column number (1-indexed)
        file: Source file path
    """

    line: int = 0
    column: int = 0
    file: str = ""

    def __post_init__(self):
        """Validate location fields."""
        if self.line < 0:
            raise ValueError(f"Line number must be non-negative, got {self.line}")
        if self.column < 0:
            raise ValueError(f"Column number must be non-negative, got {self.column}")


@dataclass
class TypeAnnotation:
    """Type annotation for program elements.

    Attributes:
        base_type: Base type name (e.g., "float", "vector", "function")
        shape: Shape for tensor types
        parameters: Type parameters for generic types
        nullable: Whether the type can be null
    """

    base_type: str = "any"
    shape: tuple[int, ...] | None = None
    parameters: list[TypeAnnotation] = field(default_factory=list)
    nullable: bool = False

    def __post_init__(self):
        """Normalize base type."""
        self.base_type = self.base_type.lower().strip()

    def __str__(self) -> str:
        """Convert to string representation."""
        result = self.base_type
        if self.parameters:
            params = ", ".join(str(p) for p in self.parameters)
            result += f"[{params}]"
        if self.shape:
            shape_str = ", ".join(str(d) for d in self.shape)
            result += f"[{shape_str}]"
        if self.nullable:
            result += "?"
        return result


@dataclass
class ASTNode:
    """Base class for all AST nodes.

    Attributes:
        node_type: Type of this AST node
        location: Source location information
        metadata: Additional node metadata
    """

    node_type: ASTNodeType = ASTNodeType.NULL
    location: SourceLocation = field(default_factory=SourceLocation)
    metadata: dict[str, Any] = field(default_factory=dict)

    def children(self) -> list[ASTNode]:
        """Return child nodes for tree traversal."""
        return []


# Literal nodes


@dataclass
class NumberLiteral(ASTNode):
    """Numeric literal node.

    Attributes:
        value: The numeric value
    """

    value: float = 0.0

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.NUMBER


@dataclass
class StringLiteral(ASTNode):
    """String literal node.

    Attributes:
        value: The string value
    """

    value: str = ""

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.STRING


@dataclass
class BooleanLiteral(ASTNode):
    """Boolean literal node.

    Attributes:
        value: The boolean value
    """

    value: bool = False

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.BOOLEAN


@dataclass
class NullLiteral(ASTNode):
    """Null literal node."""

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.NULL


@dataclass
class VectorLiteral(ASTNode):
    """Vector (numpy array) literal node.

    Attributes:
        values: The vector values
        dtype: Data type string
    """

    values: list[float] = field(default_factory=list)
    dtype: str = "float64"

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.VECTOR

    def to_numpy(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array(self.values, dtype=self.dtype)


# Variable nodes


@dataclass
class VariableRef(ASTNode):
    """Variable reference node.

    Attributes:
        name: Variable name
    """

    name: str = ""

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.VARIABLE
        if not self.name:
            raise ValueError("Variable name cannot be empty")


@dataclass
class ParameterRef(ASTNode):
    """Parameter reference node (for function parameters).

    Attributes:
        name: Parameter name
        type_annotation: Optional type annotation
        default_value: Optional default value
    """

    name: str = ""
    type_annotation: TypeAnnotation | None = None
    default_value: ASTNode | None = None

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.PARAMETER
        if not self.name:
            raise ValueError("Parameter name cannot be empty")


# Expression nodes


@dataclass
class BinaryOp(ASTNode):
    """Binary operation node.

    Attributes:
        operator: Binary operator
        left: Left operand
        right: Right operand
    """

    operator: BinaryOperator = BinaryOperator.ADD
    left: ASTNode = field(default_factory=lambda: NumberLiteral(0.0))
    right: ASTNode = field(default_factory=lambda: NumberLiteral(0.0))

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.BINARY_OP

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        return [self.left, self.right]


@dataclass
class UnaryOp(ASTNode):
    """Unary operation node.

    Attributes:
        operator: Unary operator
        operand: Operand expression
    """

    operator: UnaryOperator = UnaryOperator.NEG
    operand: ASTNode = field(default_factory=lambda: NumberLiteral(0.0))

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.UNARY_OP

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        return [self.operand]


@dataclass
class CallExpression(ASTNode):
    """Function call expression node.

    Attributes:
        callee: Function being called
        arguments: Call arguments
        keyword_args: Keyword arguments
    """

    callee: ASTNode = field(default_factory=lambda: VariableRef(""))
    arguments: list[ASTNode] = field(default_factory=list)
    keyword_args: dict[str, ASTNode] = field(default_factory=dict)

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.CALL

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        children = [self.callee] + self.arguments
        children.extend(self.keyword_args.values())
        return children


@dataclass
class IndexExpression(ASTNode):
    """Index/slice expression node.

    Attributes:
        target: Expression being indexed
        index: Index expression
    """

    target: ASTNode = field(default_factory=lambda: VariableRef(""))
    index: ASTNode = field(default_factory=lambda: NumberLiteral(0.0))

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.INDEX

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        return [self.target, self.index]


@dataclass
class AttributeExpression(ASTNode):
    """Attribute access expression node.

    Attributes:
        target: Expression being accessed
        attribute: Attribute name
    """

    target: ASTNode = field(default_factory=lambda: VariableRef(""))
    attribute: str = ""

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.ATTRIBUTE
        if not self.attribute:
            raise ValueError("Attribute name cannot be empty")

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        return [self.target]


# Control flow nodes


@dataclass
class Conditional(ASTNode):
    """Conditional (if-then-else) node.

    Attributes:
        condition: Condition expression
        then_branch: Then branch
        else_branch: Else branch (optional)
    """

    condition: ASTNode = field(default_factory=lambda: BooleanLiteral(True))
    then_branch: ASTNode = field(default_factory=lambda: Sequence([]))
    else_branch: ASTNode | None = None

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.CONDITIONAL

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        children = [self.condition, self.then_branch]
        if self.else_branch:
            children.append(self.else_branch)
        return children


@dataclass
class Loop(ASTNode):
    """Loop node (for or while style).

    Attributes:
        iterable: Iterable expression
        body: Loop body
        loop_variable: Loop variable name
    """

    iterable: ASTNode = field(default_factory=lambda: VectorLiteral([]))
    body: ASTNode = field(default_factory=lambda: Sequence([]))
    loop_variable: str = "i"

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.LOOP

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        return [self.iterable, self.body]


@dataclass
class Sequence(ASTNode):
    """Sequence of statements node.

    Attributes:
        statements: List of statements
    """

    statements: list[ASTNode] = field(default_factory=list)

    def __post_init__(self):
        """Set node type."""
        self.node_type = ASTNodeType.SEQUENCE

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        return list(self.statements)


# Declaration nodes


@dataclass
class FunctionDef(ASTNode):
    """Function definition node.

    Attributes:
        name: Function name
        parameters: Function parameters
        body: Function body
        return_type: Return type annotation
    """

    name: str = ""
    parameters: list[ParameterRef] = field(default_factory=list)
    body: ASTNode = field(default_factory=lambda: Sequence([]))
    return_type: TypeAnnotation | None = None

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.FUNCTION_DEF
        if not self.name:
            raise ValueError("Function name cannot be empty")

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        children: list[ASTNode] = list(self.parameters)
        children.append(self.body)
        return children


@dataclass
class VariableDecl(ASTNode):
    """Variable declaration node.

    Attributes:
        name: Variable name
        initializer: Initial value
        type_annotation: Type annotation
        mutable: Whether the variable is mutable
    """

    name: str = ""
    initializer: ASTNode | None = None
    type_annotation: TypeAnnotation | None = None
    mutable: bool = True

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.VARIABLE_DECL
        if not self.name:
            raise ValueError("Variable name cannot be empty")

    def children(self) -> list[ASTNode]:
        """Return child nodes."""
        if self.initializer:
            return [self.initializer]
        return []


# Special reference nodes for STRONG integration


@dataclass
class BeliefRef(ASTNode):
    """Reference to a belief from the belief system.

    Attributes:
        belief_id: Belief identifier
    """

    belief_id: str = ""

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.BELIEF_REF
        if not self.belief_id:
            raise ValueError("Belief ID cannot be empty")


@dataclass
class RuleRef(ASTNode):
    """Reference to a symbolic rule.

    Attributes:
        rule_name: Rule name
    """

    rule_name: str = ""

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.RULE_REF
        if not self.rule_name:
            raise ValueError("Rule name cannot be empty")


@dataclass
class HypothesisRef(ASTNode):
    """Reference to a hypothesis.

    Attributes:
        hypothesis_id: Hypothesis identifier
    """

    hypothesis_id: str = ""

    def __post_init__(self):
        """Set node type and validate."""
        self.node_type = ASTNodeType.HYPOTHESIS_REF
        if not self.hypothesis_id:
            raise ValueError("Hypothesis ID cannot be empty")


@dataclass
class Program:
    """A synthesized program.

    Attributes:
        program_id: Unique program identifier
        program_type: Type of program
        name: Program name
        description: Human-readable description
        ast: Root AST node
        imports: Required imports/modules
        metadata: Additional program metadata
    """

    program_id: str = ""
    program_type: ProgramType = ProgramType.FUNCTION
    name: str = ""
    description: str = ""
    ast: ASTNode = field(default_factory=lambda: Sequence([]))
    imports: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate program."""
        if not self.name:
            raise ValueError("Program name cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        """Convert program to dictionary."""
        return {
            "program_id": self.program_id,
            "program_type": self.program_type.name,
            "name": self.name,
            "description": self.description,
            "imports": self.imports,
            "metadata": self.metadata,
        }


@dataclass
class ProgramSchema:
    """Schema definition for program validation.

    Attributes:
        name: Schema name
        version: Schema version
        allowed_node_types: Allowed AST node types
        required_imports: Required imports
        constraints: Additional validation constraints
    """

    name: str = ""
    version: str = "1.0.0"
    allowed_node_types: set[ASTNodeType] = field(default_factory=set)
    required_imports: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Set default allowed types if not specified."""
        if not self.allowed_node_types:
            self.allowed_node_types = set(ASTNodeType)

    def allows_node_type(self, node_type: ASTNodeType) -> bool:
        """Check if a node type is allowed."""
        return node_type in self.allowed_node_types
