"""Tests for Dynamic Weight Adjuster (ST-ICT-023).

Tests the time-based weight decay algorithm for ICT signals:
- Signals within 5 minutes: full weight (1.0x)
- Signals 5-15 minutes old: 0.8x multiplier
- Signals 15-30 minutes old: 0.5x multiplier
- Signals older than 30 minutes: excluded from confluence

BOS/CHoCH signals are INCLUDED (re-enabled after accuracy fix).
"""

from ict.weights.dynamic_weight_adjuster import (
    TIER_MULTIPLIERS,
    TIER_THRESHOLDS,
    DynamicWeightAdjuster,
    DynamicWeightResult,
    WeightedSignal,
    WeightTier,
    get_weight_adjuster,
)


# Mock Layer1Score for testing
class MockLayer1Score:
    """Mock Layer1Score for testing weight adjustment."""

    def __init__(
        self,
        signal_type: str,
        timestamp: float | None = None,
        direction: str = "bullish",
        strength: float = 0.8,
    ):
        self.signal_type = signal_type
        self.timestamp = timestamp
        self.direction = direction
        self.strength = strength
        self.weighted_score = strength
        self.confidence = 0.75

    def to_dict(self):
        return {
            "signal_type": self.signal_type,
            "timestamp": self.timestamp,
            "direction": self.direction,
        }


class TestWeightTier:
    """Test suite for WeightTier enum."""

    def test_tier_values(self):
        """Test WeightTier enum values."""
        assert WeightTier.RECENT.value == "recent"
        assert WeightTier.STALE.value == "stale"
        assert WeightTier.OLD.value == "old"
        assert WeightTier.EXCLUDED.value == "excluded"

    def test_tier_thresholds(self):
        """Test tier thresholds are correctly defined."""
        assert TIER_THRESHOLDS[WeightTier.RECENT] == 300  # 5 minutes
        assert TIER_THRESHOLDS[WeightTier.STALE] == 900  # 15 minutes
        assert TIER_THRESHOLDS[WeightTier.OLD] == 1800  # 30 minutes

    def test_tier_multipliers(self):
        """Test tier multipliers match AC."""
        assert TIER_MULTIPLIERS[WeightTier.RECENT] == 1.0
        assert TIER_MULTIPLIERS[WeightTier.STALE] == 0.8
        assert TIER_MULTIPLIERS[WeightTier.OLD] == 0.5
        assert TIER_MULTIPLIERS[WeightTier.EXCLUDED] == 0.0


