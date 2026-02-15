"""ECE daily update scheduler module.

Provides scheduled ECE recalculation for all active strategies.
Runs daily at a configurable time (default: 00:00 UTC).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from confidence import ECECalculator, ECEHistoryTracker, SignalType

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)


class PredictionOutcomeStore(Protocol):
    """Protocol for prediction-outcome data store."""

    async def get_prediction_outcome_pairs(
        self,
        strategy_id: str,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
    ) -> list[tuple[float, int]]:
        """Get prediction-outcome pairs for a strategy.

        Args:
            strategy_id: Strategy identifier
            signal_type: Optional signal type filter
            since: Optional start time filter

        Returns:
            List of (confidence, outcome) tuples where outcome is 1 or 0
        """
        ...

    async def get_active_strategies(self) -> list[str]:
        """Get list of active strategy IDs.

        Returns:
            List of strategy identifiers
        """
        ...


@dataclass
class ECEUpdateResult:
    """Result of an ECE update operation.

    Attributes:
        strategy_id: Strategy identifier
        signal_type: Signal type (None for aggregate)
        ece: Calculated ECE value
        n_bins: Number of bins used
        total_samples: Total samples in calculation
        timestamp: When the update occurred
        success: Whether the update succeeded
        error: Error message if failed
    """

    strategy_id: str
    signal_type: SignalType | None
    ece: float | None
    n_bins: int
    total_samples: int
    timestamp: datetime
    success: bool
    error: str | None = None


@dataclass
class SchedulerConfig:
    """Configuration for ECE scheduler.

    Attributes:
        update_time_utc: Time of day to run updates (HH:MM format, 24h)
        min_samples: Minimum samples required for ECE calculation
        signal_types: Signal types to calculate separately
        retry_attempts: Number of retry attempts on failure
        retry_delay_seconds: Delay between retries
    """

    update_time_utc: str = "00:00"
    min_samples: int = 30
    signal_types: list[SignalType] = field(
        default_factory=lambda: [
            SignalType.ENTRY,
            SignalType.EXIT,
            SignalType.STOP_LOSS,
            SignalType.TAKE_PROFIT,
        ]
    )
    retry_attempts: int = 3
    retry_delay_seconds: int = 60


class ECEScheduler:
    """Scheduler for daily ECE recalculation.

    Runs daily ECE updates for all active strategies at a configurable time.
    Supports manual triggering and graceful shutdown.

    Example:
        >>> scheduler = ECEScheduler(
        ...     history_tracker=ECEHistoryTracker(),
        ...     data_store=my_data_store,
        ...     config=SchedulerConfig(update_time_utc="02:00")
        ... )
        >>> await scheduler.start()
        ...  # Runs daily at 2 AM UTC
        >>> await scheduler.stop()

        # Manual trigger
        >>> results = await scheduler.trigger_update()
    """

    def __init__(
        self,
        history_tracker: ECEHistoryTracker | None = None,
        data_store: PredictionOutcomeStore | None = None,
        config: SchedulerConfig | None = None,
    ):
        """Initialize ECE scheduler.

        Args:
            history_tracker: ECE history tracker for storing results
            data_store: Data store for fetching prediction-outcome pairs
            config: Scheduler configuration
        """
        self.history_tracker = history_tracker or ECEHistoryTracker()
        self.data_store = data_store
        self.config = config or SchedulerConfig()

        self._calculator = ECECalculator(n_bins=10)
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()

    def _parse_update_time(self) -> tuple[int, int]:
        """Parse update time string into hour and minute.

        Returns:
            Tuple of (hour, minute)

        Raises:
            ValueError: If time format is invalid
        """
        try:
            hour, minute = map(int, self.config.update_time_utc.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return hour, minute
        except ValueError as e:
            msg = f"Invalid update_time_utc format: {self.config.update_time_utc}. Use HH:MM (24h)"
            raise ValueError(msg) from e

    def _get_next_run_time(self) -> datetime:
        """Calculate the next scheduled run time.

        Returns:
            Datetime of next run in UTC
        """
        hour, minute = self._parse_update_time()
        now = datetime.now(UTC)

        # Create target time for today
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If target time has passed today, schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)

        return target

    def _get_seconds_until_next_run(self) -> float:
        """Calculate seconds until next scheduled run.

        Returns:
            Seconds until next run
        """
        next_run = self._get_next_run_time()
        now = datetime.now(UTC)
        return (next_run - now).total_seconds()

    async def start(self) -> None:
        """Start the scheduler loop.

        Begins the daily update schedule. Use stop() to gracefully shutdown.
        """
        if self._running:
            logger.warning("Scheduler is already running")
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(
            f"ECE scheduler started. Next run at {self._get_next_run_time().isoformat()}"
        )

    async def stop(self) -> None:
        """Stop the scheduler gracefully.

        Cancels the scheduler loop and waits for completion.
        """
        if not self._running:
            return

        logger.info("Stopping ECE scheduler...")
        self._running = False
        self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Scheduler task did not stop gracefully, cancelling...")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        await self.history_tracker.close()
        logger.info("ECE scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop.

        Runs indefinitely until stop() is called.
        """
        while self._running:
            try:
                # Wait until next scheduled run
                seconds_until = self._get_seconds_until_next_run()
                logger.debug(f"Next ECE update in {seconds_until:.0f} seconds")

                # Wait with stop event check
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=seconds_until,
                    )
                    # Stop event was set
                    break
                except asyncio.TimeoutError:
                    # Time to run the update
                    pass

                if not self._running:
                    break

                # Run the update
                await self._run_daily_update()

            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled")
                break
            except Exception:
                logger.exception("Error in scheduler loop")
                # Wait a bit before retrying to avoid tight error loops
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=300,  # 5 minutes
                    )
                    break
                except asyncio.TimeoutError:
                    continue

    async def _run_daily_update(self) -> list[ECEUpdateResult]:
        """Execute the daily ECE update for all active strategies.

        Returns:
            List of update results
        """
        logger.info("Starting daily ECE update")
        start_time = datetime.now(UTC)

        results: list[ECEUpdateResult] = []

        try:
            # Get active strategies
            if self.data_store is None:
                logger.warning("No data store configured, cannot fetch strategies")
                return results

            strategies = await self.data_store.get_active_strategies()
            logger.info(f"Found {len(strategies)} active strategies to update")

            for strategy_id in strategies:
                strategy_results = await self._update_strategy(strategy_id)
                results.extend(strategy_results)

            # Log summary
            successful = sum(1 for r in results if r.success)
            failed = len(results) - successful
            duration = (datetime.now(UTC) - start_time).total_seconds()

            logger.info(
                f"Daily ECE update complete: {successful} successful, {failed} failed, "
                f"{duration:.1f}s"
            )

        except Exception:
            logger.exception("Error during daily ECE update")

        return results

    async def _update_strategy(self, strategy_id: str) -> list[ECEUpdateResult]:
        """Update ECE for a single strategy.

        Calculates ECE for aggregate and per-signal-type.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of update results
        """
        results: list[ECEUpdateResult] = []

        # Calculate aggregate ECE (all signal types combined)
        aggregate_result = await self._calculate_and_store_ece(
            strategy_id=strategy_id,
            signal_type=None,
        )
        results.append(aggregate_result)

        # Calculate per-signal-type ECE
        for signal_type in self.config.signal_types:
            result = await self._calculate_and_store_ece(
                strategy_id=strategy_id,
                signal_type=signal_type,
            )
            results.append(result)

        return results

    async def _calculate_and_store_ece(
        self,
        strategy_id: str,
        signal_type: SignalType | None,
    ) -> ECEUpdateResult:
        """Calculate and store ECE for a strategy.

        Args:
            strategy_id: Strategy identifier
            signal_type: Optional signal type

        Returns:
            Update result
        """
        timestamp = datetime.now(UTC)

        try:
            if self.data_store is None:
                return ECEUpdateResult(
                    strategy_id=strategy_id,
                    signal_type=signal_type,
                    ece=None,
                    n_bins=10,
                    total_samples=0,
                    timestamp=timestamp,
                    success=False,
                    error="No data store configured",
                )

            # Fetch prediction-outcome pairs
            pairs = await self.data_store.get_prediction_outcome_pairs(
                strategy_id=strategy_id,
                signal_type=signal_type,
            )

            if len(pairs) < self.config.min_samples:
                return ECEUpdateResult(
                    strategy_id=strategy_id,
                    signal_type=signal_type,
                    ece=None,
                    n_bins=10,
                    total_samples=len(pairs),
                    timestamp=timestamp,
                    success=False,
                    error=f"Insufficient samples: {len(pairs)} < {self.config.min_samples}",
                )

            # Unzip predictions and outcomes
            predictions = [p for p, _ in pairs]
            outcomes = [o for _, o in pairs]

            # Calculate ECE
            ece_result = self._calculator.calculate(
                predictions=predictions,
                outcomes=outcomes,
                signal_type=signal_type,
                strategy_id=strategy_id,
            )

            # Store in history
            success = await self.history_tracker.record_ece(ece_result)

            if success:
                logger.debug(
                    f"Updated ECE for {strategy_id}/{signal_type}: {ece_result.ece:.4f}"
                )
            else:
                logger.warning(f"Failed to store ECE for {strategy_id}/{signal_type}")

            return ECEUpdateResult(
                strategy_id=strategy_id,
                signal_type=signal_type,
                ece=ece_result.ece,
                n_bins=ece_result.n_bins,
                total_samples=ece_result.total_samples,
                timestamp=timestamp,
                success=success,
            )

        except Exception as e:
            logger.exception(f"Error calculating ECE for {strategy_id}/{signal_type}")
            return ECEUpdateResult(
                strategy_id=strategy_id,
                signal_type=signal_type,
                ece=None,
                n_bins=10,
                total_samples=0,
                timestamp=timestamp,
                success=False,
                error=str(e),
            )

    async def trigger_update(
        self, strategy_ids: list[str] | None = None
    ) -> list[ECEUpdateResult]:
        """Manually trigger an ECE update.

        Args:
            strategy_ids: Optional list of specific strategies to update.
                         If None, updates all active strategies.

        Returns:
            List of update results
        """
        logger.info(
            f"Manual ECE update triggered for strategies: {strategy_ids or 'all'}"
        )

        if strategy_ids is None:
            return await self._run_daily_update()

        results: list[ECEUpdateResult] = []
        for strategy_id in strategy_ids:
            strategy_results = await self._update_strategy(strategy_id)
            results.extend(strategy_results)

        return results

    def is_running(self) -> bool:
        """Check if scheduler is currently running.

        Returns:
            True if scheduler is active
        """
        return self._running and self._task is not None and not self._task.done()

    def get_next_run(self) -> datetime | None:
        """Get the next scheduled run time.

        Returns:
            Next run datetime or None if not running
        """
        if not self._running:
            return None
        return self._get_next_run_time()


