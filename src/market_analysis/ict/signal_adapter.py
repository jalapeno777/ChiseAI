"""ICT Signal Adapter Module.

This module provides adapters to convert ICT signal formats (CVD, FVG, Order Block)
to the signal registry format for integration with the signal generation pipeline.

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

Usage:
    from src.market_analysis.ict import ICTSignalAdapter, ICTSignalData

    adapter = ICTSignalAdapter()
    signal_data = adapter.convert_fvg(fvg_signal, token="BTC/USDT", timeframe="1H")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from signal_generation.registry.signal_types import ICTSignalType, SignalSource

if TYPE_CHECKING:
    from src.market_analysis.fvg.fvg_detector import FVG, FVGDetectionResult
    from src.market_analysis.order_block.ob_detector import OBDetectionResult

logger = logging.getLogger(__name__)


class ICTSignalDirection(str, Enum):
    """Direction of ICT signal."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class ICTSignalData:
    """Normalized ICT signal data for the registry.

    Attributes:
        signal_type: The type of ICT signal
        direction: Signal direction (bullish/bearish/neutral)
        confidence: Confidence score (0.0-1.0)
        price_high: High price level for the signal
        price_low: Low price level for the signal
        timestamp: Signal timestamp
        token: Trading pair
        timeframe: Timeframe
        metadata: Additional signal metadata
        source: Signal source
    """

    signal_type: ICTSignalType
    direction: ICTSignalDirection
    confidence: float
    price_high: float
    price_low: float
    timestamp: datetime
    token: str
    timeframe: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source: SignalSource = SignalSource.ICT

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_type": self.signal_type.value,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 4),
            "price_high": round(self.price_high, 2),
            "price_low": round(self.price_low, 2),
            "timestamp": self.timestamp.isoformat(),
            "token": self.token,
            "timeframe": self.timeframe,
            "metadata": self.metadata,
            "source": self.source.value,
        }


