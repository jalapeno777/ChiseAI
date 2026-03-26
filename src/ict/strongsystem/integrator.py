"""StrongSystem Confidence Integrator (ST-ICT-029).

Combines StrongSystem hypothesis scoring with existing ICT signals
to produce enhanced confidence scores for trade decisions.

Integration Logic:
    1. Score the StrongSystem hypothesis from market evidence
    2. Score ICT zones against the hypothesis
    3. Combine hypothesis confidence with existing ICT signal confidence
    4. Apply the 0.1-0.2 multiplier when hypothesis aligns with signals

The integrator acts as the bridge between the StrongSystem hypothesis
module and the broader ICT signal pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ict.strongsystem.hypothesis import (
    BOSConfirmation,
    HypothesisScore,
    LiquiditySweepEvidence,
    MarketStructureEvidence,
    OrderFlowEvidence,
    StrongSystemHypothesis,
)
from ict.strongsystem.zone_scorer import ICTZone, ZoneScorer, ZoneScoreResult


@dataclass
class ICTSignal:
    """An existing ICT signal for integration.

    Attributes:
        signal_type: Type of ICT signal (e.g., 'order_block', 'bos')
        direction: Signal direction (bullish/bearish)
        confidence: Signal confidence (0.0-1.0)
        zone_type: Associated zone type (if applicable)
        zone_direction: Associated zone direction (if applicable)
    """

    signal_type: str
    direction: str
    confidence: float
    zone_type: str | None = None
    zone_direction: str | None = None


@dataclass
class IntegrationResult:
    """Result of StrongSystem + ICT signal integration.

    Attributes:
        original_confidence: Confidence from ICT signals alone
        hypothesis_score: The StrongSystem hypothesis score
        zone_scores: Scored zones from the zone scorer
        enhanced_confidence: Final confidence after StrongSystem enhancement
        confidence_delta: Change in confidence from integration
        multiplier_applied: The confidence multiplier that was applied
        is_aligned: Whether signals align with hypothesis
        signal_count: Number of signals integrated
        valid_zone_count: Number of valid target zones
        summary: Human-readable summary of the integration
    """

    original_confidence: float = 0.0
    hypothesis_score: HypothesisScore | None = None
    zone_scores: list[ZoneScoreResult] = field(default_factory=list)
    enhanced_confidence: float = 0.0
    confidence_delta: float = 0.0
    multiplier_applied: float = 0.0
    is_aligned: bool = False
    signal_count: int = 0
    valid_zone_count: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_confidence": round(self.original_confidence, 4),
            "enhanced_confidence": round(self.enhanced_confidence, 4),
            "confidence_delta": round(self.confidence_delta, 4),
            "multiplier_applied": round(self.multiplier_applied, 4),
            "is_aligned": self.is_aligned,
            "signal_count": self.signal_count,
            "valid_zone_count": self.valid_zone_count,
            "hypothesis": (
                self.hypothesis_score.to_dict() if self.hypothesis_score else None
            ),
            "zone_scores": [z.to_dict() for z in self.zone_scores],
            "summary": self.summary,
        }


class StrongSystemIntegrator:
    """Integrates StrongSystem hypothesis with existing ICT signals.

    The integrator:
    1. Takes ICT signals and market evidence as input
    2. Scores the StrongSystem hypothesis
    3. Evaluates zone alignment with the hypothesis
    4. Applies confidence enhancement when signals and hypothesis align

    Per AC3: Combines with existing ICT signals for enhanced confidence.
    Per AC4: StrongSystem score adds 0.1-0.2 confidence multiplier when aligned.

    Usage:
        integrator = StrongSystemIntegrator()
        result = integrator.integrate(
            ict_signals=signals,
            market_structure=ms_ev,
            order_flow=of_ev,
            liquidity_sweep=ls_ev,
            bos_confirmation=bos_ev,
            zones=zones,
        )
    """

    def __init__(
        self,
        hypothesis_scorer: StrongSystemHypothesis | None = None,
        zone_scorer: ZoneScorer | None = None,
        min_signals_for_alignment: int = 1,
    ):
        """Initialize integrator.

        Args:
            hypothesis_scorer: Hypothesis scorer instance
            zone_scorer: Zone scorer instance
            min_signals_for_alignment: Min signals to check alignment
        """
        self.hypothesis_scorer = hypothesis_scorer or StrongSystemHypothesis()
        self.zone_scorer = zone_scorer or ZoneScorer()
        self.min_signals_for_alignment = min_signals_for_alignment

    def _check_signal_alignment(
        self,
        signals: list[ICTSignal],
        hypothesis_direction: str,
    ) -> tuple[bool, int, int]:
        """Check if ICT signals align with the hypothesis direction.

        Args:
            signals: List of ICT signals
            hypothesis_direction: Hypothesis direction string

        Returns:
            Tuple of (is_aligned, aligned_count, total_count)
        """
        if hypothesis_direction == "neutral" or not signals:
            return False, 0, 0

        aligned = 0
        total = len(signals)

        for sig in signals:
            sig_dir = sig.direction.lower()
            if sig_dir == hypothesis_direction.lower():
                aligned += 1

        # Simple majority: more aligned than not
        is_aligned = aligned > (total - aligned)
        return is_aligned, aligned, total

    def _calculate_base_confidence(
        self,
        signals: list[ICTSignal],
    ) -> float:
        """Calculate base confidence from ICT signals.

        Uses weighted average of signal confidences.

        Args:
            signals: List of ICT signals

        Returns:
            Base confidence (0.0-1.0)
        """
        if not signals:
            return 0.0

        # Weight by signal type importance
        signal_weights = {
            "order_block": 1.0,
            "bos": 0.9,
            "choch": 0.85,
            "fvg": 0.8,
            "liquidity_sweep": 0.75,
            "breaker": 0.7,
            "mitigation": 0.6,
        }

        total_weight = 0.0
        weighted_confidence = 0.0

        for sig in signals:
            weight = signal_weights.get(sig.signal_type.lower(), 0.5)
            weighted_confidence += sig.confidence * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return min(1.0, weighted_confidence / total_weight)

    def _generate_summary(
        self,
        hypothesis: HypothesisScore,
        is_aligned: bool,
        delta: float,
        signal_count: int,
        valid_zones: int,
    ) -> str:
        """Generate human-readable integration summary.

        Args:
            hypothesis: The hypothesis score
            is_aligned: Whether signals aligned
            delta: Confidence change
            signal_count: Number of signals
            valid_zones: Valid target zones

        Returns:
            Summary string
        """
        parts = [
            f"Hypothesis: {hypothesis.direction.value} "
            f"({hypothesis.strength.value}, "
            f"score={hypothesis.raw_score:.3f})"
        ]

        if is_aligned:
            parts.append(f"Signals ALIGNED with hypothesis (+{delta:.3f} confidence)")
        else:
            parts.append("Signals NOT aligned (no enhancement)")

        parts.append(f"Signals: {signal_count}, Valid zones: {valid_zones}")
        return " | ".join(parts)

    def integrate(
        self,
        ict_signals: list[ICTSignal],
        market_structure: MarketStructureEvidence,
        order_flow: OrderFlowEvidence,
        liquidity_sweep: LiquiditySweepEvidence,
        bos_confirmation: BOSConfirmation,
        zones: list[ICTZone] | None = None,
    ) -> IntegrationResult:
        """Integrate StrongSystem hypothesis with ICT signals.

        Args:
            ict_signals: List of existing ICT signals
            market_structure: Market structure evidence
            order_flow: Order flow evidence
            liquidity_sweep: Liquidity sweep evidence
            bos_confirmation: BOS confirmation evidence
            zones: Optional list of ICT zones to score

        Returns:
            IntegrationResult with enhanced confidence and details
        """
        # 1. Score the hypothesis
        hypothesis = self.hypothesis_scorer.score_hypothesis(
            market_structure=market_structure,
            order_flow=order_flow,
            liquidity_sweep=liquidity_sweep,
            bos_confirmation=bos_confirmation,
        )

        # 2. Calculate base ICT signal confidence
        base_confidence = self._calculate_base_confidence(ict_signals)

        # 3. Check signal-hypothesis alignment
        is_aligned, aligned_count, total_count = self._check_signal_alignment(
            ict_signals, hypothesis.direction.value
        )

        # 4. Score zones if provided
        zone_scores: list[ZoneScoreResult] = []
        valid_zone_count = 0
        if zones:
            zone_scores = self.zone_scorer.score_zones(zones, hypothesis)
            valid_zone_count = sum(1 for z in zone_scores if z.is_valid_target)

        # 5. Calculate enhanced confidence
        multiplier = 0.0
        if (
            is_aligned
            and hypothesis.strength.value in ("moderate", "strong")
            and len(ict_signals) >= self.min_signals_for_alignment
        ):
            multiplier = hypothesis.confidence_contribution

        enhanced = min(1.0, base_confidence + multiplier)
        delta = enhanced - base_confidence

        # 6. Generate summary
        summary = self._generate_summary(
            hypothesis, is_aligned, delta, len(ict_signals), valid_zone_count
        )

        return IntegrationResult(
            original_confidence=base_confidence,
            hypothesis_score=hypothesis,
            zone_scores=zone_scores,
            enhanced_confidence=enhanced,
            confidence_delta=delta,
            multiplier_applied=multiplier,
            is_aligned=is_aligned,
            signal_count=len(ict_signals),
            valid_zone_count=valid_zone_count,
            summary=summary,
        )


# Global integrator instance
_integrator_instance: StrongSystemIntegrator | None = None


def get_integrator() -> StrongSystemIntegrator:
    """Get or create the global StrongSystemIntegrator instance.

    Returns:
        Global StrongSystemIntegrator instance
    """
    global _integrator_instance
    if _integrator_instance is None:
        _integrator_instance = StrongSystemIntegrator()
    return _integrator_instance
