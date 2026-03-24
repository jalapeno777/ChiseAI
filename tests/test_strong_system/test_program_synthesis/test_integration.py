"""Integration tests for program synthesis module."""

from src.strong_system.program_synthesis import (
    DSLBuilder,
    ProgramDSL,
    ProgramValidator,
    TypeChecker,
    validate_program,
)
from src.strong_system.program_synthesis.dsl import (
    create_default_schema,
    create_safe_schema,
    create_strategy_schema,
)
from src.strong_system.program_synthesis.generator import (
    GenerationConfig,
    GenerationConstraints,
    GenerationContext,
    GenerationStrategy,
    HybridGenerator,
    SearchBasedGenerator,
    TemplateBasedGenerator,
    create_generator,
    generate_program,
)
from src.strong_system.program_synthesis.types import (
    NumberLiteral,
    Program,
    ProgramType,
    Sequence,
    TypeAnnotation,
    VariableRef,
)
from src.strong_system.program_synthesis.validator import (
    SemanticAnalyzer,
    ValidationErrorType,
)


class TestEndToEndProgramGeneration:
    """End-to-end tests for program generation and validation."""

    def test_generate_and_validate_simple_program(self):
        """Test generating and validating a simple program."""
        # Generate program
        prog = generate_program("simple arithmetic expression")
        assert prog is not None

        # Validate program
        result = validate_program(prog)
        assert result.valid is True, f"Validation failed: {result.errors}"

    def test_generate_with_different_strategies(self):
        """Test generating with different strategies."""
        strategies = [
            GenerationStrategy.TEMPLATE,
            GenerationStrategy.SEARCH,
            GenerationStrategy.GRAMMAR,
        ]

        for strategy in strategies:
            prog = generate_program(
                "Test program",
                strategy=strategy,
            )
            if prog is not None:
                result = validate_program(prog)
                assert (
                    result.valid is True
                ), f"Strategy {strategy.name} produced invalid program"

    def test_full_dsl_to_validation_pipeline(self):
        """Test full pipeline from DSL construction to validation."""
        # Build program using DSL
        dsl = ProgramDSL("integration_test", ProgramType.FUNCTION)
        dsl.with_description("Integration test program")
        dsl.with_import("numpy")

        builder = DSLBuilder()
        dsl.declare_variable("a", builder.number(10.0))
        dsl.declare_variable("b", builder.number(20.0))

        # Add arithmetic expression
        expr = builder.add(builder.var("a"), builder.var("b"))
        dsl.add_statement(expr)

        prog = dsl.build()

        # Validate
        result = validate_program(prog)
        assert result.valid is True
        assert prog.name == "integration_test"
        assert "numpy" in prog.imports

    def test_function_definition_pipeline(self):
        """Test defining and validating a function."""
        dsl = ProgramDSL("math_functions", ProgramType.FUNCTION)

        builder = DSLBuilder()
        params = [
            builder.param("x", TypeAnnotation(base_type="float")),
            builder.param("y", TypeAnnotation(base_type="float")),
        ]

        body = builder.sequence(
            [
                builder.mul(builder.var("x"), builder.var("y")),
            ]
        )

        dsl.define_function(
            "multiply",
            parameters=params,
            body=body,
            return_type=TypeAnnotation(base_type="float"),
        )

        prog = dsl.build()
        result = validate_program(prog)
        assert result.valid is True


class TestSchemaIntegration:
    """Integration tests for schemas and validation."""

    def test_default_schema_validation(self):
        """Test validation with default schema."""
        schema = create_default_schema()
        prog = Program(name="test", ast=Sequence(statements=[NumberLiteral(1.0)]))

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is True

    def test_safe_schema_restrictions(self):
        """Test that safe schema enforces restrictions."""
        schema = create_safe_schema()

        # Try to create a program with a forbidden call
        from src.strong_system.program_synthesis.types import CallExpression

        call = CallExpression(callee=VariableRef(name="exec"))
        prog = Program(name="test", ast=Sequence(statements=[call]))

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False

    def test_strategy_schema_with_belief_refs(self):
        """Test that strategy schema allows belief references."""
        from src.strong_system.program_synthesis.types import BeliefRef

        schema = create_strategy_schema()
        belief_ref = BeliefRef(belief_id="belief_123")
        prog = Program(
            name="test",
            ast=Sequence(statements=[belief_ref]),
            imports=["numpy", "src.strong_system"],  # Required by strategy schema
        )

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is True


