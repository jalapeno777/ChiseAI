"""Tests for program synthesis DSL module."""

import json

import pytest

from src.strong_system.program_synthesis.dsl import (
    DSLBuilder,
    ProgramDSL,
    ProgramDeserializer,
    ProgramSerializer,
    SchemaRegistry,
    create_default_schema,
    create_safe_schema,
    create_strategy_schema,
    schema_registry,
)
from src.strong_system.program_synthesis.types import (
    ASTNodeType,
    BinaryOp,
    BinaryOperator,
    CallExpression,
    Conditional,
    FunctionDef,
    NumberLiteral,
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
    VectorLiteral,
)


class TestDSLBuilder:
    """Test suite for DSLBuilder class."""

    def test_number(self):
        """Test creating number literal."""
        builder = DSLBuilder()
        lit = builder.number(42.0)
        assert isinstance(lit, NumberLiteral)
        assert lit.value == 42.0

    def test_string(self):
        """Test creating string literal."""
        builder = DSLBuilder()
        lit = builder.string("hello")
        assert isinstance(lit, StringLiteral)
        assert lit.value == "hello"

    def test_vector(self):
        """Test creating vector literal."""
        builder = DSLBuilder()
        lit = builder.vector([1.0, 2.0, 3.0])
        assert isinstance(lit, VectorLiteral)
        assert lit.values == [1.0, 2.0, 3.0]

    def test_var(self):
        """Test creating variable reference."""
        builder = DSLBuilder()
        var = builder.var("x")
        assert isinstance(var, VariableRef)
        assert var.name == "x"

    def test_add(self):
        """Test creating addition expression."""
        builder = DSLBuilder()
        left = builder.number(5.0)
        right = builder.number(3.0)
        expr = builder.add(left, right)
        assert isinstance(expr, BinaryOp)
        assert expr.operator == BinaryOperator.ADD
        assert expr.left == left
        assert expr.right == right

    def test_sub(self):
        """Test creating subtraction expression."""
        builder = DSLBuilder()
        left = builder.number(5.0)
        right = builder.number(3.0)
        expr = builder.sub(left, right)
        assert isinstance(expr, BinaryOp)
        assert expr.operator == BinaryOperator.SUB

    def test_mul(self):
        """Test creating multiplication expression."""
        builder = DSLBuilder()
        left = builder.number(5.0)
        right = builder.number(3.0)
        expr = builder.mul(left, right)
        assert isinstance(expr, BinaryOp)
        assert expr.operator == BinaryOperator.MUL

    def test_div(self):
        """Test creating division expression."""
        builder = DSLBuilder()
        left = builder.number(5.0)
        right = builder.number(3.0)
        expr = builder.div(left, right)
        assert isinstance(expr, BinaryOp)
        assert expr.operator == BinaryOperator.DIV

    def test_eq(self):
        """Test creating equality expression."""
        builder = DSLBuilder()
        left = builder.number(5.0)
        right = builder.number(3.0)
        expr = builder.eq(left, right)
        assert isinstance(expr, BinaryOp)
        assert expr.operator == BinaryOperator.EQ

    def test_lt(self):
        """Test creating less-than expression."""
        builder = DSLBuilder()
        left = builder.number(5.0)
        right = builder.number(3.0)
        expr = builder.lt(left, right)
        assert isinstance(expr, BinaryOp)
        assert expr.operator == BinaryOperator.LT

    def test_neg(self):
        """Test creating negation expression."""
        builder = DSLBuilder()
        operand = builder.number(5.0)
        expr = builder.neg(operand)
        assert isinstance(expr, UnaryOp)
        assert expr.operator == UnaryOperator.NEG
        assert expr.operand == operand

    def test_call_with_string(self):
        """Test creating function call with string callee."""
        builder = DSLBuilder()
        call = builder.call("print", [builder.string("hello")])
        assert isinstance(call, CallExpression)
        assert isinstance(call.callee, VariableRef)
        assert call.callee.name == "print"
        assert len(call.arguments) == 1

    def test_call_with_node(self):
        """Test creating function call with node callee."""
        builder = DSLBuilder()
        func_var = builder.var("my_func")
        call = builder.call(func_var)
        assert isinstance(call, CallExpression)
        assert call.callee == func_var

    def test_sequence(self):
        """Test creating sequence of statements."""
        builder = DSLBuilder()
        stmt1 = builder.number(1.0)
        stmt2 = builder.number(2.0)
        seq = builder.sequence([stmt1, stmt2])
        assert isinstance(seq, Sequence)
        assert len(seq.statements) == 2

    def test_param(self):
        """Test creating parameter reference."""
        builder = DSLBuilder()
        type_ann = TypeAnnotation(base_type="float")
        param = builder.param("x", type_annotation=type_ann)
        assert param.name == "x"
        assert param.type_annotation == type_ann