class TestDynamicWeightAdjuster:
    """Test suite for DynamicWeightAdjuster."""

    def test_initialization(self):
        """Test adjuster initialization with default thresholds."""
        adjuster = DynamicWeightAdjuster()

        assert adjuster.recent_threshold == 300  # 5 minutes
        assert adjuster.stale_threshold == 900  # 15 minutes
        assert adjuster.old_threshold == 1800  # 30 minutes

    def test_initialization_custom_thresholds(self):
        """Test adjuster initialization with custom thresholds."""
        adjuster = DynamicWeightAdjuster(
            recent_threshold_seconds=600,  # 10 minutes
            stale_threshold_seconds=1200,  # 20 minutes
            old_threshold_seconds=2400,  # 40 minutes
        )

        assert adjuster.recent_threshold == 600
        assert adjuster.stale_threshold == 1200
        assert adjuster.old_threshold == 2400

    def test_get_tier_for_age_recent(self):
        """Test RECENT tier for signals 0-5 minutes old."""
        adjuster = DynamicWeightAdjuster()

        assert adjuster.get_tier_for_age(0) == WeightTier.RECENT
        assert adjuster.get_tier_for_age(60) == WeightTier.RECENT
        assert adjuster.get_tier_for_age(299) == WeightTier.RECENT

    def test_get_tier_for_age_stale(self):
        """Test STALE tier for signals 5-15 minutes old."""
        adjuster = DynamicWeightAdjuster()

        assert adjuster.get_tier_for_age(300) == WeightTier.STALE
        assert adjuster.get_tier_for_age(600) == WeightTier.STALE
        assert adjuster.get_tier_for_age(899) == WeightTier.STALE

    def test_get_tier_for_age_old(self):
        """Test OLD tier for signals 15-30 minutes old."""
        adjuster = DynamicWeightAdjuster()

        assert adjuster.get_tier_for_age(900) == WeightTier.OLD
        assert adjuster.get_tier_for_age(1500) == WeightTier.OLD
        assert adjuster.get_tier_for_age(1799) == WeightTier.OLD

    def test_get_tier_for_age_excluded(self):
        """Test EXCLUDED tier for signals older than 30 minutes."""
        adjuster = DynamicWeightAdjuster()

        assert adjuster.get_tier_for_age(1800) == WeightTier.EXCLUDED
        assert adjuster.get_tier_for_age(3600) == WeightTier.EXCLUDED
        assert adjuster.get_tier_for_age(7200) == WeightTier.EXCLUDED

    def test_get_tier_for_age_future_timestamp(self):
        """Test that future timestamps are treated as RECENT."""
        adjuster = DynamicWeightAdjuster()
        assert adjuster.get_tier_for_age(-60) == WeightTier.RECENT

    def test_get_multiplier_for_tier(self):
        """Test multiplier retrieval for each tier."""
        adjuster = DynamicWeightAdjuster()

        assert adjuster.get_multiplier_for_tier(WeightTier.RECENT) == 1.0
        assert adjuster.get_multiplier_for_tier(WeightTier.STALE) == 0.8
        assert adjuster.get_multiplier_for_tier(WeightTier.OLD) == 0.5
        assert adjuster.get_multiplier_for_tier(WeightTier.EXCLUDED) == 0.0

    def test_get_multiplier_for_age(self):
        """Test multiplier retrieval by age."""
        adjuster = DynamicWeightAdjuster()

        assert adjuster.get_multiplier_for_age(0) == 1.0  # Recent
        assert adjuster.get_multiplier_for_age(300) == 0.8  # Stale
        assert adjuster.get_multiplier_for_age(900) == 0.5  # Old
        assert adjuster.get_multiplier_for_age(1800) == 0.0  # Excluded

    def test_calculate_effective_weight_recent(self):
        """Test effective weight calculation for recent signals."""
        adjuster = DynamicWeightAdjuster()

        weight, tier, included = adjuster.calculate_effective_weight(1.0, 60)

        assert weight == 1.0
        assert tier == WeightTier.RECENT
        assert included is True

    def test_calculate_effective_weight_stale(self):
        """Test effective weight calculation for stale signals (0.8x)."""
        adjuster = DynamicWeightAdjuster()

        weight, tier, included = adjuster.calculate_effective_weight(1.0, 600)

        assert weight == 0.8  # 1.0 * 0.8
        assert tier == WeightTier.STALE
        assert included is True

    def test_calculate_effective_weight_old(self):
        """Test effective weight calculation for old signals (0.5x)."""
        adjuster = DynamicWeightAdjuster()

        weight, tier, included = adjuster.calculate_effective_weight(1.0, 1200)

        assert weight == 0.5  # 1.0 * 0.5
        assert tier == WeightTier.OLD
        assert included is True

    def test_calculate_effective_weight_excluded(self):
        """Test effective weight calculation for excluded signals."""
        adjuster = DynamicWeightAdjuster()

        weight, tier, included = adjuster.calculate_effective_weight(1.0, 3600)

        assert weight == 0.0
        assert tier == WeightTier.EXCLUDED
        assert included is False

    def test_calculate_effective_weight_with_base_weight(self):
        """Test effective weight with different base weights."""
        adjuster = DynamicWeightAdjuster()

        # CVD/FVG with base weight 1.0, stale (0.8x)
        weight, _, _ = adjuster.calculate_effective_weight(1.0, 600)
        assert weight == 0.8

        # Order Block with base weight 0.85, stale (0.8x)
        weight, _, _ = adjuster.calculate_effective_weight(0.85, 600)
        assert weight == 0.68  # 0.85 * 0.8

    def test_adjust_weights_empty_list(self):
        """Test adjust_weights with empty list."""
        adjuster = DynamicWeightAdjuster()
        result = adjuster.adjust_weights([])

        assert len(result.weighted_signals) == 0
        assert len(result.included_signals) == 0
        assert len(result.excluded_signals) == 0

    def test_adjust_weights_all_recent(self):
        """Test adjust_weights with all recent signals."""
        adjuster = DynamicWeightAdjuster()
        current_time = 10000.0

        scores = [
            MockLayer1Score("cvd", timestamp=current_time - 60),  # 1 min old
            MockLayer1Score("fvg", timestamp=current_time - 120),  # 2 min old
            MockLayer1Score("order_block", timestamp=current_time - 180),  # 3 min old
        ]

        result = adjuster.adjust_weights(scores, current_time)

        assert len(result.weighted_signals) == 3
        assert len(result.included_signals) == 3
        assert len(result.excluded_signals) == 0

        # All recent, so multiplier should be 1.0
        for ws in result.included_signals:
            assert ws.dynamic_multiplier == 1.0
            assert ws.tier == WeightTier.RECENT

    def test_adjust_weights_mixed_ages(self):
        """Test adjust_weights with signals across all tiers."""
        adjuster = DynamicWeightAdjuster()
        current_time = 10000.0

        scores = [
            MockLayer1Score("cvd", timestamp=current_time - 60),  # 1 min: RECENT
            MockLayer1Score("fvg", timestamp=current_time - 600),  # 10 min: STALE
            MockLayer1Score(
                "order_block", timestamp=current_time - 1200
            ),  # 20 min: OLD
            MockLayer1Score("cvd", timestamp=current_time - 3600),  # 60 min: EXCLUDED
        ]

        result = adjuster.adjust_weights(scores, current_time)

        assert len(result.weighted_signals) == 4
        assert len(result.included_signals) == 3
        assert len(result.excluded_signals) == 1

        # Check tiers
        recent = [ws for ws in result.weighted_signals if ws.tier == WeightTier.RECENT]
        stale = [ws for ws in result.weighted_signals if ws.tier == WeightTier.STALE]
        old = [ws for ws in result.weighted_signals if ws.tier == WeightTier.OLD]
        excluded = [
            ws for ws in result.weighted_signals if ws.tier == WeightTier.EXCLUDED
        ]

        assert len(recent) == 1
        assert len(stale) == 1
        assert len(old) == 1
        assert len(excluded) == 1

        # Check multipliers
        assert recent[0].dynamic_multiplier == 1.0
        assert stale[0].dynamic_multiplier == 0.8
        assert old[0].dynamic_multiplier == 0.5
        assert excluded[0].dynamic_multiplier == 0.0

    def test_adjust_weights_includes_bos_choch(self):
        """Test that BOS/CHoCH signals are included (re-enabled after accuracy fix)."""
        adjuster = DynamicWeightAdjuster()
        current_time = 10000.0

        scores = [
            MockLayer1Score("bos", timestamp=current_time - 60),
            MockLayer1Score("choc", timestamp=current_time - 60),
            MockLayer1Score("cvd", timestamp=current_time - 60),
        ]

        result = adjuster.adjust_weights(scores, current_time)

        # All three signals should be included
        assert len(result.weighted_signals) == 3
        signal_types = [ws.original_score.signal_type for ws in result.weighted_signals]
        assert "cvd" in signal_types
        assert "bos" in signal_types
        assert "choc" in signal_types

    def test_adjust_weights_aggregate_metrics(self):
        """Test aggregate metrics calculation."""
        adjuster = DynamicWeightAdjuster()
        current_time = 10000.0

        scores = [
            MockLayer1Score(
                "cvd", timestamp=current_time - 60
            ),  # 1 min: 1.0 * 1.0 = 1.0
            MockLayer1Score(
                "fvg", timestamp=current_time - 600
            ),  # 10 min: 1.0 * 0.8 = 0.8
        ]

        result = adjuster.adjust_weights(scores, current_time)

        # Total weight = 1.0 + 0.8 = 1.8
        assert result.total_weight == 1.8
        # Average = (1.0 + 0.8) / 2 = 0.9
        assert result.average_effective_weight == 0.9
        assert result.excluded_count == 0

    def test_adjust_weights_with_no_timestamp(self):
        """Test adjust_weights when signals have no timestamp."""
        adjuster = DynamicWeightAdjuster()

        scores = [
            MockLayer1Score("cvd", timestamp=None),
            MockLayer1Score("fvg", timestamp=None),
        ]

        result = adjuster.adjust_weights(scores)

        # Should treat as recent (age = 0)
        assert len(result.included_signals) == 2
        for ws in result.included_signals:
            assert ws.tier == WeightTier.RECENT

    def test_get_tier_info(self):
        """Test get_tier_info returns correct configuration."""
        adjuster = DynamicWeightAdjuster()
        info = adjuster.get_tier_info()

        assert "tiers" in info
        assert "configured_thresholds" in info

        assert info["tiers"]["recent"]["multiplier"] == 1.0
        assert info["tiers"]["stale"]["multiplier"] == 0.8
        assert info["tiers"]["old"]["multiplier"] == 0.5
        assert info["tiers"]["excluded"]["multiplier"] == 0.0


