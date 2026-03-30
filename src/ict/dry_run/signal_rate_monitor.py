"""ICT signal rate monitoring for dry-run validation.

Observes ICT signal generation rates over 24 hours without trading
to validate signals are within expected production bounds.

Part of EP-ICT-006 Phase B0 remediation.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


@dataclass
class SignalRateSnapshot:
    """Snapshot of signal rates at a point in time."""

    timestamp: datetime
    hour_count: int  # Signals in last hour
    day_count: int  # Signals in last 24 hours
    symbol_counts: dict[str, int]  # Per-symbol counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "hour_count": self.hour_count,
            "day_count": self.day_count,
            "symbol_counts": self.symbol_counts,
        }


@dataclass
class SignalRateBounds:
    """Expected bounds for signal rates."""

    # Per-hour bounds
    min_signals_per_hour: int = 0
    max_signals_per_hour: int = 50

    # Per-day bounds
    min_signals_per_day: int = 10
    max_signals_per_day: int = 500

    # Per-symbol daily bounds
    max_signals_per_symbol_per_day: int = 100

    def check_hourly_rate(self, count: int) -> tuple[bool, str]:
        """Check if hourly rate is within bounds.

        Returns:
            Tuple of (is_valid, message)
        """
        if count < self.min_signals_per_hour:
            return (
                False,
                f"Hourly rate {count} below minimum {self.min_signals_per_hour}",
            )
        if count > self.max_signals_per_hour:
            return (
                False,
                f"Hourly rate {count} exceeds maximum {self.max_signals_per_hour}",
            )
        return True, f"Hourly rate {count} within bounds"

    def check_daily_rate(self, count: int) -> tuple[bool, str]:
        """Check if daily rate is within bounds."""
        if count < self.min_signals_per_day:
            return False, f"Daily rate {count} below minimum {self.min_signals_per_day}"
        if count > self.max_signals_per_day:
            return (
                False,
                f"Daily rate {count} exceeds maximum {self.max_signals_per_day}",
            )
        return True, f"Daily rate {count} within bounds"


class SignalRateMonitor:
    """Monitor ICT signal rates during dry-run period.

    Tracks signal counts over 24 hours and validates against expected bounds.
    No trades are executed - this is observation only.

    Example:
        >>> monitor = SignalRateMonitor(redis_client=redis)
        >>> await monitor.start_24h_dry_run()
        >>> # Wait 24 hours or call periodically
        >>> report = await monitor.generate_report()
        >>> print(report.summary)
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        bounds: SignalRateBounds | None = None,
    ):
        """Initialize signal rate monitor.

        Args:
            redis_client: Redis client for storing signal counts
            bounds: Expected signal rate bounds (uses defaults if None)
        """
        self._redis = redis_client or self._create_default_redis()
        self._bounds = bounds or SignalRateBounds()
        self._dry_run_key_prefix = "ict:dry_run:signals:"
        self._start_time: datetime | None = None

    def _create_default_redis(self) -> Redis:
        """Create default Redis client."""
        import os

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        return Redis.from_url(redis_url, decode_responses=True)

    async def start_24h_dry_run(self) -> None:
        """Start a 24-hour dry-run monitoring period."""
        self._start_time = datetime.now(UTC)
        logger.info(f"Started 24h ICT signal dry-run at {self._start_time.isoformat()}")

        # Store start marker in Redis
        await self._redis.set(
            f"{self._dry_run_key_prefix}start_time",
            self._start_time.isoformat(),
            ex=86400 * 2,  # 48h TTL
        )

    async def record_signal(
        self,
        symbol: str,
        signal_type: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Record an observed ICT signal (no trading).

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            signal_type: Type of ICT signal (e.g., "BOS", "CHOCH", "FVG")
            timestamp: Signal timestamp (defaults to now)
        """
        ts = timestamp or datetime.now(UTC)

        # Store in Redis with hourly bucketing
        hour_key = ts.strftime("%Y%m%d%H")
        day_key = ts.strftime("%Y%m%d")

        pipe = self._redis.pipeline()

        # Increment counters
        pipe.hincrby(f"{self._dry_run_key_prefix}hour:{hour_key}", symbol, 1)
        pipe.hincrby(f"{self._dry_run_key_prefix}day:{day_key}", symbol, 1)
        pipe.hincrby(f"{self._dry_run_key_prefix}type:{hour_key}", signal_type, 1)

        # Set TTL (25 hours for hourly, 48 hours for daily)
        pipe.expire(f"{self._dry_run_key_prefix}hour:{hour_key}", 90000)
        pipe.expire(f"{self._dry_run_key_prefix}day:{day_key}", 172800)

        await pipe.execute()

        logger.debug(f"Recorded {signal_type} signal for {symbol} at {ts.isoformat()}")

    async def get_current_snapshot(self) -> SignalRateSnapshot:
        """Get current signal rate snapshot."""
        now = datetime.now(UTC)

        # Get last hour counts
        hour_key = now.strftime("%Y%m%d%H")
        hour_data = await self._redis.hgetall(
            f"{self._dry_run_key_prefix}hour:{hour_key}"
        )
        hour_count = sum(int(v) for v in hour_data.values())

        # Get last 24 hours counts
        day_key = now.strftime("%Y%m%d")
        day_data = await self._redis.hgetall(f"{self._dry_run_key_prefix}day:{day_key}")
        day_count = sum(int(v) for v in day_data.values())

        # Per-symbol counts
        symbol_counts = {k: int(v) for k, v in day_data.items()}

        return SignalRateSnapshot(
            timestamp=now,
            hour_count=hour_count,
            day_count=day_count,
            symbol_counts=symbol_counts,
        )

    async def check_bounds(self) -> dict[str, Any]:
        """Check current signal rates against bounds.

        Returns:
            Dict with check results
        """
        snapshot = await self.get_current_snapshot()

        hour_valid, hour_msg = self._bounds.check_hourly_rate(snapshot.hour_count)
        day_valid, day_msg = self._bounds.check_daily_rate(snapshot.day_count)

        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "hourly": {
                "count": snapshot.hour_count,
                "valid": hour_valid,
                "message": hour_msg,
            },
            "daily": {
                "count": snapshot.day_count,
                "valid": day_valid,
                "message": day_msg,
            },
            "overall_valid": hour_valid and day_valid,
        }

    async def generate_report(self) -> dict[str, Any]:
        """Generate 24h dry-run report.

        Returns:
            Report with signal statistics and bounds validation
        """
        snapshot = await self.get_current_snapshot()
        bounds_check = await self.check_bounds()

        start_time_str = await self._redis.get(f"{self._dry_run_key_prefix}start_time")

        report = {
            "dry_run_type": "ICT_Signal_Rate_24h",
            "start_time": start_time_str,
            "end_time": datetime.now(UTC).isoformat(),
            "snapshot": snapshot.to_dict(),
            "bounds_check": bounds_check,
            "expected_bounds": {
                "min_signals_per_hour": self._bounds.min_signals_per_hour,
                "max_signals_per_hour": self._bounds.max_signals_per_hour,
                "min_signals_per_day": self._bounds.min_signals_per_day,
                "max_signals_per_day": self._bounds.max_signals_per_day,
            },
            "status": "PASS" if bounds_check["overall_valid"] else "FAIL",
        }

        return report


async def run_24h_dry_run():
    """Run a complete 24-hour dry-run and print report.

    This is the main entry point for B0 validation.
    """
    monitor = SignalRateMonitor()
    await monitor.start_24h_dry_run()

    logger.info("B0 Dry-run started. Run for 24 hours, then call generate_report()")
    logger.info("In production, this would be integrated with the ICT signal generator")

    # Return monitor instance for further interaction
    return monitor
