"""ICT Dynamic Weight Adjustment Module.

This module implements time-based weight decay for ICT signals to reduce the
influence of stale signals in confluence calculations.

Weight Multipliers (ST-ICT-023):
    - Recent signals (0-5 minutes): 1.0x multiplier
    - Stale signals (5-15 minutes): 0.8x multiplier
    - Old signals (15-30 minutes): 0.5x multiplier
    - Very old signals (>30 minutes): EXCLUDED from confluence

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

Integration:
    - Works with Layer 2 confluence aggregator from EP-ICT-005
    - Uses ICT signal registry (ST-ICT-015) for signal tracking
"""

from ict.weights.dynamic_weight_adjuster import (
    DynamicWeightAdjuster,
    WeightTier,
    get_weight_adjuster,
)
from ict.weights.signal_timestamp_tracker import (
    SignalTimestampTracker,
    TrackedSignal,
    get_timestamp_tracker,
)

__all__ = [
    "DynamicWeightAdjuster",
    "WeightTier",
    "get_weight_adjuster",
    "SignalTimestampTracker",
    "TrackedSignal",
    "get_timestamp_tracker",
]
