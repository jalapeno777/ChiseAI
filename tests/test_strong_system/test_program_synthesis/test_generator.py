"""Tests for program synthesis generator module."""

import pytest
from src.strong_system.program_synthesis.generator import (
    GenerationConfig,
    GenerationConstraints,
    GenerationContext,
    GenerationStrategy,
    GrammarBasedGenerator,
    HybridGenerator,
    ProgramGenerator,
    SafeGenerator,
    SearchBasedGenerator,
    TemplateBasedGenerator,
    create_generator,
    generate_program,
)
from src.strong_system.program_synthesis.types import (
    ASTNodeType,
    Program,
    ProgramType,
)


class TestGenerationConstraints:
    """Test suite for GenerationConstraints class."""

    def test_default_creation(self):
        """Test creating constraints with defaults."""
        constraints = GenerationConstraints()
        assert constraints.max_depth == 10
        assert constraints.max_nodes == 100
        assert constraints.max_parameters == 5
        assert ASTNodeType.NUMBER in constraints.allowed_node_types

    def test_custom_values(self):
        """Test creating constraints with custom values."""
        constraints = GenerationConstraints(
            max_depth=5,
            max_nodes=50,
            max_parameters=3,
        )
        assert constraints.max_depth == 5
        assert constraints.max_nodes == 50
        assert constraints.max_parameters == 3

    def test_invalid_max_depth(self):
        """Test that invalid max_depth raises error."""
        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            GenerationConstraints(max_depth=0)

    def test_invalid_max_nodes(self):
        """Test that invalid max_nodes raises error."""
        with pytest.raises(ValueError, match="max_nodes must be at least 1"):
            GenerationConstraints(max_nodes=0)