class TestGeneratorIntegration:
    """Integration tests for generator components."""

    def test_template_generator_integration(self):
        """Test template generator with validation."""
        config = GenerationConfig(strategy=GenerationStrategy.TEMPLATE)
        generator = TemplateBasedGenerator(config)

        context = GenerationContext(
            description="Generate a simple calculation",
            target_type=ProgramType.FUNCTION,
        )

        prog = generator.generate(context)
        assert prog is not None

        # Validate the generated program
        result = generator.validate_generation(prog)
        assert result.valid is True

    def test_search_generator_with_constraints(self):
        """Test search generator respects constraints."""
        constraints = GenerationConstraints(
            max_depth=3,
            max_nodes=20,
        )
        config = GenerationConfig(
            strategy=GenerationStrategy.SEARCH,
            constraints=constraints,
        )
        generator = SearchBasedGenerator(config)

        context = GenerationContext(target_type=ProgramType.FUNCTION)
        prog = generator.generate(context)

        if prog is not None:
            # Program should be within constraints
            result = generator.validate_generation(prog)
            assert result.valid is True

    def test_hybrid_generator_selects_best(self):
        """Test that hybrid generator can produce valid programs."""
        config = GenerationConfig(strategy=GenerationStrategy.HYBRID)
        generator = HybridGenerator(config)

        context = GenerationContext(target_type=ProgramType.FUNCTION)
        prog = generator.generate(context)

        if prog is not None:
            result = generator.validate_generation(prog)
            assert result.valid is True


class TestTypeSystemIntegration:
    """Integration tests for type system."""

    def test_type_inference_on_generated_program(self):
        """Test type inference on generated program."""
        builder = DSLBuilder()

        # Create expression: 5.0 + 10.0
        expr = builder.add(builder.number(5.0), builder.number(10.0))

        dsl = ProgramDSL("type_test")
        dsl.add_statement(expr)
        prog = dsl.build()

        # Check type inference
        type_checker = TypeChecker()
        result = type_checker.check_types(prog)
        assert result.valid is True  # No type errors

    def test_type_annotations_in_function(self):
        """Test type annotations in function definition."""
        builder = DSLBuilder()

        params = [
            builder.param("x", TypeAnnotation(base_type="float")),
            builder.param("y", TypeAnnotation(base_type="float")),
        ]

        body = builder.sequence(
            [
                builder.add(builder.var("x"), builder.var("y")),
            ]
        )

        dsl = ProgramDSL("typed_function")
        dsl.define_function(
            "add",
            parameters=params,
            body=body,
            return_type=TypeAnnotation(base_type="float"),
        )

        prog = dsl.build()
        result = validate_program(prog)
        assert result.valid is True


class TestSemanticAnalysisIntegration:
    """Integration tests for semantic analysis."""

    def test_undefined_variable_detection(self):
        """Test detection of undefined variables."""
        # Program uses x without defining it
        dsl = ProgramDSL("undefined_test")
        dsl.add_statement(VariableRef(name="undefined_var"))
        prog = dsl.build()

        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(prog)
        assert result.valid is False
        assert any(
            e.error_type == ValidationErrorType.UNDEFINED_REFERENCE
            for e in result.errors
        )

    def test_defined_variable_no_error(self):
        """Test that defined variables don't cause errors."""
        dsl = ProgramDSL("defined_test")
        builder = DSLBuilder()

        dsl.declare_variable("x", builder.number(10.0))
        dsl.add_statement(builder.var("x"))

        prog = dsl.build()

        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(prog)
        assert result.valid is True

    def test_unused_variable_warning(self):
        """Test detection of unused variables."""
        dsl = ProgramDSL("unused_test")
        builder = DSLBuilder()

        # Declare x but never use it
        dsl.declare_variable("x", builder.number(10.0))

        prog = dsl.build()

        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(prog)
        # Should have warning but still be valid
        assert result.valid is True
        assert any("Unused" in w.message for w in result.warnings)


