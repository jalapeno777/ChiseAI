"""Tests for cross-timeframe zone awareness.

Covers:
- Zone model validation and properties
- Timeframe weight application (AC2)
- Multi-timeframe aggregation (AC1)
- Confluence detection (AC3)
- Performance within 20ms (AC4)
"""

from __future__ import annotations

import time

import pytest

from ict.timeframe.aggregator import CrossTimeframeAggregator
from ict.timeframe.models import (
    TIMEFRAME_WEIGHTS,
    ConfluenceGroup,
    CrossTimeframeResult,
    Timeframe,
    WeightedZone,
    Zone,
    ZoneType,
    ZONE_MATCH_THRESHOLD_PCT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zone(
    zone_type: ZoneType = ZoneType.DEMAND,
    timeframe: Timeframe = Timeframe.M15,
    price_mid: float = 100.0,
    width: float = 0.5,
    strength: float = 0.8,
    source: str = "test",
) -> Zone:
    """Create a Zone with a given midpoint and width."""
    half = width / 2.0
    return Zone(
        zone_type=zone_type,
        timeframe=timeframe,
        price_high=price_mid + half,
        price_low=price_mid - half,
        strength=strength,
        source=source,
    )


# ---------------------------------------------------------------------------
# Zone model tests
# ---------------------------------------------------------------------------


class TestZoneModel:
    """Tests for Zone dataclass."""

    def test_valid_zone(self) -> None:
        zone = _make_zone()
        assert zone.zone_type == ZoneType.DEMAND
        assert zone.timeframe == Timeframe.M15
        assert zone.midpoint == 100.0

    def test_invalid_price_range(self) -> None:
        with pytest.raises(ValueError, match="price_high"):
            Zone(
                zone_type=ZoneType.DEMAND,
                timeframe=Timeframe.M15,
                price_high=90.0,
                price_low=100.0,
            )

    def test_invalid_strength(self) -> None:
        with pytest.raises(ValueError, match="strength"):
            _make_zone(strength=1.5)
        with pytest.raises(ValueError, match="strength"):
            _make_zone(strength=-0.1)

    def test_midpoint(self) -> None:
        zone = _make_zone(price_mid=200.0, width=2.0)
        assert zone.midpoint == 200.0

    def test_width_pct(self) -> None:
        zone = _make_zone(price_mid=100.0, width=1.0)
        assert zone.width_pct == pytest.approx(1.0)

    def test_directional_type_bullish(self) -> None:
        for zt in [ZoneType.DEMAND, ZoneType.ORDER_BLOCK_BULL, ZoneType.FVG_BULL]:
            zone = _make_zone(zone_type=zt)
            assert zone.directional_type == "bullish"

    def test_directional_type_bearish(self) -> None:
        for zt in [ZoneType.SUPPLY, ZoneType.ORDER_BLOCK_BEAR, ZoneType.FVG_BEAR]:
            zone = _make_zone(zone_type=zt)
            assert zone.directional_type == "bearish"

    def test_directional_type_neutral(self) -> None:
        zone = _make_zone(zone_type=ZoneType.EQUILIBRIUM)
        assert zone.directional_type == "neutral"

    def test_overlaps(self) -> None:
        a = _make_zone(price_mid=100.0, width=2.0)
        b = _make_zone(price_mid=101.0, width=2.0)
        assert a.overlaps(b)

    def test_no_overlap(self) -> None:
        a = _make_zone(price_mid=100.0, width=0.5)
        b = _make_zone(price_mid=200.0, width=0.5)
        assert not a.overlaps(b)

    def test_is_similar_to_same_type_nearby(self) -> None:
        a = _make_zone(zone_type=ZoneType.DEMAND, price_mid=100.0)
        b = _make_zone(zone_type=ZoneType.DEMAND, price_mid=100.1)
        assert a.is_similar_to(b)

    def test_is_similar_to_different_type(self) -> None:
        a = _make_zone(zone_type=ZoneType.DEMAND, price_mid=100.0)
        b = _make_zone(zone_type=ZoneType.SUPPLY, price_mid=100.0)
        assert not a.is_similar_to(b)

    def test_is_similar_to_far_away(self) -> None:
        a = _make_zone(zone_type=ZoneType.DEMAND, price_mid=100.0)
        b = _make_zone(zone_type=ZoneType.DEMAND, price_mid=200.0)
        assert not a.is_similar_to(b)

    def test_to_dict(self) -> None:
        zone = _make_zone()
        d = zone.to_dict()
        assert d["zone_type"] == "demand"
        assert d["timeframe"] == "15m"
        assert "midpoint" in d
        assert "directional_type" in d


# ---------------------------------------------------------------------------
# WeightedZone tests
# ---------------------------------------------------------------------------


class TestWeightedZone:
    """Tests for WeightedZone dataclass."""

    def test_weight_applied(self) -> None:
        zone = _make_zone(strength=0.8)
        wz = WeightedZone(zone=zone, timeframe_weight=2.0)
        assert wz.weighted_strength == pytest.approx(1.6)

    def test_default_weight(self) -> None:
        zone = _make_zone(strength=0.5)
        wz = WeightedZone(zone=zone, timeframe_weight=1.0)
        assert wz.weighted_strength == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Timeframe weight tests (AC2)
# ---------------------------------------------------------------------------


class TestTimeframeWeights:
    """Tests for timeframe weight assignments.

    AC2: Higher timeframe zones receive higher weight.
    - 1h zone = 2x 15m zone weight
    """

    def test_h1_weight_is_2x_m15(self) -> None:
        assert TIMEFRAME_WEIGHTS[Timeframe.H1] == pytest.approx(
            2.0 * TIMEFRAME_WEIGHTS[Timeframe.M15]
        )

    def test_h4_weight_is_4x_m15(self) -> None:
        assert TIMEFRAME_WEIGHTS[Timeframe.H4] == pytest.approx(
            4.0 * TIMEFRAME_WEIGHTS[Timeframe.M15]
        )

    def test_weight_ordering(self) -> None:
        """Weights must increase monotonically with timeframe."""
        tfs = [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4]
        weights = [TIMEFRAME_WEIGHTS[tf] for tf in tfs]
        for i in range(len(weights) - 1):
            assert weights[i] < weights[i + 1], (
                f"{tfs[i].value} weight ({weights[i]}) should be < "
                f"{tfs[i + 1].value} weight ({weights[i + 1]})"
            )

    def test_custom_weights(self) -> None:
        agg = CrossTimeframeAggregator(
            timeframe_weights={Timeframe.M15: 5.0, Timeframe.H1: 10.0}
        )
        zone = _make_zone(timeframe=Timeframe.H1, strength=0.5)
        result = agg.aggregate([zone])
        assert result.weighted_zones[0].timeframe_weight == 10.0


# ---------------------------------------------------------------------------
# Multi-timeframe aggregation tests (AC1)
# ---------------------------------------------------------------------------


class TestMultiTimeframeAggregation:
    """Tests for aggregating zones across multiple timeframes.

    AC1: Aggregate zones across 1m, 5m, 15m, 1h, 4h timeframes.
    """

    def test_aggregate_all_five_timeframes(self) -> None:
        zones = [
            _make_zone(timeframe=Timeframe.M1, price_mid=100.0),
            _make_zone(timeframe=Timeframe.M5, price_mid=100.0),
            _make_zone(timeframe=Timeframe.M15, price_mid=100.0),
            _make_zone(timeframe=Timeframe.H1, price_mid=100.0),
            _make_zone(timeframe=Timeframe.H4, price_mid=100.0),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)

        assert result.zone_count == 5
        # All zones should have weights applied
        assert len(result.weighted_zones) == 5
        # Verify each timeframe has correct weight
        for wz in result.weighted_zones:
            assert wz.timeframe_weight == TIMEFRAME_WEIGHTS[wz.timeframe]

    def test_aggregate_empty_zones(self) -> None:
        agg = CrossTimeframeAggregator()
        result = agg.aggregate([])
        assert result.zone_count == 0
        assert result.confluence_count == 0
        assert result.dominant_zone_type is None
        assert result.dominant_direction == "neutral"

    def test_aggregate_single_timeframe(self) -> None:
        zones = [
            _make_zone(timeframe=Timeframe.H1, zone_type=ZoneType.SUPPLY),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.zone_count == 1
        assert result.dominant_zone_type == ZoneType.SUPPLY
        assert result.dominant_direction == "bearish"

    def test_aggregate_mixed_types(self) -> None:
        zones = [
            _make_zone(zone_type=ZoneType.DEMAND, timeframe=Timeframe.H1, strength=0.9),
            _make_zone(
                zone_type=ZoneType.SUPPLY, timeframe=Timeframe.M15, strength=0.5
            ),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        # H1 demand (0.9 * 2.0 = 1.8) > M15 supply (0.5 * 1.0 = 0.5)
        assert result.dominant_zone_type == ZoneType.DEMAND
        assert result.dominant_direction == "bullish"

    def test_total_weighted_strength(self) -> None:
        zones = [
            _make_zone(timeframe=Timeframe.M15, strength=0.5),
            _make_zone(timeframe=Timeframe.H1, strength=0.5),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        # M15: 0.5 * 1.0 = 0.5, H1: 0.5 * 2.0 = 1.0
        assert result.total_weighted_strength == pytest.approx(1.5)

    def test_result_serialization(self) -> None:
        zones = [_make_zone()]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        d = result.to_dict()
        assert "weighted_zones" in d
        assert "confluence_groups" in d
        assert "dominant_zone_type" in d
        assert "calculation_time_ms" in d


# ---------------------------------------------------------------------------
# Confluence detection tests (AC3)
# ---------------------------------------------------------------------------


class TestConfluenceDetection:
    """Tests for multi-timeframe confluence detection.

    AC3: Detect confluence when multiple timeframes show same zone type.
    """

    def test_confluence_two_timeframes_same_zone(self) -> None:
        """Two timeframes with same zone type at same price = confluence."""
        zones = [
            _make_zone(
                zone_type=ZoneType.DEMAND,
                timeframe=Timeframe.M15,
                price_mid=100.0,
            ),
            _make_zone(
                zone_type=ZoneType.DEMAND,
                timeframe=Timeframe.H1,
                price_mid=100.1,  # Within 0.3% threshold
            ),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.confluence_count >= 1

        # Find the demand confluence group
        demand_groups = [
            g for g in result.confluence_groups if g.zone_type == ZoneType.DEMAND
        ]
        assert len(demand_groups) == 1
        group = demand_groups[0]
        assert group.has_confluence
        assert group.count == 2
        assert Timeframe.M15 in group.timeframes
        assert Timeframe.H1 in group.timeframes

    def test_confluence_three_timeframes(self) -> None:
        """Three timeframes with same zone = stronger confluence."""
        zones = [
            _make_zone(
                zone_type=ZoneType.ORDER_BLOCK_BULL,
                timeframe=Timeframe.M5,
                price_mid=150.0,
            ),
            _make_zone(
                zone_type=ZoneType.ORDER_BLOCK_BULL,
                timeframe=Timeframe.M15,
                price_mid=150.05,
            ),
            _make_zone(
                zone_type=ZoneType.ORDER_BLOCK_BULL,
                timeframe=Timeframe.H1,
                price_mid=149.9,
            ),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.confluence_count >= 1

        ob_groups = [
            g
            for g in result.confluence_groups
            if g.zone_type == ZoneType.ORDER_BLOCK_BULL
        ]
        assert len(ob_groups) == 1
        assert ob_groups[0].count == 3
        assert ob_groups[0].has_confluence

    def test_no_confluence_different_types(self) -> None:
        """Different zone types should NOT produce confluence."""
        zones = [
            _make_zone(zone_type=ZoneType.DEMAND, timeframe=Timeframe.H1),
            _make_zone(zone_type=ZoneType.SUPPLY, timeframe=Timeframe.M15),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.confluence_count == 0

    def test_no_confluence_same_type_far_apart(self) -> None:
        """Same zone type but far apart in price = no confluence."""
        zones = [
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.H1, price_mid=100.0
            ),
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.M15, price_mid=200.0
            ),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.confluence_count == 0

    def test_confluence_highest_timeframe(self) -> None:
        """Confluence group should report highest timeframe."""
        zones = [
            _make_zone(
                zone_type=ZoneType.FVG_BULL, timeframe=Timeframe.M5, price_mid=100.0
            ),
            _make_zone(
                zone_type=ZoneType.FVG_BULL, timeframe=Timeframe.H4, price_mid=100.1
            ),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        fvg_groups = [
            g for g in result.confluence_groups if g.zone_type == ZoneType.FVG_BULL
        ]
        assert len(fvg_groups) == 1
        assert fvg_groups[0].highest_timeframe == Timeframe.H4

    def test_confluence_group_serialization(self) -> None:
        zones = [
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.M15, price_mid=100.0
            ),
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.H1, price_mid=100.1
            ),
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        d = result.to_dict()
        assert len(d["confluence_groups"]) >= 1
        cg = d["confluence_groups"][0]
        assert "has_confluence" in cg
        assert "highest_timeframe" in cg
        assert "count" in cg


# ---------------------------------------------------------------------------
# Performance tests (AC4)
# ---------------------------------------------------------------------------


class TestPerformance:
    """Tests for cross-timeframe resolution within 20ms.

    AC4: Cross-timeframe resolution within 20ms.
    """

    def test_small_input_under_20ms(self) -> None:
        """Small input (5 zones) should be well under 20ms."""
        zones = [_make_zone(timeframe=tf, price_mid=100.0) for tf in Timeframe]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.calculation_time_ms < 20.0

    def test_medium_input_under_20ms(self) -> None:
        """Medium input (50 zones across 5 TFs) should be under 20ms."""
        zones = []
        for tf in Timeframe:
            for i in range(10):
                zones.append(
                    _make_zone(
                        zone_type=ZoneType.DEMAND,
                        timeframe=tf,
                        price_mid=100.0 + i * 0.1,
                        strength=0.5 + i * 0.05,
                    )
                )
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.calculation_time_ms < 20.0, (
            f"Aggregation took {result.calculation_time_ms:.2f}ms, expected < 20ms"
        )

    def test_large_input_under_20ms(self) -> None:
        """Large input (100 zones, mixed types) should still be under 20ms."""
        zones = []
        types = list(ZoneType)
        for i in range(100):
            tf = list(Timeframe)[i % len(list(Timeframe))]
            zt = types[i % len(types)]
            zones.append(
                _make_zone(
                    zone_type=zt,
                    timeframe=tf,
                    price_mid=100.0 + (i % 20) * 0.2,
                    strength=0.3 + (i % 10) * 0.07,
                )
            )
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.calculation_time_ms < 20.0, (
            f"Aggregation took {result.calculation_time_ms:.2f}ms, expected < 20ms"
        )

    def test_repeated_calls_consistent_performance(self) -> None:
        """Multiple calls should all be under 20ms."""
        zones = [_make_zone(timeframe=tf, price_mid=100.0) for tf in Timeframe]
        agg = CrossTimeframeAggregator()
        for _ in range(100):
            result = agg.aggregate(zones)
            assert result.calculation_time_ms < 20.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_zero_midpoint_zone(self) -> None:
        """Zone at price 0 should not crash midpoint calculations."""
        zone = _make_zone(price_mid=0.0, width=0.0, strength=0.5)
        assert zone.midpoint == 0.0
        assert zone.width_pct == 0.0

    def test_single_zone_no_confluence(self) -> None:
        """Single zone should not produce confluence."""
        zones = [_make_zone(timeframe=Timeframe.H1)]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.confluence_count == 0

    def test_all_equilibrium_zones(self) -> None:
        """All neutral zones should produce neutral direction."""
        zones = [
            _make_zone(zone_type=ZoneType.EQUILIBRIUM, timeframe=tf) for tf in Timeframe
        ]
        agg = CrossTimeframeAggregator()
        result = agg.aggregate(zones)
        assert result.dominant_direction == "neutral"

    def test_tight_threshold_custom(self) -> None:
        """Custom tight threshold should reduce confluence."""
        zones = [
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.M15, price_mid=100.0
            ),
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.H1, price_mid=100.5
            ),
        ]
        # With default threshold (0.3%), 0.5% apart should NOT match
        agg = CrossTimeframeAggregator(zone_match_threshold_pct=0.1)
        result = agg.aggregate(zones)
        assert result.confluence_count == 0

    def test_wide_threshold_custom(self) -> None:
        """Custom wide threshold should increase confluence."""
        zones = [
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.M15, price_mid=100.0
            ),
            _make_zone(
                zone_type=ZoneType.DEMAND, timeframe=Timeframe.H1, price_mid=105.0
            ),
        ]
        # With 10% threshold, 5% apart should match
        agg = CrossTimeframeAggregator(zone_match_threshold_pct=10.0)
        result = agg.aggregate(zones)
        assert result.confluence_count >= 1
