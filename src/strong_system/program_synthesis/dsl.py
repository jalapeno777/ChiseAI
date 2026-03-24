"""Domain-Specific Language (DSL) for program synthesis.

Provides the DSL definition, program schema, type system, and
serialization/deserialization for program components.
"""

from __future__ import annotations

import json
from typing import Any

from src.strong_system.program_synthesis.types import (
    ASTNode,
    ASTNodeType,
    BinaryOp,
    BinaryOperator,
    BooleanLiteral,
    CallExpression,
    FunctionDef,
    NullLiteral,
    NumberLiteral,
    ParameterRef,
    Program,
    ProgramSchema,
    ProgramType,
    Sequence,
    SourceLocation,
    StringLiteral,
    TypeAnnotation,
    UnaryOp,
    UnaryOperator,
    VariableDecl,
    VariableRef,
    VectorLiteral,
)


class ProgramDSL:
    """Domain-Specific Language for program definition.

    Provides a fluent interface for constructing programs programmatically
    with type-safe operations and validation.
    """

    def __init__(self, name: str, program_type: ProgramType = ProgramType.FUNCTION):
        """Initialize a new DSL builder.

        Args:
            name: Program name
            program_type: Type of program being defined
        """
        self.name = name
        self.program_type = program_type
        self.description = ""
        self.imports: list[str] = []
        self.statements: list[ASTNode] = []
        self.metadata: dict[str, Any] = {}

    def with_description(self, description: str) -> ProgramDSL:
        """Set program description.

        Args:
            description: Human-readable description

        Returns:
            Self for method chaining
        """
        self.description = description
        return self

    def with_import(self, module: str) -> ProgramDSL:
        """Add an import.

        Args:
            module: Module to import

        Returns:
            Self for method chaining
        """
        if module not in self.imports:
            self.imports.append(module)
        return self

    def with_metadata(self, key: str, value: Any) -> ProgramDSL:
        """Add metadata.

        Args:
            key: Metadata key
            value: Metadata value

        Returns:
            Self for method chaining
        """
        self.metadata[key] = value
        return self

    def add_statement(self, statement: ASTNode) -> ProgramDSL:
        """Add a statement to the program.

        Args:
            statement: AST node to add

        Returns:
            Self for method chaining
        """
        self.statements.append(statement)
        return self

    def declare_variable(
        self,
        name: str,
        initializer: ASTNode | None = None,
        type_annotation: TypeAnnotation | None = None,
    ) -> VariableDecl:
        """Declare a variable.

        Args:
            name: Variable name
            initializer: Initial value
            type_annotation: Type annotation

        Returns:
            Variable declaration node
        """
        decl = VariableDecl(
            name=name,
            initializer=initializer,
            type_annotation=type_annotation,
        )
        self.statements.append(decl)
        return decl

    def define_function(
        self,
        name: str,
        parameters: list[ParameterRef] | None = None,
        body: Sequence | None = None,
        return_type: TypeAnnotation | None = None,
    ) -> FunctionDef:
        """Define a function.

        Args:
            name: Function name
            parameters: Function parameters
            body: Function body
            return_type: Return type annotation

        Returns:
            Function definition node
        """
        func = FunctionDef(
            name=name,
            parameters=parameters or [],
            body=body or Sequence([]),
            return_type=return_type,
        )
        self.statements.append(func)
        return func

    def build(self) -> Program:
        """Build the program.

        Returns:
            Compiled program
        """
        return Program(
            name=self.name,
            program_type=self.program_type,
            description=self.description,
            ast=Sequence(statements=self.statements),
            imports=self.imports,
            metadata=self.metadata,
        )