class TestFullWorkflowIntegration:
    """Full workflow integration tests."""

    def test_complete_program_workflow(self):
        """Test complete workflow: define, generate, validate."""
        # Step 1: Create program using DSL
        dsl = ProgramDSL("complete_workflow", ProgramType.FUNCTION)
        dsl.with_description("A complete workflow test")
        dsl.with_import("numpy")

        builder = DSLBuilder()

        # Define a function
        params = [builder.param("price", TypeAnnotation(base_type="float"))]
        func_body = builder.sequence(
            [
                builder.mul(builder.var("price"), builder.number(1.1)),
            ]
        )
        dsl.define_function(
            "increase_price",
            parameters=params,
            body=func_body,
            return_type=TypeAnnotation(base_type="float"),
        )

        prog = dsl.build()

        # Step 2: Validate with comprehensive checks
        result = validate_program(
            prog,
            check_types=True,
            check_semantics=True,
        )
        assert result.valid is True

        # Step 3: Verify program structure
        assert prog.name == "complete_workflow"
        assert prog.program_type == ProgramType.FUNCTION
        assert "numpy" in prog.imports

    def test_generator_with_context(self):
        """Test generator with rich context."""
        config = GenerationConfig(
            strategy=GenerationStrategy.TEMPLATE,
            constraints=GenerationConstraints(max_depth=5),
        )
        generator = create_generator(GenerationStrategy.TEMPLATE, config)

        context = GenerationContext(
            description="Generate strategy function",
            target_type=ProgramType.STRATEGY,
            variables={
                "price": TypeAnnotation(base_type="float"),
                "volume": TypeAnnotation(base_type="float"),
            },
        )

        prog = generator.generate(context)
        assert prog is not None

        # Validate the generated program
        result = validate_program(prog)
        assert result.valid is True

    def test_complex_arithmetic_expression(self):
        """Test complex arithmetic expression generation and validation."""
        builder = DSLBuilder()

        # Create: ((a + b) * c) / d
        a = builder.var("a")
        b = builder.var("b")
        c = builder.var("c")
        d = builder.var("d")

        expr = builder.div(
            builder.mul(
                builder.add(a, b),
                c,
            ),
            d,
        )

        dsl = ProgramDSL("complex_arithmetic")
        dsl.declare_variable("a", builder.number(10.0))
        dsl.declare_variable("b", builder.number(20.0))
        dsl.declare_variable("c", builder.number(2.0))
        dsl.declare_variable("d", builder.number(5.0))
        dsl.add_statement(expr)

        prog = dsl.build()
        result = validate_program(prog)
        assert result.valid is True


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""

    def test_validation_error_reporting(self):
        """Test that validation errors are properly reported."""
        # Create program with validation error (missing required import)
        from src.strong_system.program_synthesis.dsl import create_strategy_schema

        schema = create_strategy_schema()
        # Strategy schema requires imports that we won't provide
        prog = Program(name="test", imports=[])

        from src.strong_system.program_synthesis.validator import ProgramValidator

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_schema_violation_detection(self):
        """Test detection of schema violations."""
        schema = create_safe_schema()

        # Try to use a node type not allowed in safe schema
        from src.strong_system.program_synthesis.types import Loop

        prog = Program(
            name="test",
            ast=Sequence(statements=[Loop()]),
        )

        validator = ProgramValidator(schema)
        result = validator.validate(prog)
        assert result.valid is False
        assert any(
            e.error_type == ValidationErrorType.UNSUPPORTED_NODE for e in result.errors
        )

    def test_recovery_from_invalid_generation(self):
        """Test that invalid generation attempts are handled gracefully."""
        config = GenerationConfig(
            strategy=GenerationStrategy.SEARCH,
        )
        generator = SearchBasedGenerator(config)

        # Try multiple times, should eventually succeed or return None
        attempts = 0
        prog = None
        while attempts < 5 and prog is None:
            context = GenerationContext(target_type=ProgramType.FUNCTION)
            prog = generator.generate(context)
            attempts += 1

        # Should either succeed or gracefully return None
        assert prog is None or isinstance(prog, Program)
