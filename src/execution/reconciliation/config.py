"""Configuration for reconciliation service."""

from dataclasses import dataclass, field
from datetime import timedelta


@dataclass
class ReconciliationTimingConfig:
    """Timing configuration for reconciliation runs.

    Provides predefined intervals (hourly/daily) and a configurable default
    for controlling the lookback window of reconciliation runs.
    """

    # Predefined intervals (in seconds)
    INTERVAL_HOURLY: int = 3600  # 1 hour
    INTERVAL_DAILY: int = 86400  # 24 hours

    # Default interval
    default_interval_seconds: int = INTERVAL_DAILY

    @property
    def default_time_range(self) -> timedelta:
        """Get default time range as timedelta."""
        return timedelta(seconds=self.default_interval_seconds)

    def get_time_range(self, interval_seconds: int | None = None) -> timedelta:
        """Get time range for specified interval.

        Args:
            interval_seconds: Interval in seconds (uses default if None)

        Returns:
            timedelta for the interval
        """
        seconds = interval_seconds or self.default_interval_seconds
        return timedelta(seconds=seconds)


@dataclass
class ReconciliationConfig:
    """Configuration for reconciliation thresholds and timing.

    Attributes:
        warn_threshold_pct: Percentage delta that triggers WARN status
        fail_threshold_pct: Percentage delta that triggers FAIL status
        categories: List of categories to reconcile
        timing: Timing configuration (auto-created with defaults if not provided)
    """

    warn_threshold_pct: float = 1.0
    fail_threshold_pct: float = 5.0
    categories: list[str] | None = None
    timing: ReconciliationTimingConfig = field(
        default_factory=ReconciliationTimingConfig
    )

    def __post_init__(self):
        if self.categories is None:
            self.categories = ["signals", "orders", "fills", "outcomes"]
