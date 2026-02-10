"""Timeframe configuration for multi-timeframe data ingestion.

Defines the supported timeframes and their configurations including
interval durations, freshness thresholds, and aggregation rules.
"""

from dataclasses import dataclass
from enum import Enum


class Timeframe(Enum):
    """Supported timeframe intervals."""

    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"


@dataclass(frozen=True)
class TimeframeConfig:
    """Configuration for a specific timeframe.

    Attributes:
        interval_seconds: Duration of one candle in seconds
        freshness_multiplier: Max age multiplier (data considered stale if
            older than interval * freshness_multiplier)
        ccxt_code: The timeframe code used by ccxt library
        aggregation_factor: How many of the base timeframe (1m) make up this timeframe
    """

    interval_seconds: int
    freshness_multiplier: float
    ccxt_code: str
    aggregation_factor: int


# Configuration for each timeframe
TIMEFRAME_CONFIG: dict[Timeframe, TimeframeConfig] = {
    Timeframe.MINUTE_1: TimeframeConfig(
        interval_seconds=60,
        freshness_multiplier=2.0,
        ccxt_code="1m",
        aggregation_factor=1,
    ),
    Timeframe.MINUTE_5: TimeframeConfig(
        interval_seconds=300,
        freshness_multiplier=2.0,
        ccxt_code="5m",
        aggregation_factor=5,
    ),
    Timeframe.MINUTE_15: TimeframeConfig(
        interval_seconds=900,
        freshness_multiplier=2.0,
        ccxt_code="15m",
        aggregation_factor=15,
    ),
    Timeframe.HOUR_1: TimeframeConfig(
        interval_seconds=3600,
        freshness_multiplier=2.0,
        ccxt_code="1h",
        aggregation_factor=60,
    ),
    Timeframe.HOUR_4: TimeframeConfig(
        interval_seconds=14400,
        freshness_multiplier=2.0,
        ccxt_code="4h",
        aggregation_factor=240,
    ),
    Timeframe.DAY_1: TimeframeConfig(
        interval_seconds=86400,
        freshness_multiplier=2.0,
        ccxt_code="1d",
        aggregation_factor=1440,
    ),
}


def get_freshness_threshold(timeframe: Timeframe) -> float:
    """Calculate the freshness threshold in seconds for a timeframe.

    Data is considered stale if its timestamp is older than:
    interval_seconds * freshness_multiplier

    Args:
        timeframe: The timeframe to calculate threshold for

    Returns:
        Maximum age in seconds before data is considered stale
    """
    config = TIMEFRAME_CONFIG[timeframe]
    return config.interval_seconds * config.freshness_multiplier


def get_all_timeframes() -> list[Timeframe]:
    """Return list of all supported timeframes in order from smallest to largest.

    Returns:
        List of Timeframe enum values ordered by interval duration
    """
    return [
        Timeframe.MINUTE_1,
        Timeframe.MINUTE_5,
        Timeframe.MINUTE_15,
        Timeframe.HOUR_1,
        Timeframe.HOUR_4,
        Timeframe.DAY_1,
    ]


def timeframe_from_string(tf_str: str) -> Timeframe:
    """Convert a string timeframe code to Timeframe enum.

    Args:
        tf_str: Timeframe string (e.g., "1m", "5m", "1h")

    Returns:
        Corresponding Timeframe enum value

    Raises:
        ValueError: If the string doesn't match any known timeframe
    """
    mapping = {
        "1m": Timeframe.MINUTE_1,
        "5m": Timeframe.MINUTE_5,
        "15m": Timeframe.MINUTE_15,
        "1h": Timeframe.HOUR_1,
        "4h": Timeframe.HOUR_4,
        "1d": Timeframe.DAY_1,
    }
    if tf_str not in mapping:
        raise ValueError(f"Unknown timeframe: {tf_str}")
    return mapping[tf_str]
