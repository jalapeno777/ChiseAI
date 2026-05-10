"""Error rate monitoring and alert integration.

Tracks error rates by category (API, validation, execution) and integrates
with Discord alerts when thresholds are exceeded.

Redis keys:
- chise:paper:metrics:error_rate:<category>:total - Total operations
- chise:paper:metrics:error_rate:<category>:errors - Error count
- chise:paper:metrics:error_rate:<category>:rate - Current error rate
- chise:paper:metrics:error_rate:<category>:last_alert - Last alert timestamp

For ST-PARTY-E2E-REMEDIATION-001: Error Rate Monitor & Alert Integration
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Error categories for tracking."""

    API = "api"
    VALIDATION = "validation"
    EXECUTION = "execution"
    DATABASE = "database"
    NETWORK = "network"
    UNKNOWN = "unknown"


class AlertSeverity(Enum):
    """Alert severity levels."""

    WARNING = "warning"
    CRITICAL = "critical"
    INFO = "info"


@dataclass
class ErrorRateThresholds:
    """Configurable error rate thresholds.

    Attributes:
        warning: Error rate percentage that triggers warning (default 5%)
        critical: Error rate percentage that triggers critical alert (default 10%)
        min_operations: Minimum operations before calculating rate (default 10)
        alert_cooldown_minutes: Minutes between duplicate alerts (default 15)
    """

    warning: float = 5.0
    critical: float = 10.0
    min_operations: int = 10
    alert_cooldown_minutes: int = 15

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "warning": self.warning,
            "critical": self.critical,
            "min_operations": self.min_operations,
            "alert_cooldown_minutes": self.alert_cooldown_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorRateThresholds:
        """Create from dictionary."""
        return cls(
            warning=data.get("warning", 5.0),
            critical=data.get("critical", 10.0),
            min_operations=data.get("min_operations", 10),
            alert_cooldown_minutes=data.get("alert_cooldown_minutes", 15),
        )


@dataclass
class ErrorRateSnapshot:
    """Snapshot of error rate for a category.

    Attributes:
        category: Error category
        total_operations: Total operations count
        error_count: Error count
        error_rate: Calculated error rate percentage
        timestamp: When snapshot was taken
        threshold_warning: Warning threshold used
        threshold_critical: Critical threshold used
    """

    category: ErrorCategory
    total_operations: int
    error_count: int
    error_rate: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    threshold_warning: float = 5.0
    threshold_critical: float = 10.0

    @property
    def is_warning(self) -> bool:
        """Check if error rate exceeds warning threshold."""
        return self.error_rate >= self.threshold_warning

    @property
    def is_critical(self) -> bool:
        """Check if error rate exceeds critical threshold."""
        return self.error_rate >= self.threshold_critical

    @property
    def severity(self) -> AlertSeverity:
        """Get alert severity based on error rate."""
        if self.is_critical:
            return AlertSeverity.CRITICAL
        elif self.is_warning:
            return AlertSeverity.WARNING
        return AlertSeverity.INFO

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "total_operations": self.total_operations,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "timestamp": self.timestamp.isoformat(),
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical,
            "is_warning": self.is_warning,
            "is_critical": self.is_critical,
            "severity": self.severity.value,
        }


