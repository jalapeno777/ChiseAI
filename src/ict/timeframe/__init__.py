"""Cross-timeframe zone awareness module.

Aggregates zones across multiple timeframes (1m, 5m, 15m, 1h, 4h),
applies higher-weight to higher timeframes, and detects multi-timeframe
confluence. Resolution target: <20ms per aggregation call.
"""

from ict.timeframe.aggregator import CrossTimeframeAggregator
from ict.timeframe.models import (
    CrossTimeframeResult,
    Timeframe,
    WeightedZone,
    Zone,
    ZoneType,
)

__all__ = [
    "CrossTimeframeAggregator",
    "Timeframe",
    "Zone",
    "ZoneType",
    "WeightedZone",
    "CrossTimeframeResult",
]
