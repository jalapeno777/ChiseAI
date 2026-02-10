"""Timeframe aggregator for multi-timeframe data consistency.

Aggregates OHLCV data across multiple timeframes and validates
consistency between aggregated and fetched data.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import (
    TIMEFRAME_CONFIG,
    Timeframe,
    get_all_timeframes,
)

logger = logging.getLogger(__name__)


@dataclass
class AggregationResult:
    """Result of timeframe aggregation and validation.

    Attributes:
        timeframe: The timeframe this result represents
        data: Aggregated OHLCV data
        is_consistent: Whether aggregated data matches fetched data
        consistency_errors: List of consistency error messages
        aggregated_from: The source timeframe used for aggregation (if applicable)
    """

    timeframe: Timeframe
    data: list[OHLCVData]
    is_consistent: bool
    consistency_errors: list[str] = field(default_factory=list)
    aggregated_from: Timeframe | None = None


class TimeframeAggregator:
    """Aggregator for multi-timeframe OHLCV data with consistency validation."""

    def __init__(self, tolerance_percent: float = 0.1):
        """Initialize timeframe aggregator.

        Args:
            tolerance_percent: Percentage tolerance for price comparisons
                when validating consistency
        """
        self.tolerance_percent = tolerance_percent

    def aggregate(
        self,
        source_data: list[OHLCVData],
        source_timeframe: Timeframe,
        target_timeframe: Timeframe,
    ) -> list[OHLCVData]:
        """Aggregate OHLCV data from a smaller to larger timeframe.

        For example, aggregate 1m data into 5m candles.

        Args:
            source_data: OHLCV data at the source timeframe
            source_timeframe: The timeframe of the source data
            target_timeframe: The desired output timeframe

        Returns:
            List of aggregated OHLCVData at target timeframe

        Raises:
            ValueError: If target timeframe is smaller than source
        """
        source_config = TIMEFRAME_CONFIG[source_timeframe]
        target_config = TIMEFRAME_CONFIG[target_timeframe]

        if target_config.interval_seconds < source_config.interval_seconds:
            raise ValueError(
                f"Cannot aggregate from {source_timeframe.value} to "
                f"{target_timeframe.value}: target must be larger timeframe"
            )

        if not source_data:
            return []

        # Calculate aggregation ratio
        ratio = target_config.interval_seconds // source_config.interval_seconds

        if ratio == 1:
            # No aggregation needed
            return source_data

        # Sort by timestamp
        sorted_data = sorted(source_data, key=lambda x: x.timestamp)

        aggregated: list[OHLCVData] = []
        current_bucket: list[OHLCVData] = []

        # Calculate bucket start times aligned to target timeframe
        first_ts = sorted_data[0].timestamp
        bucket_start = (first_ts // (target_config.interval_seconds * 1000)) * (
            target_config.interval_seconds * 1000
        )

        for candle in sorted_data:
            # Check if candle belongs to current bucket
            if candle.timestamp < bucket_start + target_config.interval_seconds * 1000:
                current_bucket.append(candle)
            else:
                # Process current bucket and start new one
                if current_bucket:
                    aggregated.append(self._aggregate_bucket(current_bucket))

                # Move to next bucket(s) if needed (handle gaps)
                while (
                    candle.timestamp
                    >= bucket_start + target_config.interval_seconds * 1000
                ):
                    bucket_start += target_config.interval_seconds * 1000

                current_bucket = [candle]

        # Process final bucket
        if current_bucket:
            aggregated.append(self._aggregate_bucket(current_bucket))

        logger.debug(
            f"Aggregated {len(source_data)} {source_timeframe.value} candles "
            f"into {len(aggregated)} {target_timeframe.value} candles"
        )

        return aggregated

    def _aggregate_bucket(self, candles: list[OHLCVData]) -> OHLCVData:
        """Aggregate a bucket of candles into a single candle.

        Args:
            candles: List of candles to aggregate

        Returns:
            Aggregated OHLCVData
        """
        if not candles:
            raise ValueError("Cannot aggregate empty bucket")

        # Use the first candle's timestamp (aligned to bucket start)
        timestamp = candles[0].timestamp

        # OHLC aggregation
        open_price = candles[0].open_price
        close_price = candles[-1].close_price
        high_price = max(c.high_price for c in candles)
        low_price = min(c.low_price for c in candles)
        volume = sum(c.volume for c in candles)

        return OHLCVData(
            timestamp=timestamp,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
        )

    def validate_consistency(
        self,
        aggregated_data: list[OHLCVData],
        fetched_data: list[OHLCVData],
        target_timeframe: Timeframe,
    ) -> tuple[bool, list[str]]:
        """Validate that aggregated data matches fetched data.

        Args:
            aggregated_data: Data produced by aggregation
            fetched_data: Data fetched directly from exchange
            target_timeframe: The timeframe being validated

        Returns:
            Tuple of (is_consistent, list of error messages)
        """
        errors: list[str] = []

        if not aggregated_data and not fetched_data:
            return True, []

        if not aggregated_data:
            return False, ["Aggregated data is empty but fetched data exists"]

        if not fetched_data:
            return False, ["Fetched data is empty but aggregated data exists"]

        # Create lookup by timestamp
        aggregated_by_ts = {d.timestamp: d for d in aggregated_data}
        fetched_by_ts = {d.timestamp: d for d in fetched_data}

        # Check for missing timestamps
        agg_timestamps = set(aggregated_by_ts.keys())
        fetched_timestamps = set(fetched_by_ts.keys())

        missing_in_agg = fetched_timestamps - agg_timestamps
        missing_in_fetched = agg_timestamps - fetched_timestamps

        if missing_in_agg:
            errors.append(
                f"Timestamps in fetched but not aggregated: "
                f"{len(missing_in_agg)} candles"
            )

        if missing_in_fetched:
            errors.append(
                f"Timestamps in aggregated but not fetched: "
                f"{len(missing_in_fetched)} candles"
            )

        # Compare overlapping candles
        common_timestamps = agg_timestamps & fetched_timestamps

        for ts in common_timestamps:
            agg = aggregated_by_ts[ts]
            fetched = fetched_by_ts[ts]

            # Check OHLCV values within tolerance
            checks = [
                ("open", agg.open_price, fetched.open_price),
                ("high", agg.high_price, fetched.high_price),
                ("low", agg.low_price, fetched.low_price),
                ("close", agg.close_price, fetched.close_price),
                ("volume", agg.volume, fetched.volume),
            ]

            for name, agg_val, fetched_val in checks:
                if not self._values_match(agg_val, fetched_val):
                    errors.append(
                        f"Mismatch at {ts} {name}: "
                        f"aggregated={agg_val}, fetched={fetched_val}"
                    )

        is_consistent = len(errors) == 0

        if not is_consistent:
            logger.warning(
                f"Consistency validation failed for {target_timeframe.value}: "
                f"{len(errors)} errors"
            )

        return is_consistent, errors

    def _values_match(self, val1: float, val2: float) -> bool:
        """Check if two values match within tolerance.

        Args:
            val1: First value
            val2: Second value

        Returns:
            True if values match within tolerance
        """
        if val1 == 0 and val2 == 0:
            return True

        if val1 == 0 or val2 == 0:
            return False

        diff_percent = abs(val1 - val2) / max(abs(val1), abs(val2)) * 100
        return diff_percent <= self.tolerance_percent

    def aggregate_and_validate(
        self,
        data_map: dict[Timeframe, list[OHLCVData]],
        base_timeframe: Timeframe = Timeframe.MINUTE_1,
    ) -> dict[Timeframe, AggregationResult]:
        """Aggregate data from base timeframe and validate consistency.

        Args:
            data_map: Dictionary mapping timeframe to OHLCV data
            base_timeframe: The base timeframe to aggregate from

        Returns:
            Dictionary mapping timeframe to AggregationResult
        """
        results: dict[Timeframe, AggregationResult] = {}

        if base_timeframe not in data_map:
            logger.error(f"Base timeframe {base_timeframe.value} not in data map")
            return results

        base_data = data_map[base_timeframe]

        # Process all timeframes
        for timeframe in get_all_timeframes():
            if timeframe == base_timeframe:
                # Base timeframe uses original data
                results[timeframe] = AggregationResult(
                    timeframe=timeframe,
                    data=data_map.get(timeframe, []),
                    is_consistent=True,
                    consistency_errors=[],
                    aggregated_from=None,
                )
            elif timeframe in data_map:
                # Aggregate from base and validate
                try:
                    aggregated = self.aggregate(base_data, base_timeframe, timeframe)

                    fetched = data_map[timeframe]
                    is_consistent, errors = self.validate_consistency(
                        aggregated, fetched, timeframe
                    )

                    results[timeframe] = AggregationResult(
                        timeframe=timeframe,
                        data=aggregated,
                        is_consistent=is_consistent,
                        consistency_errors=errors,
                        aggregated_from=base_timeframe,
                    )

                except Exception as e:
                    logger.error(f"Aggregation failed for {timeframe.value}: {e}")
                    results[timeframe] = AggregationResult(
                        timeframe=timeframe,
                        data=[],
                        is_consistent=False,
                        consistency_errors=[str(e)],
                        aggregated_from=base_timeframe,
                    )
            else:
                # Aggregate but no fetched data to compare
                try:
                    aggregated = self.aggregate(base_data, base_timeframe, timeframe)

                    results[timeframe] = AggregationResult(
                        timeframe=timeframe,
                        data=aggregated,
                        is_consistent=True,
                        consistency_errors=["No fetched data available for validation"],
                        aggregated_from=base_timeframe,
                    )

                except Exception as e:
                    logger.error(f"Aggregation failed for {timeframe.value}: {e}")
                    results[timeframe] = AggregationResult(
                        timeframe=timeframe,
                        data=[],
                        is_consistent=False,
                        consistency_errors=[str(e)],
                        aggregated_from=base_timeframe,
                    )

        return results

    def get_consistency_summary(
        self,
        results: dict[Timeframe, AggregationResult],
    ) -> dict[str, Any]:
        """Generate a summary of consistency across all timeframes.

        Args:
            results: Dictionary of AggregationResult by timeframe

        Returns:
            Summary dictionary with consistency metrics
        """
        total_timeframes = len(results)
        consistent_timeframes = sum(1 for r in results.values() if r.is_consistent)

        total_errors = sum(len(r.consistency_errors) for r in results.values())

        timeframe_status = {
            tf.value: {
                "consistent": r.is_consistent,
                "errors": len(r.consistency_errors),
                "candles": len(r.data),
                "aggregated_from": (
                    r.aggregated_from.value if r.aggregated_from else None
                ),
            }
            for tf, r in results.items()
        }

        return {
            "total_timeframes": total_timeframes,
            "consistent_timeframes": consistent_timeframes,
            "inconsistent_timeframes": total_timeframes - consistent_timeframes,
            "total_consistency_errors": total_errors,
            "overall_consistent": consistent_timeframes == total_timeframes,
            "timeframe_status": timeframe_status,
        }