class TestProgramDSL:
    """Test suite for ProgramDSL class."""

    def test_creation(self):
        """Test creating DSL builder."""
        dsl = ProgramDSL("test_prog", ProgramType.FUNCTION)
        assert dsl.name == "test_prog"
        assert dsl.program_type == ProgramType.FUNCTION

    def test_with_description(self):
        """Test setting description."""
        dsl = ProgramDSL("test")
        result = dsl.with_description("A test program")
        assert result is dsl  # Returns self for chaining
        assert dsl.description == "A test program"

    def test_with_import(self):
        """Test adding import."""
        dsl = ProgramDSL("test")
        dsl.with_import("numpy")
        assert "numpy" in dsl.imports

    def test_duplicate_import_ignored(self):
        """Test that duplicate imports are ignored."""
        dsl = ProgramDSL("test")
        dsl.with_import("numpy")
        dsl.with_import("numpy")
        assert dsl.imports.count("numpy") == 1

    def test_with_metadata(self):
        """Test adding metadata."""
        dsl = ProgramDSL("test")
        dsl.with_metadata("author", "test_user")
        assert dsl.metadata["author"] == "test_user"

    def test_add_statement(self):
        """Test adding statement."""
        dsl = ProgramDSL("test")
        stmt = NumberLiteral(value=42.0)
        dsl.add_statement(stmt)
        assert stmt in dsl.statements

    def test_declare_variable(self):
        """Test declaring variable."""
        dsl = ProgramDSL("test")
        init = NumberLiteral(value=10.0)
        decl = dsl.declare_variable("x", initializer=init)
        assert isinstance(decl, VariableDecl)
        assert decl.name == "x"
        assert decl.initializer == init
        assert decl in dsl.statements

    def test_define_function(self):
        """Test defining function."""
        dsl = ProgramDSL("test")
        func = dsl.define_function("test_func")
        assert isinstance(func, FunctionDef)
        assert func.name == "test_func"
        assert func in dsl.statements

    def test_build(self):
        """Test building program."""
        dsl = ProgramDSL("test_prog", ProgramType.STRATEGY)
        dsl.with_description("A test")
        dsl.with_import("numpy")
        dsl.with_metadata("version", "1.0")
        dsl.add_statement(NumberLiteral(value=1.0))

        prog = dsl.build()
        assert isinstance(prog, Program)
        assert prog.name == "test_prog"
        assert prog.program_type == ProgramType.STRATEGY
        assert prog.description == "A test"
        assert "numpy" in prog.imports
        assert prog.metadata["version"] == "1.0"

    def test_chaining(self):
        """Test method chaining."""
        prog = (
            ProgramDSL("test", ProgramType.FUNCTION)
            .with_description("Chained")
            .with_import("numpy")
            .with_metadata("key", "value")
            .build()
        )
        assert prog.name == "test"
        assert prog.description == "Chained"


