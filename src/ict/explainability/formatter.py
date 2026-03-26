"""Formatters for rendering ICT explanations to Discord and dashboard payloads.

Each renderer takes an ICTExplanationResult and produces a target-specific
string or dict suitable for its consumption context.
"""

from __future__ import annotations

from typing import Any

from .explainer import ICTExplanationResult

# Direction emoji mapping.
_DIRECTION_EMOJI: dict[str, str] = {
    "bullish": "\U0001f7e2",  # green circle
    "bearish": "\U0001f534",  # red circle
    "neutral": "\U0001f7e1",  # yellow circle
}

# Confidence tier emoji.
_CONFIDENCE_EMOJI: dict[str, str] = {
    "high": "\U0001f525",
    "moderate": "\u26a1",
    "low": "\u26a0\ufe0f",
}


def format_for_discord(result: ICTExplanationResult, *, token: str = "") -> str:
    """Render an ICTExplanationResult as a Discord-friendly markdown message.

    Uses bold text, emoji prefixes, and numbered lists matching the
    existing AlertFormatter patterns in ``discord_alerts.alert_formatter``.

    Args:
        result: The explanation to render.
        token: Optional token symbol for the header line.

    Returns:
        A plain-text markdown string suitable for Discord message content
        or embed description fields.
    """
    dir_emoji = _DIRECTION_EMOJI.get(result.direction, "\u2139\ufe0f")
    conf_emoji = _CONFIDENCE_EMOJI.get(result.confidence_tier, "")

    header = f"{dir_emoji} **{result.direction.title()} {result.signal_type} Signal**"
    if token:
        header += f" \u2014 {token}"

    lines: list[str] = [
        header,
        f"{conf_emoji} Confidence: **{result.confidence:.0%}** ({result.confidence_tier})",
        "",
        f"**{result.concept_name}**",
        result.concept_summary,
        "",
        result.explanation,
        "",
        "**Key Factors:**",
    ]
    for i, factor in enumerate(result.key_factors, 1):
        lines.append(f"{i}. {factor}")

    if result.timeframe:
        lines.append("")
        lines.append(f"\U0001f552 Timeframe: **{result.timeframe}**")

    return "\n".join(lines)


def format_for_dashboard(result: ICTExplanationResult) -> dict[str, Any]:
    """Render an ICTExplanationResult as a dashboard-consumable dict.

    The output is a flat, JSON-serialisable dict that extends
    ``ICTExplanationResult.to_dict()`` with rendering-ready fields
    for frontend consumption.

    Args:
        result: The explanation to render.

    Returns:
        A dict suitable for JSON serialisation and dashboard display.
    """
    base = result.to_dict()
    base["direction_emoji"] = _DIRECTION_EMOJI.get(result.direction, "")
    base["confidence_emoji"] = _CONFIDENCE_EMOJI.get(result.confidence_tier, "")
    base["display_label"] = (
        f"{_DIRECTION_EMOJI.get(result.direction, '')} "
        f"{result.direction.title()} {result.signal_type}"
    )
    base["concept_traits_list"] = list(result.concept_traits)
    return base
