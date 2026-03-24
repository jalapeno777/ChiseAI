"""Tests for program synthesis validator module."""

import pytest
from src.strong_system.program_synthesis.dsl import (
    ProgramDSL,
    create_default_schema,
    create_safe_schema,
)
from src.strong_system.program_synthesis.types import (
    BinaryOp,
    BinaryOperator,
    CallExpression,
    FunctionDef,
    NumberLiteral,
    ParameterRef,
    Program,
    ProgramSchema,
    Sequence,
    StringLiteral,
    VariableDecl,
    VariableRef,
)
from src.strong_system.program_synthesis.validator import (
    ProgramValidator,
    SemanticAnalyzer,
    TypeChecker,
    ValidationError,
    ValidationErrorType,
    ValidationResult,
    validate_program,
)


class TestValidationError:
    """Test suite for ValidationError class."""

    def test_creation(self):
        """Test creating validation error."""
        error = ValidationError(
            error_type=ValidationErrorType.SYNTAX_ERROR,
            message="Test error",
        )
        assert error.error_type == ValidationErrorType.SYNTAX_ERROR
        assert error.message == "Test error"
        assert error.severity == "error"

    def test_with_location(self):
        """Test error with location."""
        error = ValidationError(
            error_type=ValidationErrorType.TYPE_ERROR,
            message="Type mismatch",
            line=10,
            column=5,
        )
        assert error.line == 10
        assert error.column == 5

    def test_string_representation(self):
        """Test string representation of error."""
        error = ValidationError(
            error_type=ValidationErrorType.SYNTAX_ERROR,
            message="Missing semicolon",
            line=5,
        )
        str_repr = str(error)
        assert "SYNTAX_ERROR" in str_repr
        assert "Missing semicolon" in str_repr
        assert "line 5" in str_repr


class TestValidationResult:
    """Test suite for ValidationResult class."""

    def test_default_creation(self):
        """Test creating validation result with defaults."""
        result = ValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_error(self):
        """Test adding error to result."""
        result = ValidationResult()
        result.add_error(
            ValidationErrorType.SYNTAX_ERROR,
            "Test error",
        )
        assert result.valid is False
        assert len(result.errors) == 1

    def test_add_warning(self):
        """Test adding warning to result."""
        result = ValidationResult()
        result.add_warning(
            ValidationErrorType.SEMANTIC_ERROR,
            "Test warning",
        )
        # Result should still be valid with warnings only
        assert result.valid is True
        assert len(result.warnings) == 1

    def test_add_error_with_node(self):
        """Test adding error with associated node."""
        result = ValidationResult()
        node = NumberLiteral(value=42.0)
        result.add_error(
            ValidationErrorType.TYPE_ERROR,
            "Invalid type",
            node=node,
        )
        assert len(result.errors) == 1
        assert result.errors[0].node == node

    def test_merge(self):
        """Test merging two validation results."""
        result1 = ValidationResult()
        result1.add_error(ValidationErrorType.SYNTAX_ERROR, "Error 1")

        result2 = ValidationResult()
        result2.add_warning(ValidationErrorType.SEMANTIC_ERROR, "Warning 1")

        result1.merge(result2)
        assert len(result1.errors) == 1
        assert len(result1.warnings) == 1

    def test_merge_makes_invalid(self):
        """Test that merging invalid result makes result invalid."""
        result1 = ValidationResult()  # Valid
        result2 = ValidationResult()
        result2.add_error(ValidationErrorType.SYNTAX_ERROR, "Error")

        result1.merge(result2)
        assert result1.valid is False

    def test_string_representation(self):
        """Test string representation of result."""
        result = ValidationResult()
        result.add_error(ValidationErrorType.SYNTAX_ERROR, "Error")
        result.add_warning(ValidationErrorType.SEMANTIC_ERROR, "Warning")

        str_repr = str(result)
        assert "INVALID" in str_repr
        assert "Errors: 1" in str_repr
        assert "Warnings: 1" in str_repr