class ErrorRateTracker:
    """Tracks error rates by category in Redis.

    Stores metrics in Redis with keys:
    - chise:paper:metrics:error_rate:<category>:total
    - chise:paper:metrics:error_rate:<category>:errors
    - chise:paper:metrics:error_rate:<category>:rate
    """

    REDIS_KEY_PREFIX = "chise:paper:metrics:error_rate"

    def __init__(
        self,
        redis_client: Any | None = None,
        thresholds: ErrorRateThresholds | None = None,
    ):
        """Initialize error rate tracker.

        Args:
            redis_client: Redis client instance (optional)
            thresholds: Error rate thresholds (uses defaults if not provided)
        """
        self._redis = redis_client
        self.thresholds = thresholds or ErrorRateThresholds()
        self._local_stats: dict[ErrorCategory, dict[str, int]] = {}

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                from src.execution.paper.redis_config import get_redis_client_sync

                self._redis = get_redis_client_sync(decode_responses=True)
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self._redis = None
        return self._redis

    def _get_key(self, category: ErrorCategory, suffix: str) -> str:
        """Get Redis key for category."""
        return f"{self.REDIS_KEY_PREFIX}:{category.value}:{suffix}"

    def record_operation(
        self,
        category: ErrorCategory,
        success: bool = True,
        error_details: dict[str, Any] | None = None,
    ) -> ErrorRateSnapshot:
        """Record an operation and its outcome.

        Args:
            category: Error category
            success: Whether the operation succeeded
            error_details: Optional error details for failed operations

        Returns:
            Updated error rate snapshot
        """
        redis_client = self._get_redis()

        if redis_client:
            try:
                # Increment total operations
                total = redis_client.hincrby(
                    self._get_key(category, "stats"), "total", 1
                )

                # Increment errors if failed
                errors = 0
                if not success:
                    errors = redis_client.hincrby(
                        self._get_key(category, "stats"), "errors", 1
                    )
                    # Store error details
                    if error_details:
                        error_json = json.dumps(
                            {
                                **error_details,
                                "timestamp": datetime.now(UTC).isoformat(),
                            }
                        )
                        redis_client.lpush(
                            self._get_key(category, "error_log"), error_json
                        )
                        # Trim error log to last 100 entries
                        redis_client.ltrim(self._get_key(category, "error_log"), 0, 99)
                else:
                    # Get current error count
                    errors_str = redis_client.hget(
                        self._get_key(category, "stats"), "errors"
                    )
                    errors = int(errors_str) if errors_str else 0

                # Calculate and store error rate
                error_rate = (errors / total * 100) if total > 0 else 0.0
                redis_client.hset(
                    self._get_key(category, "stats"),
                    "error_rate",
                    str(error_rate),
                )
                redis_client.hset(
                    self._get_key(category, "stats"),
                    "last_updated",
                    datetime.now(UTC).isoformat(),
                )

                return ErrorRateSnapshot(
                    category=category,
                    total_operations=total,
                    error_count=errors,
                    error_rate=error_rate,
                    threshold_warning=self.thresholds.warning,
                    threshold_critical=self.thresholds.critical,
                )

            except Exception as e:
                logger.error(f"Failed to record operation in Redis: {e}")

        # Fallback to local stats if Redis unavailable
        if category not in self._local_stats:
            self._local_stats[category] = {"total": 0, "errors": 0}

        self._local_stats[category]["total"] += 1
        if not success:
            self._local_stats[category]["errors"] += 1

        total = self._local_stats[category]["total"]
        errors = self._local_stats[category]["errors"]
        error_rate = (errors / total * 100) if total > 0 else 0.0

        return ErrorRateSnapshot(
            category=category,
            total_operations=total,
            error_count=errors,
            error_rate=error_rate,
            threshold_warning=self.thresholds.warning,
            threshold_critical=self.thresholds.critical,
        )

    def get_error_rate(self, category: ErrorCategory) -> ErrorRateSnapshot:
        """Get current error rate for a category.

        Args:
            category: Error category

        Returns:
            Current error rate snapshot
        """
        redis_client = self._get_redis()

        if redis_client:
            try:
                stats = redis_client.hgetall(self._get_key(category, "stats"))
                if stats:
                    total = int(stats.get("total", 0))
                    errors = int(stats.get("errors", 0))
                    error_rate = float(stats.get("error_rate", 0))

                    return ErrorRateSnapshot(
                        category=category,
                        total_operations=total,
                        error_count=errors,
                        error_rate=error_rate,
                        threshold_warning=self.thresholds.warning,
                        threshold_critical=self.thresholds.critical,
                    )
            except Exception as e:
                logger.error(f"Failed to get error rate from Redis: {e}")

        # Fallback to local stats
        if category in self._local_stats:
            stats = self._local_stats[category]
            total = stats["total"]
            errors = stats["errors"]
            error_rate = (errors / total * 100) if total > 0 else 0.0

            return ErrorRateSnapshot(
                category=category,
                total_operations=total,
                error_count=errors,
                error_rate=error_rate,
                threshold_warning=self.thresholds.warning,
                threshold_critical=self.thresholds.critical,
            )

        return ErrorRateSnapshot(
            category=category,
            total_operations=0,
            error_count=0,
            error_rate=0.0,
            threshold_warning=self.thresholds.warning,
            threshold_critical=self.thresholds.critical,
        )

    def get_all_error_rates(self) -> dict[ErrorCategory, ErrorRateSnapshot]:
        """Get error rates for all categories.

        Returns:
            Dictionary mapping categories to snapshots
        """
        return {category: self.get_error_rate(category) for category in ErrorCategory}

    def reset_category(self, category: ErrorCategory) -> bool:
        """Reset error stats for a category.

        Args:
            category: Error category to reset

        Returns:
            True if successful
        """
        redis_client = self._get_redis()

        if redis_client:
            try:
                redis_client.delete(self._get_key(category, "stats"))
                redis_client.delete(self._get_key(category, "error_log"))
                logger.info(f"Reset error stats for category: {category.value}")
                return True
            except Exception as e:
                logger.error(f"Failed to reset error stats: {e}")

        # Reset local stats
        if category in self._local_stats:
            del self._local_stats[category]

        return True

    def get_recent_errors(
        self, category: ErrorCategory, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent error details for a category.

        Args:
            category: Error category
            limit: Maximum number of errors to return

        Returns:
            List of error detail dictionaries
        """
        redis_client = self._get_redis()

        if redis_client:
            try:
                errors = redis_client.lrange(
                    self._get_key(category, "error_log"), 0, limit - 1
                )
                return [json.loads(e) for e in errors if e]
            except Exception as e:
                logger.error(f"Failed to get recent errors: {e}")

        return []


class ErrorRateAlertIntegration:
    """Integrates error rate monitoring with Discord alerts.

    Monitors error rates and sends Discord notifications when thresholds
    are exceeded.
    """

    def __init__(
        self,
        tracker: ErrorRateTracker | None = None,
        discord_webhook_url: str | None = None,
        enabled: bool = True,
    ):
        """Initialize error rate alert integration.

        Args:
            tracker: ErrorRateTracker instance (creates default if None)
            discord_webhook_url: Discord webhook URL for alerts
            enabled: Whether alerts are enabled
        """
        self.tracker = tracker or ErrorRateTracker()
        self.discord_webhook_url = discord_webhook_url
        self.enabled = enabled
        self._stats = {
            "alerts_sent": 0,
            "alerts_suppressed": 0,
            "errors": 0,
        }

    def _should_send_alert(
        self, category: ErrorCategory, severity: AlertSeverity
    ) -> bool:
        """Check if alert should be sent based on cooldown.

        Args:
            category: Error category
            severity: Alert severity

        Returns:
            True if alert should be sent
        """
        if not self.enabled:
            return False

        redis_client = self.tracker._get_redis()
        if not redis_client:
            return True  # Send if Redis unavailable

        try:
            cooldown_key = f"{self.tracker.REDIS_KEY_PREFIX}:{category.value}:last_alert:{severity.value}"
            last_alert = redis_client.get(cooldown_key)

            if last_alert:
                last_time = datetime.fromisoformat(last_alert)
                cooldown = timedelta(
                    minutes=self.tracker.thresholds.alert_cooldown_minutes
                )
                if datetime.now(UTC) - last_time < cooldown:
                    return False

            # Update last alert time
            redis_client.set(cooldown_key, datetime.now(UTC).isoformat())
            return True

        except Exception as e:
            logger.error(f"Failed to check alert cooldown: {e}")
            return True

    async def check_and_alert(
        self, category: ErrorCategory | None = None
    ) -> dict[str, Any]:
        """Check error rates and send alerts if thresholds exceeded.

        Args:
            category: Specific category to check (checks all if None)

        Returns:
            Alert results dictionary
        """
        results = {
            "checked": [],
            "alerts_sent": [],
            "alerts_suppressed": [],
            "errors": [],
        }

        categories = [category] if category else list(ErrorCategory)

        for cat in categories:
            if cat is None:
                continue

            snapshot = self.tracker.get_error_rate(cat)

            # Skip if not enough operations
            if snapshot.total_operations < self.tracker.thresholds.min_operations:
                results["checked"].append(
                    {
                        "category": cat.value,
                        "status": "skipped",
                        "reason": "insufficient_operations",
                        "total_operations": snapshot.total_operations,
                    }
                )
                continue

            results["checked"].append(
                {
                    "category": cat.value,
                    "status": "checked",
                    "error_rate": snapshot.error_rate,
                    "severity": snapshot.severity.value,
                }
            )

            # Safety gate: verify producer has written recently
            redis_client = self.tracker._get_redis()
            if redis_client:
                stats_key = f"{self.tracker.REDIS_KEY_PREFIX}:{cat.value}:stats"
                try:
                    last_updated_str = redis_client.hget(stats_key, "last_updated")
                    if last_updated_str:
                        last_updated = datetime.fromisoformat(last_updated_str)
                        age_seconds = (datetime.now(UTC) - last_updated).total_seconds()
                        if age_seconds > 3600:
                            logger.warning(
                                f"Suppressing alert for {cat.value}: producer data stale "
                                f"({age_seconds / 3600:.1f}h old)"
                            )
                            results["alerts_suppressed"].append(
                                {
                                    "category": cat.value,
                                    "reason": "stale_producer_data",
                                    "last_updated": last_updated_str,
                                }
                            )
                            self._stats["alerts_suppressed"] += 1
                            continue
                    else:
                        logger.warning(
                            f"Suppressing alert for {cat.value}: no producer data (last_updated field missing)"
                        )
                        results["alerts_suppressed"].append(
                            {
                                "category": cat.value,
                                "reason": "no_producer_data",
                            }
                        )
                        self._stats["alerts_suppressed"] += 1
                        continue
                except Exception as e:
                    logger.error(
                        f"Error checking producer freshness for {cat.value}: {e}"
                    )

            # Check if alert needed
            if snapshot.is_critical or snapshot.is_warning:
                severity = (
                    AlertSeverity.CRITICAL
                    if snapshot.is_critical
                    else AlertSeverity.WARNING
                )

                if self._should_send_alert(cat, severity):
                    alert_result = await self._send_discord_alert(snapshot)
                    if alert_result.get("sent"):
                        results["alerts_sent"].append(alert_result)
                        self._stats["alerts_sent"] += 1
                    else:
                        results["errors"].append(alert_result)
                        self._stats["errors"] += 1
                else:
                    results["alerts_suppressed"].append(
                        {
                            "category": cat.value,
                            "severity": severity.value,
                            "reason": "cooldown",
                        }
                    )
                    self._stats["alerts_suppressed"] += 1

        return results

    async def _send_discord_alert(self, snapshot: ErrorRateSnapshot) -> dict[str, Any]:
        """Send Discord alert for error rate.

        Args:
            snapshot: Error rate snapshot

        Returns:
            Alert result dictionary
        """
        try:
            import aiohttp

            webhook_url = self.discord_webhook_url
            if not webhook_url:
                # Try to get from environment
                import os

                webhook_url = os.getenv("DISCORD_ALERT_WEBHOOK_URL")

            if not webhook_url:
                return {
                    "sent": False,
                    "category": snapshot.category.value,
                    "error": "No Discord webhook URL configured",
                }

            # Build embed
            if snapshot.is_critical:
                color = 0xFF0000  # Red
                emoji = "🚨"
                title = f"{emoji} CRITICAL: High Error Rate Detected"
            else:
                color = 0xFFA500  # Orange
                emoji = "⚠️"
                title = f"{emoji} WARNING: Elevated Error Rate"

            embed = {
                "title": title,
                "description": (
                    f"Error rate for **{snapshot.category.value.upper()}** "
                    f"has exceeded the {snapshot.severity.value} threshold."
                ),
                "color": color,
                "fields": [
                    {
                        "name": "📊 Error Rate",
                        "value": f"{snapshot.error_rate:.2f}%",
                        "inline": True,
                    },
                    {
                        "name": "❌ Errors",
                        "value": str(snapshot.error_count),
                        "inline": True,
                    },
                    {
                        "name": "✅ Total Operations",
                        "value": str(snapshot.total_operations),
                        "inline": True,
                    },
                    {
                        "name": "⚠️ Warning Threshold",
                        "value": f"{snapshot.threshold_warning:.2f}%",
                        "inline": True,
                    },
                    {
                        "name": "🚨 Critical Threshold",
                        "value": f"{snapshot.threshold_critical:.2f}%",
                        "inline": True,
                    },
                ],
                "timestamp": datetime.now(UTC).isoformat(),
                "footer": {"text": "ChiseAI Error Rate Monitor"},
            }

            payload = {"embeds": [embed]}

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 204:
                        logger.warning(
                            f"Error rate alert sent: {snapshot.category.value} "
                            f"at {snapshot.error_rate:.2f}%"
                        )
                        return {
                            "sent": True,
                            "category": snapshot.category.value,
                            "severity": snapshot.severity.value,
                            "error_rate": snapshot.error_rate,
                        }
                    else:
                        text = await response.text()
                        return {
                            "sent": False,
                            "category": snapshot.category.value,
                            "error": f"HTTP {response.status}: {text}",
                        }

        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return {
                "sent": False,
                "category": snapshot.category.value,
                "error": str(e),
            }

    def get_stats(self) -> dict[str, Any]:
        """Get alert integration statistics."""
        return self._stats.copy()

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all error rate metrics."""
        snapshots = self.tracker.get_all_error_rates()
        return {
            "categories": {
                cat.value: snap.to_dict() for cat, snap in snapshots.items()
            },
            "alert_stats": self._stats,
            "thresholds": self.tracker.thresholds.to_dict(),
        }
