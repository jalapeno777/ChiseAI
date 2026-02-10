"""Gap detector for identifying missing data in OHLCV time series.

Detects gaps in time series data where expected candles are missing,
enabling automatic backfill operations.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import TIMEFRAME_CONFIG, Timeframe

logger = logging.getLogger(__name__)


@dataclass
class DataGap:
    """Represents a gap in OHLCV data.

    Attributes:
        start_timestamp: Start of the gap (milliseconds)
        end_timestamp: End of the gap (milliseconds)
        expected_candles: Number of candles that should exist in this range
        timeframe: The timeframe this gap is in
    """

    start_timestamp: int
    end_timestamp: int
    expected_candles: int
    timeframe: Timeframe

    @property
    def duration_seconds(self) -> float:
        """Duration of the gap in seconds."""
        return (self.end_timestamp - self.start_timestamp) / 1000

    @property
    def start_datetime(self) -> datetime:
        """Start of gap as UTC datetime."""
        return datetime.fromtimestamp(self.start_timestamp / 1000, tz=UTC)

    @property
    def end_datetime(self) -> datetime:
        """End of gap as UTC datetime."""
        return datetime.fromtimestamp(self.end_timestamp / 1000, tz=UTC)


class GapDetector:
    """Detector for missing data gaps in OHLCV time series."""

    def __init__(
        self,
        tolerance_percent: float = 5.0,
        max_gap_duration_hours: float = 24.0,
    ):
        """Initialize gap detector.

        Args:
            tolerance_percent: Percentage tolerance for timestamp alignment
                (accounts for small timing variations)
            max_gap_duration_hours: Maximum gap duration to report
                (longer gaps may indicate market closure)
        """
        self.tolerance_percent = tolerance_percent
        self.max_gap_duration_hours = max_gap_duration_hours

    def detect_gaps(
        self,
        data: list[OHLCVData],
        timeframe: Timeframe,
        expected_start: int | None = None,
        expected_end: int | None = None,
    ) -> list[DataGap]:
        """Detect gaps in OHLCV data.

        Args:
            data: List of OHLCV data points (must be sorted by timestamp)
            timeframe: Timeframe the data represents
            expected_start: Expected start timestamp (optional)
            expected_end: Expected end timestamp (optional)

        Returns:
            List of DataGap objects representing detected gaps
        """
        gaps: list[DataGap] = []

        if not data:
            logger.warning("No data provided for gap detection")
            return gaps

        # Sort data by timestamp to ensure proper ordering
        sorted_data = sorted(data, key=lambda x: x.timestamp)

        tf_config = TIMEFRAME_CONFIG[timeframe]
        interval_ms = tf_config.interval_seconds * 1000

        # Check for gap at the beginning
        if expected_start is not None:
            first_ts = sorted_data[0].timestamp
            if first_ts > expected_start + self._get_tolerance(interval_ms):
                gap_duration_ms = first_ts - expected_start
                expected_count = int(gap_duration_ms / interval_ms)

                if self._is_valid_gap_duration(gap_duration_ms):
                    gaps.append(
                        DataGap(
                            start_timestamp=expected_start,
                            end_timestamp=first_ts,
                            expected_candles=expected_count,
                            timeframe=timeframe,
                        )
                    )
                    logger.info(
                        f"Detected leading gap: {expected_count} missing candles "
                        f"at {timeframe.value}"
                    )

        # Check for gaps between consecutive candles
        for i in range(1, len(sorted_data)):
            prev_ts = sorted_data[i - 1].timestamp
            curr_ts = sorted_data[i].timestamp

            gap_duration_ms = curr_ts - prev_ts
            expected_interval = interval_ms

            # Check if gap is larger than expected interval (with tolerance)
            if gap_duration_ms > expected_interval + self._get_tolerance(
                expected_interval
            ):
                expected_count = int(gap_duration_ms / expected_interval)

                if self._is_valid_gap_duration(gap_duration_ms):
                    gaps.append(
                        DataGap(
                            start_timestamp=prev_ts + expected_interval,
                            end_timestamp=curr_ts,
                            expected_candles=expected_count,
                            timeframe=timeframe,
                        )
                    )

        # Check for gap at the end
        if expected_end is not None:
            last_ts = sorted_data[-1].timestamp
            if expected_end > last_ts + self._get_tolerance(interval_ms):
                gap_duration_ms = expected_end - last_ts
                expected_count = int(gap_duration_ms / interval_ms)

                if self._is_valid_gap_duration(gap_duration_ms):
                    gaps.append(
                        DataGap(
                            start_timestamp=last_ts + interval_ms,
                            end_timestamp=expected_end,
                            expected_candles=expected_count,
                            timeframe=timeframe,
                        )
                    )
                    logger.info(
                        f"Detected trailing gap: {expected_count} missing candles "
                        f"at {timeframe.value}"
                    )

        if gaps:
            total_missing = sum(g.expected_candles for g in gaps)
            logger.info(
                f"Detected {len(gaps)} gaps with {total_missing} "
                f"total missing candles at {timeframe.value}"
            )

        return gaps

    def detect_gaps_batch(
        self,
        data_map: dict[Timeframe, list[OHLCVData]],
        expected_ranges: dict[Timeframe, tuple[int, int]] | None = None,
    ) -> dict[Timeframe, list[DataGap]]:
        """Detect gaps across multiple timeframes.

        Args:
            data_map: Dictionary mapping timeframe to data list
            expected_ranges: Optional dict mapping timeframe to
                (expected_start, expected_end) tuples

        Returns:
            Dictionary mapping timeframe to list of DataGap objects
        """
        results: dict[Timeframe, list[DataGap]] = {}

        for timeframe, data in data_map.items():
            expected_start = None
            expected_end = None

            if expected_ranges and timeframe in expected_ranges:
                expected_start, expected_end = expected_ranges[timeframe]

            results[timeframe] = self.detect_gaps(
                data, timeframe, expected_start, expected_end
            )

        return results

    def _get_tolerance(self, interval_ms: int) -> float:
        """Calculate tolerance in milliseconds for timestamp alignment.

        Args:
            interval_ms: Expected interval in milliseconds

        Returns:
            Tolerance in milliseconds
        """
        return interval_ms * (self.tolerance_percent / 100.0)

    def _is_valid_gap_duration(self, gap_duration_ms: float) -> bool:
        """Check if a gap duration should be reported.

        Filters out gaps that are likely due to market closure
        or other expected interruptions.

        Args:
            gap_duration_ms: Gap duration in milliseconds

        Returns:
            True if gap should be reported
        """
        max_duration_ms = self.max_gap_duration_hours * 3600 * 1000
        return gap_duration_ms <= max_duration_ms

    def estimate_missing_candles(
        self,
        gap: DataGap,
        timeframe: Timeframe,
    ) -> int:
        """Estimate the number of missing candles in a gap.

        Args:
            gap: The data gap to analyze
            timeframe: The timeframe

        Returns:
            Estimated number of missing candles
        """
        tf_config = TIMEFRAME_CONFIG[timeframe]
        interval_ms = tf_config.interval_seconds * 1000

        duration_ms = gap.end_timestamp - gap.start_timestamp
        return max(0, int(duration_ms / interval_ms))
