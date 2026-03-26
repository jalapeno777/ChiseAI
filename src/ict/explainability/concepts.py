"""ICT concept knowledge base for neuro-symbolic explanations.

Maps ICT signal types to their theoretical descriptions, practical
interpretations, and key characteristics used in explanation generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class ICTConcept(str, Enum):
    """Core ICT concepts recognized by the explainability module."""

    CVD = "CVD"
    FVG = "FVG"
    ORDER_BLOCK = "ORDER_BLOCK"


@dataclass(frozen=True)
class ConceptEntry:
    """Structured knowledge about a single ICT concept.

    Attributes:
        name: Human-readable concept name.
        description: Concise theoretical description.
        mechanism: How the concept works in practice.
        bullish_interpretation: What a bullish signal implies.
        bearish_interpretation: What a bearish signal implies.
        key_traits: Defining characteristics used in explanations.
    """

    name: str
    description: str
    mechanism: str
    bullish_interpretation: str
    bearish_interpretation: str
    key_traits: tuple[str, ...] = ()


class ICTConceptRegistry:
    """Immutable registry of ICT concept definitions.

    Used by ICTExplainer to ground generated explanations in
    established ICT theory. Each concept entry provides the
    symbolic layer that connects quantitative signals to
    human-understandable market structure narratives.
    """

    _ENTRIES: ClassVar[dict[ICTConcept, ConceptEntry]] = {
        ICTConcept.CVD: ConceptEntry(
            name="Cumulative Volume Delta",
            description=(
                "Tracks net volume flow by accumulating tick-level "
                "buy/sell volume deltas to identify institutional "
                "buying/selling pressure."
            ),
            mechanism=(
                "Buy-initiated trades add to the delta while sell-initiated "
                "trades subtract. Sustained divergence between CVD direction "
                "and price direction signals potential institutional activity."
            ),
            bullish_interpretation=(
                "Positive CVD divergence with rising price confirms "
                "institutional buying support behind the move."
            ),
            bearish_interpretation=(
                "Negative CVD divergence with falling price confirms "
                "institutional selling pressure driving the decline."
            ),
            key_traits=(
                "volume flow",
                "institutional pressure",
                "tick-level deltas",
                "divergence",
            ),
        ),
        ICTConcept.FVG: ConceptEntry(
            name="Fair Value Gap",
            description=(
                "Detects bullish and bearish gaps in price action using "
                "3-candle patterns, indicating potential fair value zones "
                "where price may revisit."
            ),
            mechanism=(
                "An FVG forms when candle 1's high is below candle 3's low "
                "(bullish) or candle 1's low is above candle 3's high "
                "(bearish). The gap represents an imbalance that price tends "
                "to retrace and fill."
            ),
            bullish_interpretation=(
                "A bullish FVG marks a zone where buyers overwhelmed sellers, "
                "creating an inefficiency the market may return to fill before "
                "continuing higher."
            ),
            bearish_interpretation=(
                "A bearish FVG marks a zone where sellers overwhelmed buyers, "
                "creating an inefficiency the market may return to fill before "
                "continuing lower."
            ),
            key_traits=(
                "price imbalance",
                "3-candle pattern",
                "retracement zone",
                "inefficiency fill",
            ),
        ),
        ICTConcept.ORDER_BLOCK: ConceptEntry(
            name="Order Block",
            description=(
                "Detects consolidation zones where institutional traders "
                "positioned themselves before a strong directional move."
            ),
            mechanism=(
                "Identified as the last opposing candle before a significant "
                "impulsive move. The block represents a zone where large "
                "orders were accumulated and often acts as support/resistance "
                "on revisits."
            ),
            bullish_interpretation=(
                "A bullish order block (last bearish candle before bullish "
                "impulse) represents institutional accumulation that acts as "
                "support on price revisits."
            ),
            bearish_interpretation=(
                "A bearish order block (last bullish candle before bearish "
                "impulse) represents institutional distribution that acts as "
                "resistance on price revisits."
            ),
            key_traits=(
                "institutional accumulation",
                "support/resistance zone",
                "pre-impulse consolidation",
                "revisit target",
            ),
        ),
    }

    def __init__(self) -> None:
        # Freeze to prevent mutation.
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("ICTConceptRegistry is immutable")
        super().__setattr__(name, value)

    def get(self, concept: ICTConcept) -> ConceptEntry | None:
        """Look up a concept entry by enum value."""
        return self._ENTRIES.get(concept)

    def get_by_name(self, name: str) -> ConceptEntry | None:
        """Look up a concept entry by signal type name (case-insensitive)."""
        try:
            key = ICTConcept(name.upper())
            return self._ENTRIES.get(key)
        except ValueError:
            return None

    @property
    def all_concepts(self) -> dict[ICTConcept, ConceptEntry]:
        """Return a shallow copy of all registered concepts."""
        return dict(self._ENTRIES)

    @property
    def supported_types(self) -> list[str]:
        """Return list of supported signal type name strings."""
        return [c.value for c in ICTConcept]
