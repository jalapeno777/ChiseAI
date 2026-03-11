#!/usr/bin/env python3
"""Pipeline health alerting system.

Monitors pipeline_status transitions and sends alerts when:
- Pipeline becomes stale (>5 minutes without signals)
- Pipeline recovers from stale state
- Consumer backlog exceeds threshold
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PipelineAlertManager:
    """Manages pipeline health alerts."""

    # Redis keys
    HEARTBEAT_KEY = "bmad:chiseai:scheduler:heartbeat"
    ALERT_STATE_KEY = "bmad:chiseai:pipeline:alert_state"

    # Alert thresholds
    STALE_THRESHOLD_MINUTES = 5
    BACKLOG_THRESHOLD = 10

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or self._connect_redis()
        self.discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
        self.last_alert_time = None
        self.alert_cooldown_minutes = 15

    def _connect_redis(self) -> redis.Redis:
        """Connect to Redis."""
        return redis.Redis(
            host=os.getenv("REDIS_HOST", "host.docker.internal"),
            port=int(os.getenv("REDIS_PORT", "6380")),
            decode_responses=True,
        )

    def check_and_alert(self):
        """Check pipeline health and send alerts if needed."""
        try:
            heartbeat = self.redis.hgetall(self.HEARTBEAT_KEY)

            if not heartbeat:
                logger.warning("No heartbeat found")
                return

            pipeline_status = heartbeat.get("pipeline_status", "unknown")
            signals_15m = int(heartbeat.get("signals_15m", "0"))
            consumer_backlog = int(heartbeat.get("consumer_backlog", "0"))
            latest_signal_age = float(heartbeat.get("latest_signal_age_m", "0"))

            # Check for stale pipeline
            if (
                pipeline_status == "stale"
                and latest_signal_age > self.STALE_THRESHOLD_MINUTES
            ):
                if self._should_alert("stale_pipeline"):
                    self._send_alert(
                        severity=AlertSeverity.CRITICAL,
                        title="🚨 Pipeline Stale Alert",
                        message=f"No signals generated in {latest_signal_age:.1f} minutes. "
                        f"Last 15m signals: {signals_15m}",
                        fields={
                            "Status": pipeline_status,
                            "Signals (15m)": str(signals_15m),
                            "Latest Signal Age": f"{latest_signal_age:.1f}m",
                            "Consumer Backlog": str(consumer_backlog),
                        },
                    )
                    self._record_alert("stale_pipeline")

            # Check for recovery
            elif pipeline_status == "healthy":
                last_alert = self._get_last_alert_state()
                if last_alert == "stale_pipeline":
                    self._send_alert(
                        severity=AlertSeverity.INFO,
                        title="✅ Pipeline Recovered",
                        message=f"Pipeline is healthy again. "
                        f"Signals in last 15m: {signals_15m}",
                        fields={
                            "Status": pipeline_status,
                            "Signals (15m)": str(signals_15m),
                            "Consumer Backlog": str(consumer_backlog),
                        },
                    )
                    self._record_alert("healthy")

            # Check for high backlog
            if consumer_backlog > self.BACKLOG_THRESHOLD:
                if self._should_alert("high_backlog"):
                    self._send_alert(
                        severity=AlertSeverity.WARNING,
                        title="⚠️ High Consumer Backlog",
                        message=f"Consumer backlog is {consumer_backlog} signals",
                        fields={
                            "Backlog": str(consumer_backlog),
                            "Status": pipeline_status,
                        },
                    )
                    self._record_alert("high_backlog")

        except Exception as e:
            logger.exception(f"Error checking pipeline health: {e}")

    def _should_alert(self, alert_type: str) -> bool:
        """Check if we should send alert based on cooldown."""
        if self.last_alert_time is None:
            return True

        cooldown_expired = datetime.now(UTC) > (
            self.last_alert_time + timedelta(minutes=self.alert_cooldown_minutes)
        )

        return cooldown_expired

    def _record_alert(self, alert_type: str):
        """Record alert state in Redis."""
        self.last_alert_time = datetime.now(UTC)
        self.redis.hset(
            self.ALERT_STATE_KEY,
            mapping={
                "last_alert_type": alert_type,
                "last_alert_time": self.last_alert_time.isoformat(),
            },
        )

    def _get_last_alert_state(self) -> str:
        """Get last alert state from Redis."""
        state = self.redis.hgetall(self.ALERT_STATE_KEY)
        return state.get("last_alert_type", "")

    def _send_alert(
        self, severity: AlertSeverity, title: str, message: str, fields: dict
    ):
        """Send alert via Discord webhook and log."""
        # Log alert
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
        }.get(severity, logger.info)

        log_method(f"ALERT [{severity.value.upper()}] {title}: {message}")

        # Send Discord webhook if configured
        if self.discord_webhook:
            try:
                import requests

                color = {
                    AlertSeverity.INFO: 0x00FF00,  # Green
                    AlertSeverity.WARNING: 0xFFA500,  # Orange
                    AlertSeverity.CRITICAL: 0xFF0000,  # Red
                }.get(severity, 0x808080)

                embed_fields = [
                    {"name": k, "value": str(v), "inline": True}
                    for k, v in fields.items()
                ]

                payload = {
                    "embeds": [
                        {
                            "title": title,
                            "description": message,
                            "color": color,
                            "fields": embed_fields,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ]
                }

                response = requests.post(self.discord_webhook, json=payload, timeout=10)
                response.raise_for_status()

            except Exception as e:
                logger.error(f"Failed to send Discord alert: {e}")


def main():
    """Main monitoring loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    manager = PipelineAlertManager()

    logger.info("Pipeline alert manager starting...")

    import time

    while True:
        try:
            manager.check_and_alert()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.exception(f"Error in alert loop: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
