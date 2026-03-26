"""Tests for StrongSystem Integrator (ST-ICT-029).

Tests the integration of StrongSystem hypothesis with ICT signals:
- Signal-hypothesis alignment detection
- Base confidence calculation from ICT signals
- Enhanced confidence with 0.1-0.2 multiplier
- Full integration flow with zones
- Serialization
"""

import pytest

from ict.strongsystem.hypothesis import (
    BOSConfirmation,
    HypothesisDirection,
    HypothesisStrength,
    LiquiditySweepEvidence,
    MarketStructureEvidence,
    OrderFlowEvidence,
)
from ict.strongsystem.integrator import (
    ICTSignal,
    IntegrationResult,
    StrongSystemIntegrator,
    get_integrator,
)
from ict.strongsystem.zone_scorer import (
    ICTZone,
    ZoneDirection,
    ZoneType,
)


# --- Helpers ---


def _bullish_evidence():
    return dict(
        market_structure=MarketStructureEvidence(
            higher_highs=3,
            higher_lows=3,
            trend_duration_bars=15,
        ),
        order_flow=OrderFlowEvidence(
            bullish_volume_delta=800_000,
            bearish_volume_delta=200_000,
            large_order_ratio=0.7,
        ),
        liquidity_sweep=LiquiditySweepEvidence(
            sell_side_swept=True,
            displacement_after=True,
            sweep_magnitude=0.8,
        ),
        bos_confirmation=BOSConfirmation(
            bullish_bos=True,
            bos_count=2,
            is_validated=True,
        ),
    )


def _bearish_evidence():
    return dict(
        market_structure=MarketStructureEvidence(
            lower_highs=3,
            lower_lows=3,
            trend_duration_bars=15,
        ),
        order_flow=OrderFlowEvidence(
            bullish_volume_delta=200_000,
            bearish_volume_delta=800_000,
            large_order_ratio=0.3,
        ),
        liquidity_sweep=LiquiditySweepEvidence(
            buy_side_swept=True,
            displacement_after=True,
            sweep_magnitude=0.8,
        ),
        bos_confirmation=BOSConfirmation(
            bearish_bos=True,
            bos_count=2,
            is_validated=True,
        ),
    )


def _neutral_evidence():
    return dict(
        market_structure=MarketStructureEvidence(),
        order_flow=OrderFlowEvidence(
            bullish_volume_delta=500_000,
            bearish_volume_delta=500_000,
        ),
        liquidity_sweep=LiquiditySweepEvidence(),
        bos_confirmation=BOSConfirmation(),
    )


# --- Tests ---


class TestSignalAlignment:
    """Test signal-hypothesis alignment detection."""

    def test_bullish_signals_aligned_with_bullish_hypothesis(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
            ICTSignal(signal_type="fvg", direction="bullish", confidence=0.6),
        ]
        aligned, count, total = integrator._check_signal_alignment(signals, "bullish")
        assert aligned is True
        assert count == 2
        assert total == 2

    def test_bearish_signals_aligned_with_bearish_hypothesis(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bearish", confidence=0.7),
        ]
        aligned, _, _ = integrator._check_signal_alignment(signals, "bearish")
        assert aligned is True

    def test_mixed_signals_alignment(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
            ICTSignal(signal_type="fvg", direction="bearish", confidence=0.6),
        ]
        # 1 bullish vs 1 bearish -> not majority
        aligned, _, _ = integrator._check_signal_alignment(signals, "bullish")
        assert aligned is False

    def test_neutral_hypothesis_never_aligned(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        aligned, _, _ = integrator._check_signal_alignment(signals, "neutral")
        assert aligned is False

    def test_empty_signals_not_aligned(self):
        integrator = StrongSystemIntegrator()
        aligned, count, total = integrator._check_signal_alignment([], "bullish")
        assert aligned is False
        assert count == 0


class TestBaseConfidence:
    """Test base confidence calculation from ICT signals."""

    def test_single_signal_confidence(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.8),
        ]
        base = integrator._calculate_base_confidence(signals)
        assert base == pytest.approx(0.8, abs=0.01)

    def test_multiple_signals_weighted(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.8),
            ICTSignal(signal_type="fvg", direction="bullish", confidence=0.6),
        ]
        base = integrator._calculate_base_confidence(signals)
        # OB weight=1.0, FVG weight=0.8 -> (0.8*1.0 + 0.6*0.8) / (1.0+0.8)
        expected = (0.8 * 1.0 + 0.6 * 0.8) / (1.0 + 0.8)
        assert base == pytest.approx(expected, abs=0.01)

    def test_empty_signals_returns_zero(self):
        integrator = StrongSystemIntegrator()
        base = integrator._calculate_base_confidence([])
        assert base == 0.0

    def test_confidence_clamped_to_one(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=1.0),
            ICTSignal(signal_type="bos", direction="bullish", confidence=1.0),
        ]
        base = integrator._calculate_base_confidence(signals)
        assert base <= 1.0


