"""Cross-timeframe zone aggregator.

Aggregates zones across multiple timeframes, applies weighted scoring,
detects confluence, and produces a unified cross-timeframe result.

Performance target: <20ms per aggregation call for typical inputs
(5 timeframes x ~10 zones each).
"""

from __future__ import annotations

import logging
import time

from ict.timeframe.models import (
    TIMEFRAME_WEIGHTS,
    ConfluenceGroup,
    CrossTimeframeResult,
    Timeframe,
    WeightedZone,
    Zone,
    ZoneType,
)

logger = logging.getLogger(__name__)


class CrossTimeframeAggregator:
    """Aggregates zones across 1m, 5m, 15m, 1h, 4h timeframes.

    Higher timeframe zones receive proportionally higher weight:
        M1=0.5x, M5=0.75x, M15=1.0x (baseline), H1=2.0x, H4=4.0x

    Confluence is detected when the same zone type appears across
    multiple timeframes with overlapping or nearby price levels.
    """

    def __init__(
        self,
        timeframe_weights: dict[Timeframe, float] | None = None,
        zone_match_threshold_pct: float = 0.3,
        min_confluence_count: int = 2,
    ) -> None:
        """Initialize the aggregator.

        Args:
            timeframe_weights: Override default timeframe weights.
            zone_match_threshold_pct: Percentage threshold for zone matching.
            min_confluence_count: Minimum timeframes for confluence.
        """
        self._weights = timeframe_weights or dict(TIMEFRAME_WEIGHTS)
        self._zone_match_threshold_pct = zone_match_threshold_pct
        self._min_confluence_count = min_confluence_count

    def aggregate(self, zones: list[Zone]) -> CrossTimeframeResult:
        """Aggregate zones across timeframes into a unified result.

        Steps:
            1. Apply timeframe weights to each zone.
            2. Group zones by type and detect confluence.
            3. Determine dominant zone type and direction.
            4. Build result with timing.

        Args:
            zones: List of Zone objects from multiple timeframes.

        Returns:
            CrossTimeframeResult with weighted zones and confluence data.
        """
        start = time.perf_counter()

        # Step 1: Apply timeframe weights
        weighted_zones = self._apply_weights(zones)

        # Step 2: Detect confluence groups
        confluence_groups = self._detect_confluence(weighted_zones)

        # Step 3: Determine dominant type and direction
        dominant_type, dominant_direction = self._determine_dominant(weighted_zones)

        # Step 4: Compute totals
        total_strength = sum(wz.weighted_strength for wz in weighted_zones)

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        result = CrossTimeframeResult(
            weighted_zones=weighted_zones,
            confluence_groups=confluence_groups,
            dominant_zone_type=dominant_type,
            dominant_direction=dominant_direction,
            total_weighted_strength=total_strength,
            calculation_time_ms=elapsed_ms,
            zone_count=len(zones),
            confluence_count=len([g for g in confluence_groups if g.has_confluence]),
        )

        logger.debug(
            "Cross-timeframe aggregation: %d zones, %d confluence groups, %.2fms",
            result.zone_count,
            result.confluence_count,
            elapsed_ms,
        )

        return result

    def _apply_weights(self, zones: list[Zone]) -> list[WeightedZone]:
        """Apply timeframe weights to zones.

        Args:
            zones: Raw zones.

        Returns:
            List of WeightedZone objects.
        """
        weighted: list[WeightedZone] = []
        for zone in zones:
            weight = self._weights.get(zone.timeframe, 1.0)
            weighted.append(WeightedZone(zone=zone, timeframe_weight=weight))
        return weighted

    def _detect_confluence(
        self, weighted_zones: list[WeightedZone]
    ) -> list[ConfluenceGroup]:
        """Detect multi-timeframe confluence by grouping similar zones.

        Groups zones by zone_type, then merges zones with overlapping
        or nearby price levels into confluence groups.

        Args:
            weighted_zones: Weighted zones to analyze.

        Returns:
            List of ConfluenceGroup objects.
        """
        # Group by zone_type
        type_groups: dict[ZoneType, list[WeightedZone]] = {}
        for wz in weighted_zones:
            type_groups.setdefault(wz.zone_type, []).append(wz)

        confluence: list[ConfluenceGroup] = []
        for zone_type, wz_list in type_groups.items():
            groups = self._merge_similar_zones(zone_type, wz_list)
            confluence.extend(groups)

        # Sort by total weighted strength descending
        confluence.sort(key=lambda g: g.total_weighted_strength, reverse=True)
        return confluence

    def _merge_similar_zones(
        self, zone_type: ZoneType, weighted_zones: list[WeightedZone]
    ) -> list[ConfluenceGroup]:
        """Merge zones of the same type that are price-proximate.

        Uses a greedy clustering approach: iterate zones sorted by
        timeframe (highest first, so higher-TF zones anchor groups),
        and merge nearby lower-TF zones into the same group.

        Args:
            zone_type: The zone type being clustered.
            weighted_zones: Weighted zones of this type.

        Returns:
            List of ConfluenceGroup objects.
        """
        if not weighted_zones:
            return []

        # Sort by timeframe weight descending (highest TF first)
        sorted_zones = sorted(
            weighted_zones, key=lambda wz: wz.timeframe_weight, reverse=True
        )

        groups: list[ConfluenceGroup] = []

        for wz in sorted_zones:
            merged = False
            for group in groups:
                # Use the group's merged midpoint for proximity check
                group_mid = group.merged_midpoint
                zone_mid = wz.zone.midpoint

                if group_mid == 0:
                    continue

                distance_pct = abs(zone_mid - group_mid) / group_mid * 100.0
                if distance_pct <= self._zone_match_threshold_pct:
                    # Merge into this group
                    group.timeframes.add(wz.timeframe)
                    group.merged_price_high = max(
                        group.merged_price_high, wz.zone.price_high
                    )
                    group.merged_price_low = min(
                        group.merged_price_low, wz.zone.price_low
                    )
                    # Recalculate average midpoint
                    group.merged_midpoint = (
                        group.merged_price_high + group.merged_price_low
                    ) / 2.0
                    group.total_weighted_strength += wz.weighted_strength
                    group.count += 1
                    merged = True
                    break

            if not merged:
                # Start a new group
                groups.append(
                    ConfluenceGroup(
                        zone_type=zone_type,
                        timeframes={wz.timeframe},
                        merged_price_high=wz.zone.price_high,
                        merged_price_low=wz.zone.price_low,
                        merged_midpoint=wz.zone.midpoint,
                        total_weighted_strength=wz.weighted_strength,
                        count=1,
                    )
                )

        return groups

    def _determine_dominant(
        self, weighted_zones: list[WeightedZone]
    ) -> tuple[ZoneType | None, str]:
        """Determine the dominant zone type and overall direction.

        Args:
            weighted_zones: Weighted zones to analyze.

        Returns:
            Tuple of (dominant zone type, dominant direction).
        """
        if not weighted_zones:
            return None, "neutral"

        # Aggregate weighted strength by zone type
        type_strengths: dict[ZoneType, float] = {}
        for wz in weighted_zones:
            type_strengths[wz.zone_type] = (
                type_strengths.get(wz.zone_type, 0.0) + wz.weighted_strength
            )

        if not type_strengths:
            return None, "neutral"

        # Dominant type = highest total weighted strength
        dominant_type = max(type_strengths, key=type_strengths.get)  # type: ignore[arg-type]

        # Determine overall direction from confluence-weighted zones
        bullish_strength = 0.0
        bearish_strength = 0.0
        for wz in weighted_zones:
            d = wz.zone.directional_type
            if d == "bullish":
                bullish_strength += wz.weighted_strength
            elif d == "bearish":
                bearish_strength += wz.weighted_strength

        if bullish_strength > bearish_strength and bullish_strength > 0:
            direction = "bullish"
        elif bearish_strength > bullish_strength and bearish_strength > 0:
            direction = "bearish"
        else:
            direction = "neutral"

        return dominant_type, direction