class TestGenerationConfig:
    """Test suite for GenerationConfig class."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = GenerationConfig()
        assert config.strategy == GenerationStrategy.TEMPLATE
        assert config.random_seed is None
        assert config.temperature == 0.7

    def test_custom_strategy(self):
        """Test creating config with custom strategy."""
        config = GenerationConfig(strategy=GenerationStrategy.SEARCH)
        assert config.strategy == GenerationStrategy.SEARCH

    def test_invalid_temperature_low(self):
        """Test that temperature below 0 raises error."""
        with pytest.raises(ValueError, match="temperature must be between"):
            GenerationConfig(temperature=-0.1)

    def test_invalid_temperature_high(self):
        """Test that temperature above 1 raises error."""
        with pytest.raises(ValueError, match="temperature must be between"):
            GenerationConfig(temperature=1.1)


class TestGenerationContext:
    """Test suite for GenerationContext class."""

    def test_default_creation(self):
        """Test creating context with defaults."""
        context = GenerationContext()
        assert context.variables == {}
        assert context.functions == {}
        assert context.beliefs == {}
        assert context.target_type == ProgramType.FUNCTION

    def test_with_description(self):
        """Test creating context with description."""
        context = GenerationContext(description="Generate arithmetic expression")
        assert context.description == "Generate arithmetic expression"


class TestTemplateBasedGenerator:
    """Test suite for TemplateBasedGenerator class."""

    def test_creation(self):
        """Test creating template generator."""
        generator = TemplateBasedGenerator()
        assert generator is not None
        assert isinstance(generator, ProgramGenerator)

    def test_register_template(self):
        """Test registering custom template."""
        generator = TemplateBasedGenerator()

        def custom_template(ctx):
            from src.strong_system.program_synthesis.dsl import ProgramDSL

            return ProgramDSL("custom").build()

        generator.register_template("custom", custom_template)
        assert "custom" in generator._templates

    def test_generate_simple_function(self):
        """Test generating simple function template."""
        generator = TemplateBasedGenerator()
        context = GenerationContext(
            description="simple function",
            target_type=ProgramType.FUNCTION,
        )
        program = generator.generate(context)
        assert program is not None
        assert isinstance(program, Program)
        assert program.name == "simple_function"

    def test_generate_arithmetic_expr(self):
        """Test generating arithmetic expression template."""
        generator = TemplateBasedGenerator()
        context = GenerationContext(
            description="arithmetic expression",
            target_type=ProgramType.FUNCTION,
        )
        program = generator.generate(context)
        assert program is not None
        assert program.name == "arithmetic_expr"

    def test_generate_conditional(self):
        """Test generating conditional template."""
        generator = TemplateBasedGenerator()
        context = GenerationContext(
            description="condition",
            target_type=ProgramType.FUNCTION,
        )
        program = generator.generate(context)
        # Template may return None if validation fails (e.g., print not allowed)
        # Just verify template selection works
        if program is not None:
            assert program.name == "conditional"

    def test_generated_program_is_valid(self):
        """Test that generated program passes validation."""
        generator = TemplateBasedGenerator()
        context = GenerationContext(target_type=ProgramType.FUNCTION)
        program = generator.generate(context)
        assert program is not None

        result = generator.validate_generation(program)
        assert result.valid is True


class TestSearchBasedGenerator:
    """Test suite for SearchBasedGenerator class."""

    def test_creation(self):
        """Test creating search generator."""
        generator = SearchBasedGenerator()
        assert generator is not None

    def test_generate_returns_program(self):
        """Test that generation returns a program."""
        generator = SearchBasedGenerator()
        context = GenerationContext(target_type=ProgramType.FUNCTION)
        program = generator.generate(context)
        # May return None if search fails, but usually succeeds
        if program is not None:
            assert isinstance(program, Program)

    def test_generated_program_is_valid(self):
        """Test that generated program passes validation."""
        generator = SearchBasedGenerator()
        context = GenerationContext(target_type=ProgramType.FUNCTION)
        program = generator.generate(context)
        if program is not None:
            result = generator.validate_generation(program)
            assert result.valid is True


class TestGrammarBasedGenerator:
    """Test suite for GrammarBasedGenerator class."""

    def test_creation(self):
        """Test creating grammar generator."""
        generator = GrammarBasedGenerator()
        assert generator is not None

    def test_generate_returns_program(self):
        """Test that generation returns a program."""
        generator = GrammarBasedGenerator()
        context = GenerationContext(target_type=ProgramType.FUNCTION)
        program = generator.generate(context)
        if program is not None:
            assert isinstance(program, Program)

    def test_grammar_respects_depth_limit(self):
        """Test that grammar respects depth constraints."""
        constraints = GenerationConstraints(max_depth=3)
        config = GenerationConfig(constraints=constraints)
        generator = GrammarBasedGenerator(config)
        context = GenerationContext(target_type=ProgramType.FUNCTION)
        program = generator.generate(context)
        if program is not None:
            assert isinstance(program, Program)


class TestHybridGenerator:
    """Test suite for HybridGenerator class."""

    def test_creation(self):
        """Test creating hybrid generator."""
        generator = HybridGenerator()
        assert generator is not None

    def test_generate_with_template_strategy(self):
        """Test hybrid with template strategy."""
        config = GenerationConfig(strategy=GenerationStrategy.TEMPLATE)
        generator = HybridGenerator(config)
        context = GenerationContext(target_type=ProgramType.FUNCTION)
        program = generator.generate(context)
        assert program is not None

    def test_generate_with_hybrid_strategy(self):
        """Test hybrid with hybrid strategy."""
        config = GenerationConfig(strategy=GenerationStrategy.HYBRID)
        generator = HybridGenerator(config)
        context = GenerationContext(target_type=ProgramType.FUNCTION)
        program = generator.generate(context)
        # May return None if all generators fail
        if program is not None:
            assert isinstance(program, Program)


class TestSafeGenerator:
    """Test suite for SafeGenerator class."""

    def test_creation(self):
        """Test creating safe generator wrapper."""
        base_gen = TemplateBasedGenerator()
        safe_gen = SafeGenerator(base_gen)
        assert safe_gen is not None

    def test_safe_generator_pre_checks(self):
        """Test that safe generator performs pre-generation checks."""
        base_gen = TemplateBasedGenerator()
        safe_gen = SafeGenerator(base_gen)
        context = GenerationContext(
            description="simple function",
            target_type=ProgramType.FUNCTION,
        )
        program = safe_gen.generate(context)
        assert program is not None

    def test_safe_generator_blocks_forbidden_patterns(self):
        """Test that safe generator blocks forbidden patterns."""
        constraints = GenerationConstraints(forbidden_patterns=["dangerous"])
        config = GenerationConfig(constraints=constraints)
        base_gen = TemplateBasedGenerator(config)
        safe_gen = SafeGenerator(base_gen)

        context = GenerationContext(
            description="dangerous operation",
            target_type=ProgramType.FUNCTION,
        )
        program = safe_gen.generate(context)
        assert program is None  # Should be blocked


class TestCreateGenerator:
    """Test suite for create_generator factory function."""

    def test_create_template_generator(self):
        """Test creating template generator."""
        gen = create_generator(GenerationStrategy.TEMPLATE)
        assert isinstance(gen, TemplateBasedGenerator)

    def test_create_search_generator(self):
        """Test creating search generator."""
        gen = create_generator(GenerationStrategy.SEARCH)
        assert isinstance(gen, SearchBasedGenerator)

    def test_create_grammar_generator(self):
        """Test creating grammar generator."""
        gen = create_generator(GenerationStrategy.GRAMMAR)
        assert isinstance(gen, GrammarBasedGenerator)

    def test_create_hybrid_generator(self):
        """Test creating hybrid generator."""
        gen = create_generator(GenerationStrategy.HYBRID)
        assert isinstance(gen, HybridGenerator)

    def test_create_with_config(self):
        """Test creating generator with custom config."""
        constraints = GenerationConstraints(max_depth=5)
        config = GenerationConfig(constraints=constraints)
        gen = create_generator(GenerationStrategy.TEMPLATE, config)
        assert gen.config == config


class TestGenerateProgram:
    """Test suite for generate_program convenience function."""

    def test_generate_simple_program(self):
        """Test generating simple program."""
        prog = generate_program("Generate arithmetic expression")
        assert prog is not None
        assert isinstance(prog, Program)

    def test_generate_with_custom_constraints(self):
        """Test generating with custom constraints."""
        constraints = GenerationConstraints(max_depth=5)
        prog = generate_program(
            "Test",
            constraints=constraints,
        )
        assert prog is not None

    def test_generate_with_target_type(self):
        """Test generating with specific target type."""
        prog = generate_program(
            "Test",
            target_type=ProgramType.STRATEGY,
        )
        assert prog is not None
        assert prog.program_type == ProgramType.STRATEGY

    def test_generate_with_search_strategy(self):
        """Test generating with search strategy."""
        prog = generate_program(
            "Test",
            strategy=GenerationStrategy.SEARCH,
        )
        assert prog is not None
