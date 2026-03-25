"""Smart Mitigation Tracker for Order Blocks.

Tracks when price returns to and mitigates order block zones.
Mitigation occurs when price enters the OB zone after its formation.

Usage:
    from src.market_analysis.order_block import MitigationTracker

    tracker = MitigationTracker()
    tracker.update(current_price, order_blocks)
"""

from dataclasses import dataclass
from datetime import datetime

from src.market_analysis.order_block.ob_detector import OBDetectionResult, OBPolaridade
from src.market_analysis.zones import Zone


@dataclass
class MitigationEvent:
    """Record of a mitigation event.

    Attributes:
        timestamp: When mitigation occurred
        price: Price at mitigation
        ob_result: The OB that was mitigated
        mitigation_type: Type of mitigation
    """

    timestamp: datetime
    price: float
    ob_result: OBDetectionResult
    mitigation_type: str  # "full", "partial", "invalidated"


class MitigationTracker:
    """Tracks mitigation of order blocks.

    Smart mitigation detection identifies when price returns to an OB zone
    and tests/mitigates it. The tracker maintains state about which OBs
    have been tested or mitigated.

    Mitigation rules:
    - FULL_MITIGATION: Price closes beyond the OB zone in the opposite direction
    - TESTED: Price enters OB zone but reverses
    - INVALIDATED: Price moves sharply through OB without reaction

    For bullish OBs, mitigation typically occurs when price returns and
    fails to hold, breaking below the OB zone.

    For bearish OBs, mitigation typically occurs when price returns and
    fails to hold, breaking above the OB zone.
    """

    def __init__(self):
        """Initialize mitigation tracker."""
        self._tested_ob_uuids: set[str] = set()
        self._mitigated_ob_uuids: set[str] = set()

    def check_mitigation(
        self,
        current_price: float,
        ob_result: OBDetectionResult,
        current_candle_high: float,
        current_candle_low: float,
        prev_candle_close: float | None = None,
    ) -> tuple[bool, str]:
        """Check if price has mitigated an order block.

        Args:
            current_price: Current price level
            ob_result: The order block to check
            current_candle_high: High of current candle
            current_candle_low: Low of current candle
            prev_candle_close: Previous candle close (for direction confirmation)

        Returns:
            Tuple of (is_mitigated, mitigation_type)
        """
        zone = ob_result.zone
        ob_high = zone.price_range.high
        ob_low = zone.price_range.low
        uuid_str = str(zone.uuid)

        # Check if already fully mitigated
        if uuid_str in self._mitigated_ob_uuids:
            return True, "full"

        # Check if price is within OB zone
        price_in_zone = ob_low <= current_price <= ob_high

        # Check for candle-based mitigation BEFORE price-in-zone check
        # This handles cases where candle breaks through zone boundary
        if ob_result.polarity == OBPolaridade.BULLISH:
            # Bullish OB is mitigated when candle breaks below OB low
            if (
                current_candle_low < ob_low
                or prev_candle_close is not None
                and prev_candle_close < ob_low
            ):
                self._mitigated_ob_uuids.add(uuid_str)
                return True, "full"
        else:  # BEARISH
            # Bearish OB is mitigated when candle breaks above OB high
            if (
                current_candle_high > ob_high
                or prev_candle_close is not None
                and prev_candle_close > ob_high
            ):
                self._mitigated_ob_uuids.add(uuid_str)
                return True, "full"

        # If we get here, no candle-based mitigation occurred
        if not price_in_zone:
            return False, ""

        # Price is in zone - this is just a test, not full mitigation
        if uuid_str not in self._tested_ob_uuids:
            self._tested_ob_uuids.add(uuid_str)
        return False, "tested"

    def check_test(
        self,
        current_price: float,
        ob_result: OBDetectionResult,
    ) -> bool:
        """Check if price has tested (entered) an order block.

        Args:
            current_price: Current price level
            ob_result: The order block to check

        Returns:
            True if price has entered the OB zone
        """
        zone = ob_result.zone
        ob_high = zone.price_range.high
        ob_low = zone.price_range.low

        return ob_low <= current_price <= ob_high

    def is_mitigated(self, ob_result: OBDetectionResult) -> bool:
        """Check if an OB has been fully mitigated.

        Args:
            ob_result: The order block to check

        Returns:
            True if OB has been fully mitigated
        """
        return str(ob_result.zone.uuid) in self._mitigated_ob_uuids

    def is_tested(self, ob_result: OBDetectionResult) -> bool:
        """Check if an OB has been tested (price entered zone).

        Args:
            ob_result: The order block to check

        Returns:
            True if OB has been tested
        """
        return str(ob_result.zone.uuid) in self._tested_ob_uuids

    def mark_invalidated(self, ob_result: OBDetectionResult) -> None:
        """Mark an order block as invalidated.

        Use when price moves through OB without any reaction,
        indicating the institutional order may have been filled already.

        Args:
            ob_result: The order block to invalidate
        """
        uuid_str = str(ob_result.zone.uuid)
        self._mitigated_ob_uuids.add(uuid_str)
        self._tested_ob_uuids.discard(uuid_str)

    def reset(self) -> None:
        """Reset all tracking state."""
        self._tested_ob_uuids.clear()
        self._mitigated_ob_uuids.clear()


def determine_mitigation_outcome(
    ob_result: OBDetectionResult,
    entry_price: float,
    exit_price: float,
    zone: Zone,
) -> str:
    """Determine the mitigation outcome for an OB zone.

    Args:
        ob_result: The order block that was hit
        entry_price: Price when zone was entered
        exit_price: Price when zone was exited
        zone: The zone that was hit

    Returns:
        Outcome string: "full", "partial", or "invalidated"
    """
    ob_high = zone.price_range.high
    ob_low = zone.price_range.low

    if ob_result.polarity == OBPolaridade.BULLISH:
        # For bullish OB: full mitigation if price closes below OB low
        # or if price drops significantly below entry
        if exit_price < ob_low:
            return "full"
        elif exit_price < entry_price * 0.995:  # 0.5% drop from entry
            return "partial"
        else:
            return "invalidated"
    else:  # BEARISH
        # For bearish OB: full mitigation if price closes above OB high
        # or if price rises significantly above entry
        if exit_price > ob_high:
            return "full"
        elif exit_price > entry_price * 1.005:  # 0.5% rise from entry
            return "partial"
        else:
            return "invalidated"