class DSLBuilder:
    """Builder for constructing AST nodes fluently."""

    @staticmethod
    def number(value: float) -> NumberLiteral:
        """Create a number literal.

        Args:
            value: Numeric value

        Returns:
            Number literal node
        """
        return NumberLiteral(value=value)

    @staticmethod
    def string(value: str) -> StringLiteral:
        """Create a string literal.

        Args:
            value: String value

        Returns:
            String literal node
        """
        return StringLiteral(value=value)

    @staticmethod
    def boolean(value: bool) -> BooleanLiteral:
        """Create a boolean literal.

        Args:
            value: Boolean value

        Returns:
            Boolean literal node
        """
        return BooleanLiteral(value=value)

    @staticmethod
    def null() -> NullLiteral:
        """Create a null literal.

        Returns:
            Null literal node
        """
        return NullLiteral()

    @staticmethod
    def vector(values: list[float]) -> VectorLiteral:
        """Create a vector literal.

        Args:
            values: Vector values

        Returns:
            Vector literal node
        """
        return VectorLiteral(values=values)

    @staticmethod
    def var(name: str) -> VariableRef:
        """Create a variable reference.

        Args:
            name: Variable name

        Returns:
            Variable reference node
        """
        return VariableRef(name=name)

    @staticmethod
    def param(
        name: str,
        type_annotation: TypeAnnotation | None = None,
        default_value: ASTNode | None = None,
    ) -> ParameterRef:
        """Create a parameter reference.

        Args:
            name: Parameter name
            type_annotation: Type annotation
            default_value: Default value

        Returns:
            Parameter reference node
        """
        return ParameterRef(
            name=name,
            type_annotation=type_annotation,
            default_value=default_value,
        )

    @staticmethod
    def add(left: ASTNode, right: ASTNode) -> BinaryOp:
        """Create addition expression.

        Args:
            left: Left operand
            right: Right operand

        Returns:
            Binary operation node
        """
        return BinaryOp(
            operator=BinaryOperator.ADD,
            left=left,
            right=right,
        )

    @staticmethod
    def sub(left: ASTNode, right: ASTNode) -> BinaryOp:
        """Create subtraction expression.

        Args:
            left: Left operand
            right: Right operand

        Returns:
            Binary operation node
        """
        return BinaryOp(
            operator=BinaryOperator.SUB,
            left=left,
            right=right,
        )

    @staticmethod
    def mul(left: ASTNode, right: ASTNode) -> BinaryOp:
        """Create multiplication expression.

        Args:
            left: Left operand
            right: Right operand

        Returns:
            Binary operation node
        """
        return BinaryOp(
            operator=BinaryOperator.MUL,
            left=left,
            right=right,
        )

    @staticmethod
    def div(left: ASTNode, right: ASTNode) -> BinaryOp:
        """Create division expression.

        Args:
            left: Left operand
            right: Right operand

        Returns:
            Binary operation node
        """
        return BinaryOp(
            operator=BinaryOperator.DIV,
            left=left,
            right=right,
        )

    @staticmethod
    def eq(left: ASTNode, right: ASTNode) -> BinaryOp:
        """Create equality comparison.

        Args:
            left: Left operand
            right: Right operand

        Returns:
            Binary operation node
        """
        return BinaryOp(
            operator=BinaryOperator.EQ,
            left=left,
            right=right,
        )

    @staticmethod
    def lt(left: ASTNode, right: ASTNode) -> BinaryOp:
        """Create less-than comparison.

        Args:
            left: Left operand
            right: Right operand

        Returns:
            Binary operation node
        """
        return BinaryOp(
            operator=BinaryOperator.LT,
            left=left,
            right=right,
        )

    @staticmethod
    def neg(operand: ASTNode) -> UnaryOp:
        """Create negation expression.

        Args:
            operand: Operand to negate

        Returns:
            Unary operation node
        """
        return UnaryOp(
            operator=UnaryOperator.NEG,
            operand=operand,
        )

    @staticmethod
    def call(
        callee: ASTNode | str,
        arguments: list[ASTNode] | None = None,
        keyword_args: dict[str, ASTNode] | None = None,
    ) -> CallExpression:
        """Create a function call.

        Args:
            callee: Function being called (AST node or name)
            arguments: Positional arguments
            keyword_args: Keyword arguments

        Returns:
            Call expression node
        """
        if isinstance(callee, str):
            callee = VariableRef(name=callee)
        return CallExpression(
            callee=callee,
            arguments=arguments or [],
            keyword_args=keyword_args or {},
        )

    @staticmethod
    def sequence(statements: list[ASTNode]) -> Sequence:
        """Create a sequence of statements.

        Args:
            statements: List of statements

        Returns:
            Sequence node
        """
        return Sequence(statements=statements)


class SchemaRegistry:
    """Registry for program schemas."""

    def __init__(self):
        """Initialize empty registry."""
        self._schemas: dict[str, ProgramSchema] = {}

    def register(self, schema: ProgramSchema) -> None:
        """Register a schema.

        Args:
            schema: Schema to register
        """
        self._schemas[schema.name] = schema

    def get(self, name: str) -> ProgramSchema | None:
        """Get a schema by name.

        Args:
            name: Schema name

        Returns:
            Schema if found, None otherwise
        """
        return self._schemas.get(name)

    def list_schemas(self) -> list[str]:
        """List all registered schema names.

        Returns:
            List of schema names
        """
        return list(self._schemas.keys())

    def unregister(self, name: str) -> bool:
        """Unregister a schema.

        Args:
            name: Schema name

        Returns:
            True if schema was removed, False if not found
        """
        if name in self._schemas:
            del self._schemas[name]
            return True
        return False


def create_default_schema(name: str = "default") -> ProgramSchema:
    """Create the default program schema.

    Args:
        name: Schema name

    Returns:
        Default program schema
    """
    # Allow all node types except potentially dangerous ones
    allowed_types = set(ASTNodeType)

    return ProgramSchema(
        name=name,
        version="1.0.0",
        allowed_node_types=allowed_types,
        required_imports=[],
        constraints={
            "max_nesting_depth": 100,
            "max_statements": 10000,
            "max_parameters": 100,
        },
    )


