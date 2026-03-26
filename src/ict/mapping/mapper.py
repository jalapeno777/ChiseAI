"""
Zone-to-Signal Mapper for ICT Trading.

Maps ICT zones (Order Blocks, FVGs, CVD divergence zones) to trading signals
for the confluence pipeline.

Zone Mapping Rules:
    - Order Block (OB) zones → Entry signals
        - Bullish OB (polarity=bullish) → LONG entry signal
        - Bearish OB (polarity=bearish) → SHORT entry signal
    - FVG zones → Continuation signals
        - Bullish FVG → LONG continuation
        - Bearish FVG → SHORT continuation
    - CVD divergence zones → Momentum signals
        - Bullish CVD divergence → LONG momentum
        - Bearish CVD divergence → SHORT momentum

Zone Lifecycle Handling:
    - ACTIVE zones: Full signal generation
    - TESTED zones: Reduced confidence (0.85x multiplier)
    - MITIGATED zones: No signal generation (paused)
    - INVALIDATED zones: No signal generation (removed from consideration)

Performance Target:
    - Zone-to-signal resolution within 10ms

Usage:
    from src.ict.mapping import ZoneSignalMapper

    mapper = ZoneSignalMapper(
        zone_manager=zone_manager,
        zone_storage=zone_storage,
    )
    result = mapper.get_signals(token="BTC/USDT", timeframe="1H", current_price=50000.0)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.ict.mapping.signal_models import (
    ContinuationSignal,
    EntrySignal,
    MomentumSignal,
    SignalDirection,
    SignalResolution,
    ZoneSignalType,
    ZoneToSignalResult,
)
from src.market_analysis.zones.redis_storage import ZoneRedisStorage
from src.market_analysis.zones.zone_manager import ZoneManager
from src.market_analysis.zones.zone_models import Zone, ZoneStatus, ZoneType

if TYPE_CHECKING:
    from src.market_analysis.cvd.cvd_detector import CVDDetectionResult
    from src.market_analysis.fvg.fvg_detector import FVGDetectionResult
    from src.market_analysis.order_block.ob_detector import OBDetectionResult

logger = logging.getLogger(__name__)


# Confidence multipliers based on zone status
ZONE_STATUS_CONFIDENCE_MULTIPLIERS = {
    ZoneStatus.ACTIVE: 1.0,
    ZoneStatus.TESTED: 0.85,  # Reduced confidence for tested zones
    ZoneStatus.MITIGATED: 0.0,  # No signals from mitigated zones
    ZoneStatus.INVALIDATED: 0.0,  # No signals from invalidated zones
}


@dataclass
class ZoneSignalMapper:
    """
    Maps ICT zones to trading signals.

    This mapper retrieves zones from the ZoneManager/ZoneRedisStorage and converts
    them to signals based on zone type and current market conditions.

    Attributes:
        zone_manager: ZoneManager instance for zone CRUD operations
        zone_storage: ZoneRedisStorage instance for direct storage access
        enable_ob_signals: Whether to generate entry signals from Order Blocks
        enable_fvg_signals: Whether to generate continuation signals from FVGs
        enable_cvd_signals: Whether to generate momentum signals from CVD
        confidence_multipliers: Multipliers applied to confidence based on zone status
        tested_confidence_multiplier: Deprecated, use confidence_multipliers instead
    """

    zone_manager: ZoneManager | None = None
    zone_storage: ZoneRedisStorage | None = None
    enable_ob_signals: bool = True
    enable_fvg_signals: bool = True
    enable_cvd_signals: bool = True
    confidence_multipliers: dict[ZoneStatus, float] = field(
        default_factory=lambda: ZONE_STATUS_CONFIDENCE_MULTIPLIERS.copy()
    )
    tested_confidence_multiplier: float = 0.85  # Deprecated, use confidence_multipliers

    def __post_init__(self) -> None:
        """Validate mapper configuration."""
        if self.zone_manager is None and self.zone_storage is None:
            raise ValueError("Either zone_manager or zone_storage must be provided")

        # For backwards compatibility
        if self.zone_manager is not None:
            self._storage = self.zone_manager._storage
        else:
            self._storage = self.zone_storage

    def _get_storage(self) -> ZoneRedisStorage:
        """Get the storage instance."""
        return self._storage

    def get_signals(
        self,
        token: str,
        timeframe: str,
        current_price: float,
        ob_results: list[OBDetectionResult] | None = None,
        fvg_results: list[FVGDetectionResult] | None = None,
        cvd_results: list[CVDDetectionResult] | None = None,
        include_tested: bool = True,
    ) -> ZoneToSignalResult:
        """
        Get all signals for a token/timeframe based on active zones.

        Args:
            token: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Trading timeframe (e.g., "1H", "4H")
            current_price: Current market price for zone proximity calculations
            ob_results: Optional list of Order Block detection results
            fvg_results: Optional list of FVG detection results
            cvd_results: Optional list of CVD detection results
            include_tested: Whether to include TESTED zones (with reduced confidence)

        Returns:
            ZoneToSignalResult containing all generated signals
        """
        start_time = time.perf_counter()
        result = ZoneToSignalResult()

        try:
            storage = self._get_storage()

            # Get all zones for token/timeframe
            zones = storage.get_by_token_timeframe(token, timeframe)

            # Count zones by status
            for zone in zones:
                result.zones_processed += 1
                if zone.status == ZoneStatus.ACTIVE:
                    result.zones_active += 1
                elif zone.status == ZoneStatus.TESTED:
                    result.zones_tested += 1
                elif zone.status == ZoneStatus.MITIGATED:
                    result.zones_mitigated += 1
                elif zone.status == ZoneStatus.INVALIDATED:
                    result.zones_invalidated += 1

            if not zones:
                result.resolution = SignalResolution.NO_ACTIVE_ZONES
                return result

            # Filter zones based on status
            active_zones = [
                z
                for z in zones
                if z.status == ZoneStatus.ACTIVE
                or (include_tested and z.status == ZoneStatus.TESTED)
            ]

            if not active_zones:
                result.resolution = SignalResolution.ZONES_INVALIDATED
                return result

            # Generate signals based on zone type
            for zone in active_zones:
                if zone.zone_type == ZoneType.OB and self.enable_ob_signals:
                    self._map_ob_zone(zone, current_price, result, ob_results)

                elif zone.zone_type == ZoneType.FVG and self.enable_fvg_signals:
                    self._map_fvg_zone(zone, current_price, result, fvg_results)

            # Handle CVD signals separately (from detection results, not zones)
            if self.enable_cvd_signals and cvd_results:
                for cvd_result in cvd_results:
                    self._map_cvd_result(cvd_result, current_price, result)

            result.resolution = SignalResolution.SUCCESS

        except Exception as e:
            logger.exception(f"Error resolving zones to signals: {e}")
            result.resolution = SignalResolution.RESOLUTION_ERROR
            result.error_message = str(e)

        finally:
            elapsed = time.perf_counter() - start_time
            result.resolution_time_ms = elapsed * 1000

        return result

    def _map_ob_zone(
        self,
        zone: Zone,
        current_price: float,
        result: ZoneToSignalResult,
        ob_results: list[OBDetectionResult] | None = None,
    ) -> None:
        """
        Map an Order Block zone to an entry signal.

        Args:
            zone: The Order Block zone to map
            current_price: Current market price
            result: The result object to append signals to
            ob_results: Optional OB detection results for additional metadata
        """
        # Find matching OB result if available
        ob_metadata: dict[str, Any] = {"source": "zone_persistence"}
        polarity = "neutral"

        if ob_results:
            for ob in ob_results:
                if hasattr(ob, "zone") and ob.zone.uuid == zone.uuid:
                    polarity = (
                        ob.polarity.value if hasattr(ob, "polarity") else "neutral"
                    )
                    ob_metadata = {
                        "source": "ob_detector",
                        "anchor_candle_index": getattr(ob, "anchor_candle_index", None),
                        "momentum_candle_index": getattr(
                            ob, "momentum_candle_index", None
                        ),
                        "volume_confirmed": getattr(ob, "volume_confirmed", False),
                        "strength_score": getattr(ob, "strength_score", 0.5),
                    }
                    break

        # Determine direction from polarity or zone notes
        direction = SignalDirection.NEUTRAL
        if polarity == "bullish" or "bullish" in (zone.notes or "").lower():
            direction = SignalDirection.LONG
        elif polarity == "bearish" or "bearish" in (zone.notes or "").lower():
            direction = SignalDirection.SHORT

        # Calculate confidence based on zone status
        base_confidence = ob_metadata.get("strength_score", 0.68)
        multiplier = self.confidence_multipliers.get(zone.status, 1.0)
        confidence = base_confidence * multiplier

        # Calculate optimal entry price (midpoint of zone)
        optimal_entry = (zone.price_range.high + zone.price_range.low) / 2

        # Calculate stop loss (outside the zone)
        if direction == SignalDirection.LONG:
            stop_loss = zone.price_range.low * 0.999  # Just below the zone
        else:
            stop_loss = zone.price_range.high * 1.001  # Just above the zone

        # Calculate risk-reward ratio
        risk = abs(current_price - stop_loss)
        reward = abs(current_price - optimal_entry)
        rr_ratio = reward / risk if risk > 0 else 0.0

        signal = EntrySignal(
            signal_type=ZoneSignalType.ENTRY,
            direction=direction,
            zone_uuid=zone.uuid,
            zone_type=zone.zone_type.value,
            token=zone.token,
            timeframe=zone.timeframe,
            price_high=zone.price_range.high,
            price_low=zone.price_range.low,
            confidence=confidence,
            zone_status=zone.status.value,
            timestamp=datetime.utcnow(),
            metadata=ob_metadata,
            entry_type="limit",  # Limit entry at zone
            zone_polarity=polarity,
            optimal_entry_price=optimal_entry,
            stop_loss=stop_loss,
            risk_reward_ratio=rr_ratio,
        )

        result.entry_signals.append(signal)

    def _map_fvg_zone(
        self,
        zone: Zone,
        current_price: float,
        result: ZoneToSignalResult,
        fvg_results: list[FVGDetectionResult] | None = None,
    ) -> None:
        """
        Map an FVG zone to a continuation signal.

        Args:
            zone: The FVG zone to map
            current_price: Current market price
            result: The result object to append signals to
            fvg_results: Optional FVG detection results for additional metadata
        """
        # Find matching FVG result if available
        fvg_metadata: dict[str, Any] = {"source": "zone_persistence"}
        fvg_direction = "neutral"
        mitigation_status = "none"

        if fvg_results:
            for fvg_result in fvg_results:
                if hasattr(fvg_result, "zone_uuid"):
                    if fvg_result.zone_uuid == zone.uuid:
                        mitigation_status = (
                            fvg_result.mitigation.value
                            if hasattr(fvg_result, "mitigation")
                            else "none"
                        )
                        fvg_direction = (
                            fvg_result.direction.value
                            if hasattr(fvg_result, "direction")
                            else "neutral"
                        )
                        fvg_metadata = {
                            "source": "fvg_detector",
                            "ce50_reached": getattr(fvg_result, "ce50_reached", False),
                        }
                        break

        # Determine direction from zone notes or detect from price relationship
        direction = SignalDirection.NEUTRAL
        if fvg_direction == "bullish":
            direction = SignalDirection.LONG
        elif fvg_direction == "bearish":
            direction = SignalDirection.SHORT

        # Fallback: detect direction from zone position relative to price
        if direction == SignalDirection.NEUTRAL:
            if current_price > zone.price_range.high:
                direction = (
                    SignalDirection.SHORT
                )  # Price above FVG = bearish continuation
            elif current_price < zone.price_range.low:
                direction = (
                    SignalDirection.LONG
                )  # Price below FVG = bullish continuation

        # Calculate confidence based on mitigation status
        MITIGATION_CONFIDENCE = {
            "none": 0.80,
            "wick": 0.70,
            "close": 0.55,
            "full": 0.30,
        }
        base_confidence = MITIGATION_CONFIDENCE.get(mitigation_status, 0.50)

        # Apply zone status multiplier
        multiplier = self.confidence_multipliers.get(zone.status, 1.0)
        confidence = base_confidence * multiplier

        # Calculate zone size and midpoint
        zone_size = zone.price_range.high - zone.price_range.low
        midpoint = (zone.price_range.high + zone.price_range.low) / 2

        signal = ContinuationSignal(
            signal_type=ZoneSignalType.CONTINUATION,
            direction=direction,
            zone_uuid=zone.uuid,
            zone_type=zone.zone_type.value,
            token=zone.token,
            timeframe=zone.timeframe,
            price_high=zone.price_range.high,
            price_low=zone.price_range.low,
            confidence=confidence,
            zone_status=zone.status.value,
            timestamp=datetime.utcnow(),
            metadata=fvg_metadata,
            fvg_direction=fvg_direction,
            mitigation_status=mitigation_status,
            midpoint=midpoint,
            zone_size=zone_size,
        )

        result.continuation_signals.append(signal)

    def _map_cvd_result(
        self,
        cvd_result: CVDDetectionResult,
        current_price: float,
        result: ZoneToSignalResult,
    ) -> None:
        """
        Map a CVD detection result to a momentum signal.

        Args:
            cvd_result: The CVD detection result
            current_price: Current market price
            result: The result object to append signals to
        """
        # Extract direction from CVD result
        direction_str = getattr(cvd_result, "direction", "neutral")
        direction = SignalDirection.NEUTRAL

        if direction_str == "bullish":
            direction = SignalDirection.LONG
        elif direction_str == "bearish":
            direction = SignalDirection.SHORT

        # Calculate confidence
        base_confidence = getattr(cvd_result, "confidence", 0.65)
        threshold = getattr(cvd_result, "threshold", 0.0)
        confidence = min(1.0, base_confidence + (threshold * 0.1))

        # Extract other metadata
        price_at_formation = getattr(cvd_result, "price_at_formation", current_price)
        divergence_strength = getattr(
            cvd_result, "strength", divergence_strength := 0.5
        )

        signal = MomentumSignal(
            signal_type=ZoneSignalType.MOMENTUM,
            direction=direction,
            zone_uuid=UUID(
                "00000000-0000-0000-0000-000000000000"
            ),  # CVD has no zone UUID
            zone_type="CVD",
            token=getattr(cvd_result, "token", "UNKNOWN"),
            timeframe=getattr(cvd_result, "timeframe", "1H"),
            price_high=current_price * 1.001,  # Neutral zone
            price_low=current_price * 0.999,
            confidence=confidence,
            zone_status="ACTIVE",  # CVD results don't have zone status
            timestamp=datetime.utcnow(),
            metadata={
                "source": "cvd_detector",
                "divergence_index": getattr(cvd_result, "index", None),
                "threshold": threshold,
            },
            cvd_direction=direction_str,
            divergence_strength=divergence_strength,
            threshold=threshold,
            price_at_formation=price_at_formation,
        )

        result.momentum_signals.append(signal)

    def get_signals_for_ob_zones(
        self,
        token: str,
        timeframe: str,
        current_price: float,
        ob_results: list[OBDetectionResult] | None = None,
    ) -> list[EntrySignal]:
        """
        Get entry signals specifically from Order Block zones.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe
            current_price: Current market price
            ob_results: Optional OB detection results

        Returns:
            List of EntrySignal objects
        """
        result = self.get_signals(
            token=token,
            timeframe=timeframe,
            current_price=current_price,
            ob_results=ob_results,
            fvg_results=None,
            cvd_results=None,
            include_tested=True,
        )
        return result.entry_signals

    def get_signals_for_fvg_zones(
        self,
        token: str,
        timeframe: str,
        current_price: float,
        fvg_results: list[FVGDetectionResult] | None = None,
    ) -> list[ContinuationSignal]:
        """
        Get continuation signals specifically from FVG zones.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe
            current_price: Current market price
            fvg_results: Optional FVG detection results

        Returns:
            List of ContinuationSignal objects
        """
        result = self.get_signals(
            token=token,
            timeframe=timeframe,
            current_price=current_price,
            ob_results=None,
            fvg_results=fvg_results,
            cvd_results=None,
            include_tested=True,
        )
        return result.continuation_signals

    def get_signals_for_cvd(
        self,
        token: str,
        timeframe: str,
        current_price: float,
        cvd_results: list[CVDDetectionResult],
    ) -> list[MomentumSignal]:
        """
        Get momentum signals from CVD divergence results.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe
            current_price: Current market price
            cvd_results: CVD detection results

        Returns:
            List of MomentumSignal objects
        """
        result = self.get_signals(
            token=token,
            timeframe=timeframe,
            current_price=current_price,
            ob_results=None,
            fvg_results=None,
            cvd_results=cvd_results,
            include_tested=True,
        )
        return result.momentum_signals

    def invalidate_zone_signals(self, zone_uuid: UUID) -> bool:
        """
        Invalidate all signals related to a specific zone.

        This is called when a zone is invalidated to ensure stale signals
        are not propagated.

        Args:
            zone_uuid: UUID of the invalidated zone

        Returns:
            True if signals were invalidated, False otherwise
        """
        # This would typically interact with a signal cache or queue
        # For now, just log the invalidation
        logger.info(f"Invalidating signals for zone: {zone_uuid}")
        return True

    def get_zone_proximity(
        self,
        zone: Zone,
        current_price: float,
    ) -> float:
        """
        Calculate how close the current price is to a zone.

        Args:
            zone: The zone to check
            current_price: Current market price

        Returns:
            Proximity score (0.0 = price in zone, 1.0 = far from zone)
        """
        if zone.price_range.contains(current_price):
            return 0.0  # Price is within zone

        zone_midpoint = (zone.price_range.high + zone.price_range.low) / 2
        zone_size = zone.price_range.high - zone.price_range.low

        if zone_size == 0:
            return 1.0

        distance = abs(current_price - zone_midpoint)
        return min(1.0, distance / (zone_size * 10))  # Normalize to 0-1
