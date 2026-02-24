"""Explanation Formatter Module.

Formats explanations for different audiences with support for
technical vs. non-technical outputs and multiple format types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import logging
import json

logger = logging.getLogger(__name__)


class AudienceType(Enum):
    """Target audience types for explanation formatting."""

    TECHNICAL = "technical"  # Data scientists, ML engineers
    TRADER = "trader"  # Professional traders
    EXECUTIVE = "executive"  # C-level, management
    GENERAL = "general"  # General audience
    DEVELOPER = "developer"  # Software developers


class OutputFormat(Enum):
    """Output format types."""

    TEXT = "text"  # Plain text
    MARKDOWN = "markdown"  # Markdown format
    HTML = "html"  # HTML format
    JSON = "json"  # JSON format
    STRUCTURED = "structured"  # Structured data


@dataclass
class FormatterConfig:
    """Configuration for explanation formatting."""

    audience: AudienceType = AudienceType.GENERAL
    output_format: OutputFormat = OutputFormat.TEXT
    max_summary_length: int = 200
    max_reasoning_steps: int = 5
    include_confidence: bool = True
    include_evidence: bool = True
    include_metadata: bool = False
    decimal_precision: int = 2
    use_emoji: bool = False
    include_timestamp: bool = False


@dataclass
class FormattedExplanation:
    """A formatted explanation ready for display."""

    content: str
    audience: AudienceType
    format: OutputFormat
    sections: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "content": self.content,
            "audience": self.audience.value,
            "format": self.format.value,
            "sections": self.sections,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class ExplanationFormatter:
    """Formats explanations for different audiences.

    This class transforms raw explanation data into audience-appropriate
    formats, supporting technical detail for engineers and simplified
    summaries for executives.

    Example:
        >>> formatter = ExplanationFormatter()
        >>> formatted = formatter.format(
        ...     explanation={'summary': 'Buy signal...', ...},
        ...     audience=AudienceType.TRADER
        ... )
        >>> print(formatted.content)
        'TRADE SIGNAL: Buy with 85% confidence...'
    """

    # Templates for different audiences
    _AUDIENCE_TEMPLATES = {
        AudienceType.TECHNICAL: {
            "header": "# Technical Analysis Explanation",
            "summary_label": "## Summary",
            "reasoning_label": "## Reasoning Chain",
            "factors_label": "## Feature Contributions",
            "confidence_label": "## Confidence Metrics",
            "step_format": "{step_number}. [{confidence:.2%}] {description}",
        },
        AudienceType.TRADER: {
            "header": "📊 Trade Signal Analysis",
            "summary_label": "**Signal Summary**",
            "reasoning_label": "**Reasoning**",
            "factors_label": "**Key Drivers**",
            "confidence_label": "**Confidence Level**",
            "step_format": "• {description} (confidence: {confidence:.0%})",
        },
        AudienceType.EXECUTIVE: {
            "header": "Decision Summary",
            "summary_label": "Overview",
            "reasoning_label": "Key Points",
            "factors_label": "Main Factors",
            "confidence_label": "Assurance Level",
            "step_format": "• {description}",
        },
        AudienceType.GENERAL: {
            "header": "Analysis Explanation",
            "summary_label": "Summary",
            "reasoning_label": "Why This Decision?",
            "factors_label": "Important Factors",
            "confidence_label": "How Confident?",
            "step_format": "{step_number}. {description}",
        },
        AudienceType.DEVELOPER: {
            "header": "# Explanation Output",
            "summary_label": "## Summary",
            "reasoning_label": "## Reasoning Chain",
            "factors_label": "## Feature Analysis",
            "confidence_label": "## Metrics",
            "step_format": "Step {step_number}: {description} (conf: {confidence:.2f})",
        },
    }

    # Confidence level descriptions by audience
    _CONFIDENCE_DESCRIPTIONS = {
        AudienceType.TECHNICAL: {
            "very_high": "Very high confidence (>90%)",
            "high": "High confidence (75-90%)",
            "moderate": "Moderate confidence (50-75%)",
            "low": "Low confidence (25-50%)",
            "very_low": "Very low confidence (<25%)",
        },
        AudienceType.TRADER: {
            "very_high": "Strong signal conviction",
            "high": "Good signal conviction",
            "moderate": "Moderate conviction - proceed with caution",
            "low": "Weak conviction - consider additional analysis",
            "very_low": "Very weak signal - not recommended",
        },
        AudienceType.EXECUTIVE: {
            "very_high": "Highly reliable",
            "high": "Reliable",
            "moderate": "Reasonably reliable",
            "low": "Use with caution",
            "very_low": "Limited reliability",
        },
        AudienceType.GENERAL: {
            "very_high": "Very confident",
            "high": "Confident",
            "moderate": "Somewhat confident",
            "low": "Not very confident",
            "very_low": "Uncertain",
        },
        AudienceType.DEVELOPER: {
            "very_high": "CONFIDENCE_VERY_HIGH",
            "high": "CONFIDENCE_HIGH",
            "moderate": "CONFIDENCE_MODERATE",
            "low": "CONFIDENCE_LOW",
            "very_low": "CONFIDENCE_VERY_LOW",
        },
    }

    # Emoji mappings for signals
    _SIGNAL_EMOJI = {
        "buy": "🟢",
        "sell": "🔴",
        "hold": "🟡",
        "up": "📈",
        "down": "📉",
        "neutral": "➡️",
    }

    def __init__(self, config: Optional[FormatterConfig] = None):
        """Initialize the explanation formatter.

        Args:
            config: Configuration for formatting.
                   Uses defaults if not provided.
        """
        self.config = config or FormatterConfig()
        logger.info(
            "ExplanationFormatter initialized for audience=%s, format=%s",
            self.config.audience.value,
            self.config.output_format.value,
        )

    def format(
        self,
        explanation: dict[str, Any],
        audience: Optional[AudienceType] = None,
        output_format: Optional[OutputFormat] = None,
    ) -> FormattedExplanation:
        """Format an explanation for a specific audience.

        Args:
            explanation: The explanation data to format.
            audience: Target audience (uses config default if not provided).
            output_format: Output format (uses config default if not provided).

        Returns:
            FormattedExplanation ready for display.
        """
        target_audience = audience or self.config.audience
        target_format = output_format or self.config.output_format

        # Get templates for audience
        templates = self._AUDIENCE_TEMPLATES.get(
            target_audience,
            self._AUDIENCE_TEMPLATES[AudienceType.GENERAL],
        )

        # Build sections
        sections = {}

        # Header
        sections["header"] = templates["header"]

        # Summary section
        sections["summary"] = self._format_summary(
            explanation, templates, target_audience
        )

        # Reasoning chain section
        sections["reasoning"] = self._format_reasoning_chain(
            explanation, templates, target_audience
        )

        # Key factors section
        sections["factors"] = self._format_key_factors(
            explanation, templates, target_audience
        )

        # Confidence section
        if self.config.include_confidence:
            sections["confidence"] = self._format_confidence(
                explanation, templates, target_audience
            )

        # Combine into full content
        content = self._combine_sections(sections, target_format)

        return FormattedExplanation(
            content=content,
            audience=target_audience,
            format=target_format,
            sections=sections,
            metadata={
                "explanation_type": explanation.get("explanation_type", "unknown"),
                "formatter_version": "1.0",
            },
        )

    def format_for_technical(
        self,
        explanation: dict[str, Any],
    ) -> FormattedExplanation:
        """Format explanation for technical audience.

        Args:
            explanation: The explanation data.

        Returns:
            FormattedExplanation for technical audience.
        """
        return self.format(
            explanation,
            audience=AudienceType.TECHNICAL,
            output_format=OutputFormat.MARKDOWN,
        )

    def format_for_trader(
        self,
        explanation: dict[str, Any],
    ) -> FormattedExplanation:
        """Format explanation for professional traders.

        Args:
            explanation: The explanation data.

        Returns:
            FormattedExplanation for trader audience.
        """
        return self.format(
            explanation,
            audience=AudienceType.TRADER,
            output_format=OutputFormat.TEXT,
        )

    def format_for_executive(
        self,
        explanation: dict[str, Any],
    ) -> FormattedExplanation:
        """Format explanation for executive audience.

        Args:
            explanation: The explanation data.

        Returns:
            FormattedExplanation for executive audience.
        """
        return self.format(
            explanation,
            audience=AudienceType.EXECUTIVE,
            output_format=OutputFormat.TEXT,
        )

    def format_as_json(
        self,
        explanation: dict[str, Any],
    ) -> FormattedExplanation:
        """Format explanation as JSON.

        Args:
            explanation: The explanation data.

        Returns:
            FormattedExplanation in JSON format.
        """
        return self.format(
            explanation,
            output_format=OutputFormat.JSON,
        )

    def format_as_markdown(
        self,
        explanation: dict[str, Any],
    ) -> FormattedExplanation:
        """Format explanation as Markdown.

        Args:
            explanation: The explanation data.

        Returns:
            FormattedExplanation in Markdown format.
        """
        return self.format(
            explanation,
            output_format=OutputFormat.MARKDOWN,
        )

    def format_as_html(
        self,
        explanation: dict[str, Any],
    ) -> FormattedExplanation:
        """Format explanation as HTML.

        Args:
            explanation: The explanation data.

        Returns:
            FormattedExplanation in HTML format.
        """
        return self.format(
            explanation,
            output_format=OutputFormat.HTML,
        )

    def create_summary_only(
        self,
        explanation: dict[str, Any],
        audience: Optional[AudienceType] = None,
    ) -> str:
        """Create a brief summary-only explanation.

        Args:
            explanation: The explanation data.
            audience: Target audience.

        Returns:
            Brief summary string.
        """
        target_audience = audience or self.config.audience
        summary = explanation.get("summary", "No summary available.")
        confidence = explanation.get("overall_confidence", 0.5)

        if target_audience == AudienceType.TRADER:
            signal = self._extract_signal(explanation)
            emoji = self._SIGNAL_EMOJI.get(signal, "") if self.config.use_emoji else ""
            conf_level = self._get_confidence_level(confidence)
            return f"{emoji} {signal.upper()}: {summary} ({conf_level} confidence)"

        elif target_audience == AudienceType.EXECUTIVE:
            return f"Recommendation: {summary}"

        return summary

    def create_bullet_summary(
        self,
        explanation: dict[str, Any],
        max_bullets: int = 5,
    ) -> list[str]:
        """Create a bullet-point summary of the explanation.

        Args:
            explanation: The explanation data.
            max_bullets: Maximum number of bullet points.

        Returns:
            List of bullet point strings.
        """
        bullets = []

        # Add summary
        summary = explanation.get("summary", "")
        if summary:
            bullets.append(f"Summary: {summary}")

        # Add key factors
        key_factors = explanation.get("key_factors", {})
        if key_factors:
            sorted_factors = sorted(
                key_factors.items(),
                key=lambda x: abs(x[1]),
                reverse=True,
            )[: max_bullets - 1]

            for name, value in sorted_factors:
                direction = "positive" if value > 0 else "negative"
                bullets.append(f"{name}: {direction} impact ({abs(value):.2f})")

        # Add confidence
        confidence = explanation.get("overall_confidence", 0.5)
        bullets.append(f"Overall confidence: {confidence:.0%}")

        return bullets[:max_bullets]

    def _format_summary(
        self,
        explanation: dict[str, Any],
        templates: dict[str, str],
        audience: AudienceType,
    ) -> str:
        """Format the summary section."""
        summary = explanation.get("summary", "No summary available.")

        if audience == AudienceType.TECHNICAL:
            return f"{templates['summary_label']}\n\n{summary}"

        elif audience == AudienceType.TRADER:
            signal = self._extract_signal(explanation)
            emoji = self._SIGNAL_EMOJI.get(signal, "") if self.config.use_emoji else ""
            return f"{templates['summary_label']}\n{emoji} {summary}"

        elif audience == AudienceType.EXECUTIVE:
            # Simplify for executives
            words = summary.split()
            if len(words) > 30:
                summary = " ".join(words[:30]) + "..."
            return f"{templates['summary_label']}: {summary}"

        return f"{templates['summary_label']}\n{summary}"

    def _format_reasoning_chain(
        self,
        explanation: dict[str, Any],
        templates: dict[str, str],
        audience: AudienceType,
    ) -> str:
        """Format the reasoning chain section."""
        reasoning_chain = explanation.get("reasoning_chain", [])

        if not reasoning_chain:
            return ""

        lines = [templates["reasoning_label"], ""]

        step_format = templates.get(
            "step_format",
            "{step_number}. {description}",
        )

        max_steps = min(len(reasoning_chain), self.config.max_reasoning_steps)

        for i, step in enumerate(reasoning_chain[:max_steps]):
            if isinstance(step, dict):
                description = step.get("description", "No description")
                confidence = step.get("confidence", 0.5)
                step_num = step.get("step_number", i + 1)

                if audience in (AudienceType.EXECUTIVE, AudienceType.GENERAL):
                    # Simplify descriptions for non-technical audiences
                    description = self._simplify_description(description)

                formatted_step = step_format.format(
                    step_number=step_num,
                    description=description,
                    confidence=confidence,
                )
                lines.append(formatted_step)
            else:
                lines.append(f"• {step}")

        return "\n".join(lines)

    def _format_key_factors(
        self,
        explanation: dict[str, Any],
        templates: dict[str, str],
        audience: AudienceType,
    ) -> str:
        """Format the key factors section."""
        key_factors = explanation.get("key_factors", {})

        if not key_factors:
            return ""

        lines = [templates["factors_label"], ""]

        # Sort by absolute importance
        sorted_factors = sorted(
            key_factors.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )

        for name, value in sorted_factors:
            if audience == AudienceType.TECHNICAL:
                lines.append(f"- {name}: {value:+.{self.config.decimal_precision}f}")

            elif audience == AudienceType.TRADER:
                direction = "↑" if value > 0 else "↓"
                impact = "strong" if abs(value) > 0.3 else "moderate"
                lines.append(f"• {name}: {direction} {impact} impact")

            elif audience == AudienceType.EXECUTIVE:
                direction = "supports" if value > 0 else "opposes"
                lines.append(f"• {name} {direction} this decision")

            else:
                direction = "positive" if value > 0 else "negative"
                lines.append(f"• {name}: {direction}")

        return "\n".join(lines)

    def _format_confidence(
        self,
        explanation: dict[str, Any],
        templates: dict[str, str],
        audience: AudienceType,
    ) -> str:
        """Format the confidence section."""
        confidence = explanation.get("overall_confidence", 0.5)

        descriptions = self._CONFIDENCE_DESCRIPTIONS.get(
            audience,
            self._CONFIDENCE_DESCRIPTIONS[AudienceType.GENERAL],
        )

        conf_level = self._get_confidence_level(confidence)
        description = descriptions.get(conf_level, "Unknown confidence")

        lines = [templates["confidence_label"], ""]

        if audience == AudienceType.TECHNICAL:
            lines.append(f"Score: {confidence:.4f}")
            lines.append(f"Level: {description}")
        elif audience == AudienceType.TRADER:
            lines.append(f"{confidence:.0%} - {description}")
        elif audience == AudienceType.EXECUTIVE:
            lines.append(description.capitalize())
        else:
            lines.append(f"{confidence:.0%} ({description})")

        return "\n".join(lines)

    def _combine_sections(
        self,
        sections: dict[str, str],
        output_format: OutputFormat,
    ) -> str:
        """Combine sections into final content based on format."""
        if output_format == OutputFormat.JSON:
            return json.dumps(sections, indent=2)

        if output_format == OutputFormat.HTML:
            html_parts = ["<div class='explanation'>"]
            for name, content in sections.items():
                if content:
                    html_parts.append(f"<div class='section {name}'>")
                    html_parts.append(content.replace("\n", "<br>"))
                    html_parts.append("</div>")
            html_parts.append("</div>")
            return "\n".join(html_parts)

        # Text or Markdown
        parts = []
        for name, content in sections.items():
            if content:
                parts.append(content)
                parts.append("")  # Empty line between sections

        return "\n".join(parts).strip()

    def _extract_signal(self, explanation: dict[str, Any]) -> str:
        """Extract signal type from explanation."""
        metadata = explanation.get("metadata", {})
        if "signal" in metadata:
            return metadata["signal"].lower()

        summary = explanation.get("summary", "").lower()
        for signal in ["buy", "sell", "hold"]:
            if signal in summary:
                return signal

        return "hold"

    def _get_confidence_level(self, confidence: float) -> str:
        """Get confidence level string from score."""
        if confidence >= 0.9:
            return "very_high"
        elif confidence >= 0.75:
            return "high"
        elif confidence >= 0.5:
            return "moderate"
        elif confidence >= 0.25:
            return "low"
        return "very_low"

    def _simplify_description(self, description: str) -> str:
        """Simplify technical descriptions for non-technical audiences."""
        # Replace technical terms
        replacements = {
            "RSI": "momentum indicator",
            "MACD": "trend indicator",
            "SHAP": "importance",
            "feature": "factor",
            "contribution": "impact",
            "prediction": "forecast",
            "signal": "recommendation",
        }

        result = description
        for old, new in replacements.items():
            result = result.replace(old, new)

        return result


__all__ = [
    "AudienceType",
    "OutputFormat",
    "FormatterConfig",
    "FormattedExplanation",
    "ExplanationFormatter",
]
