"""Neuro-symbolic explanation generator for ICT signals.

Combines quantitative signal data (the "neural" layer) with structured
ICT concept knowledge (the "symbolic" layer) to produce human-readable
explanations that ground numeric outputs in market-structure theory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .concepts import ICTConceptRegistry

logger = logging.getLogger(__name__)


class SignalDirection(str, Enum):
    """Normalized signal direction for explanation purposes."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    LONG = "LONG"
    SHORT = "SHORT"


# Map aggregated directions to their base directional label.
_DIRECTION_LABEL: dict[str, str] = {
    "BULLISH": "bullish",
    "BEARISH": "bearish",
    "NEUTRAL": "neutral",
    "LONG": "bullish",
    "SHORT": "bearish",
}


def _normalise_direction(raw: str) -> str:
    """Normalise a raw direction string to lowercase directional label."""
    upper = raw.strip().upper()
    return _DIRECTION_LABEL.get(upper, upper.lower())


def _confidence_tier(confidence: float) -> str:
    """Classify a 0-1 confidence value into a human-readable tier."""
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "moderate"
    return "low"


def _strength_label(strength: float) -> str:
    """Classify a 0-1 strength value into a human-readable label."""
    if strength >= 0.8:
        return "strong"
    if strength >= 0.5:
        return "moderate"
    return "weak"