class TestWeightedSignal:
    """Test suite for WeightedSignal dataclass."""

    def test_weighted_signal_creation(self):
        """Test creating a WeightedSignal."""
        mock_score = MockLayer1Score("cvd", timestamp=10000)

        ws = WeightedSignal(
            original_score=mock_score,
            tier=WeightTier.RECENT,
            age_seconds=60.0,
            base_weight=1.0,
            dynamic_multiplier=1.0,
            effective_weight=1.0,
            is_included=True,
        )

        assert ws.original_score.signal_type == "cvd"
        assert ws.tier == WeightTier.RECENT
        assert ws.age_seconds == 60.0
        assert ws.effective_weight == 1.0
        assert ws.is_included is True


class TestDynamicWeightResult:
    """Test suite for DynamicWeightResult dataclass."""

    def test_result_to_dict(self):
        """Test DynamicWeightResult serialization."""
        mock_score = MockLayer1Score("cvd", timestamp=10000)

        weighted = WeightedSignal(
            original_score=mock_score,
            tier=WeightTier.RECENT,
            age_seconds=60.0,
            base_weight=1.0,
            dynamic_multiplier=1.0,
            effective_weight=1.0,
            is_included=True,
        )

        result = DynamicWeightResult(
            weighted_signals=[weighted],
            included_signals=[weighted],
            excluded_signals=[],
            average_effective_weight=1.0,
            total_weight=1.0,
            excluded_count=0,
        )

        data = result.to_dict()

        assert data["weighted_signals_count"] == 1
        assert data["included_signals_count"] == 1
        assert data["excluded_signals_count"] == 0
        assert data["average_effective_weight"] == 1.0
        assert data["total_weight"] == 1.0


