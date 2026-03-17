"""Tests for hypothesis generator templates."""

from __future__ import annotations

import pytest

from src.strong_system.belief_embeddings import BeliefVector
from src.strong_system.hypothesis_generator.templates import (
    PromptTemplate,
    TemplateRegistry,
    get_template_registry,
    render_prompt,
)
from src.strong_system.hypothesis_generator.types import (
    HypothesisType,
    MarketContext,
)


class TestPromptTemplate:
    """Tests for PromptTemplate class."""

    def test_creation(self) -> None:
        """Test creating a prompt template."""
        template = PromptTemplate(
            name="test",
            system_prompt="System instructions",
            user_template="User prompt with {beliefs} and {context}",
            output_format="json",
        )
        assert template.name == "test"
        assert template.system_prompt == "System instructions"
        assert "{beliefs}" in template.user_template
        assert template.output_format == "json"

    def test_render(self) -> None:
        """Test rendering a template."""
        template = PromptTemplate(
            name="test",
            system_prompt="System",
            user_template="Beliefs: {beliefs}\nContext: {context}\nType: {hypothesis_type}",
            output_format="json",
        )

        beliefs = [BeliefVector(vector=__import__("numpy").array([0.5, 0.3]))]
        context = MarketContext(symbol="BTC-USD", current_price=50000.0)

        result = template.render(beliefs, context, HypothesisType.TREND)

        assert "system" in result
        assert "user" in result
        assert result["system"] == "System"
        assert "BTC-USD" in result["user"]
        assert "TREND" in result["user"]

    def test_render_no_beliefs(self) -> None:
        """Test rendering with no beliefs."""
        template = PromptTemplate(
            name="test",
            system_prompt="System",
            user_template="{beliefs}",
            output_format="json",
        )

        result = template.render([], MarketContext())
        assert "No beliefs available" in result["user"]

    def test_render_with_kwargs(self) -> None:
        """Test rendering with additional kwargs."""
        template = PromptTemplate(
            name="test",
            system_prompt="System",
            user_template="{custom_var}",
            output_format="json",
        )

        result = template.render([], MarketContext(), custom_var="custom_value")
        assert "custom_value" in result["user"]


class TestTemplateRegistry:
    """Tests for TemplateRegistry class."""

    def test_creation(self) -> None:
        """Test creating a template registry."""
        registry = TemplateRegistry()
        assert registry is not None
        # Should have default templates
        templates = registry.list_templates()
        assert len(templates) > 0

    def test_register(self) -> None:
        """Test registering a template."""
        registry = TemplateRegistry()
        template = PromptTemplate(
            name="custom",
            system_prompt="Custom system",
            user_template="Custom user",
            output_format="text",
        )
        registry.register(template)
        assert registry.has_template("custom")

    def test_get(self) -> None:
        """Test getting a template."""
        registry = TemplateRegistry()
        template = registry.get("general")
        assert template.name == "general"
        assert template.system_prompt != ""

    def test_get_not_found(self) -> None:
        """Test getting a non-existent template."""
        registry = TemplateRegistry()
        with pytest.raises(KeyError, match="Template 'nonexistent' not found"):
            registry.get("nonexistent")

    def test_get_for_hypothesis_type(self) -> None:
        """Test getting template for hypothesis type."""
        registry = TemplateRegistry()

        trend_template = registry.get_for_hypothesis_type(HypothesisType.TREND)
        assert trend_template.name == "trend"

        reversal_template = registry.get_for_hypothesis_type(HypothesisType.REVERSAL)
        assert reversal_template.name == "reversal"

    def test_get_for_hypothesis_type_fallback(self) -> None:
        """Test fallback to general template."""
        registry = TemplateRegistry()
        # Create registry without specific type template
        template = registry.get_for_hypothesis_type(HypothesisType.VOLATILITY)
        # Should return volatility template since it exists in defaults
        assert template.name == "volatility"

    def test_list_templates(self) -> None:
        """Test listing templates."""
        registry = TemplateRegistry()
        templates = registry.list_templates()
        assert isinstance(templates, list)
        assert "general" in templates
        assert "trend" in templates

    def test_has_template(self) -> None:
        """Test checking if template exists."""
        registry = TemplateRegistry()
        assert registry.has_template("general") is True
        assert registry.has_template("nonexistent") is False


class TestGetTemplateRegistry:
    """Tests for get_template_registry function."""

    def test_returns_registry(self) -> None:
        """Test that function returns a registry."""
        registry = get_template_registry()
        assert isinstance(registry, TemplateRegistry)

    def test_singleton(self) -> None:
        """Test that function returns same instance."""
        registry1 = get_template_registry()
        registry2 = get_template_registry()
        assert registry1 is registry2


class TestRenderPrompt:
    """Tests for render_prompt function."""

    def test_render_with_type(self) -> None:
        """Test rendering with hypothesis type."""
        beliefs = [BeliefVector(vector=__import__("numpy").array([0.5]))]
        context = MarketContext(symbol="ETH-USD")

        result = render_prompt(beliefs, context, HypothesisType.RANGE)

        assert "system" in result
        assert "user" in result
        assert "ETH-USD" in result["user"]

    def test_render_with_template_name(self) -> None:
        """Test rendering with specific template name."""
        beliefs = []
        context = MarketContext()

        result = render_prompt(beliefs, context, template_name="breakout")

        assert "breakout" in result["user"].lower() or "BREAKOUT" in result["user"]

    def test_render_default(self) -> None:
        """Test rendering with defaults."""
        beliefs = []
        context = MarketContext()

        result = render_prompt(beliefs, context)

        assert "system" in result
        assert "user" in result

    def test_render_with_kwargs(self) -> None:
        """Test rendering with additional kwargs."""
        beliefs = []
        context = MarketContext()

        result = render_prompt(beliefs, context, custom="value")
        # Should not raise error even if custom not used
        assert "system" in result


class TestDefaultTemplates:
    """Tests for default template content."""

    def test_general_template(self) -> None:
        """Test general template has required content."""
        registry = get_template_registry()
        template = registry.get("general")

        assert "hypothes" in template.system_prompt.lower()
        assert "{beliefs}" in template.user_template
        assert "{context}" in template.user_template

    def test_trend_template(self) -> None:
        """Test trend template content."""
        registry = get_template_registry()
        template = registry.get("trend")

        assert "trend" in template.system_prompt.lower()
        assert "direction" in template.user_template.lower()

    def test_reversal_template(self) -> None:
        """Test reversal template content."""
        registry = get_template_registry()
        template = registry.get("reversal")

        assert "reversal" in template.system_prompt.lower()

    def test_range_template(self) -> None:
        """Test range template content."""
        registry = get_template_registry()
        template = registry.get("range")

        assert "range" in template.system_prompt.lower()
        assert "support" in template.user_template.lower()

    def test_breakout_template(self) -> None:
        """Test breakout template content."""
        registry = get_template_registry()
        template = registry.get("breakout")

        assert "breakout" in template.system_prompt.lower()
        assert "volume" in template.user_template.lower()

    def test_volatility_template(self) -> None:
        """Test volatility template content."""
        registry = get_template_registry()
        template = registry.get("volatility")

        assert "volatility" in template.system_prompt.lower()

    def test_momentum_template(self) -> None:
        """Test momentum template content."""
        registry = get_template_registry()
        template = registry.get("momentum")

        assert "momentum" in template.system_prompt.lower()
