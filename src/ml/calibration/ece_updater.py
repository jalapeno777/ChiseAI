"""Daily ECE Update Service module.

This module provides scheduled daily updates for ECE (Expected Calibration Error)
calculations. It fetches prediction-outcome pairs from the outcome service,
calculates ECE for each strategy and signal type, triggers alerts when ECE
exceeds thresholds, and persists results to time-series storage.

Features:
- Scheduled daily execution at configurable time
- Fetches prediction-outcome pairs from outcome service
- Calculates ECE for each strategy/signal-type combination
- Triggers alerts when ECE > 0.15 (degradation threshold)
- Persists results to InfluxDB for historical tracking
- Completes within 5 minutes (SLA requirement)

Example:
    >>> from ml.calibration.ece_updater import ECEUpdateService, UpdateConfig
    >>> from ml.calibration.ece_calculator import InMemoryOutcomeDataStore
    >>> from confidence.ece_tracker import ECEHistoryTracker
    >>>
    >>> config = UpdateConfig(update_time_utc="00:00")
    >>> store = InMemoryOutcomeDataStore()
    >>> tracker = ECEHistoryTracker()
    >>> service = ECEUpdateService(config, store, tracker)
    >>>
    >>> # Start scheduled updates
    >>> await service.start()
    >>>
    >>> # Or trigger manual update
    >>> result = await service.trigger_update()
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from confidence.ece import ECEResult, SignalType
from ml.calibration.ece_calculator import (
    ECECalculationRequest,
    OutcomeBasedECECalculator,
    OutcomeDataStore,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Alert thresholds
ECE_DEGRADATION_THRESHOLD = 0.15  # Alert when ECE exceeds this value
ECE_CRITICAL_THRESHOLD = 0.25  # Critical alert threshold
MAX_UPDATE_DURATION_SECONDS = 300  # 5 minutes SLA


@dataclass(frozen=True)
class UpdateConfig:
    """Configuration for the ECE update service.

    Attributes:
        update_time_utc: Time of day to run ECE update (HH:MM format, 24-hour)
        lookback_days: Number of days to look back for outcome data
        min_samples: Minimum samples required per calculation
        max_update_duration_seconds: Maximum allowed update duration (SLA)
        n_bins: Number of bins for ECE calculation
        ece_alert_threshold: ECE value that triggers degradation alert
        enable_alerts: Whether to trigger alerts for high ECE
        retry_attempts: Number of retry attempts on failure
        retry_delay_seconds: Delay between retry attempts
    """

    update_time_utc: str = "00:00"
    lookback_days: int = 30
    min_samples: int = 10
    max_update_duration_seconds: float = 300.0
    n_bins: int = 10
    ece_alert_threshold: float = ECE_DEGRADATION_THRESHOLD
    enable_alerts: bool = True
    retry_attempts: int = 3
    retry_delay_seconds: float = 60.0

    def __post_init__(self):
        # Validate time format
        try:
            datetime.strptime(self.update_time_utc, "%H:%M")
        except ValueError as e:
            msg = (
                f"Invalid update_time_utc format: {self.update_time_utc}. "
                "Use HH:MM format."
            )
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
class SignalTypeECE:
    """ECE result for a specific signal type.

    Attributes:
        signal_type: Type of signal (entry, exit, sl, tp)
        ece: ECE value
        sample_count: Number of samples used
        alert_triggered: Whether an alert was triggered
    """

    signal_type: SignalType
    ece: float
    sample_count: int
    alert_triggered: bool = False


@dataclass(frozen=True)
class StrategyUpdateResult:
    """Result of ECE update for a single strategy.

    Attributes:
        strategy_id: Strategy identifier
        overall_ece: Overall ECE across all signal types
        overall_samples: Total samples across all signal types
        per_signal_type: Dict mapping signal type to ECE results
        success: Whether the update succeeded
        error_message: Error message if failed
        update_duration_ms: Time taken for this strategy's update
    """

    strategy_id: str
    overall_ece: float | None = None
    overall_samples: int = 0
    per_signal_type: dict[SignalType, SignalTypeECE] = field(default_factory=dict)
    success: bool = False
    error_message: str | None = None
    update_duration_ms: float = 0.0


@dataclass(frozen=True)
class DailyUpdateResult:
    """Result of a daily ECE update operation.

    Attributes:
        success: Whether the overall update succeeded
        timestamp: When the update was performed
        strategy_results: Results for each strategy
        total_strategies: Total number of strategies processed
        successful_strategies: Number of successful strategy updates
        failed_strategies: Number of failed strategy updates
        alerts_triggered: Number of alerts triggered
        total_duration_ms: Total time for the update
        error_message: Overall error message if failed
    """

    success: bool
    timestamp: datetime
    strategy_results: dict[str, StrategyUpdateResult]
    total_strategies: int = 0
    successful_strategies: int = 0
    failed_strategies: int = 0
    alerts_triggered: int = 0
    total_duration_ms: float = 0.0
    error_message: str | None = None

    @property
    def all_strategies_successful(self) -> bool:
        """Check if all strategies were updated successfully."""
        return self.failed_strategies == 0 and self.successful_strategies > 0

    @property
    def has_degradation_alerts(self) -> bool:
        """Check if any degradation alerts were triggered."""
        return self.alerts_triggered > 0


class AlertHandler(Protocol):
    """Protocol for alert handlers.

    Implementations must provide methods to handle ECE degradation alerts.
    """

    async def handle_degradation_alert(
        self,
        strategy_id: str,
        signal_type: SignalType,
        ece: float,
        threshold: float,
    ) -> None:
        """Handle ECE degradation alert.

        Args:
            strategy_id: Strategy with degraded ECE
            signal_type: Signal type with degraded ECE
            ece: Current ECE value
            threshold: Threshold that was exceeded
        """
        ...


class LoggingAlertHandler:
    """Simple alert handler that logs alerts.

    This is the default alert handler that logs alerts at WARNING level
    for degradation and ERROR level for critical thresholds.
    """

    async def handle_degradation_alert(
        self,
        strategy_id: str,
        signal_type: SignalType,
        ece: float,
        threshold: float,
    ) -> None:
        """Log degradation alert.

        Args:
            strategy_id: Strategy with degraded ECE
            signal_type: Signal type with degraded ECE
            ece: Current ECE value
            threshold: Threshold that was exceeded
        """
        if ece >= ECE_CRITICAL_THRESHOLD:
            logger.error(
                f"CRITICAL ECE ALERT: strategy={strategy_id}, "
                f"signal_type={signal_type.value}, ece={ece:.4f}, "
                f"threshold={threshold:.4f}"
            )
        else:
            logger.warning(
                f"ECE DEGRADATION ALERT: strategy={strategy_id}, "
                f"signal_type={signal_type.value}, ece={ece:.4f}, "
                f"threshold={threshold:.4f}"
            )


class ECEUpdateService:
    """Daily ECE update service.

    Runs scheduled daily ECE recalculation at a configurable time.
    Fetches prediction-outcome pairs, calculates ECE per strategy and
    signal type, triggers alerts for degradation, and stores results.

    Example:
        >>> config = UpdateConfig(update_time_utc="02:00")
        >>> service = ECEUpdateService(config, outcome_store, history_tracker)
        >>> await service.start()
        >>>
        >>> # Let it run, or trigger manually
        >>> result = await service.trigger_update()
        >>>
        >>> await service.stop()
    """

    def __init__(
        self,
        config: UpdateConfig,
        store: OutcomeDataStore,
        history_tracker: Any,  # ECEHistoryTracker
        alert_handler: AlertHandler | None = None,
    ):
        """Initialize the ECE update service.

        Args:
            config: Update configuration
            store: Outcome data store
            history_tracker: ECE history tracker for persistence
            alert_handler: Optional custom alert handler
        """
        self.config = config
        self.store = store
        self.history_tracker = history_tracker
        self.alert_handler = alert_handler or LoggingAlertHandler()

        self._calculator = OutcomeBasedECECalculator(
            store=store,
            n_bins=config.n_bins,
        )
        self._running = False
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """Check if the service is currently running."""
        return self._running

    async def start(self) -> None:
        """Start the scheduled update service.

        Begins the scheduling loop that triggers ECE updates
        at the configured time each day.
        """
        if self._running:
            logger.warning("ECE update service is already running")
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._scheduling_loop())
        logger.info(
            "ECE update service started "
            f"(update time: {self.config.update_time_utc} UTC)"
        )

    async def stop(self) -> None:
        """Stop the service gracefully.

        Gracefully stops the scheduling loop and waits for
        any in-progress operations to complete.
        """
        if not self._running:
            logger.warning("ECE update service is not running")
            return

        logger.info("Stopping ECE update service...")
        self._running = False
        self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except TimeoutError:
                logger.warning("Service task did not stop gracefully, cancelling...")
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            self._task = None

        logger.info("ECE update service stopped")

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
                    logger.info(
                        f"Next ECE update scheduled at {next_update.isoformat()} "
                        f"(in {wait_seconds / 3600:.1f} hours)"
                    )

                    # Wait for either the scheduled time or stop signal
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=wait_seconds,
                        )
                        # Stop event was set
                        break
                    except TimeoutError:
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

    async def trigger_update(self) -> DailyUpdateResult:
        """Manually trigger an ECE update.

        Fetches prediction-outcome pairs, calculates ECE for each
        strategy and signal type, triggers alerts, and stores results.

        Returns:
            DailyUpdateResult with details of the operation
        """
        start_time = datetime.now(UTC)
        logger.info("Starting daily ECE update...")

        try:
            result = await self._perform_update()

            total_duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            # Log completion status
            if result.success:
                logger.info(
                    "Daily ECE update completed: "
                    f"strategies={result.successful_strategies}/"
                    f"{result.total_strategies}, "
                    f"alerts={result.alerts_triggered}, "
                    f"duration={total_duration_ms:.0f}ms"
                )
            else:
                logger.error(
                    f"Daily ECE update failed: {result.error_message}, "
                    f"successful={result.successful_strategies}, "
                    f"failed={result.failed_strategies}"
                )

            return result

        except Exception as e:
            logger.exception("Daily ECE update failed with exception")
            total_duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return DailyUpdateResult(
                success=False,
                timestamp=start_time,
                strategy_results={},
                error_message=str(e),
                total_duration_ms=total_duration_ms,
            )

    async def _perform_update(self) -> DailyUpdateResult:
        """Perform the actual daily ECE update.

        Fetches all strategies, calculates ECE per signal type,
        triggers alerts, and stores results.

        Returns:
            DailyUpdateResult with all strategy results
        """
        timestamp = datetime.now(UTC)
        strategy_results: dict[str, StrategyUpdateResult] = {}

        # Get all unique strategy IDs from records
        since = timestamp - timedelta(days=self.config.lookback_days)
        records = await self.store.fetch_prediction_outcomes(since=since)

        if not records:
            logger.warning("No prediction-outcome records found for update")
            return DailyUpdateResult(
                success=True,
                timestamp=timestamp,
                strategy_results={},
                total_strategies=0,
                successful_strategies=0,
                failed_strategies=0,
                alerts_triggered=0,
            )

        # Get unique strategy IDs
        strategy_ids = sorted({r.strategy_id for r in records})
        logger.info(f"Found {len(strategy_ids)} strategies to update")

        total_alerts = 0
        successful = 0
        failed = 0

        # Process each strategy
        for strategy_id in strategy_ids:
            try:
                strategy_result = await self._update_strategy(strategy_id)
                strategy_results[strategy_id] = strategy_result

                if strategy_result.success:
                    successful += 1
                else:
                    failed += 1

                total_alerts += sum(
                    1
                    for s in strategy_result.per_signal_type.values()
                    if s.alert_triggered
                )

            except Exception as e:
                logger.exception(f"Error updating strategy {strategy_id}")
                strategy_results[strategy_id] = StrategyUpdateResult(
                    strategy_id=strategy_id,
                    success=False,
                    error_message=str(e),
                )
                failed += 1

        total_duration_ms = (datetime.now(UTC) - timestamp).total_seconds() * 1000

        return DailyUpdateResult(
            success=failed == 0,
            timestamp=timestamp,
            strategy_results=strategy_results,
            total_strategies=len(strategy_ids),
            successful_strategies=successful,
            failed_strategies=failed,
            alerts_triggered=total_alerts,
            total_duration_ms=total_duration_ms,
        )

    async def _update_strategy(self, strategy_id: str) -> StrategyUpdateResult:
        """Update ECE for a single strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            StrategyUpdateResult with per-signal-type results
        """
        start_time = datetime.now(UTC)
        per_signal_type: dict[SignalType, SignalTypeECE] = {}

        # Calculate overall ECE (all signal types combined)
        overall_request = ECECalculationRequest(
            strategy_id=strategy_id,
            days=self.config.lookback_days,
            min_samples=self.config.min_samples,
        )

        overall_response = await self._calculator.calculate(overall_request)
        overall_ece = (
            overall_response.ece_result.ece if overall_response.ece_result else None
        )
        overall_samples = overall_response.sample_count

        # Store overall ECE
        if overall_response.ece_result and self.history_tracker:
            await self._store_ece_result(overall_response.ece_result)

        # Calculate per-signal-type ECE
        for signal_type in SignalType:
            signal_request = ECECalculationRequest(
                strategy_id=strategy_id,
                signal_type=signal_type,
                days=self.config.lookback_days,
                min_samples=self.config.min_samples,
            )

            signal_response = await self._calculator.calculate(signal_request)

            if signal_response.success and signal_response.ece_result:
                ece = signal_response.ece_result.ece

                # Check if alert should be triggered
                alert_triggered = ece > self.config.ece_alert_threshold

                if alert_triggered and self.config.enable_alerts:
                    await self.alert_handler.handle_degradation_alert(
                        strategy_id=strategy_id,
                        signal_type=signal_type,
                        ece=ece,
                        threshold=self.config.ece_alert_threshold,
                    )

                per_signal_type[signal_type] = SignalTypeECE(
                    signal_type=signal_type,
                    ece=ece,
                    sample_count=signal_response.sample_count,
                    alert_triggered=alert_triggered,
                )

                # Store per-signal-type ECE
                if self.history_tracker:
                    await self._store_ece_result(signal_response.ece_result)
            else:
                per_signal_type[signal_type] = SignalTypeECE(
                    signal_type=signal_type,
                    ece=0.0,
                    sample_count=signal_response.sample_count,
                    alert_triggered=False,
                )

        update_duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return StrategyUpdateResult(
            strategy_id=strategy_id,
            overall_ece=overall_ece,
            overall_samples=overall_samples,
            per_signal_type=per_signal_type,
            success=overall_response.success,
            error_message=overall_response.error_message,
            update_duration_ms=update_duration_ms,
        )

    async def _store_ece_result(self, result: ECEResult) -> bool:
        """Store ECE result to history tracker.

        Args:
            result: ECEResult to store

        Returns:
            True if successfully stored
        """
        if not self.history_tracker:
            return False

        try:
            # Use record_ece method if available
            if hasattr(self.history_tracker, "record_ece"):
                await self.history_tracker.record_ece(result)
                return True
            else:
                logger.warning("History tracker does not have record_ece method")
                return False
        except Exception as e:
            logger.error(f"Failed to store ECE result: {e}")
            return False

    async def get_next_update_time(self) -> datetime:
        """Get the next scheduled update time.

        Returns:
            Next scheduled update time in UTC
        """
        return self.config.get_next_update_time()

    def get_status(self) -> dict[str, Any]:
        """Get current service status.

        Returns:
            Dictionary with service status
        """
        return {
            "running": self._running,
            "next_update": self.config.get_next_update_time().isoformat(),
            "config": {
                "update_time_utc": self.config.update_time_utc,
                "lookback_days": self.config.lookback_days,
                "ece_alert_threshold": self.config.ece_alert_threshold,
                "enable_alerts": self.config.enable_alerts,
            },
        }


async def create_default_service(
    store: OutcomeDataStore,
    history_tracker: Any,
    update_time_utc: str = "00:00",
    alert_handler: AlertHandler | None = None,
) -> ECEUpdateService:
    """Create an ECE update service with default configuration.

    Convenience factory function for creating a service with
    sensible defaults.

    Args:
        store: Outcome data store
        history_tracker: ECE history tracker
        update_time_utc: Time of day for updates (HH:MM)
        alert_handler: Optional custom alert handler

    Returns:
        Configured ECEUpdateService instance
    """
    config = UpdateConfig(update_time_utc=update_time_utc)
    return ECEUpdateService(config, store, history_tracker, alert_handler)


# Convenience exports
__all__ = [
    "ECEUpdateService",
    "UpdateConfig",
    "DailyUpdateResult",
    "StrategyUpdateResult",
    "SignalTypeECE",
    "AlertHandler",
    "LoggingAlertHandler",
    "ECE_DEGRADATION_THRESHOLD",
    "ECE_CRITICAL_THRESHOLD",
    "MAX_UPDATE_DURATION_SECONDS",
    "create_default_service",
]
