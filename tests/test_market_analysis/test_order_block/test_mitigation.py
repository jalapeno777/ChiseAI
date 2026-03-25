"""Tests for Order Block Mitigation Tracker.

Tests smart mitigation detection, testing vs full mitigation,
and OB lifecycle tracking.
"""

from dataclasses import dataclass
from datetime import datetime

import pytest
from src.market_analysis.order_block import (
    OBDetectionResult,
    OBPolaridade,
)
from src.market_analysis.order_block.mitigation_tracker import (
    MitigationTracker,
    determine_mitigation_outcome,
)
from src.market_analysis.zones import Zone, ZoneType
from src.market_analysis.zones.zone_models import PriceRange


@dataclass
class MockOHLCV:
    """Mock OHLCV candle for testing."""

    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float = 0.0
    token: str = "BTC/USDT"
    timeframe: str = "1H"


def create_mock_ob(
    polarity: OBPolaridade, high: float = 105.0, low: float = 100.0
) -> OBDetectionResult:
    """Create a mock OB detection result for testing."""
    zone = Zone(
        zone_type=ZoneType.OB,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=high, low=low),
    )
    return OBDetectionResult(
        polarity=polarity,
        zone=zone,
        anchor_candle_index=1,
        momentum_candle_index=2,
        strength_score=0.8,
        volume_confirmed=False,
    )


class TestMitigationDetection:
    """Tests for mitigation detection logic."""

    def test_price_enters_bullish_ob_zone(self):
        """Test detection when price enters bullish OB zone."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        # Price in zone
        is_mitigated, mit_type = tracker.check_mitigation(
            current_price=102.0,
            ob_result=ob,
            current_candle_high=103.0,
            current_candle_low=101.0,
        )

        assert is_mitigated is False
        # When price enters the zone but doesn't break out, it's a "test"
        assert mit_type == "tested"

    def test_bullish_ob_full_mitigation_below_low(self):
        """Test full mitigation when price closes below bullish OB."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        # Price breaks below zone
        is_mitigated, mit_type = tracker.check_mitigation(
            current_price=99.0,
            ob_result=ob,
            current_candle_high=100.0,
            current_candle_low=98.0,
        )

        assert is_mitigated is True
        assert mit_type == "full"

    def test_bearish_ob_full_mitigation_above_high(self):
        """Test full mitigation when price closes above bearish OB."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BEARISH, high=105.0, low=100.0)

        # Price breaks above zone
        is_mitigated, mit_type = tracker.check_mitigation(
            current_price=106.0,
            ob_result=ob,
            current_candle_high=107.0,
            current_candle_low=105.0,
        )

        assert is_mitigated is True
        assert mit_type == "full"

    def test_bullish_ob_mitigation_with_prev_close(self):
        """Test bullish OB mitigation with previous candle close."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        # Price not currently in zone but prev close was below
        is_mitigated, mit_type = tracker.check_mitigation(
            current_price=102.0,
            ob_result=ob,
            current_candle_high=103.0,
            current_candle_low=101.0,
            prev_candle_close=99.0,
        )

        assert is_mitigated is True
        assert mit_type == "full"

    def test_bearish_ob_mitigation_with_prev_close(self):
        """Test bearish OB mitigation with previous candle close."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BEARISH, high=105.0, low=100.0)

        # Price not currently in zone but prev close was above
        is_mitigated, mit_type = tracker.check_mitigation(
            current_price=102.0,
            ob_result=ob,
            current_candle_high=103.0,
            current_candle_low=101.0,
            prev_candle_close=106.0,
        )

        assert is_mitigated is True
        assert mit_type == "full"


class TestMitigationTrackerState:
    """Tests for mitigation tracker state management."""

    def test_tracker_remembers_mitigated_ob(self):
        """Test that tracker remembers mitigated OBs."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        # First check - breaks below
        tracker.check_mitigation(
            current_price=99.0,
            ob_result=ob,
            current_candle_high=100.0,
            current_candle_low=98.0,
        )

        assert tracker.is_mitigated(ob) is True

    def test_tracker_remembers_tested_ob(self):
        """Test that tracker remembers tested (but not mitigated) OBs."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        # Price enters zone but doesn't break
        tracker.check_mitigation(
            current_price=102.0,
            ob_result=ob,
            current_candle_high=103.0,
            current_candle_low=101.0,
        )

        assert tracker.is_tested(ob) is True
        assert tracker.is_mitigated(ob) is False

    def test_tracker_can_mark_invalidated(self):
        """Test marking an OB as invalidated."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        tracker.mark_invalidated(ob)

        assert tracker.is_mitigated(ob) is True

    def test_tracker_reset_clears_state(self):
        """Test that reset clears all tracking state."""
        tracker = MitigationTracker()
        ob1 = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)
        ob2 = create_mock_ob(OBPolaridade.BEARISH, high=205.0, low=200.0)

        # Mark some as mitigated
        tracker.check_mitigation(
            current_price=99.0,
            ob_result=ob1,
            current_candle_high=100.0,
            current_candle_low=98.0,
        )
        tracker.check_mitigation(
            current_price=206.0,
            ob_result=ob2,
            current_candle_high=207.0,
            current_candle_low=205.0,
        )

        assert tracker.is_mitigated(ob1) is True
        assert tracker.is_mitigated(ob2) is True

        tracker.reset()

        assert tracker.is_mitigated(ob1) is False
        assert tracker.is_mitigated(ob2) is False


