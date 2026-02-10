"""Backfiller for automatically filling missing OHLCV data gaps.

Provides automatic backfill operations to retrieve missing historical data
and integrate it into the existing dataset.
"""

import asyncio
import logging
from dataclasses import dataclass

from data_ingestion.gap_detector import DataGap, GapDetector
from data_ingestion.ohlcv_fetcher import OHLCVData, OHLCVFetcher
from data_ingestion.timeframe_config import Timeframe

logger = logging.getLogger(__name__)


@dataclass
class BackfillResult:
    """Result of a backfill operation.

    Attributes:
        gap: The gap that was targeted for backfill
        fetched_candles: Number of candles successfully fetched
        success: Whether the backfill was successful
        error_message: Error message if backfill failed
    """

    gap: DataGap
    fetched_candles: int
    success: bool
    error_message: str | None


class Backfiller:
    """Automatic backfiller for missing OHLCV data."""

    def __init__(
        self,
        fetcher: OHLCVFetcher,
        gap_detector: GapDetector | None = None,
        max_backfill_candles: int = 1000,
        concurrency_limit: int = 3,
    ):
        """Initialize backfiller.

        Args:
            fetcher: OHLCVFetcher instance for retrieving data
            gap_detector: GapDetector instance (creates default if None)
            max_backfill_candles: Maximum candles to fetch per backfill request
            concurrency_limit: Maximum concurrent backfill operations
        """
        self.fetcher = fetcher
        self.gap_detector = gap_detector or GapDetector()
        self.max_backfill_candles = max_backfill_candles
        self.concurrency_limit = concurrency_limit
        self._semaphore = asyncio.Semaphore(concurrency_limit)

    async def backfill_gap(
        self,
        symbol: str,
        gap: DataGap,
    ) -> BackfillResult:
        """Backfill a single data gap.

        Args:
            symbol: Trading pair symbol
            gap: The data gap to backfill

        Returns:
            BackfillResult with operation status
        """
        async with self._semaphore:
            try:
                logger.info(
                    f"Backfilling gap for {symbol} {gap.timeframe.value}: "
                    f"{gap.expected_candles} candles from "
                    f"{gap.start_datetime.isoformat()}"
                )

                # Calculate limit (don't exceed max_backfill_candles)
                limit = min(gap.expected_candles, self.max_backfill_candles)

                # Fetch data for the gap period
                fetched_data = await self.fetcher.fetch(
                    symbol=symbol,
                    timeframe=gap.timeframe,
                    since=gap.start_timestamp,
                    limit=limit,
                )

                if not fetched_data:
                    return BackfillResult(
                        gap=gap,
                        fetched_candles=0,
                        success=False,
                        error_message="No data returned from fetcher",
                    )

                # Check if we got the expected amount of data
                fetched_count = len(fetched_data)

                if fetched_count < gap.expected_candles * 0.5:
                    logger.warning(
                        f"Partial backfill: got {fetched_count}/"
                        f"{gap.expected_candles} expected candles"
                    )

                logger.info(
                    f"Successfully backfilled {fetched_count} candles for "
                    f"{symbol} {gap.timeframe.value}"
                )

                return BackfillResult(
                    gap=gap,
                    fetched_candles=fetched_count,
                    success=True,
                    error_message=None,
                )

            except Exception as e:
                logger.error(f"Backfill failed for {symbol}: {e}")
                return BackfillResult(
                    gap=gap,
                    fetched_candles=0,
                    success=False,
                    error_message=str(e),
                )

    async def backfill_gaps(
        self,
        symbol: str,
        gaps: list[DataGap],
    ) -> list[BackfillResult]:
        """Backfill multiple gaps concurrently.

        Args:
            symbol: Trading pair symbol
            gaps: List of data gaps to backfill

        Returns:
            List of BackfillResult objects
        """
        if not gaps:
            return []

        logger.info(f"Starting backfill for {len(gaps)} gaps on {symbol}")

        # Create tasks for all gaps
        tasks = [self.backfill_gap(symbol, gap) for gap in gaps]

        # Execute with controlled concurrency
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed_results: list[BackfillResult] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Backfill task failed with exception: {result}")
                # Create a failed result for the exception
                # We need to associate it with a gap, but we lost the mapping
                # This shouldn't happen with proper error handling in backfill_gap
                continue
            processed_results.append(result)  # type: ignore[arg-type]

        # Log summary
        successful = sum(1 for r in processed_results if r.success)
        total_fetched = sum(r.fetched_candles for r in processed_results)

        logger.info(
            f"Backfill complete: {successful}/{len(gaps)} gaps filled, "
            f"{total_fetched} total candles fetched"
        )

        return processed_results

    async def detect_and_backfill(
        self,
        symbol: str,
        data: list[OHLCVData],
        timeframe: Timeframe,
        expected_start: int | None = None,
        expected_end: int | None = None,
    ) -> tuple[list[DataGap], list[BackfillResult]]:
        """Detect gaps and backfill them in one operation.

        Args:
            symbol: Trading pair symbol
            data: Current OHLCV data
            timeframe: Timeframe
            expected_start: Expected start timestamp
            expected_end: Expected end timestamp

        Returns:
            Tuple of (detected gaps, backfill results)
        """
        # Detect gaps
        gaps = self.gap_detector.detect_gaps(
            data, timeframe, expected_start, expected_end
        )

        if not gaps:
            logger.debug(f"No gaps detected for {symbol} {timeframe.value}")
            return [], []

        # Backfill detected gaps
        results = await self.backfill_gaps(symbol, gaps)

        return gaps, results

    async def detect_and_backfill_batch(
        self,
        symbol: str,
        data_map: dict[Timeframe, list[OHLCVData]],
        expected_ranges: dict[Timeframe, tuple[int, int]] | None = None,
    ) -> dict[Timeframe, tuple[list[DataGap], list[BackfillResult]]]:
        """Detect and backfill gaps across multiple timeframes.

        Args:
            symbol: Trading pair symbol
            data_map: Dictionary mapping timeframe to data list
            expected_ranges: Optional expected time ranges per timeframe

        Returns:
            Dictionary mapping timeframe to (gaps, results) tuples
        """
        results: dict[Timeframe, tuple[list[DataGap], list[BackfillResult]]] = {}

        for timeframe, data in data_map.items():
            expected_start = None
            expected_end = None

            if expected_ranges and timeframe in expected_ranges:
                expected_start, expected_end = expected_ranges[timeframe]

            gaps, backfill_results = await self.detect_and_backfill(
                symbol, data, timeframe, expected_start, expected_end
            )

            results[timeframe] = (gaps, backfill_results)

        return results

    def get_backfill_summary(self, results: list[BackfillResult]) -> dict[str, int]:
        """Generate summary statistics from backfill results.

        Args:
            results: List of BackfillResult objects

        Returns:
            Dictionary with summary statistics
        """
        total_gaps = len(results)
        successful_gaps = sum(1 for r in results if r.success)
        failed_gaps = total_gaps - successful_gaps
        total_candles = sum(r.fetched_candles for r in results)

        return {
            "total_gaps": total_gaps,
            "successful_gaps": successful_gaps,
            "failed_gaps": failed_gaps,
            "total_candles_fetched": total_candles,
        }