class TestSchemaRegistry:
    """Test suite for SchemaRegistry class."""

    def test_creation(self):
        """Test creating empty registry."""
        registry = SchemaRegistry()
        assert registry.list_schemas() == []

    def test_register(self):
        """Test registering schema."""
        registry = SchemaRegistry()
        schema = ProgramSchema(name="test")
        registry.register(schema)
        assert "test" in registry.list_schemas()

    def test_get(self):
        """Test getting registered schema."""
        registry = SchemaRegistry()
        schema = ProgramSchema(name="test")
        registry.register(schema)
        retrieved = registry.get("test")
        assert retrieved is schema

    def test_get_nonexistent(self):
        """Test getting non-existent schema returns None."""
        registry = SchemaRegistry()
        assert registry.get("nonexistent") is None

    def test_unregister(self):
        """Test unregistering schema."""
        registry = SchemaRegistry()
        schema = ProgramSchema(name="test")
        registry.register(schema)
        assert registry.unregister("test") is True
        assert "test" not in registry.list_schemas()

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent schema."""
        registry = SchemaRegistry()
        assert registry.unregister("nonexistent") is False


class TestCreateSchemas:
    """Test suite for schema factory functions."""

    def test_create_default_schema(self):
        """Test creating default schema."""
        schema = create_default_schema("default")
        assert schema.name == "default"
        assert schema.version == "1.0.0"
        # Should allow all node types
        assert len(schema.allowed_node_types) == len(ASTNodeType)

    def test_create_strategy_schema(self):
        """Test creating strategy schema."""
        schema = create_strategy_schema("strategy")
        assert schema.name == "strategy"
        # Should have restricted node types
        assert ASTNodeType.NUMBER in schema.allowed_node_types
        assert ASTNodeType.LOOP not in schema.allowed_node_types
        # Should require certain imports
        assert "numpy" in schema.required_imports

    def test_create_safe_schema(self):
        """Test creating safe schema."""
        schema = create_safe_schema("safe")
        assert schema.name == "safe"
        # Should have very restricted node types
        assert len(schema.allowed_node_types) < len(ASTNodeType)
        # Should not allow arbitrary calls
        assert schema.constraints.get("allow_arbitrary_calls") is False


class TestProgramSerializer:
    """Test suite for ProgramSerializer class."""

    def test_to_dict_simple(self):
        """Test serializing simple program to dict."""
        prog = Program(name="test", program_id="123")
        data = ProgramSerializer.to_dict(prog)
        assert data["name"] == "test"
        assert data["program_id"] == "123"
        assert data["program_type"] == "FUNCTION"

    def test_to_dict_with_ast(self):
        """Test serializing program with AST."""
        dsl = ProgramDSL("test")
        dsl.add_statement(NumberLiteral(value=42.0))
        prog = dsl.build()

        data = ProgramSerializer.to_dict(prog)
        assert "ast" in data
        assert data["ast"]["node_type"] == "SEQUENCE"

    def test_to_json(self):
        """Test serializing to JSON."""
        prog = Program(name="test")
        json_str = ProgramSerializer.to_json(prog)
        assert isinstance(json_str, str)
        # Should be valid JSON
        data = json.loads(json_str)
        assert data["name"] == "test"


class TestProgramDeserializer:
    """Test suite for ProgramDeserializer class."""

    def test_from_dict_simple(self):
        """Test deserializing simple program from dict."""
        data = {
            "program_id": "123",
            "name": "test",
            "program_type": "FUNCTION",
            "description": "A test",
            "imports": ["numpy"],
            "metadata": {"key": "value"},
            "ast": {"node_type": "SEQUENCE"},
        }
        prog = ProgramDeserializer.from_dict(data)
        assert isinstance(prog, Program)
        assert prog.program_id == "123"
        assert prog.name == "test"
        assert prog.description == "A test"

    def test_from_dict_number_literal(self):
        """Test deserializing number literal."""
        data = {
            "name": "test",
            "ast": {
                "node_type": "NUMBER",
                "value": 42.0,
            },
        }
        prog = ProgramDeserializer.from_dict(data)
        assert isinstance(prog.ast, NumberLiteral)
        assert prog.ast.value == 42.0

    def test_from_dict_binary_op(self):
        """Test deserializing binary operation."""
        data = {
            "name": "test",
            "ast": {
                "node_type": "BINARY_OP",
                "operator": "+",
                "left": {"node_type": "NUMBER", "value": 5.0},
                "right": {"node_type": "NUMBER", "value": 3.0},
            },
        }
        prog = ProgramDeserializer.from_dict(data)
        assert isinstance(prog.ast, BinaryOp)
        assert prog.ast.operator == BinaryOperator.ADD

    def test_from_json(self):
        """Test deserializing from JSON."""
        json_str = '{"name": "test", "program_type": "STRATEGY"}'
        prog = ProgramDeserializer.from_json(json_str)
        assert prog.name == "test"
        assert prog.program_type == ProgramType.STRATEGY


class TestGlobalSchemaRegistry:
    """Test suite for global schema_registry instance."""

    def test_has_default_schemas(self):
        """Test that global registry has default schemas."""
        assert "default" in schema_registry.list_schemas()
        assert "strategy" in schema_registry.list_schemas()
        assert "safe" in schema_registry.list_schemas()

    def test_can_get_default(self):
        """Test that default schema can be retrieved."""
        default = schema_registry.get("default")
        assert isinstance(default, ProgramSchema)
        assert default.name == "default"

    def test_can_get_strategy(self):
        """Test that strategy schema can be retrieved."""
        strategy = schema_registry.get("strategy")
        assert isinstance(strategy, ProgramSchema)
        assert strategy.name == "strategy"

    def test_can_get_safe(self):
        """Test that safe schema can be retrieved."""
        safe = schema_registry.get("safe")
        assert isinstance(safe, ProgramSchema)
        assert safe.name == "safe"
