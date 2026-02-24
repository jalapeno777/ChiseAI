"""Uptime Monitor for High Availability Infrastructure (NFR-006)."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from src.infrastructure.ha.health_check import HealthStatus

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class UptimeRecord:
    start_time: datetime
    end_time: datetime
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    total_downtime_seconds: float = 0.0

    @property
    def uptime_percentage(self) -> float:
        return (
            (self.successful_checks / self.total_checks * 100)
            if self.total_checks > 0
            else 100.0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "total_checks": self.total_checks,
            "successful_checks": self.successful_checks,
            "uptime_percentage": self.uptime_percentage,
            "total_downtime_seconds": self.total_downtime_seconds,
        }


@dataclass
class Alert:
    id: str
    service_name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "service_name": self.service_name,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat()
            if self.acknowledged_at
            else None,
            "details": self.details,
        }


@dataclass
class UptimeTarget:
    service_name: str
    target_percentage: float = 99.9
    measurement_window_hours: int = 24
    alert_threshold_percentage: float = 99.5
    critical_threshold_percentage: float = 99.0


@dataclass
class UptimeMonitorConfig:
    check_interval_seconds: float = 60.0
    history_retention_days: int = 30
    alert_cooldown_seconds: float = 300.0
    max_alerts_per_service: int = 100


class UptimeMonitor:
    def __init__(self, config: UptimeMonitorConfig | None = None):
        self.config = config or UptimeMonitorConfig()
        self._targets: dict[str, UptimeTarget] = {}
        self._records: dict[str, list[UptimeRecord]] = defaultdict(list)
        self._alerts: dict[str, list[Alert]] = defaultdict(list)
        self._last_alert_time: dict[str, datetime] = {}
        self._alert_callbacks: list[Callable[[Alert], None]] = []
        self._last_status: dict[str, HealthStatus] = {}
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._alert_counter = 0

    def register_target(self, target: UptimeTarget) -> None:
        self._targets[target.service_name] = target
        logger.info(f"Registered uptime target: {target.service_name}")

    def unregister_target(self, service_name: str) -> bool:
        if service_name in self._targets:
            del self._targets[service_name]
            return True
        return False

    def record_check(self, service_name: str, status: HealthStatus) -> Alert | None:
        if service_name not in self._targets:
            return None
        now = datetime.now(UTC)
        target = self._targets[service_name]
        records = self._records[service_name]

        current_record = records[-1] if records else None
        if (
            not current_record
            or (now - current_record.start_time).total_seconds() >= 3600
        ):
            current_record = UptimeRecord(start_time=now, end_time=now)
            records.append(current_record)

        current_record.end_time = now
        current_record.total_checks += 1

        if status == HealthStatus.HEALTHY:
            current_record.successful_checks += 1
        else:
            current_record.failed_checks += 1

        self._last_status[service_name] = status
        self._cleanup_old_records(service_name)

        return self._check_and_generate_alert(service_name, target)

    def _check_and_generate_alert(
        self, service_name: str, target: UptimeTarget
    ) -> Alert | None:
        now = datetime.now(UTC)
        if service_name in self._last_alert_time:
            if (
                now - self._last_alert_time[service_name]
            ).total_seconds() < self.config.alert_cooldown_seconds:
                return None

        uptime = self.calculate_uptime(service_name, target.measurement_window_hours)
        if uptime is None:
            return None

        severity, message = None, ""
        if uptime < target.critical_threshold_percentage:
            severity, message = (
                AlertSeverity.CRITICAL,
                f"CRITICAL: {service_name} uptime {uptime:.2f}% < {target.critical_threshold_percentage}%",
            )
        elif uptime < target.alert_threshold_percentage:
            severity, message = (
                AlertSeverity.WARNING,
                f"WARNING: {service_name} uptime {uptime:.2f}% < {target.alert_threshold_percentage}%",
            )
        elif uptime < target.target_percentage:
            severity, message = (
                AlertSeverity.INFO,
                f"INFO: {service_name} uptime {uptime:.2f}% < {target.target_percentage}%",
            )

        if severity:
            self._last_alert_time[service_name] = now
            self._alert_counter += 1
            alert = Alert(
                id=f"uptime-alert-{self._alert_counter}",
                service_name=service_name,
                severity=severity,
                message=message,
                details={"current_uptime": uptime},
            )
            self._alerts[service_name].append(alert)
            if len(self._alerts[service_name]) > self.config.max_alerts_per_service:
                self._alerts[service_name] = self._alerts[service_name][
                    -self.config.max_alerts_per_service :
                ]
            for cb in self._alert_callbacks:
                try:
                    cb(alert)
                except Exception:
                    logger.exception("Alert callback error")
            return alert
        return None

    def calculate_uptime(self, service_name: str, hours: int = 24) -> float | None:
        if service_name not in self._records:
            return None
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        total_checks, successful_checks = 0, 0
        for record in self._records[service_name]:
            if record.end_time >= cutoff:
                if record.start_time < cutoff:
                    ratio = (record.end_time - cutoff).total_seconds() / (
                        record.end_time - record.start_time
                    ).total_seconds()
                    total_checks += int(record.total_checks * ratio)
                    successful_checks += int(record.successful_checks * ratio)
                else:
                    total_checks += record.total_checks
                    successful_checks += record.successful_checks
        return (successful_checks / total_checks * 100) if total_checks > 0 else None

    def _cleanup_old_records(self, service_name: str) -> None:
        if service_name not in self._records:
            return
        cutoff = datetime.now(UTC) - timedelta(days=self.config.history_retention_days)
        self._records[service_name] = [
            r for r in self._records[service_name] if r.end_time >= cutoff
        ]

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        for service_alerts in self._alerts.values():
            for alert in service_alerts:
                if alert.id == alert_id and not alert.acknowledged:
                    alert.acknowledged = True
                    alert.acknowledged_by = acknowledged_by
                    alert.acknowledged_at = datetime.now(UTC)
                    return True
        return False

    def add_callback(self, callback: Callable[[Alert], None]) -> None:
        self._alert_callbacks.append(callback)

    def get_service_status(self, service_name: str) -> dict[str, Any]:
        target = self._targets.get(service_name)
        return {
            "service_name": service_name,
            "target": target.target_percentage if target else None,
            "uptime_24h": self.calculate_uptime(service_name, 24),
            "uptime_7d": self.calculate_uptime(service_name, 168),
            "uptime_30d": self.calculate_uptime(service_name, 720),
            "current_status": self._last_status.get(
                service_name, HealthStatus.UNKNOWN
            ).value,
        }

    def get_all_status(self) -> dict[str, Any]:
        return {
            "services": {name: self.get_service_status(name) for name in self._targets},
            "total_services": len(self._targets),
        }

    def get_recent_alerts(
        self,
        service_name: str | None = None,
        hours: int = 24,
        unacknowledged_only: bool = False,
    ) -> list[Alert]:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        alerts = []
        services = [service_name] if service_name else list(self._alerts.keys())
        for svc in services:
            for alert in self._alerts.get(svc, []):
                if alert.timestamp >= cutoff and (
                    not unacknowledged_only or not alert.acknowledged
                ):
                    alerts.append(alert)
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("Started uptime monitor")

    async def stop(self) -> None:
        self._running = False
        logger.info("Stopped uptime monitor")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.get_all_status(),
            "recent_alerts": [a.to_dict() for a in self.get_recent_alerts(hours=1)],
            "config": {
                "check_interval_seconds": self.config.check_interval_seconds,
                "history_retention_days": self.config.history_retention_days,
            },
        }