class CVDAdapter:
    """Adapter for CVD (Cumulative Volume Delta) signals.

    CVD divergence detection results are converted to normalized signal data.
    """

    # Default confidence for CVD signals
    DEFAULT_CONFIDENCE = 0.65

    @classmethod
    def convert_divergence(
        cls,
        divergence_data: dict[str, Any],
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData:
        """Convert CVD divergence data to ICT signal data.

        Args:
            divergence_data: Dictionary containing:
                - direction: "bullish" or "bearish"
                - index: Index where divergence was detected
                - cvd_values: CVD values list
                - prices: Price values list
                - threshold: Detection threshold used
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData for the CVD divergence
        """
        direction_str = divergence_data.get("direction", "neutral")
        try:
            direction = ICTSignalDirection(direction_str)
        except ValueError:
            direction = ICTSignalDirection.NEUTRAL

        # Calculate a simple confidence based on threshold
        threshold = divergence_data.get("threshold", 0.0)
        confidence = min(1.0, cls.DEFAULT_CONFIDENCE + (threshold * 0.1))

        # CVD doesn't have specific price levels like FVG
        # Use a neutral zone representation
        price_high = divergence_data.get("current_price", 0.0) * 1.001
        price_low = divergence_data.get("current_price", 0.0) * 0.999

        return ICTSignalData(
            signal_type=ICTSignalType.CVD,
            direction=direction,
            confidence=confidence,
            price_high=price_high,
            price_low=price_low,
            timestamp=datetime.utcnow(),
            token=token,
            timeframe=timeframe,
            metadata={
                "divergence_index": divergence_data.get("index"),
                "threshold": threshold,
                "cvd_values_count": len(divergence_data.get("cvd_values", [])),
            },
        )


class FVGAdapter:
    """Adapter for FVG (Fair Value Gap) signals.

    FVG detection results are converted to normalized signal data.
    """

    # Confidence based on mitigation status
    MITIGATION_CONFIDENCE = {
        "none": 0.80,  # Fresh FVG, highest confidence
        "wick": 0.70,  # Wick-only mitigation
        "close": 0.55,  # Close within FVG
        "full": 0.30,  # Fully mitigated, low confidence
    }

    @classmethod
    def convert_fvg(
        cls,
        fvg: FVG,
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData:
        """Convert FVG to ICT signal data.

        Args:
            fvg: FVG object from FVGDetector
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData for the FVG
        """
        direction = (
            ICTSignalDirection.BULLISH
            if fvg.direction.value == "bullish"
            else ICTSignalDirection.BEARISH
        )

        # Base confidence from mitigation status
        mitigation_key = fvg.mitigation.value
        base_confidence = cls.MITIGATION_CONFIDENCE.get(mitigation_key, 0.50)

        # Adjust confidence if 50% CE reached
        if fvg.ce50_reached:
            base_confidence = min(0.95, base_confidence + 0.10)

        # Create timestamp from unix timestamp if needed
        if isinstance(fvg.timestamp, int):
            timestamp = datetime.fromtimestamp(fvg.timestamp / 1000)
        else:
            timestamp = fvg.timestamp

        return ICTSignalData(
            signal_type=ICTSignalType.FVG,
            direction=direction,
            confidence=base_confidence,
            price_high=fvg.high,
            price_low=fvg.low,
            timestamp=timestamp,
            token=token,
            timeframe=timeframe,
            metadata={
                "mitigation_status": fvg.mitigation.value,
                "ce50_reached": fvg.ce50_reached,
                "zone_size": fvg.zone_size,
                "midpoint": fvg.midpoint,
                "regime_at_formation": (
                    fvg.regime_at_formation.value if fvg.regime_at_formation else None
                ),
            },
        )

    @classmethod
    def convert_detection_result(
        cls,
        result: FVGDetectionResult,
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData | None:
        """Convert FVGDetectionResult to ICT signal data.

        Args:
            result: FVGDetectionResult from FVGDetector
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData or None if no FVG detected
        """
        if result.fvg is None:
            return None

        return cls.convert_fvg(result.fvg, token=token, timeframe=timeframe)


class OrderBlockAdapter:
    """Adapter for Order Block signals.

    Order Block detection results are converted to normalized signal data.
    """

    @classmethod
    def convert_ob(
        cls,
        ob_result: OBDetectionResult,
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData:
        """Convert OBDetectionResult to ICT signal data.

        Args:
            ob_result: OBDetectionResult from OrderBlockDetector
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData for the Order Block
        """
        direction = (
            ICTSignalDirection.BULLISH
            if ob_result.polarity.value == "bullish"
            else ICTSignalDirection.BEARISH
        )

        # Use strength_score as confidence (already 0.0-1.0)
        confidence = ob_result.strength_score

        # Get price range from zone
        zone = ob_result.zone
        price_high = zone.price_range.high
        price_low = zone.price_range.low

        # Get timeframe from zone if available
        ob_timeframe = getattr(zone, "timeframe", timeframe)

        return ICTSignalData(
            signal_type=ICTSignalType.ORDER_BLOCK,
            direction=direction,
            confidence=confidence,
            price_high=price_high,
            price_low=price_low,
            timestamp=datetime.utcnow(),
            token=token,
            timeframe=ob_timeframe,
            metadata={
                "anchor_candle_index": ob_result.anchor_candle_index,
                "momentum_candle_index": ob_result.momentum_candle_index,
                "volume_confirmed": ob_result.volume_confirmed,
                "strength_score": ob_result.strength_score,
                "zone_notes": getattr(zone, "notes", None),
            },
        )


class ICTSignalAdapter:
    """Main adapter for converting ICT signals to registry format.

    This adapter provides a unified interface for converting CVD, FVG,
    and Order Block signals to the normalized ICTSignalData format.

    Usage:
        adapter = ICTSignalAdapter()

        # Convert FVG
        fvg_signal = adapter.convert_fvg(fvg, token="BTC/USDT", timeframe="1H")

        # Convert Order Block
        ob_signal = adapter.convert_order_block(ob_result, token="BTC/USDT")

        # Convert CVD divergence
        cvd_signal = adapter.convert_cvd(divergence_data)
    """

    def __init__(self) -> None:
        """Initialize ICT signal adapter."""
        self.cvd_adapter = CVDAdapter()
        self.fvg_adapter = FVGAdapter()
        self.ob_adapter = OrderBlockAdapter()

    def convert_cvd(
        self,
        divergence_data: dict[str, Any],
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData:
        """Convert CVD divergence data to ICT signal data.

        Args:
            divergence_data: CVD divergence detection data
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData for the CVD divergence
        """
        return self.cvd_adapter.convert_divergence(
            divergence_data, token=token, timeframe=timeframe
        )

    def convert_fvg(
        self,
        fvg: FVG,
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData:
        """Convert FVG to ICT signal data.

        Args:
            fvg: FVG object from FVGDetector
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData for the FVG
        """
        return self.fvg_adapter.convert_fvg(fvg, token=token, timeframe=timeframe)

    def convert_fvg_result(
        self,
        result: FVGDetectionResult,
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData | None:
        """Convert FVGDetectionResult to ICT signal data.

        Args:
            result: FVGDetectionResult from FVGDetector
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData or None if no FVG detected
        """
        return self.fvg_adapter.convert_detection_result(
            result, token=token, timeframe=timeframe
        )

    def convert_order_block(
        self,
        ob_result: OBDetectionResult,
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData:
        """Convert Order Block to ICT signal data.

        Args:
            ob_result: OBDetectionResult from OrderBlockDetector
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData for the Order Block
        """
        return self.ob_adapter.convert_ob(ob_result, token=token, timeframe=timeframe)

    def convert_any(
        self,
        signal: Any,
        token: str = "UNKNOWN",
        timeframe: str = "1H",
    ) -> ICTSignalData | None:
        """Convert any ICT signal to ICTSignalData.

        Automatically detects signal type and converts appropriately.

        Args:
            signal: Any ICT signal (FVG, OBDetectionResult, CVD data dict)
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            ICTSignalData or None if signal type not recognized
        """
        # Import here to avoid circular imports at module level
        from src.market_analysis.fvg.fvg_detector import FVG
        from src.market_analysis.order_block.ob_detector import OBDetectionResult

        if isinstance(signal, FVG):
            return self.convert_fvg(signal, token=token, timeframe=timeframe)
        elif isinstance(signal, OBDetectionResult):
            return self.convert_order_block(signal, token=token, timeframe=timeframe)
        elif isinstance(signal, dict):
            # Assume CVD divergence data
            return self.convert_cvd(signal, token=token, timeframe=timeframe)
        else:
            logger.warning(f"Unknown signal type: {type(signal)}")
            return None
