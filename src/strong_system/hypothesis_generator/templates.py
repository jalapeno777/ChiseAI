"""Hypothesis prompt templates for LLM-based generation.

Provides structured prompt templates for generating hypotheses from
belief clusters and market context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.strong_system.belief_embeddings import BeliefVector
from src.strong_system.hypothesis_generator.types import (
    HypothesisType,
    MarketContext,
)


@dataclass
class PromptTemplate:
    """A template for generating LLM prompts.

    Attributes:
        name: Template name
        system_prompt: System-level instructions for the LLM
        user_template: User prompt template with placeholders
        output_format: Expected output format description
    """

    name: str
    system_prompt: str
    user_template: str
    output_format: str

    def render(
        self,
        beliefs: list[BeliefVector],
        context: MarketContext,
        hypothesis_type: HypothesisType | None = None,
        **kwargs: Any,
    ) -> dict[str, str]:
        """Render the template with given data.

        Args:
            beliefs: List of belief vectors to include
            context: Market context information
            hypothesis_type: Specific hypothesis type to focus on
            **kwargs: Additional template variables

        Returns:
            Dictionary with 'system' and 'user' prompt strings
        """
        # Format beliefs for the prompt
        beliefs_text = self._format_beliefs(beliefs)

        # Format context
        context_text = self._format_context(context)

        # Format hypothesis type
        type_text = hypothesis_type.name if hypothesis_type else "ANY"

        # Render user prompt
        user_prompt = self.user_template.format(
            beliefs=beliefs_text,
            context=context_text,
            hypothesis_type=type_text,
            **kwargs,
        )

        return {
            "system": self.system_prompt,
            "user": user_prompt,
        }

    def _format_beliefs(self, beliefs: list[BeliefVector]) -> str:
        """Format belief vectors for prompt inclusion."""
        if not beliefs:
            return "No beliefs available."

        lines = [f"Belief Cluster ({len(beliefs)} beliefs):"]
        for i, belief in enumerate(beliefs[:10], 1):  # Limit to 10 beliefs
            confidence = belief.metadata.confidence
            source = belief.metadata.source
            lines.append(
                f"  {i}. ID: {belief.belief_id}, "
                f"Confidence: {confidence:.2f}, Source: {source}"
            )

        if len(beliefs) > 10:
            lines.append(f"  ... and {len(beliefs) - 10} more beliefs")

        return "\n".join(lines)

    def _format_context(self, context: MarketContext) -> str:
        """Format market context for prompt inclusion."""
        lines = [
            f"Symbol: {context.symbol}",
            f"Timeframe: {context.timeframe}",
            f"Current Price: {context.current_price:.4f}",
            f"Market Regime: {context.market_regime}",
        ]

        if context.indicators:
            lines.append("Technical Indicators:")
            for name, value in context.indicators.items():
                lines.append(f"  {name}: {value:.4f}")

        return "\n".join(lines)


class TemplateRegistry:
    """Registry of prompt templates for different hypothesis types."""

    def __init__(self) -> None:
        """Initialize the template registry with default templates."""
        self._templates: dict[str, PromptTemplate] = {}
        self._register_default_templates()

    def _register_default_templates(self) -> None:
        """Register the default set of templates."""
        # General hypothesis generation template
        self.register(
            PromptTemplate(
                name="general",
                system_prompt=(
                    "You are an expert quantitative analyst and hypothesis generator "
                    "for financial markets. Your task is to generate testable "
                    "hypotheses based on provided belief clusters and market context. "
                    "Each hypothesis should be specific, measurable, and actionable."
                ),
                user_template=(
                    "Generate hypotheses based on the following data:\n\n"
                    "{beliefs}\n\n"
                    "Market Context:\n{context}\n\n"
                    "Hypothesis Type Focus: {hypothesis_type}\n\n"
                    "Generate specific, testable hypotheses with confidence scores. "
                    "For each hypothesis, provide:\n"
                    "1. A clear description\n"
                    "2. A specific prediction with measurable outcomes\n"
                    "3. A confidence score (0.0-1.0)\n"
                    "4. Supporting reasoning\n\n"
                    "Format your response as structured data."
                ),
                output_format="structured_json",
            )
        )

        # Trend hypothesis template
        self.register(
            PromptTemplate(
                name="trend",
                system_prompt=(
                    "You are a trend analysis expert. Generate hypotheses about "
                    "market trend direction and strength based on belief clusters "
                    "and technical indicators. Focus on directional momentum."
                ),
                user_template=(
                    "Analyze trend direction based on:\n\n"
                    "{beliefs}\n\n"
                    "Market Context:\n{context}\n\n"
                    "Generate trend hypotheses addressing:\n"
                    "1. Direction (bullish/bearish)\n"
                    "2. Expected magnitude of move\n"
                    "3. Time horizon\n"
                    "4. Key levels to watch\n\n"
                    "Provide confidence scores for each hypothesis."
                ),
                output_format="structured_json",
            )
        )

        # Reversal hypothesis template
        self.register(
            PromptTemplate(
                name="reversal",
                system_prompt=(
                    "You are a reversal pattern expert. Generate hypotheses about "
                    "potential market reversals based on belief clusters and "
                    "technical exhaustion signals. Focus on inflection points."
                ),
                user_template=(
                    "Identify potential reversal points based on:\n\n"
                    "{beliefs}\n\n"
                    "Market Context:\n{context}\n\n"
                    "Generate reversal hypotheses addressing:\n"
                    "1. Reversal direction\n"
                    "2. Trigger conditions\n"
                    "3. Expected reversal magnitude\n"
                    "4. Invalidation levels\n\n"
                    "Provide confidence scores for each hypothesis."
                ),
                output_format="structured_json",
            )
        )

        # Range hypothesis template
        self.register(
            PromptTemplate(
                name="range",
                system_prompt=(
                    "You are a range-bound market expert. Generate hypotheses about "
                    "consolidation patterns and range boundaries based on belief "
                    "clusters and support/resistance levels."
                ),
                user_template=(
                    "Analyze range-bound conditions based on:\n\n"
                    "{beliefs}\n\n"
                    "Market Context:\n{context}\n\n"
                    "Generate range hypotheses addressing:\n"
                    "1. Support and resistance levels\n"
                    "2. Expected range duration\n"
                    "3. Mean reversion opportunities\n"
                    "4. Breakout/breakdown scenarios\n\n"
                    "Provide confidence scores for each hypothesis."
                ),
                output_format="structured_json",
            )
        )

        # Breakout hypothesis template
        self.register(
            PromptTemplate(
                name="breakout",
                system_prompt=(
                    "You are a breakout pattern expert. Generate hypotheses about "
                    "potential breakouts from consolidation patterns based on "
                    "belief clusters and volume/price action."
                ),
                user_template=(
                    "Identify potential breakout opportunities based on:\n\n"
                    "{beliefs}\n\n"
                    "Market Context:\n{context}\n\n"
                    "Generate breakout hypotheses addressing:\n"
                    "1. Breakout direction (up/down)\n"
                    "2. Trigger price levels\n"
                    "3. Expected move magnitude post-breakout\n"
                    "4. Volume confirmation requirements\n"
                    "5. False breakout risks\n\n"
                    "Provide confidence scores for each hypothesis."
                ),
                output_format="structured_json",
            )
        )

        # Volatility hypothesis template
        self.register(
            PromptTemplate(
                name="volatility",
                system_prompt=(
                    "You are a volatility analysis expert. Generate hypotheses about "
                    "expected volatility changes based on belief clusters and "
                    "market conditions. Focus on volatility expansion/contraction."
                ),
                user_template=(
                    "Analyze volatility conditions based on:\n\n"
                    "{beliefs}\n\n"
                    "Market Context:\n{context}\n\n"
                    "Generate volatility hypotheses addressing:\n"
                    "1. Expected volatility direction (expansion/contraction)\n"
                    "2. Magnitude of volatility change\n"
                    "3. Time horizon for volatility shift\n"
                    "4. Catalysts for volatility changes\n\n"
                    "Provide confidence scores for each hypothesis."
                ),
                output_format="structured_json",
            )
        )

        # Momentum hypothesis template
        self.register(
            PromptTemplate(
                name="momentum",
                system_prompt=(
                    "You are a momentum analysis expert. Generate hypotheses about "
                    "momentum continuation or exhaustion based on belief clusters "
                    "and oscillator indicators."
                ),
                user_template=(
                    "Analyze momentum conditions based on:\n\n"
                    "{beliefs}\n\n"
                    "Market Context:\n{context}\n\n"
                    "Generate momentum hypotheses addressing:\n"
                    "1. Momentum direction and strength\n"
                    "2. Momentum continuation vs exhaustion\n"
                    "3. Divergence signals\n"
                    "4. Overbought/oversold conditions\n\n"
                    "Provide confidence scores for each hypothesis."
                ),
                output_format="structured_json",
            )
        )

    def register(self, template: PromptTemplate) -> None:
        """Register a template.

        Args:
            template: The template to register
        """
        self._templates[template.name] = template

    def get(self, name: str) -> PromptTemplate:
        """Get a template by name.

        Args:
            name: Template name

        Returns:
            The requested template

        Raises:
            KeyError: If template not found
        """
        if name not in self._templates:
            raise KeyError(f"Template '{name}' not found")
        return self._templates[name]

    def get_for_hypothesis_type(
        self, hypothesis_type: HypothesisType
    ) -> PromptTemplate:
        """Get the appropriate template for a hypothesis type.

        Args:
            hypothesis_type: The type of hypothesis

        Returns:
            Template optimized for that hypothesis type
        """
        type_name = hypothesis_type.name.lower()
        if type_name in self._templates:
            return self._templates[type_name]
        return self._templates.get("general", self._templates["general"])

    def list_templates(self) -> list[str]:
        """List all registered template names.

        Returns:
            List of template names
        """
        return list(self._templates.keys())

    def has_template(self, name: str) -> bool:
        """Check if a template exists.

        Args:
            name: Template name to check

        Returns:
            True if template exists, False otherwise
        """
        return name in self._templates


# Global template registry instance
_template_registry: TemplateRegistry | None = None


def get_template_registry() -> TemplateRegistry:
    """Get the global template registry instance.

    Returns:
        The global TemplateRegistry instance
    """
    global _template_registry
    if _template_registry is None:
        _template_registry = TemplateRegistry()
    return _template_registry


def render_prompt(
    beliefs: list[BeliefVector],
    context: MarketContext,
    hypothesis_type: HypothesisType | None = None,
    template_name: str | None = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Convenience function to render a prompt.

    Args:
        beliefs: List of belief vectors
        context: Market context
        hypothesis_type: Type of hypothesis to generate
        template_name: Specific template to use (auto-selected if None)
        **kwargs: Additional template variables

    Returns:
        Dictionary with 'system' and 'user' prompt strings
    """
    registry = get_template_registry()

    if template_name:
        template = registry.get(template_name)
    elif hypothesis_type:
        template = registry.get_for_hypothesis_type(hypothesis_type)
    else:
        template = registry.get("general")

    return template.render(beliefs, context, hypothesis_type, **kwargs)
