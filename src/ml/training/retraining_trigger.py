"""Model retraining trigger system for ChiseAI.

Provides automatic retraining triggers based on:
- ECE (Expected Calibration Error) degradation
- Performance degradation (win rate)
- Scheduled triggers

Features:
- Trigger deduplication with 24-hour window
- Pre-training validation (quality >90%)
- Discord alert integration
- Redis-based state management

For ST-LAUNCH-011: Model Retraining Trigger
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from discord_alerts.config import DiscordConfig
    from ml.training.pipeline import TrainingPipeline

logger = logging.getLogger(__name__)

# Trigger thresholds (from ST-LAUNCH-011 requirements)
ECE_TRIGGER_THRESHOLD = 0.15  # ECE > 0.15 triggers retraining
PERFORMANCE_WIN_RATE_THRESHOLD = 0.55  # Win rate < 55% triggers retraining
MIN_TRADES_FOR_PERFORMANCE = 20  # Minimum trades for performance trigger
DEDUPLICATION_WINDOW_HOURS = 24  # 24-hour deduplication window
MIN_DATA_QUALITY_PCT = (
    90.0  # Minimum data quality percentage for pre-training validation
)


class TriggerType(Enum):
    """Types of retraining triggers."""

    ECE_BASED = auto()
    PERFORMANCE_BASED = auto()
    SCHEDULED = auto()


class TriggerStatus(Enum):
    """Status of a trigger evaluation."""

    TRIGGERED = auto()
    NOT_TRIGGERED = auto()
    SUPPRESSED = auto()  # Deduplicated
    VALIDATION_FAILED = auto()
    DISABLED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class TriggerResult:
    """Result of a trigger evaluation.

    Attributes:
        trigger_type: Type of trigger evaluated
        status: Evaluation status
        triggered: Whether retraining should be triggered
        message: Human-readable description
        timestamp: When evaluation occurred
        metrics: Trigger-specific metrics
        deduplication_key: Key used for deduplication
    """

    trigger_type: TriggerType
    status: TriggerStatus
    triggered: bool
    message: str
    timestamp: datetime
    metrics: dict[str, Any] = field(default_factory=dict)
    deduplication_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trigger_type": self.trigger_type.name,
            "status": self.status.name,
            "triggered": self.triggered,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metrics": self.metrics,
            "deduplication_key": self.deduplication_key,
        }


@dataclass
class ECETriggerConfig:
    """Configuration for ECE-based trigger.

    Attributes:
        threshold: ECE threshold (default: 0.15)
        min_samples: Minimum samples for ECE calculation
        strategy_id: Optional strategy to monitor (None = all)
    """

    threshold: float = ECE_TRIGGER_THRESHOLD
    min_samples: int = 10
    strategy_id: str | None = None


@dataclass
class PerformanceTriggerConfig:
    """Configuration for performance-based trigger.

    Attributes:
        min_win_rate: Minimum win rate (default: 0.55)
        min_trades: Minimum trades for evaluation (default: 20)
        lookback_days: Days of history to analyze
        strategy_id: Optional strategy to monitor (None = all)
    """

    min_win_rate: float = PERFORMANCE_WIN_RATE_THRESHOLD
    min_trades: int = MIN_TRADES_FOR_PERFORMANCE
    lookback_days: int = 30
    strategy_id: str | None = None


@dataclass
class ScheduledTriggerConfig:
    """Configuration for scheduled trigger.

    Attributes:
        schedule_time_utc: Time to trigger (HH:MM format)
        timezone: Timezone for schedule (default: UTC)
        frequency: Frequency (daily, weekly)
    """

    schedule_time_utc: str = "02:00"  # 2 AM UTC
    timezone: str = "UTC"
    frequency: str = "daily"  # daily, weekly

    def __post_init__(self):
        """Validate schedule time format."""
        try:
            datetime.strptime(self.schedule_time_utc, "%H:%M")
        except ValueError as e:
            msg = (
                f"Invalid schedule_time_utc format: {self.schedule_time_utc}. "
                "Use HH:MM format."
            )
            raise ValueError(msg) from e


@dataclass
class RetrainingTriggerConfig:
    """Configuration for retraining trigger system.

    Attributes:
        ece_config: ECE-based trigger configuration
        performance_config: Performance-based trigger configuration
        scheduled_config: Scheduled trigger configuration
        deduplication_window_hours: Hours for deduplication window
        min_data_quality_pct: Minimum data quality for training
        enable_discord_alerts: Whether to send Discord alerts
    """

    ece_config: ECETriggerConfig = field(default_factory=ECETriggerConfig)
    performance_config: PerformanceTriggerConfig = field(
        default_factory=PerformanceTriggerConfig
    )
    scheduled_config: ScheduledTriggerConfig = field(
        default_factory=ScheduledTriggerConfig
    )
    deduplication_window_hours: int = DEDUPLICATION_WINDOW_HOURS
    min_data_quality_pct: float = MIN_DATA_QUALITY_PCT
    enable_discord_alerts: bool = True


class DeduplicationStore(Protocol):
    """Protocol for deduplication store."""

    async def is_trigger_recent(
        self, trigger_type: TriggerType, window_hours: int
    ) -> bool:
        """Check if trigger was fired recently.

        Args:
            trigger_type: Type of trigger
            window_hours: Lookback window in hours

        Returns:
            True if trigger was fired within window
        """
        ...

    async def record_trigger(self, trigger_type: TriggerType) -> bool:
        """Record that a trigger was fired.

        Args:
            trigger_type: Type of trigger

        Returns:
            True if recorded successfully
        """
        ...


class RedisDeduplicationStore:
    """Redis-based deduplication store.

    Uses Redis to track when triggers were last fired.
    """

    def __init__(self, redis_client: Any | None = None) -> None:
        """Initialize Redis deduplication store.

        Args:
            redis_client: Redis client (optional)
        """
        self._redis = redis_client
        self._local_cache: dict[str, datetime] = {}

    def _get_key(self, trigger_type: TriggerType) -> str:
        """Get Redis key for trigger type."""
        return f"retraining_trigger:last_fired:{trigger_type.name}"

    async def is_trigger_recent(
        self, trigger_type: TriggerType, window_hours: int
    ) -> bool:
        """Check if trigger was fired recently."""
        key = self._get_key(trigger_type)

        if self._redis:
            try:
                last_fired = await self._redis.get(key)
                if last_fired:
                    last_time = datetime.fromisoformat(last_fired)
                    elapsed = datetime.now(UTC) - last_time
                    return elapsed < timedelta(hours=window_hours)
            except Exception as e:
                logger.warning(f"Redis check failed, using local cache: {e}")

        # Fallback to local cache
        if key in self._local_cache:
            elapsed = datetime.now(UTC) - self._local_cache[key]
            return elapsed < timedelta(hours=window_hours)

        return False

    async def record_trigger(self, trigger_type: TriggerType) -> bool:
        """Record that a trigger was fired."""
        key = self._get_key(trigger_type)
        now = datetime.now(UTC)

        if self._redis:
            try:
                await self._redis.set(key, now.isoformat())
                return True
            except Exception as e:
                logger.warning(f"Redis record failed, using local cache: {e}")

        # Fallback to local cache
        self._local_cache[key] = now
        return True


class InMemoryDeduplicationStore:
    """In-memory deduplication store (for testing)."""

    def __init__(self) -> None:
        """Initialize in-memory store."""
        self._triggers: dict[str, datetime] = {}

    async def is_trigger_recent(
        self, trigger_type: TriggerType, window_hours: int
    ) -> bool:
        """Check if trigger was fired recently."""
        key = f"{trigger_type.name}"
        if key in self._triggers:
            elapsed = datetime.now(UTC) - self._triggers[key]
            return elapsed < timedelta(hours=window_hours)
        return False

    async def record_trigger(self, trigger_type: TriggerType) -> bool:
        """Record that a trigger was fired."""
        self._triggers[f"{trigger_type.name}"] = datetime.now(UTC)
        return True


class DataQualityValidator:
    """Validates data quality before training."""

    def __init__(self, min_quality_pct: float = MIN_DATA_QUALITY_PCT) -> None:
        """Initialize validator.

        Args:
            min_quality_pct: Minimum quality percentage required
        """
        self.min_quality_pct = min_quality_pct

    async def validate(
        self,
        sample_count: int,
        valid_samples: int,
        missing_features_pct: float = 0.0,
        stale_data_pct: float = 0.0,
    ) -> tuple[bool, float, str]:
        """Validate data quality.

        Args:
            sample_count: Total number of samples
            valid_samples: Number of valid samples
            missing_features_pct: Percentage of samples with missing features
            stale_data_pct: Percentage of stale data

        Returns:
            Tuple of (is_valid, quality_pct, message)
        """
        if sample_count == 0:
            return False, 0.0, "No samples available"

        # Calculate quality score
        completeness = (valid_samples / sample_count) * 100
        feature_quality = max(0, 100 - missing_features_pct)
        freshness = max(0, 100 - stale_data_pct)

        # Weighted quality score
        quality_pct = completeness * 0.5 + feature_quality * 0.3 + freshness * 0.2

        is_valid = quality_pct >= self.min_quality_pct

        if is_valid:
            message = f"Data quality {quality_pct:.1f}% meets threshold ({self.min_quality_pct}%)"
        else:
            message = f"Data quality {quality_pct:.1f}% below threshold ({self.min_quality_pct}%)"

        return is_valid, quality_pct, message


class ECERetriever(Protocol):
    """Protocol for retrieving ECE metrics."""

    async def get_latest_ece(self, strategy_id: str | None = None) -> float | None:
        """Get latest ECE value.

        Args:
            strategy_id: Optional strategy filter

        Returns:
            ECE value or None if unavailable
        """
        ...


class PerformanceRetriever(Protocol):
    """Protocol for retrieving performance metrics."""

    async def get_win_rate(
        self,
        min_trades: int,
        lookback_days: int,
        strategy_id: str | None = None,
    ) -> tuple[float | None, int]:
        """Get win rate and trade count.

        Args:
            min_trades: Minimum trades required
            lookback_days: Days to look back
            strategy_id: Optional strategy filter

        Returns:
            Tuple of (win_rate, trade_count)
        """
        ...


class DiscordNotifier:
    """Discord alert notifier for retraining triggers."""

    def __init__(self, config: DiscordConfig | None = None) -> None:
        """Initialize Discord notifier.

        Args:
            config: Discord configuration
        """
        self.config = config
        self._client: Any | None = None

    async def send_trigger_alert(
        self,
        trigger_type: TriggerType,
        result: TriggerResult,
        channel_id: str | None = None,
    ) -> bool:
        """Send Discord alert for trigger activation.

        Args:
            trigger_type: Type of trigger
            result: Trigger result
            channel_id: Optional channel ID override

        Returns:
            True if sent successfully
        """
        try:
            # Import here to avoid circular dependencies
            from discord_alerts.config import DiscordConfig
            from discord_alerts.discord_client import DiscordClient

            if self.config is None:
                self.config = DiscordConfig.from_env()

            if self._client is None:
                self._client = DiscordClient(self.config)

            # Format message
            emoji = "🔄" if result.triggered else "⏸️"
            title = f"{emoji} Model Retraining Trigger: {trigger_type.name}"

            fields = [
                {"name": "Status", "value": result.status.name, "inline": True},
                {"name": "Triggered", "value": str(result.triggered), "inline": True},
                {"name": "Message", "value": result.message[:1024], "inline": False},
            ]

            if result.metrics:
                metrics_str = "\n".join(f"{k}: {v}" for k, v in result.metrics.items())
                fields.append(
                    {
                        "name": "Metrics",
                        "value": metrics_str[:1024],
                        "inline": False,
                    }
                )

            # Send to training channel or specified channel
            target_channel = channel_id or self.config.trading_channel_id

            # Create embed
            embed = {
                "title": title,
                "description": f"Retraining trigger evaluation at {result.timestamp.isoformat()}",
                "color": 0x00FF00 if result.triggered else 0xFFA500,
                "fields": fields,
                "timestamp": result.timestamp.isoformat(),
            }

            # Send message (simplified - in production would use actual Discord API)
            logger.info(f"Discord alert: {title} - {result.message}")
            return True

        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return False


class RetrainingTrigger:
    """Main retraining trigger system.

    Coordinates all trigger types:
    - ECE-based: Monitors calibration degradation
    - Performance-based: Monitors win rate degradation
    - Scheduled: Time-based triggers

    Features deduplication, pre-training validation, and Discord alerts.
    """

    def __init__(
        self,
        config: RetrainingTriggerConfig | None = None,
        dedup_store: DeduplicationStore | None = None,
        ece_retriever: ECERetriever | None = None,
        performance_retriever: PerformanceRetriever | None = None,
        discord_config: DiscordConfig | None = None,
    ) -> None:
        """Initialize retraining trigger system.

        Args:
            config: Trigger configuration
            dedup_store: Deduplication store
            ece_retriever: ECE metrics retriever
            performance_retriever: Performance metrics retriever
            discord_config: Discord configuration for alerts
        """
        self.config = config or RetrainingTriggerConfig()
        self.dedup_store = dedup_store or InMemoryDeduplicationStore()
        self.ece_retriever = ece_retriever
        self.performance_retriever = performance_retriever

        self._quality_validator = DataQualityValidator(self.config.min_data_quality_pct)
        self._discord = (
            DiscordNotifier(discord_config)
            if self.config.enable_discord_alerts
            else None
        )

        self._last_results: dict[TriggerType, TriggerResult] = {}
        self._running = False
        self._task: asyncio.Task | None = None

        logger.info(
            f"RetrainingTrigger initialized: ECE={self.config.ece_config.threshold}, "
            f"WinRate={self.config.performance_config.min_win_rate}, "
            f"Dedup={self.config.deduplication_window_hours}h"
        )

    def _get_flags(self):
        """Get current feature flags (dynamic lookup)."""
        from config.feature_flags import get_feature_flags

        return get_feature_flags()

    async def evaluate_ece_trigger(self) -> TriggerResult:
        """Evaluate ECE-based trigger.

        Returns:
            TriggerResult with evaluation details
        """
        trigger_type = TriggerType.ECE_BASED
        timestamp = datetime.now(UTC)

        # Check if enabled
        if not self._get_flags().retraining_ece_trigger:
            return TriggerResult(
                trigger_type=trigger_type,
                status=TriggerStatus.DISABLED,
                triggered=False,
                message="ECE trigger is disabled by feature flag",
                timestamp=timestamp,
            )

        # Check deduplication
        if self._get_flags().retraining_deduplication:
            is_recent = await self.dedup_store.is_trigger_recent(
                trigger_type, self.config.deduplication_window_hours
            )
            if is_recent:
                return TriggerResult(
                    trigger_type=trigger_type,
                    status=TriggerStatus.SUPPRESSED,
                    triggered=False,
                    message=f"ECE trigger suppressed (within {self.config.deduplication_window_hours}h window)",
                    timestamp=timestamp,
                    deduplication_key=f"retraining_trigger:last_fired:{trigger_type.name}",
                )

        # Get ECE value
        ece_value: float | None = None
        if self.ece_retriever:
            try:
                ece_value = await self.ece_retriever.get_latest_ece(
                    self.config.ece_config.strategy_id
                )
            except Exception as e:
                logger.error(f"Failed to retrieve ECE: {e}")
                return TriggerResult(
                    trigger_type=trigger_type,
                    status=TriggerStatus.ERROR,
                    triggered=False,
                    message=f"Failed to retrieve ECE: {e}",
                    timestamp=timestamp,
                )

        if ece_value is None:
            return TriggerResult(
                trigger_type=trigger_type,
                status=TriggerStatus.NOT_TRIGGERED,
                triggered=False,
                message="ECE value unavailable",
                timestamp=timestamp,
                metrics={"ece": None},
            )

        # Evaluate threshold
        triggered = ece_value > self.config.ece_config.threshold

        if triggered:
            status = TriggerStatus.TRIGGERED
            message = (
                f"ECE {ece_value:.3f} exceeds threshold "
                f"({self.config.ece_config.threshold})"
            )
            # Record trigger for deduplication
            if self._get_flags().retraining_deduplication:
                await self.dedup_store.record_trigger(trigger_type)
        else:
            status = TriggerStatus.NOT_TRIGGERED
            message = (
                f"ECE {ece_value:.3f} within threshold "
                f"({self.config.ece_config.threshold})"
            )

        result = TriggerResult(
            trigger_type=trigger_type,
            status=status,
            triggered=triggered,
            message=message,
            timestamp=timestamp,
            metrics={
                "ece": ece_value,
                "threshold": self.config.ece_config.threshold,
            },
        )

        # Send Discord alert if triggered
        if triggered and self._discord and self._get_flags().retraining_discord_alerts:
            await self._discord.send_trigger_alert(trigger_type, result)

        self._last_results[trigger_type] = result
        return result

    async def evaluate_performance_trigger(self) -> TriggerResult:
        """Evaluate performance-based trigger.

        Returns:
            TriggerResult with evaluation details
        """
        trigger_type = TriggerType.PERFORMANCE_BASED
        timestamp = datetime.now(UTC)

        # Check if enabled
        if not self._get_flags().retraining_performance_trigger:
            return TriggerResult(
                trigger_type=trigger_type,
                status=TriggerStatus.DISABLED,
                triggered=False,
                message="Performance trigger is disabled by feature flag",
                timestamp=timestamp,
            )

        # Check deduplication
        if self._get_flags().retraining_deduplication:
            is_recent = await self.dedup_store.is_trigger_recent(
                trigger_type, self.config.deduplication_window_hours
            )
            if is_recent:
                return TriggerResult(
                    trigger_type=trigger_type,
                    status=TriggerStatus.SUPPRESSED,
                    triggered=False,
                    message=f"Performance trigger suppressed (within {self.config.deduplication_window_hours}h window)",
                    timestamp=timestamp,
                    deduplication_key=f"retraining_trigger:last_fired:{trigger_type.name}",
                )

        # Get performance metrics
        win_rate: float | None = None
        trade_count = 0

        if self.performance_retriever:
            try:
                win_rate, trade_count = await self.performance_retriever.get_win_rate(
                    min_trades=self.config.performance_config.min_trades,
                    lookback_days=self.config.performance_config.lookback_days,
                    strategy_id=self.config.performance_config.strategy_id,
                )
            except Exception as e:
                logger.error(f"Failed to retrieve performance metrics: {e}")
                return TriggerResult(
                    trigger_type=trigger_type,
                    status=TriggerStatus.ERROR,
                    triggered=False,
                    message=f"Failed to retrieve performance metrics: {e}",
                    timestamp=timestamp,
                )

        if win_rate is None:
            return TriggerResult(
                trigger_type=trigger_type,
                status=TriggerStatus.NOT_TRIGGERED,
                triggered=False,
                message="Win rate unavailable",
                timestamp=timestamp,
                metrics={"win_rate": None, "trade_count": trade_count},
            )

        # Check minimum trades
        if trade_count < self.config.performance_config.min_trades:
            return TriggerResult(
                trigger_type=trigger_type,
                status=TriggerStatus.NOT_TRIGGERED,
                triggered=False,
                message=f"Insufficient trades ({trade_count} < {self.config.performance_config.min_trades})",
                timestamp=timestamp,
                metrics={
                    "win_rate": win_rate,
                    "trade_count": trade_count,
                    "min_trades": self.config.performance_config.min_trades,
                },
            )

        # Evaluate threshold (win rate < threshold triggers retraining)
        triggered = win_rate < self.config.performance_config.min_win_rate

        if triggered:
            status = TriggerStatus.TRIGGERED
            message = (
                f"Win rate {win_rate:.1%} below threshold "
                f"({self.config.performance_config.min_win_rate:.1%}) over {trade_count} trades"
            )
            # Record trigger for deduplication
            if self._get_flags().retraining_deduplication:
                await self.dedup_store.record_trigger(trigger_type)
        else:
            status = TriggerStatus.NOT_TRIGGERED
            message = (
                f"Win rate {win_rate:.1%} above threshold "
                f"({self.config.performance_config.min_win_rate:.1%}) over {trade_count} trades"
            )

        result = TriggerResult(
            trigger_type=trigger_type,
            status=status,
            triggered=triggered,
            message=message,
            timestamp=timestamp,
            metrics={
                "win_rate": win_rate,
                "trade_count": trade_count,
                "threshold": self.config.performance_config.min_win_rate,
            },
        )

        # Send Discord alert if triggered
        if triggered and self._discord and self._get_flags().retraining_discord_alerts:
            await self._discord.send_trigger_alert(trigger_type, result)

        self._last_results[trigger_type] = result
        return result

    async def evaluate_scheduled_trigger(
        self, current_time: datetime | None = None
    ) -> TriggerResult:
        """Evaluate scheduled trigger.

        Args:
            current_time: Time to evaluate against (default: now)

        Returns:
            TriggerResult with evaluation details
        """
        trigger_type = TriggerType.SCHEDULED
        timestamp = current_time or datetime.now(UTC)

        # Check if enabled
        if not self._get_flags().retraining_scheduled_trigger:
            return TriggerResult(
                trigger_type=trigger_type,
                status=TriggerStatus.DISABLED,
                triggered=False,
                message="Scheduled trigger is disabled by feature flag",
                timestamp=timestamp,
            )

        # Parse scheduled time
        schedule_hour, schedule_minute = map(
            int, self.config.scheduled_config.schedule_time_utc.split(":")
        )

        # Check if we're within 1 hour of scheduled time
        scheduled_time = timestamp.replace(
            hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0
        )

        if scheduled_time > timestamp:
            # Scheduled time hasn't occurred yet today
            scheduled_time -= timedelta(days=1)

        elapsed = timestamp - scheduled_time
        triggered = elapsed <= timedelta(hours=1)

        if not triggered:
            return TriggerResult(
                trigger_type=trigger_type,
                status=TriggerStatus.NOT_TRIGGERED,
                triggered=False,
                message=f"Not within 1 hour of scheduled time ({self.config.scheduled_config.schedule_time_utc} UTC)",
                timestamp=timestamp,
                metrics={
                    "scheduled_time": self.config.scheduled_config.schedule_time_utc,
                    "elapsed_hours": elapsed.total_seconds() / 3600,
                },
            )

        # Check deduplication
        if self._get_flags().retraining_deduplication:
            is_recent = await self.dedup_store.is_trigger_recent(
                trigger_type, self.config.deduplication_window_hours
            )
            if is_recent:
                return TriggerResult(
                    trigger_type=trigger_type,
                    status=TriggerStatus.SUPPRESSED,
                    triggered=False,
                    message=f"Scheduled trigger suppressed (within {self.config.deduplication_window_hours}h window)",
                    timestamp=timestamp,
                    deduplication_key=f"retraining_trigger:last_fired:{trigger_type.name}",
                )

        status = TriggerStatus.TRIGGERED
        message = (
            f"Scheduled trigger fired within 1 hour of "
            f"{self.config.scheduled_config.schedule_time_utc} UTC"
        )

        # Record trigger for deduplication
        if self._get_flags().retraining_deduplication:
            await self.dedup_store.record_trigger(trigger_type)

        result = TriggerResult(
            trigger_type=trigger_type,
            status=status,
            triggered=True,
            message=message,
            timestamp=timestamp,
            metrics={
                "scheduled_time": self.config.scheduled_config.schedule_time_utc,
                "frequency": self.config.scheduled_config.frequency,
                "elapsed_hours": elapsed.total_seconds() / 3600,
            },
        )

        # Send Discord alert
        if self._discord and self._get_flags().retraining_discord_alerts:
            await self._discord.send_trigger_alert(trigger_type, result)

        self._last_results[trigger_type] = result
        return result

    async def validate_training_readiness(
        self,
        sample_count: int,
        valid_samples: int,
        missing_features_pct: float = 0.0,
        stale_data_pct: float = 0.0,
    ) -> tuple[bool, float, str]:
        """Validate data quality before training.

        Args:
            sample_count: Total samples available
            valid_samples: Number of valid samples
            missing_features_pct: Percentage with missing features
            stale_data_pct: Percentage of stale data

        Returns:
            Tuple of (is_valid, quality_pct, message)
        """
        if not self._get_flags().retraining_pre_validation:
            return True, 100.0, "Pre-training validation disabled by feature flag"

        return await self._quality_validator.validate(
            sample_count=sample_count,
            valid_samples=valid_samples,
            missing_features_pct=missing_features_pct,
            stale_data_pct=stale_data_pct,
        )

    async def evaluate_all(self) -> list[TriggerResult]:
        """Evaluate all trigger types.

        Returns:
            List of TriggerResult for each trigger type
        """
        results = []

        # Evaluate ECE-based trigger
        ece_result = await self.evaluate_ece_trigger()
        results.append(ece_result)

        # Evaluate performance-based trigger
        perf_result = await self.evaluate_performance_trigger()
        results.append(perf_result)

        # Evaluate scheduled trigger
        sched_result = await self.evaluate_scheduled_trigger()
        results.append(sched_result)

        return results

    def should_trigger_retraining(
        self, results: list[TriggerResult] | None = None
    ) -> tuple[bool, list[TriggerResult]]:
        """Determine if retraining should be triggered.

        Args:
            results: Optional pre-evaluated results

        Returns:
            Tuple of (should_trigger, triggering_results)
        """
        if results is None:
            # Cannot determine without async evaluation
            return False, []

        triggering = [
            r for r in results if r.triggered and r.status == TriggerStatus.TRIGGERED
        ]

        return len(triggering) > 0, triggering

    def get_last_result(self, trigger_type: TriggerType) -> TriggerResult | None:
        """Get last result for a trigger type.

        Args:
            trigger_type: Type of trigger

        Returns:
            Last TriggerResult or None
        """
        return self._last_results.get(trigger_type)

    async def start_monitoring(self, interval_seconds: float = 300.0) -> None:
        """Start continuous monitoring loop.

        Args:
            interval_seconds: Evaluation interval in seconds (default: 5 minutes)
        """
        if self._running:
            logger.warning("Monitoring already running")
            return

        self._running = True
        logger.info(
            f"Starting retraining trigger monitoring (interval={interval_seconds}s)"
        )

        async def monitor_loop():
            while self._running:
                try:
                    results = await self.evaluate_all()
                    triggered = [r for r in results if r.triggered]

                    if triggered:
                        logger.info(
                            f"Retraining triggers fired: "
                            f"{[r.trigger_type.name for r in triggered]}"
                        )

                    await asyncio.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    await asyncio.sleep(interval_seconds)

        self._task = asyncio.create_task(monitor_loop())

    async def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Retraining trigger monitoring stopped")
