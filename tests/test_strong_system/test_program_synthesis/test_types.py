"""Tests for program synthesis types module."""

import numpy as np
import pytest
from src.strong_system.program_synthesis.types import (
    ASTNodeType,
    BinaryOp,
    BinaryOperator,
    BooleanLiteral,
    FunctionDef,
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


class TestSourceLocation:
    """Test suite for SourceLocation class."""

    def test_default_creation(self):
        """Test creating source location with defaults."""
        loc = SourceLocation()
        assert loc.line == 0
        assert loc.column == 0
        assert loc.file == ""

    def test_custom_creation(self):
        """Test creating source location with custom values."""
        loc = SourceLocation(line=10, column=5, file="test.py")
        assert loc.line == 10
        assert loc.column == 5
        assert loc.file == "test.py"

    def test_negative_line_validation(self):
        """Test that negative line raises error."""
        with pytest.raises(ValueError, match="Line number must be non-negative"):
            SourceLocation(line=-1)

    def test_negative_column_validation(self):
        """Test that negative column raises error."""
        with pytest.raises(ValueError, match="Column number must be non-negative"):
            SourceLocation(column=-1)


class TestTypeAnnotation:
    """Test suite for TypeAnnotation class."""

    def test_default_creation(self):
        """Test creating type annotation with defaults."""
        type_ann = TypeAnnotation()
        assert type_ann.base_type == "any"
        assert type_ann.shape is None
        assert type_ann.parameters == []
        assert type_ann.nullable is False

    def test_custom_creation(self):
        """Test creating type annotation with custom values."""
        type_ann = TypeAnnotation(
            base_type="vector",
            shape=(3, 4),
            nullable=True,
        )
        assert type_ann.base_type == "vector"
        assert type_ann.shape == (3, 4)
        assert type_ann.nullable is True

    def test_to_string_simple(self):
        """Test string representation of simple type."""
        type_ann = TypeAnnotation(base_type="float")
        assert str(type_ann) == "float"

    def test_to_string_with_shape(self):
        """Test string representation with shape."""
        type_ann = TypeAnnotation(base_type="vector", shape=(3,))
        assert str(type_ann) == "vector[3]"

    def test_to_string_nullable(self):
        """Test string representation with nullable."""
        type_ann = TypeAnnotation(base_type="float", nullable=True)
        assert str(type_ann) == "float?"

    def test_base_type_normalization(self):
        """Test that base type is normalized to lowercase."""
        type_ann = TypeAnnotation(base_type="FLOAT")
        assert type_ann.base_type == "float"


class TestNumberLiteral:
    """Test suite for NumberLiteral class."""

    def test_default_creation(self):
        """Test creating number literal with defaults."""
        lit = NumberLiteral()
        assert lit.value == 0.0
        assert lit.node_type == ASTNodeType.NUMBER

    def test_custom_value(self):
        """Test creating number literal with custom value."""
        lit = NumberLiteral(value=42.5)
        assert lit.value == 42.5

    def test_integer_value(self):
        """Test that integer values are accepted."""
        lit = NumberLiteral(value=10)
        assert lit.value == 10.0


class TestStringLiteral:
    """Test suite for StringLiteral class."""

    def test_default_creation(self):
        """Test creating string literal with defaults."""
        lit = StringLiteral()
        assert lit.value == ""
        assert lit.node_type == ASTNodeType.STRING

    def test_custom_value(self):
        """Test creating string literal with custom value."""
        lit = StringLiteral(value="hello")
        assert lit.value == "hello"


class TestBooleanLiteral:
    """Test suite for BooleanLiteral class."""

    def test_default_creation(self):
        """Test creating boolean literal with defaults."""
        lit = BooleanLiteral()
        assert lit.value is False
        assert lit.node_type == ASTNodeType.BOOLEAN

    def test_true_value(self):
        """Test creating true boolean literal."""
        lit = BooleanLiteral(value=True)
        assert lit.value is True


class TestVectorLiteral:
    """Test suite for VectorLiteral class."""

    def test_default_creation(self):
        """Test creating vector literal with defaults."""
        lit = VectorLiteral()
        assert lit.values == []
        assert lit.dtype == "float64"
        assert lit.node_type == ASTNodeType.VECTOR

    def test_custom_values(self):
        """Test creating vector literal with custom values."""
        lit = VectorLiteral(values=[1.0, 2.0, 3.0])
        assert lit.values == [1.0, 2.0, 3.0]

    def test_to_numpy(self):
        """Test conversion to numpy array."""
        lit = VectorLiteral(values=[1.0, 2.0, 3.0])
        arr = lit.to_numpy()
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.float64
        np.testing.assert_array_equal(arr, [1.0, 2.0, 3.0])


class TestVariableRef:
    """Test suite for VariableRef class."""

    def test_creation(self):
        """Test creating variable reference."""
        var = VariableRef(name="x")
        assert var.name == "x"
        assert var.node_type == ASTNodeType.VARIABLE

    def test_empty_name_validation(self):
        """Test that empty name raises error."""
        with pytest.raises(ValueError, match="Variable name cannot be empty"):
            VariableRef(name="")


class TestParameterRef:
    """Test suite for ParameterRef class."""

    def test_creation(self):
        """Test creating parameter reference."""
        param = ParameterRef(name="x")
        assert param.name == "x"
        assert param.node_type == ASTNodeType.PARAMETER
        assert param.type_annotation is None

    def test_with_type_annotation(self):
        """Test creating parameter with type annotation."""
        type_ann = TypeAnnotation(base_type="float")
        param = ParameterRef(name="x", type_annotation=type_ann)
        assert param.type_annotation == type_ann

    def test_empty_name_validation(self):
        """Test that empty name raises error."""
        with pytest.raises(ValueError, match="Parameter name cannot be empty"):
            ParameterRef(name="")


class TestBinaryOp:
    """Test suite for BinaryOp class."""

    def test_default_creation(self):
        """Test creating binary operation with defaults."""
        op = BinaryOp()
        assert op.operator == BinaryOperator.ADD
        assert op.node_type == ASTNodeType.BINARY_OP

    def test_custom_operator(self):
        """Test creating binary operation with custom operator."""
        left = NumberLiteral(value=5.0)
        right = NumberLiteral(value=3.0)
        op = BinaryOp(operator=BinaryOperator.MUL, left=left, right=right)
        assert op.operator == BinaryOperator.MUL
        assert op.left == left
        assert op.right == right

    def test_children(self):
        """Test that children returns left and right."""
        left = NumberLiteral(value=5.0)
        right = NumberLiteral(value=3.0)
        op = BinaryOp(left=left, right=right)
        children = op.children()
        assert len(children) == 2
        assert left in children
        assert right in children


class TestUnaryOp:
    """Test suite for UnaryOp class."""

    def test_default_creation(self):
        """Test creating unary operation with defaults."""
        op = UnaryOp()
        assert op.operator == UnaryOperator.NEG
        assert op.node_type == ASTNodeType.UNARY_OP

    def test_custom_operator(self):
        """Test creating unary operation with custom operator."""
        operand = NumberLiteral(value=5.0)
        op = UnaryOp(operator=UnaryOperator.NOT, operand=operand)
        assert op.operator == UnaryOperator.NOT
        assert op.operand == operand

    def test_children(self):
        """Test that children returns operand."""
        operand = NumberLiteral(value=5.0)
        op = UnaryOp(operand=operand)
        children = op.children()
        assert len(children) == 1
        assert children[0] == operand


class TestSequence:
    """Test suite for Sequence class."""

    def test_default_creation(self):
        """Test creating sequence with defaults."""
        seq = Sequence()
        assert seq.statements == []
        assert seq.node_type == ASTNodeType.SEQUENCE

    def test_with_statements(self):
        """Test creating sequence with statements."""
        stmt1 = NumberLiteral(value=1.0)
        stmt2 = NumberLiteral(value=2.0)
        seq = Sequence(statements=[stmt1, stmt2])
        assert len(seq.statements) == 2
        assert stmt1 in seq.statements
        assert stmt2 in seq.statements

    def test_children(self):
        """Test that children returns statements."""
        stmt1 = NumberLiteral(value=1.0)
        stmt2 = NumberLiteral(value=2.0)
        seq = Sequence(statements=[stmt1, stmt2])
        children = seq.children()
        assert len(children) == 2
        assert stmt1 in children
        assert stmt2 in children


class TestFunctionDef:
    """Test suite for FunctionDef class."""

    def test_creation(self):
        """Test creating function definition."""
        func = FunctionDef(name="test_func")
        assert func.name == "test_func"
        assert func.parameters == []
        assert func.node_type == ASTNodeType.FUNCTION_DEF

    def test_with_parameters(self):
        """Test creating function with parameters."""
        param1 = ParameterRef(name="x")
        param2 = ParameterRef(name="y")
        func = FunctionDef(name="add", parameters=[param1, param2])
        assert len(func.parameters) == 2

    def test_empty_name_validation(self):
        """Test that empty function name raises error."""
        with pytest.raises(ValueError, match="Function name cannot be empty"):
            FunctionDef(name="")

    def test_children(self):
        """Test that children includes parameters and body."""
        param = ParameterRef(name="x")
        body = Sequence(statements=[NumberLiteral(value=1.0)])
        func = FunctionDef(name="test", parameters=[param], body=body)
        children = func.children()
        assert len(children) == 2
        assert param in children
        assert body in children


class TestVariableDecl:
    """Test suite for VariableDecl class."""

    def test_creation(self):
        """Test creating variable declaration."""
        decl = VariableDecl(name="x")
        assert decl.name == "x"
        assert decl.initializer is None
        assert decl.mutable is True
        assert decl.node_type == ASTNodeType.VARIABLE_DECL

    def test_with_initializer(self):
        """Test creating variable with initializer."""
        init = NumberLiteral(value=10.0)
        decl = VariableDecl(name="x", initializer=init)
        assert decl.initializer == init

    def test_empty_name_validation(self):
        """Test that empty variable name raises error."""
        with pytest.raises(ValueError, match="Variable name cannot be empty"):
            VariableDecl(name="")

    def test_children(self):
        """Test that children returns initializer if present."""
        init = NumberLiteral(value=10.0)
        decl = VariableDecl(name="x", initializer=init)
        children = decl.children()
        assert len(children) == 1
        assert children[0] == init

    def test_children_no_initializer(self):
        """Test that children returns empty list when no initializer."""
        decl = VariableDecl(name="x")
        children = decl.children()
        assert children == []


class TestProgram:
    """Test suite for Program class."""

    def test_creation(self):
        """Test creating program."""
        prog = Program(name="test_program")
        assert prog.name == "test_program"
        assert prog.program_type == ProgramType.FUNCTION
        assert isinstance(prog.ast, Sequence)

    def test_empty_name_validation(self):
        """Test that empty program name raises error."""
        with pytest.raises(ValueError, match="Program name cannot be empty"):
            Program(name="")

    def test_to_dict(self):
        """Test conversion to dictionary."""
        prog = Program(
            program_id="prog_123",
            name="test_program",
            description="A test program",
            program_type=ProgramType.STRATEGY,
            imports=["numpy"],
            metadata={"author": "test"},
        )
        data = prog.to_dict()
        assert data["program_id"] == "prog_123"
        assert data["name"] == "test_program"
        assert data["description"] == "A test program"
        assert data["program_type"] == "STRATEGY"
        assert data["imports"] == ["numpy"]
        assert data["metadata"] == {"author": "test"}


class TestProgramSchema:
    """Test suite for ProgramSchema class."""

    def test_default_creation(self):
        """Test creating schema with defaults."""
        schema = ProgramSchema(name="test")
        assert schema.name == "test"
        assert schema.version == "1.0.0"
        assert len(schema.allowed_node_types) == len(ASTNodeType)

    def test_allows_node_type(self):
        """Test checking if node type is allowed."""
        schema = ProgramSchema(
            name="test",
            allowed_node_types={ASTNodeType.NUMBER, ASTNodeType.STRING},
        )
        assert schema.allows_node_type(ASTNodeType.NUMBER) is True
        assert schema.allows_node_type(ASTNodeType.FUNCTION_DEF) is False

    def test_default_allowed_types(self):
        """Test that all types are allowed by default."""
        schema = ProgramSchema(name="test")
        for node_type in ASTNodeType:
            assert schema.allows_node_type(node_type) is True