def create_strategy_schema(name: str = "strategy") -> ProgramSchema:
    """Create a schema for trading strategies.

    Args:
        name: Schema name

    Returns:
        Strategy program schema
    """
    allowed_types = {
        ASTNodeType.NUMBER,
        ASTNodeType.STRING,
        ASTNodeType.BOOLEAN,
        ASTNodeType.VECTOR,
        ASTNodeType.VARIABLE,
        ASTNodeType.PARAMETER,
        ASTNodeType.BINARY_OP,
        ASTNodeType.UNARY_OP,
        ASTNodeType.CALL,
        ASTNodeType.INDEX,
        ASTNodeType.ATTRIBUTE,
        ASTNodeType.CONDITIONAL,
        ASTNodeType.SEQUENCE,
        ASTNodeType.FUNCTION_DEF,
        ASTNodeType.VARIABLE_DECL,
        ASTNodeType.BELIEF_REF,
        ASTNodeType.RULE_REF,
    }

    return ProgramSchema(
        name=name,
        version="1.0.0",
        allowed_node_types=allowed_types,
        required_imports=["numpy", "src.strong_system"],
        constraints={
            "max_nesting_depth": 50,
            "max_statements": 1000,
            "max_parameters": 20,
            "require_type_annotations": True,
        },
    )