class TestProgramValidator:
    """Test suite for ProgramValidator class."""

    def test_creation_with_default_schema(self):
        """Test creating validator with default schema."""
        validator = ProgramValidator()
        assert validator.schema is not None

    def test_creation_with_custom_schema(self):
        """Test creating validator with custom schema."""
        schema = create_safe_schema()
        validator = ProgramValidator(schema)
        assert validator.schema == schema

    def test_validate_valid_program(self):
        """Test validating a valid program."""
        prog = Program(name="test_prog")
        validator = ProgramValidator()
        result = validator.validate(prog)
        assert result.valid is True

    def test_validate_empty_name(self):
        """Test validating program with empty name raises ValueError."""
        with pytest.raises(ValueError, match="Program name cannot be empty"):
            Program(name="")

    def test_validate_missing_import(self):
        """Test validating program missing required import."""
        schema = ProgramSchema(
            name="test",
            required_imports=["numpy"],
        )
        prog = Program(name="test", imports=[])
        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False
        assert any(
            e.error_type == ValidationErrorType.SCHEMA_VIOLATION for e in result.errors
        )

    def test_validate_unsupported_node(self):
        """Test validating program with unsupported node type."""
        schema = create_safe_schema()
        # Safe schema doesn't allow LOOP nodes
        from src.strong_system.program_synthesis.types import Loop

        loop = Loop()
        prog = Program(name="test", ast=Sequence(statements=[loop]))

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False
        assert any(
            e.error_type == ValidationErrorType.UNSUPPORTED_NODE for e in result.errors
        )

    def test_validate_nesting_depth(self):
        """Test validating deeply nested program."""
        schema = create_default_schema()
        schema.constraints["max_nesting_depth"] = 2

        # Create a deeply nested structure
        inner = BinaryOp(
            left=NumberLiteral(1.0),
            right=NumberLiteral(2.0),
        )
        middle = BinaryOp(left=inner, right=NumberLiteral(3.0))
        outer = BinaryOp(left=middle, right=NumberLiteral(4.0))

        prog = Program(name="test", ast=outer)
        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False
        assert any(
            e.error_type == ValidationErrorType.RECURSION_LIMIT for e in result.errors
        )

    def test_validate_function_params(self):
        """Test validating function with too many parameters."""
        schema = create_default_schema()
        schema.constraints["max_parameters"] = 2

        params = [ParameterRef(name=f"p{i}") for i in range(5)]
        func = FunctionDef(name="test_func", parameters=params)
        prog = Program(name="test", ast=Sequence(statements=[func]))

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False
        assert any(
            e.message.startswith("Function has 5 parameters") for e in result.errors
        )

    def test_validate_invalid_variable_name(self):
        """Test validating variable with invalid name."""
        decl = VariableDecl(name="123invalid")  # Invalid identifier
        prog = Program(name="test", ast=Sequence(statements=[decl]))
        validator = ProgramValidator()
        result = validator.validate(prog)
        assert result.valid is False

    def test_validate_arbitrary_call_not_allowed(self):
        """Test validating call when arbitrary calls not allowed."""
        schema = create_safe_schema()
        call = CallExpression(callee=VariableRef(name="dangerous_func"))
        prog = Program(name="test", ast=Sequence(statements=[call]))

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False