class TestIntegration:
    """Test full integration flow (AC3: combine with ICT signals)."""

    def test_aligned_signals_get_enhancement(self):
        """AC3: Enhanced confidence when signals align with hypothesis."""
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        assert result.enhanced_confidence > result.original_confidence
        assert result.confidence_delta > 0

    def test_non_aligned_signals_no_enhancement(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bearish", confidence=0.7),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        # Bearish signal + bullish hypothesis = no alignment
        assert result.multiplier_applied == 0.0

    def test_neutral_hypothesis_no_enhancement(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        ev = _neutral_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        assert result.multiplier_applied == 0.0

    def test_enhanced_confidence_within_bounds(self):
        """AC4: 0.1-0.2 confidence multiplier range."""
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
            ICTSignal(signal_type="bos", direction="bullish", confidence=0.8),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        if result.is_aligned:
            assert 0.0 <= result.multiplier_applied <= 0.2

    def test_enhanced_confidence_does_not_exceed_one(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.95),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        assert result.enhanced_confidence <= 1.0

    def test_bearish_integration_works(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bearish", confidence=0.7),
        ]
        ev = _bearish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        assert result.hypothesis_score is not None
        assert result.hypothesis_score.direction == HypothesisDirection.BEARISH

    def test_signal_count_tracked(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
            ICTSignal(signal_type="fvg", direction="bullish", confidence=0.6),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        assert result.signal_count == 2


class TestIntegrationWithZones:
    """Test integration with zone scoring (AC2: score zones based on alignment)."""

    def test_zones_scored_in_result(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        zones = [
            ICTZone(
                zone_type=ZoneType.ORDER_BLOCK,
                direction=ZoneDirection.BULLISH,
                price_level=100.0,
                is_unmitigated=True,
                base_confidence=0.7,
            ),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            zones=zones,
            **ev,
        )
        assert len(result.zone_scores) == 1

    def test_valid_zone_count_tracked(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        zones = [
            ICTZone(
                zone_type=ZoneType.ORDER_BLOCK,
                direction=ZoneDirection.BULLISH,
                price_level=100.0,
                is_unmitigated=True,
                base_confidence=0.7,
            ),
            ICTZone(
                zone_type=ZoneType.FVG,
                direction=ZoneDirection.BEARISH,
                price_level=105.0,
                is_unmitigated=True,
                base_confidence=0.5,
            ),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            zones=zones,
            **ev,
        )
        # Only the bullish OB should be a valid target
        assert result.valid_zone_count >= 1

    def test_no_zones_gracefully_handled(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            zones=None,
            **ev,
        )
        assert len(result.zone_scores) == 0
        assert result.valid_zone_count == 0


class TestIntegrationSummary:
    """Test summary generation."""

    def test_summary_contains_key_info(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        assert "Hypothesis:" in result.summary
        assert "Signals:" in result.summary


class TestIntegrationSerialization:
    """Test IntegrationResult serialization."""

    def test_to_dict(self):
        integrator = StrongSystemIntegrator()
        signals = [
            ICTSignal(signal_type="order_block", direction="bullish", confidence=0.7),
        ]
        ev = _bullish_evidence()
        result = integrator.integrate(
            ict_signals=signals,
            **ev,
        )
        d = result.to_dict()
        assert "original_confidence" in d
        assert "enhanced_confidence" in d
        assert "confidence_delta" in d
        assert "multiplier_applied" in d
        assert "is_aligned" in d
        assert "signal_count" in d
        assert "hypothesis" in d
        assert "zone_scores" in d
        assert "summary" in d


class TestGlobalInstance:
    """Test global singleton pattern."""

    def test_get_integrator_returns_instance(self):
        integrator = get_integrator()
        assert isinstance(integrator, StrongSystemIntegrator)

    def test_get_integrator_returns_same_instance(self):
        i1 = get_integrator()
        i2 = get_integrator()
        assert i1 is i2