class TestGetWeightAdjuster:
    """Test suite for get_weight_adjuster singleton."""

    def test_returns_same_instance(self):
        """Test that get_weight_adjuster returns the same instance."""
        adjuster1 = get_weight_adjuster()
        adjuster2 = get_weight_adjuster()

        assert adjuster1 is adjuster2

    def test_instance_is_correct_type(self):
        """Test that returned instance is DynamicWeightAdjuster."""
        adjuster = get_weight_adjuster()
        assert isinstance(adjuster, DynamicWeightAdjuster)


class TestEdgeCases:
    """Test edge cases for dynamic weight adjustment."""

    def test_boundary_5_minutes(self):
        """Test boundary at exactly 5 minutes (300 seconds)."""
        adjuster = DynamicWeightAdjuster()

        # Just under 5 minutes = RECENT
        assert adjuster.get_tier_for_age(299) == WeightTier.RECENT
        # Exactly 5 minutes = STALE
        assert adjuster.get_tier_for_age(300) == WeightTier.STALE

    def test_boundary_15_minutes(self):
        """Test boundary at exactly 15 minutes (900 seconds)."""
        adjuster = DynamicWeightAdjuster()

        # Just under 15 minutes = STALE
        assert adjuster.get_tier_for_age(899) == WeightTier.STALE
        # Exactly 15 minutes = OLD
        assert adjuster.get_tier_for_age(900) == WeightTier.OLD

    def test_boundary_30_minutes(self):
        """Test boundary at exactly 30 minutes (1800 seconds)."""
        adjuster = DynamicWeightAdjuster()

        # Just under 30 minutes = OLD
        assert adjuster.get_tier_for_age(1799) == WeightTier.OLD
        # Exactly 30 minutes = EXCLUDED
        assert adjuster.get_tier_for_age(1800) == WeightTier.EXCLUDED

    def test_zero_age(self):
        """Test zero age signals (just created)."""
        adjuster = DynamicWeightAdjuster()

        weight, tier, included = adjuster.calculate_effective_weight(1.0, 0)

        assert weight == 1.0
        assert tier == WeightTier.RECENT
        assert included is True

    def test_very_large_age(self):
        """Test very old signals (e.g., hours old)."""
        adjuster = DynamicWeightAdjuster()

        # 1 hour old
        weight, tier, included = adjuster.calculate_effective_weight(1.0, 3600)
        assert weight == 0.0
        assert tier == WeightTier.EXCLUDED
        assert included is False

        # 1 day old
        weight, tier, included = adjuster.calculate_effective_weight(1.0, 86400)
        assert weight == 0.0
        assert tier == WeightTier.EXCLUDED
        assert included is False

    def test_very_small_base_weight(self):
        """Test signals with very small base weights."""
        adjuster = DynamicWeightAdjuster()

        # Small but valid weight
        weight, _, _ = adjuster.calculate_effective_weight(0.01, 60)
        assert weight == 0.01  # 0.01 * 1.0

        # Stale signal with small weight
        weight, _, _ = adjuster.calculate_effective_weight(0.01, 600)
        assert weight == 0.008  # 0.01 * 0.8

    def test_all_signal_types(self):
        """Test all supported signal types have valid weights."""
        adjuster = DynamicWeightAdjuster()

        for signal_type in ["cvd", "fvg", "order_block"]:
            scores = [MockLayer1Score(signal_type, timestamp=10000)]
            result = adjuster.adjust_weights(scores, 10060)

            assert len(result.weighted_signals) == 1
            assert result.weighted_signals[0].is_included is True