class TestTypeChecker:
    """Test suite for TypeChecker class."""

    def test_creation(self):
        """Test creating type checker."""
        checker = TypeChecker()
        assert checker._type_env == {}

    def test_infer_number_type(self):
        """Test inferring type of number literal."""
        checker = TypeChecker()
        node = NumberLiteral(value=42.0)
        type_ann = checker.infer_type(node)
        assert type_ann is not None
        assert type_ann.base_type == "float"

    def test_infer_string_type(self):
        """Test inferring type of string literal."""
        checker = TypeChecker()
        node = StringLiteral(value="hello")
        type_ann = checker.infer_type(node)
        assert type_ann is not None
        assert type_ann.base_type == "str"

    def test_infer_boolean_type(self):
        """Test inferring type of boolean literal."""
        checker = TypeChecker()
        from src.strong_system.program_synthesis.types import BooleanLiteral

        node = BooleanLiteral(value=True)
        type_ann = checker.infer_type(node)
        assert type_ann is not None
        assert type_ann.base_type == "bool"

    def test_infer_vector_type(self):
        """Test inferring type of vector literal."""
        checker = TypeChecker()
        from src.strong_system.program_synthesis.types import VectorLiteral

        node = VectorLiteral(values=[1.0, 2.0, 3.0])
        type_ann = checker.infer_type(node)
        assert type_ann is not None
        assert type_ann.base_type == "vector"
        assert type_ann.shape == (3,)

    def test_infer_comparison_type(self):
        """Test inferring type of comparison expression."""
        checker = TypeChecker()
        left = NumberLiteral(value=5.0)
        right = NumberLiteral(value=3.0)
        comp = BinaryOp(operator=BinaryOperator.LT, left=left, right=right)
        type_ann = checker.infer_type(comp)
        assert type_ann is not None
        assert type_ann.base_type == "bool"

    def test_infer_arithmetic_type(self):
        """Test inferring type of arithmetic expression."""
        checker = TypeChecker()
        left = NumberLiteral(value=5.0)
        right = NumberLiteral(value=3.0)
        expr = BinaryOp(operator=BinaryOperator.ADD, left=left, right=right)
        type_ann = checker.infer_type(expr)
        assert type_ann is not None
        assert type_ann.base_type == "float"


class TestSemanticAnalyzer:
    """Test suite for SemanticAnalyzer class."""

    def test_creation(self):
        """Test creating semantic analyzer."""
        analyzer = SemanticAnalyzer()
        assert analyzer._defined_symbols == set()
        assert analyzer._used_symbols == set()

    def test_detect_undefined_reference(self):
        """Test detecting undefined variable reference."""
        # Use variable x without declaring it
        var_ref = VariableRef(name="x")
        prog = Program(name="test", ast=Sequence(statements=[var_ref]))

        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(prog)
        assert result.valid is False
        assert any(
            e.error_type == ValidationErrorType.UNDEFINED_REFERENCE
            for e in result.errors
        )

    def test_no_error_for_defined_variable(self):
        """Test no error when variable is defined."""
        decl = VariableDecl(name="x", initializer=NumberLiteral(10.0))
        var_ref = VariableRef(name="x")
        prog = Program(name="test", ast=Sequence(statements=[decl, var_ref]))

        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(prog)
        assert result.valid is True

    def test_detect_unused_variable(self):
        """Test detecting unused variable."""
        decl = VariableDecl(name="x", initializer=NumberLiteral(10.0))
        # x is declared but never used
        prog = Program(name="test", ast=Sequence(statements=[decl]))

        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(prog)
        # Should have a warning but still be valid
        assert result.valid is True
        assert any(
            e.error_type == ValidationErrorType.SEMANTIC_ERROR and "Unused" in e.message
            for e in result.warnings
        )


class TestValidateProgram:
    """Test suite for validate_program function."""

    def test_validate_simple_program(self):
        """Test validating simple program."""
        prog = Program(name="test")
        result = validate_program(prog)
        assert result.valid is True

    def test_validate_with_type_checking_disabled(self):
        """Test validating with type checking disabled."""
        prog = Program(name="test")
        result = validate_program(prog, check_types=False)
        assert result.valid is True

    def test_validate_with_semantics_disabled(self):
        """Test validating with semantics disabled."""
        prog = Program(name="test")
        result = validate_program(prog, check_semantics=False)
        assert result.valid is True

    def test_validate_comprehensive(self):
        """Test comprehensive validation."""
        dsl = ProgramDSL("comprehensive_test")
        dsl.declare_variable("x", NumberLiteral(10.0))
        dsl.declare_variable("y", NumberLiteral(20.0))
        # Use x and y
        dsl.add_statement(
            BinaryOp(
                operator=BinaryOperator.ADD,
                left=VariableRef(name="x"),
                right=VariableRef(name="y"),
            )
        )
        prog = dsl.build()

        result = validate_program(prog)
        assert result.valid is True
