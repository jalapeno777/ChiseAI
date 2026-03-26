"""Data models for cross-timeframe zone awareness.

Defines zone types, timeframe weights, weighted zones, and aggregation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Timeframe(str, Enum):
    """Supported timeframes for zone analysis.

    Ordered from lowest to highest timeframe.
    """

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"


class ZoneType(str, Enum):
    """Types of ICT zones that can be detected."""

    DEMAND = "demand"
    SUPPLY = "supply"
    ORDER_BLOCK_BULL = "order_block_bull"
    ORDER_BLOCK_BEAR = "order_block_bear"
    FVG_BULL = "fvg_bull"
    FVG_BEAR = "fvg_bear"
    EQUILIBRIUM = "equilibrium"


# Timeframe weight multipliers.
# Higher timeframe zones receive proportionally higher weight.
# 1h zone = 2x 15m zone weight (per AC3).
TIMEFRAME_WEIGHTS: dict[Timeframe, float] = {
    Timeframe.M1: 0.5,
    Timeframe.M5: 0.75,
    Timeframe.M15: 1.0,
    Timeframe.H1: 2.0,
    Timeframe.H4: 4.0,
}

# Price proximity threshold for zone matching (percentage).
# Two zones on different timeframes are considered "same zone" if
# their midpoints are within this percentage of each other.
ZONE_MATCH_THRESHOLD_PCT: float = 0.3

# Minimum confluence count to report as "confluence detected".
MIN_CONFLUENCE_COUNT: int = 2


@dataclass(frozen=True)
class Zone:
    """A single zone detected on a specific timeframe.

    Attributes:
        zone_type: Type of zone (demand, supply, order block, etc.)
        timeframe: Timeframe on which this zone was detected.
        price_high: Upper price boundary of the zone.
        price_low: Lower price boundary of the zone.
        strength: Raw strength score from detection (0.0-1.0).
        source: Identifier for the detection source (e.g., "fvg_detector").
    """

    zone_type: ZoneType
    timeframe: Timeframe
    price_high: float
    price_low: float
    strength: float = 1.0
    source: str = ""

    def __post_init__(self) -> None:
        if self.price_high < self.price_low:
            raise ValueError(
                f"price_high ({self.price_high}) must be >= price_low ({self.price_low})"
            )
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"strength must be in [0.0, 1.0], got {self.strength}")

    @property
    def midpoint(self) -> float:
        """Midpoint price of the zone."""
        return (self.price_high + self.price_low) / 2.0

    @property
    def width_pct(self) -> float:
        """Zone width as a percentage of its midpoint."""
        if self.midpoint == 0:
            return 0.0
        return (self.price_high - self.price_low) / self.midpoint * 100.0

    @property
    def directional_type(self) -> str:
        """Simplified bullish/bearish/neutral classification."""
        bullish_types = {ZoneType.DEMAND, ZoneType.ORDER_BLOCK_BULL, ZoneType.FVG_BULL}
        bearish_types = {ZoneType.SUPPLY, ZoneType.ORDER_BLOCK_BEAR, ZoneType.FVG_BEAR}
        if self.zone_type in bullish_types:
            return "bullish"
        if self.zone_type in bearish_types:
            return "bearish"
        return "neutral"

    def overlaps(self, other: Zone) -> bool:
        """Check if this zone overlaps with another zone by price range.

        Args:
            other: Another zone to check overlap with.

        Returns:
            True if the price ranges overlap.
        """
        return self.price_low <= other.price_high and other.price_low <= self.price_high

    def midpoint_distance_pct(self, other: Zone) -> float:
        """Distance between midpoints as a percentage.

        Args:
            other: Another zone.

        Returns:
            Absolute percentage distance between midpoints.
        """
        if self.midpoint == 0:
            return float("inf")
        return abs(self.midpoint - other.midpoint) / self.midpoint * 100.0

    def is_similar_to(self, other: Zone) -> bool:
        """Check if two zones are similar enough to be considered the same zone.

        Two zones match if they share the same zone_type (or compatible types)
        and their midpoints are within ZONE_MATCH_THRESHOLD_PCT.

        Args:
            other: Another zone.

        Returns:
            True if zones are similar.
        """
        if self.zone_type != other.zone_type:
            return False
        return self.midpoint_distance_pct(other) <= ZONE_MATCH_THRESHOLD_PCT

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "zone_type": self.zone_type.value,
            "timeframe": self.timeframe.value,
            "price_high": round(self.price_high, 6),
            "price_low": round(self.price_low, 6),
            "midpoint": round(self.midpoint, 6),
            "strength": round(self.strength, 4),
            "source": self.source,
            "directional_type": self.directional_type,
        }


@dataclass
class WeightedZone:
    """A zone with its timeframe weight applied.

    Attributes:
        zone: The original zone.
        timeframe_weight: Weight multiplier for the zone's timeframe.
        weighted_strength: strength * timeframe_weight.
    """

    zone: Zone
    timeframe_weight: float
    weighted_strength: float = 0.0

    def __post_init__(self) -> None:
        self.weighted_strength = self.zone.strength * self.timeframe_weight

    @property
    def timeframe(self) -> Timeframe:
        return self.zone.timeframe

    @property
    def zone_type(self) -> ZoneType:
        return self.zone.zone_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone": self.zone.to_dict(),
            "timeframe_weight": round(self.timeframe_weight, 4),
            "weighted_strength": round(self.weighted_strength, 4),
        }


@dataclass
class ConfluenceGroup:
    """A group of zones from different timeframes that represent confluence.

    Attributes:
        zone_type: The common zone type across timeframes.
        timeframes: Set of timeframes showing this zone type.
        merged_price_high: Widest high across all zones.
        merged_price_low: Lowest low across all zones.
        merged_midpoint: Average midpoint across all zones.
        total_weighted_strength: Sum of weighted strengths.
        count: Number of timeframes showing this zone.
    """

    zone_type: ZoneType
    timeframes: set[Timeframe] = field(default_factory=set)
    merged_price_high: float = 0.0
    merged_price_low: float = 0.0
    merged_midpoint: float = 0.0
    total_weighted_strength: float = 0.0
    count: int = 0

    @property
    def has_confluence(self) -> bool:
        """True if multiple timeframes show this zone type."""
        return self.count >= MIN_CONFLUENCE_COUNT

    @property
    def highest_timeframe(self) -> Timeframe | None:
        """The highest timeframe in this confluence group."""
        if not self.timeframes:
            return None
        # Timeframe enum order: M1 < M5 < M15 < H1 < H4
        ordered = sorted(self.timeframes, key=lambda tf: list(Timeframe).index(tf))
        return ordered[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_type": self.zone_type.value,
            "timeframes": sorted(tf.value for tf in self.timeframes),
            "count": self.count,
            "has_confluence": self.has_confluence,
            "merged_price_high": round(self.merged_price_high, 6),
            "merged_price_low": round(self.merged_price_low, 6),
            "merged_midpoint": round(self.merged_midpoint, 6),
            "total_weighted_strength": round(self.total_weighted_strength, 4),
            "highest_timeframe": (
                self.highest_timeframe.value if self.highest_timeframe else None
            ),
        }


@dataclass
class CrossTimeframeResult:
    """Result of cross-timeframe zone aggregation.

    Attributes:
        weighted_zones: All zones with timeframe weights applied.
        confluence_groups: Groups of zones showing multi-timeframe confluence.
        dominant_zone_type: The zone type with the highest total weighted strength.
        dominant_direction: Overall bullish/bearish/neutral from aggregated zones.
        total_weighted_strength: Sum of all weighted zone strengths.
        calculation_time_ms: Time taken for aggregation in milliseconds.
        zone_count: Total number of zones across all timeframes.
        confluence_count: Number of confluence groups detected.
    """

    weighted_zones: list[WeightedZone] = field(default_factory=list)
    confluence_groups: list[ConfluenceGroup] = field(default_factory=list)
    dominant_zone_type: ZoneType | None = None
    dominant_direction: str = "neutral"
    total_weighted_strength: float = 0.0
    calculation_time_ms: float = 0.0
    zone_count: int = 0
    confluence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "weighted_zones": [wz.to_dict() for wz in self.weighted_zones],
            "confluence_groups": [cg.to_dict() for cg in self.confluence_groups],
            "dominant_zone_type": (
                self.dominant_zone_type.value if self.dominant_zone_type else None
            ),
            "dominant_direction": self.dominant_direction,
            "total_weighted_strength": round(self.total_weighted_strength, 4),
            "calculation_time_ms": round(self.calculation_time_ms, 2),
            "zone_count": self.zone_count,
            "confluence_count": self.confluence_count,
        }