class InMemoryPredictionOutcomeStore:
    """In-memory implementation of prediction-outcome store.

    Useful for testing and development.
    """

    def __init__(self):
        """Initialize in-memory store."""
        self._data: dict[str, list[tuple[float, int]]] = {}
        self._active_strategies: set[str] = set()

    def add_prediction_outcome(
        self,
        strategy_id: str,
        confidence: float,
        outcome: int,
    ) -> None:
        """Add a prediction-outcome pair.

        Args:
            strategy_id: Strategy identifier
            confidence: Predicted confidence (0.0-1.0)
            outcome: Actual outcome (1=correct, 0=incorrect)
        """
        if strategy_id not in self._data:
            self._data[strategy_id] = []
        self._data[strategy_id].append((confidence, outcome))
        self._active_strategies.add(strategy_id)

    def set_active_strategies(self, strategies: list[str]) -> None:
        """Set the list of active strategies.

        Args:
            strategies: List of strategy IDs
        """
        self._active_strategies = set(strategies)

    async def get_prediction_outcome_pairs(
        self,
        strategy_id: str,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
    ) -> list[tuple[float, int]]:
        """Get prediction-outcome pairs for a strategy.

        Note: signal_type and since filters are not implemented for in-memory store.
        """
        return self._data.get(strategy_id, [])

    async def get_active_strategies(self) -> list[str]:
        """Get list of active strategy IDs."""
        return sorted(self._active_strategies)
