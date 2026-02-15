"""ECE Daily Update Scheduler module.

Provides scheduled daily recalculation of Expected Calibration Error (ECE)
using prediction-outcome pairs. Uses asyncio-based scheduling without
external dependencies like APScheduler.

Example:
    >>> from confidence.ece_scheduler import ECEScheduler, SchedulerConfig
    >>> from confidence.ece_tracker import ECEHistoryTracker
    >>>
    >>> config = SchedulerConfig(update_time_utc="00:00")
    >>> tracker = ECEHistoryTracker()
    >>> scheduler = ECEScheduler(config, tracker)
    >>>
    >>> # Start the scheduler
    >>> await scheduler.start()
    >>>
    >>> # Or trigger manual update
    >>> result = await scheduler.trigger_update()
    >>>
    >>> # Stop the scheduler
    >>> await scheduler.stop()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from confidence.ece import ECECalculator, ECEResult, SignalType
from confidence.ece_tracker import ECEHistoryTracker

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchedulerConfig:
    """Configuration for the ECE scheduler.

    Attributes:
        update_time_utc: Time of day to run ECE update (HH:MM format, 24-hour)
        min_samples: Minimum number of samples required for ECE calculation
        max_retry_attempts: Maximum number of retry attempts on failure
        retry_delay_seconds: Delay between retry attempts
        n_bins: Number of bins for ECE calculation
    """

    update_time_utc: str = "00:00"
    min_samples: int = 10
    max_retry_attempts: int = 3
    retry_delay_seconds: float = 60.0
    n_bins: int = 10

    def __post_init__(self):
        # Validate time format
        try:
            datetime.strptime(self.update_time_utc, "%H:%M")
        except ValueError as e:
            msg = f"Invalid update_time_utc format: {self.update_time_utc}. Use HH:MM format."
            raise ValueError(msg) from e

    def get_next_update_time(self, from_time: datetime | None = None) -> datetime:
        """Calculate the next scheduled update time.

        Args:
            from_time: Reference time (defaults to now)

        Returns:
            Next scheduled update time in UTC
        """
        now = from_time or datetime.now(UTC)
        hour, minute = map(int, self.update_time_utc.split(":"))

        # Create next update time for today
        next_update = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If already passed, schedule for tomorrow
        if next_update <= now:
            next_update += timedelta(days=1)

        return next_update


@dataclass(frozen=True)
class PredictionOutcomePair:
    """A single prediction-outcome pair for ECE calculation.

    Attributes:
        prediction: Confidence score (0.0-1.0)
        outcome: Binary outcome (1=correct, 0=incorrect)
        timestamp: When the prediction was made
        signal_type: Type of signal (entry, exit, etc.)
        strategy_id: Strategy identifier
    """

    prediction: float
    outcome: int
    timestamp: datetime
    signal_type: SignalType | None = None
    strategy_id: str | None = None


@dataclass(frozen=True)
class ECEUpdateResult:
    """Result of an ECE update operation.

    Attributes:
        success: Whether the update was successful
        timestamp: When the update was performed
        ece_result: ECEResult from calculation (if successful)
        sample_count: Number of samples used in calculation
        error_message: Error message (if failed)
        retry_count: Number of retry attempts made
    """

    success: bool
    timestamp: datetime
    ece_result: ECEResult | None = None
    sample_count: int = 0
    error_message: str | None = None
    retry_count: int = 0


class PredictionOutcomeStore(Protocol):
    """Protocol for prediction-outcome data stores.

    Implementations must provide methods to fetch prediction-outcome
    pairs for ECE calculation.
    """

    async def fetch_pairs(
        self,
        since: datetime | None = None,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
    ) -> Sequence[PredictionOutcomePair]:
        """Fetch prediction-outcome pairs from the store.

        Args:
            since: Only fetch pairs after this time
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type

        Returns:
            Sequence of prediction-outcome pairs
        """
        ...

    async def get_sample_count(
        self,
        since: datetime | None = None,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
    ) -> int:
        """Get count of available samples without fetching all data.

        Args:
            since: Only count pairs after this time
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type

        Returns:
            Number of matching samples
        """
        ...


class InMemoryPredictionOutcomeStore:
    """In-memory implementation of PredictionOutcomeStore for testing.

    Stores prediction-outcome pairs in memory. Suitable for testing
    and development, not for production use.

    Example:
        >>> store = InMemoryPredictionOutcomeStore()
        >>> pair = PredictionOutcomePair(
        ...     prediction=0.85,
        ...     outcome=1,
        ...     timestamp=datetime.now(UTC)
        ... )
        >>> await store.add_pair(pair)
        >>> pairs = await store.fetch_pairs()
    """

    def __init__(self):
        """Initialize empty in-memory store."""
        self._pairs: list[PredictionOutcomePair] = []
        self._lock = asyncio.Lock()

    async def add_pair(self, pair: PredictionOutcomePair) -> None:
        """Add a prediction-outcome pair to the store.

        Args:
            pair: Prediction-outcome pair to add
        """
        async with self._lock:
            self._pairs.append(pair)

    async def add_pairs(self, pairs: Sequence[PredictionOutcomePair]) -> int:
        """Add multiple prediction-outcome pairs to the store.

        Args:
            pairs: Sequence of pairs to add

        Returns:
            Number of pairs added
        """
        async with self._lock:
            self._pairs.extend(pairs)
            return len(pairs)

    async def clear(self) -> None:
        """Clear all pairs from the store."""
        async with self._lock:
            self._pairs.clear()

    async def fetch_pairs(
        self,
        since: datetime | None = None,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
    ) -> Sequence[PredictionOutcomePair]:
        """Fetch prediction-outcome pairs from the store.

        Args:
            since: Only fetch pairs after this time
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type

        Returns:
            Sequence of matching prediction-outcome pairs
        """
        async with self._lock:
            result = self._pairs.copy()

        if since:
            result = [p for p in result if p.timestamp >= since]
        if strategy_id:
            result = [p for p in result if p.strategy_id == strategy_id]
        if signal_type:
            result = [p for p in result if p.signal_type == signal_type]

        return result

    async def get_sample_count(
        self,
        since: datetime | None = None,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
    ) -> int:
        """Get count of available samples.

        Args:
            since: Only count pairs after this time
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type

        Returns:
            Number of matching samples
        """
        pairs = await self.fetch_pairs(since, strategy_id, signal_type)
        return len(pairs)


class ECEScheduler:
    """Daily ECE update scheduler.

    Runs ECE recalculation at a configurable time each day using
    asyncio-based scheduling. Fetches prediction-outcome pairs,
    calculates ECE, and stores results via ECEHistoryTracker.

    Example:
        >>> config = SchedulerConfig(update_time_utc="02:00")
        >>> tracker = ECEHistoryTracker()
        >>> store = InMemoryPredictionOutcomeStore()
        >>>
        >>> scheduler = ECEScheduler(config, tracker, store)
        >>> await scheduler.start()
        >>>
        >>> # Let it run, or trigger manually
        >>> result = await scheduler.trigger_update()
        >>>
        >>> await scheduler.stop()
    """

    def __init__(
        self,
        config: SchedulerConfig,
        history_tracker: ECEHistoryTracker,
        store: PredictionOutcomeStore | None = None,
    ):
        """Initialize the ECE scheduler.

        Args:
            config: Scheduler configuration
            history_tracker: Tracker for storing ECE results
            store: Prediction-outcome store (optional, can be set later)
        """
        self.config = config
        self.history_tracker = history_tracker
        self.store = store

        self._calculator = ECECalculator(n_bins=config.n_bins)
        self._running = False
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """Check if the scheduler is currently running."""
        return self._running

    async def start(self) -> None:
        """Start the scheduler.

        Begins the scheduling loop that triggers ECE updates
        at the configured time each day.
        """
        if self._running:
            logger.warning("Scheduler is already running")
            return

        if self.store is None:
            msg = "PredictionOutcomeStore must be set before starting scheduler"
            raise RuntimeError(msg)

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._scheduling_loop())
        logger.info(
            f"ECE scheduler started (update time: {self.config.update_time_utc} UTC)"
        )

    async def stop(self) -> None:
        """Stop the scheduler.

        Gracefully stops the scheduling loop and waits for
        any in-progress operations to complete.
        """
        if not self._running:
            logger.warning("Scheduler is not running")
            return

        logger.info("Stopping ECE scheduler...")
        self._running = False
        self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Scheduler task did not stop gracefully, cancelling...")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

        logger.info("ECE scheduler stopped")

    async def _scheduling_loop(self) -> None:
        """Main scheduling loop.

        Waits until the next scheduled update time, triggers the update,
        and then waits for the next day.
        """
        while self._running:
            try:
                next_update = self.config.get_next_update_time()
                now = datetime.now(UTC)
                wait_seconds = (next_update - now).total_seconds()

                if wait_seconds > 0:
                    logger.debug(
                        f"Next ECE update scheduled at {next_update.isoformat()}"
                    )

                    # Wait for either the scheduled time or stop signal
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=wait_seconds
                        )
                        # Stop event was set
                        break
                    except asyncio.TimeoutError:
                        # Time to run the update
                        pass

                if self._running:
                    await self.trigger_update()

            except asyncio.CancelledError:
                logger.debug("Scheduling loop cancelled")
                break
            except Exception:
                logger.exception("Error in scheduling loop")
                # Wait a bit before retrying to avoid tight error loops
                await asyncio.sleep(60)

    async def trigger_update(self) -> ECEUpdateResult:
        """Manually trigger an ECE update.

        Fetches prediction-outcome pairs, calculates ECE, and stores
        the result. Retries on failure according to config.

        Returns:
            ECEUpdateResult with details of the operation
        """
        if self.store is None:
            msg = "PredictionOutcomeStore must be set before triggering update"
            raise RuntimeError(msg)

        timestamp = datetime.now(UTC)
        retry_count = 0
        last_error: Exception | None = None

        while retry_count <= self.config.max_retry_attempts:
            try:
                result = await self._perform_update()
                return ECEUpdateResult(
                    success=True,
                    timestamp=timestamp,
                    ece_result=result,
                    sample_count=result.total_samples,
                    retry_count=retry_count,
                )
            except Exception as e:
                last_error = e
                retry_count += 1

                if retry_count <= self.config.max_retry_attempts:
                    logger.warning(
                        f"ECE update failed (attempt {retry_count}), "
                        f"retrying in {self.config.retry_delay_seconds}s: {e}"
                    )
                    await asyncio.sleep(self.config.retry_delay_seconds)
                else:
                    logger.exception("ECE update failed after all retry attempts")

        return ECEUpdateResult(
            success=False,
            timestamp=timestamp,
            error_message=str(last_error) if last_error else "Unknown error",
            retry_count=retry_count - 1,
        )

    async def _perform_update(self) -> ECEResult:
        """Perform the actual ECE update.

        Fetches pairs, validates sample count, calculates ECE,
        and stores the result.

        Returns:
            ECEResult from the calculation

        Raises:
            ValueError: If insufficient samples available
        """
        assert self.store is not None

        # Fetch all prediction-outcome pairs
        pairs = await self.store.fetch_pairs()

        if len(pairs) < self.config.min_samples:
            msg = (
                f"Insufficient samples for ECE calculation: "
                f"{len(pairs)} < {self.config.min_samples}"
            )
            raise ValueError(msg)

        # Extract predictions and outcomes
        predictions = [p.prediction for p in pairs]
        outcomes = [p.outcome for p in pairs]

        # Calculate ECE
        result = self._calculator.calculate(
            predictions=predictions,
            outcomes=outcomes,
        )

        # Store in history
        await self.history_tracker.record_ece(result)

        logger.info(
            f"ECE update completed: ECE={result.ece:.4f}, "
            f"samples={result.total_samples}"
        )

        return result

    async def get_next_update_time(self) -> datetime:
        """Get the next scheduled update time.

        Returns:
            Next scheduled update time in UTC
        """
        return self.config.get_next_update_time()

    def set_store(self, store: PredictionOutcomeStore) -> None:
        """Set or update the prediction-outcome store.

        Args:
            store: New prediction-outcome store
        """
        self.store = store


async def create_default_scheduler(
    history_tracker: ECEHistoryTracker,
    store: PredictionOutcomeStore | None = None,
    update_time_utc: str = "00:00",
) -> ECEScheduler:
    """Create a scheduler with default configuration.

    Convenience factory function for creating a scheduler with
    sensible defaults.

    Args:
        history_tracker: Tracker for storing ECE results
        store: Optional prediction-outcome store
        update_time_utc: Time of day for updates (HH:MM)

    Returns:
        Configured ECEScheduler instance
    """
    config = SchedulerConfig(update_time_utc=update_time_utc)
    return ECEScheduler(config, history_tracker, store)
