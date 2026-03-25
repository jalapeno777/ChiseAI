"""Order Block Detection Module.

Detects bullish and bearish order blocks based on ICT methodology.
Order blocks are zones where institutional orders were executed,
appearing as a consolidation candle before a strong directional move.

Exports:
    OrderBlockDetector: Main detector class
    OrderBlockConfig: Configuration dataclass
    OBDetectionResult: Detection result dataclass
    OBPolaridade: Enum for OB direction (BULLISH/BEARISH)
    MitigationTracker: Tracks OB mitigation events
    MitigationEvent: Mitigation event record
"""

from src.market_analysis.order_block.mitigation_tracker import (
    MitigationEvent,
    MitigationTracker,
)
from src.market_analysis.order_block.ob_detector import (
    OBDetectionResult,
    OBPolaridade,
    OrderBlockConfig,
    OrderBlockDetector,
)

__all__ = [
    "OrderBlockDetector",
    "OrderBlockConfig",
    "OBDetectionResult",
    "OBPolaridade",
    "MitigationTracker",
    "MitigationEvent",
]