class TestMitigationOutcome:
    """Tests for mitigation outcome determination."""

    def test_full_mitigation_bullish_ob(self):
        """Test full mitigation determination for bullish OB."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        outcome = determine_mitigation_outcome(
            ob_result=ob,
            entry_price=102.0,
            exit_price=99.0,
            zone=zone,
        )

        assert outcome == "full"

    def test_partial_mitigation_bullish_ob(self):
        """Test partial mitigation determination for bullish OB."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        outcome = determine_mitigation_outcome(
            ob_result=ob,
            entry_price=102.0,
            exit_price=101.4,  # ~0.6% drop - below 0.5% threshold for partial
            zone=zone,
        )

        assert outcome == "partial"

    def test_full_mitigation_bearish_ob(self):
        """Test full mitigation determination for bearish OB."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )
        ob = create_mock_ob(OBPolaridade.BEARISH, high=105.0, low=100.0)

        outcome = determine_mitigation_outcome(
            ob_result=ob,
            entry_price=102.0,
            exit_price=106.0,
            zone=zone,
        )

        assert outcome == "full"

    def test_invalidated_bullish_ob(self):
        """Test invalidated determination for bullish OB."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        outcome = determine_mitigation_outcome(
            ob_result=ob,
            entry_price=102.0,
            exit_price=103.0,  # Price stays in zone, reverses up
            zone=zone,
        )

        assert outcome == "invalidated"


class TestCheckTest:
    """Tests for simple zone entry testing (without mitigation direction)."""

    def test_check_test_returns_true_when_price_in_zone(self):
        """Test check_test returns True when price is in zone."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        result = tracker.check_test(current_price=102.0, ob_result=ob)

        assert result is True

    def test_check_test_returns_false_when_price_outside_zone(self):
        """Test check_test returns False when price is outside zone."""
        tracker = MitigationTracker()
        ob = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)

        result = tracker.check_test(current_price=95.0, ob_result=ob)

        assert result is False


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    def test_order_block_lifecycle(self):
        """Test complete OB lifecycle: detect -> test -> mitigate."""
        # Create bullish OB
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )
        ob = OBDetectionResult(
            polarity=OBPolaridade.BULLISH,
            zone=zone,
            anchor_candle_index=1,
            momentum_candle_index=2,
            strength_score=0.8,
            volume_confirmed=False,
        )

        tracker = MitigationTracker()

        # Phase 1: OB forms and price moves away
        assert tracker.is_mitigated(ob) is False
        assert tracker.is_tested(ob) is False

        # Phase 2: Price returns to zone (test)
        is_mitigated, mit_type = tracker.check_mitigation(
            current_price=102.0,
            ob_result=ob,
            current_candle_high=104.0,
            current_candle_low=101.5,
        )
        assert is_mitigated is False
        assert tracker.is_tested(ob) is True

        # Phase 3: Price breaks below zone (full mitigation)
        is_mitigated, mit_type = tracker.check_mitigation(
            current_price=99.0,
            ob_result=ob,
            current_candle_high=100.5,
            current_candle_low=98.5,
        )
        assert is_mitigated is True
        assert mit_type == "full"
        assert tracker.is_mitigated(ob) is True

    def test_multiple_obs_tracked_simultaneously(self):
        """Test tracking multiple OBs at once."""
        tracker = MitigationTracker()
        ob1 = create_mock_ob(OBPolaridade.BULLISH, high=105.0, low=100.0)
        ob2 = create_mock_ob(OBPolaridade.BEARISH, high=205.0, low=200.0)

        # Mitigate only ob1
        tracker.check_mitigation(
            current_price=99.0,
            ob_result=ob1,
            current_candle_high=100.0,
            current_candle_low=98.0,
        )

        assert tracker.is_mitigated(ob1) is True
        assert tracker.is_mitigated(ob2) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