def create_safe_schema(name: str = "safe") -> ProgramSchema:
    """Create a restricted safe schema.

    Args:
        name: Schema name

    Returns:
        Safe program schema with minimal allowed operations
    """
    allowed_types = {
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

    return ProgramSchema(
        name=name,
        version="1.0.0",
        allowed_node_types=allowed_types,
        required_imports=[],
        constraints={
            "max_nesting_depth": 20,
            "max_statements": 100,
            "max_parameters": 10,
            "allow_arbitrary_calls": False,
            "allowed_calls": ["len", "range", "enumerate", "zip"],
        },
    )


class ProgramSerializer:
    """Serializer for programs to various formats."""

    @staticmethod
    def to_dict(program: Program) -> dict[str, Any]:
        """Serialize program to dictionary.

        Args:
            program: Program to serialize

        Returns:
            Dictionary representation
        """
        return {
            "program_id": program.program_id,
            "program_type": program.program_type.name,
            "name": program.name,
            "description": program.description,
            "imports": program.imports,
            "metadata": program.metadata,
            "ast": ProgramSerializer._ast_to_dict(program.ast),
        }

    @staticmethod
    def _ast_to_dict(node: ASTNode) -> dict[str, Any]:
        """Convert AST node to dictionary.

        Args:
            node: AST node

        Returns:
            Dictionary representation
        """
        result: dict[str, Any] = {
            "node_type": node.node_type.name,
        }

        if node.location.line > 0:
            result["location"] = {
                "line": node.location.line,
                "column": node.location.column,
                "file": node.location.file,
            }

        # Add type-specific fields
        if isinstance(node, NumberLiteral) or isinstance(node, StringLiteral) or isinstance(node, BooleanLiteral):
            result["value"] = node.value
        elif isinstance(node, VectorLiteral):
            result["values"] = node.values
            result["dtype"] = node.dtype
        elif isinstance(node, VariableRef):
            result["name"] = node.name
        elif isinstance(node, ParameterRef):
            result["name"] = node.name
            if node.type_annotation:
                result["type_annotation"] = str(node.type_annotation)
        elif isinstance(node, BinaryOp):
            result["operator"] = node.operator.value
            result["left"] = ProgramSerializer._ast_to_dict(node.left)
            result["right"] = ProgramSerializer._ast_to_dict(node.right)
        elif isinstance(node, UnaryOp):
            result["operator"] = node.operator.value
            result["operand"] = ProgramSerializer._ast_to_dict(node.operand)
        elif isinstance(node, CallExpression):
            result["callee"] = ProgramSerializer._ast_to_dict(node.callee)
            result["arguments"] = [
                ProgramSerializer._ast_to_dict(arg) for arg in node.arguments
            ]
            result["keyword_args"] = {
                k: ProgramSerializer._ast_to_dict(v)
                for k, v in node.keyword_args.items()
            }
        elif isinstance(node, Sequence):
            result["statements"] = [
                ProgramSerializer._ast_to_dict(stmt) for stmt in node.statements
            ]
        elif isinstance(node, FunctionDef):
            result["name"] = node.name
            result["parameters"] = [
                ProgramSerializer._ast_to_dict(p) for p in node.parameters
            ]
            result["body"] = ProgramSerializer._ast_to_dict(node.body)
        elif isinstance(node, VariableDecl):
            result["name"] = node.name
            if node.initializer:
                result["initializer"] = ProgramSerializer._ast_to_dict(node.initializer)
            result["mutable"] = node.mutable

        return result

    @staticmethod
    def to_json(program: Program, indent: int | None = 2) -> str:
        """Serialize program to JSON.

        Args:
            program: Program to serialize
            indent: Indentation level (None for compact)

        Returns:
            JSON string
        """
        return json.dumps(ProgramSerializer.to_dict(program), indent=indent)


class ProgramDeserializer:
    """Deserializer for programs from various formats."""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Program:
        """Deserialize program from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            Deserialized program
        """
        ast_data = data.get("ast", {})
        ast = ProgramDeserializer._ast_from_dict(ast_data)

        return Program(
            program_id=data.get("program_id", ""),
            program_type=ProgramType[data.get("program_type", "FUNCTION")],
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            ast=ast,
            imports=data.get("imports", []),
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def _ast_from_dict(data: dict[str, Any]) -> ASTNode:
        """Convert dictionary to AST node.

        Args:
            data: Dictionary representation

        Returns:
            AST node
        """
        node_type = ASTNodeType[data.get("node_type", "SEQUENCE")]

        # Extract location if present
        location = SourceLocation()
        if "location" in data:
            loc = data["location"]
            location = SourceLocation(
                line=loc.get("line", 0),
                column=loc.get("column", 0),
                file=loc.get("file", ""),
            )

        # Create appropriate node type
        if node_type == ASTNodeType.NUMBER:
            return NumberLiteral(
                value=data.get("value", 0.0),
                location=location,
            )
        elif node_type == ASTNodeType.STRING:
            return StringLiteral(
                value=data.get("value", ""),
                location=location,
            )
        elif node_type == ASTNodeType.BOOLEAN:
            return BooleanLiteral(
                value=data.get("value", False),
                location=location,
            )
        elif node_type == ASTNodeType.VECTOR:
            return VectorLiteral(
                values=data.get("values", []),
                dtype=data.get("dtype", "float64"),
                location=location,
            )
        elif node_type == ASTNodeType.VARIABLE:
            return VariableRef(
                name=data.get("name", ""),
                location=location,
            )
        elif node_type == ASTNodeType.BINARY_OP:
            return BinaryOp(
                operator=BinaryOperator(data.get("operator", "+")),
                left=ProgramDeserializer._ast_from_dict(data.get("left", {})),
                right=ProgramDeserializer._ast_from_dict(data.get("right", {})),
                location=location,
            )
        elif node_type == ASTNodeType.UNARY_OP:
            return UnaryOp(
                operator=UnaryOperator(data.get("operator", "-")),
                operand=ProgramDeserializer._ast_from_dict(data.get("operand", {})),
                location=location,
            )
        elif node_type == ASTNodeType.CALL:
            return CallExpression(
                callee=ProgramDeserializer._ast_from_dict(data.get("callee", {})),
                arguments=[
                    ProgramDeserializer._ast_from_dict(arg)
                    for arg in data.get("arguments", [])
                ],
                keyword_args={
                    k: ProgramDeserializer._ast_from_dict(v)
                    for k, v in data.get("keyword_args", {}).items()
                },
                location=location,
            )
        elif node_type == ASTNodeType.SEQUENCE:
            return Sequence(
                statements=[
                    ProgramDeserializer._ast_from_dict(stmt)
                    for stmt in data.get("statements", [])
                ],
                location=location,
            )
        elif node_type == ASTNodeType.FUNCTION_DEF:
            return FunctionDef(
                name=data.get("name", ""),
                parameters=[
                    ProgramDeserializer._ast_from_dict(p)
                    for p in data.get("parameters", [])
                ],
                body=ProgramDeserializer._ast_from_dict(data.get("body", {})),
                location=location,
            )
        elif node_type == ASTNodeType.VARIABLE_DECL:
            initializer = data.get("initializer")
            return VariableDecl(
                name=data.get("name", ""),
                initializer=ProgramDeserializer._ast_from_dict(initializer)
                if initializer
                else None,
                mutable=data.get("mutable", True),
                location=location,
            )
        else:
            # Default to sequence
            return Sequence(location=location)

    @staticmethod
    def from_json(json_str: str) -> Program:
        """Deserialize program from JSON.

        Args:
            json_str: JSON string

        Returns:
            Deserialized program
        """
        data = json.loads(json_str)
        return ProgramDeserializer.from_dict(data)


# Global schema registry instance
schema_registry = SchemaRegistry()

# Register default schemas
schema_registry.register(create_default_schema("default"))
schema_registry.register(create_strategy_schema("strategy"))
schema_registry.register(create_safe_schema("safe"))