@dataclass
class ICTExplanationResult:
    """Structured explanation produced by ICTExplainer.

    Attributes:
        signal_type: The ICT signal type that was explained (e.g. 'CVD').
        direction: Normalised direction label ('bullish', 'bearish', 'neutral').
        confidence: Numeric confidence in [0, 1].
        confidence_tier: Human-readable confidence classification.
        explanation: Primary natural-language explanation paragraph.
        concept_summary: One-line summary linking to the ICT concept.
        rationale: Step-by-step reasoning chain.
        key_factors: Ordered list of contributing factors.
        concept_name: Display name of the underlying ICT concept.
        concept_traits: Key traits of the concept.
        timeframe: Timeframe associated with the signal.
        metadata: Additional structured data for downstream consumers.
    """

    signal_type: str
    direction: str
    confidence: float
    confidence_tier: str
    explanation: str
    concept_summary: str
    rationale: list[str]
    key_factors: list[str]
    concept_name: str = ""
    concept_traits: tuple[str, ...] = ()
    timeframe: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON / dashboard payloads."""
        return {
            "signal_type": self.signal_type,
            "direction": self.direction,
            "confidence": self.confidence,
            "confidence_tier": self.confidence_tier,
            "explanation": self.explanation,
            "concept_summary": self.concept_summary,
            "rationale": self.rationale,
            "key_factors": self.key_factors,
            "concept_name": self.concept_name,
            "concept_traits": list(self.concept_traits),
            "timeframe": self.timeframe,
            "metadata": self.metadata,
        }


class ICTExplainer:
    """Generates neuro-symbolic explanations for ICT signals.

    The explainer combines quantitative signal metrics (confidence,
    strength, timeframe alignment) with a symbolic knowledge base of
    ICT concepts to produce grounded, human-readable explanations.

    Usage::

        explainer = ICTExplainer()
        result = explainer.explain(
            signal_type="ORDER_BLOCK",
            direction="BULLISH",
            confidence=0.85,
            strength=0.9,
            timeframe="15m",
        )
        print(result.explanation)
    """

    def __init__(self, registry: ICTConceptRegistry | None = None) -> None:
        self._registry = registry or ICTConceptRegistry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def explain(
        self,
        signal_type: str,
        direction: str,
        confidence: float,
        strength: float = 0.5,
        timeframe: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ICTExplanationResult:
        """Generate a full explanation for a single ICT signal.

        Args:
            signal_type: ICT signal type name (e.g. 'CVD', 'FVG', 'ORDER_BLOCK').
            direction: Signal direction (e.g. 'BULLISH', 'LONG', 'BEARISH').
            confidence: Signal confidence in [0, 1].
            strength: Signal strength in [0, 1]. Defaults to 0.5.
            timeframe: Timeframe the signal was detected on.
            metadata: Optional extra key-value data attached to the result.

        Returns:
            A fully populated ICTExplanationResult.
        """
        direction_label = _normalise_direction(direction)
        conf_tier = _confidence_tier(confidence)
        strength_lbl = _strength_label(strength)

        concept = self._registry.get_by_name(signal_type)
        concept_name = concept.name if concept else signal_type
        concept_traits = concept.key_traits if concept else ()

        rationale = self._build_rationale(
            concept=concept,
            direction_label=direction_label,
            conf_tier=conf_tier,
            strength_lbl=strength_lbl,
            timeframe=timeframe,
        )
        key_factors = self._build_key_factors(
            concept=concept,
            direction_label=direction_label,
            conf_tier=conf_tier,
            strength_lbl=strength_lbl,
            timeframe=timeframe,
        )
        explanation = self._build_explanation(
            concept_name=concept_name,
            direction_label=direction_label,
            conf_tier=conf_tier,
            strength_lbl=strength_lbl,
            timeframe=timeframe,
            key_factors=key_factors,
        )
        concept_summary = self._build_concept_summary(
            concept=concept,
            direction_label=direction_label,
        )

        return ICTExplanationResult(
            signal_type=signal_type,
            direction=direction_label,
            confidence=confidence,
            confidence_tier=conf_tier,
            explanation=explanation,
            concept_summary=concept_summary,
            rationale=rationale,
            key_factors=key_factors,
            concept_name=concept_name,
            concept_traits=concept_traits,
            timeframe=timeframe,
            metadata=metadata or {},
        )

    def explain_confluence(
        self,
        confluence_score: float,
        direction: str,
        confidence: float,
        contributing_signals: list[dict[str, Any]],
        timeframe: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ICTExplanationResult:
        """Generate an explanation for a confluence of multiple ICT signals.

        Args:
            confluence_score: Aggregated confluence strength in [0, 1].
            direction: Aggregated direction (LONG / SHORT / NEUTRAL).
            confidence: Overall confluence confidence in [0, 1].
            contributing_signals: List of dicts, each with at least
                'signal_type', 'direction', 'strength', 'confidence'.
            timeframe: Dominant timeframe.
            metadata: Optional extra key-value data.

        Returns:
            An ICTExplanationResult representing the confluence.
        """
        direction_label = _normalise_direction(direction)
        conf_tier = _confidence_tier(confidence)
        strength_lbl = _strength_label(confluence_score)

        signal_descriptions: list[str] = []
        concept_names: list[str] = []
        all_traits: set[str] = set()

        for sig in contributing_signals:
            sig_type = sig.get("signal_type", "UNKNOWN")
            sig_dir = _normalise_direction(sig.get("direction", ""))
            sig_strength = _strength_label(sig.get("strength", 0.5))
            entry = self._registry.get_by_name(sig_type)

            if entry:
                concept_names.append(entry.name)
                all_traits.update(entry.key_traits)
                interp = (
                    entry.bullish_interpretation
                    if sig_dir == "bullish"
                    else (
                        entry.bearish_interpretation
                        if sig_dir == "bearish"
                        else entry.description
                    )
                )
                signal_descriptions.append(
                    f"{entry.name} ({sig_dir}, {sig_strength}): {interp}"
                )
            else:
                concept_names.append(sig_type)
                signal_descriptions.append(f"{sig_type} ({sig_dir}, {sig_strength})")

        rationale = [
            f"Confluence of {len(contributing_signals)} ICT signals "
            f"yielded a {conf_tier}-confidence {direction_label} bias.",
            f"Aggregated confluence score: {confluence_score:.2f} ({strength_lbl}).",
        ]
        for desc in signal_descriptions:
            rationale.append(f"  - {desc}")

        key_factors = [
            f"{len(contributing_signals)}-signal confluence",
            f"{direction_label} directional alignment",
            f"{conf_tier} confidence",
            f"{strength_lbl} confluence strength",
        ]
        if timeframe:
            key_factors.append(f"{timeframe} timeframe alignment")

        joined_concepts = " + ".join(dict.fromkeys(concept_names))
        explanation = (
            f"Multiple ICT concepts ({joined_concepts}) align in the "
            f"{direction_label} direction with {conf_tier} confidence "
            f"(score: {confluence_score:.0%}). "
            f"The confluence of {len(contributing_signals)} signals "
            f"reinforces the {direction_label} bias across "
            f"{timeframe or 'multiple'} timeframe(s)."
        )
        concept_summary = (
            f"Confluence signal combining {joined_concepts} concepts "
            f"with {conf_tier} confidence and {strength_lbl} strength."
        )

        return ICTExplanationResult(
            signal_type="CONFLUENCE",
            direction=direction_label,
            confidence=confidence,
            confidence_tier=conf_tier,
            explanation=explanation,
            concept_summary=concept_summary,
            rationale=rationale,
            key_factors=key_factors,
            concept_name=joined_concepts,
            concept_traits=tuple(sorted(all_traits)),
            timeframe=timeframe,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_rationale(
        self,
        concept: Any,
        direction_label: str,
        conf_tier: str,
        strength_lbl: str,
        timeframe: str,
    ) -> list[str]:
        """Build the step-by-step reasoning chain."""
        lines: list[str] = []

        if concept:
            lines.append(f"Signal type: {concept.name} — {concept.description}")
            interp = (
                concept.bullish_interpretation
                if direction_label == "bullish"
                else (
                    concept.bearish_interpretation
                    if direction_label == "bearish"
                    else concept.description
                )
            )
            lines.append(f"{direction_label.title()} interpretation: {interp}")
        else:
            lines.append(f"Signal type: {direction_label} signal detected.")

        lines.append(f"Signal strength: {strength_lbl}")
        lines.append(f"Confidence level: {conf_tier}")
        if timeframe:
            lines.append(f"Timeframe alignment: {timeframe}")

        return lines

    @staticmethod
    def _build_key_factors(
        concept: Any,
        direction_label: str,
        conf_tier: str,
        strength_lbl: str,
        timeframe: str,
    ) -> list[str]:
        """Build the ordered list of key contributing factors."""
        factors: list[str] = [
            f"{direction_label} directional signal",
            f"{conf_tier} confidence",
            f"{strength_lbl} signal strength",
        ]
        if concept:
            for trait in concept.key_traits:
                factors.append(trait)
        if timeframe:
            factors.append(f"{timeframe} timeframe")
        return factors

    @staticmethod
    def _build_explanation(
        concept_name: str,
        direction_label: str,
        conf_tier: str,
        strength_lbl: str,
        timeframe: str,
        key_factors: list[str],
    ) -> str:
        """Build the primary natural-language explanation paragraph."""
        tf_clause = f" on the {timeframe} timeframe" if timeframe else ""
        factors_clause = ", ".join(key_factors[:4])
        return (
            f"A {strength_lbl} {direction_label} {concept_name} signal "
            f"was detected{tf_clause} with {conf_tier} confidence. "
            f"Key factors: {factors_clause}."
        )

    @staticmethod
    def _build_concept_summary(
        concept: Any,
        direction_label: str,
    ) -> str:
        """Build the one-line concept summary."""
        if not concept:
            return f"{direction_label.title()} signal detected."
        interp = (
            concept.bullish_interpretation
            if direction_label == "bullish"
            else (
                concept.bearish_interpretation
                if direction_label == "bearish"
                else concept.description
            )
        )
        return f"{concept.name}: {interp}"
