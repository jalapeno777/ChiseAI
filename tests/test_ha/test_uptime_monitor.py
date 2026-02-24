"""Tests for Uptime Monitor."""

import pytest
from src.infrastructure.ha.health_check import HealthStatus
from src.infrastructure.ha.uptime_monitor import (
    Alert,
    AlertSeverity,
    UptimeMonitor,
    UptimeMonitorConfig,
    UptimeTarget,
)


class TestUptimeTarget:
    """Tests for UptimeTarget."""

    def test_uptime_target_creation(self):
        """Test creating an uptime target."""
        target = UptimeTarget(
            service_name="api",
            target_percentage=99.9,
            alert_threshold_percentage=99.5,
        )
        assert target.service_name == "api"
        assert target.target_percentage == 99.9
        assert target.alert_threshold_percentage == 99.5


class TestAlert:
    """Tests for Alert."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            id="alert-1",
            service_name="api",
            severity=AlertSeverity.WARNING,
            message="Uptime below target",
        )
        assert alert.id == "alert-1"
        assert alert.service_name == "api"
        assert not alert.acknowledged

    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = Alert(
            id="alert-1",
            service_name="api",
            severity=AlertSeverity.CRITICAL,
            message="Critical alert",
            details={"uptime": 98.5},
        )
        d = alert.to_dict()
        assert d["id"] == "alert-1"
        assert d["severity"] == "critical"
        assert d["details"]["uptime"] == 98.5


class TestUptimeMonitor:
    """Tests for UptimeMonitor."""

    def test_uptime_monitor_creation(self):
        """Test creating an uptime monitor."""
        monitor = UptimeMonitor()
        assert len(monitor._targets) == 0

    def test_register_target(self, uptime_monitor):
        """Test registering an uptime target."""
        target = UptimeTarget(service_name="api")
        uptime_monitor.register_target(target)

        status = uptime_monitor.get_service_status("api")
        assert status["service_name"] == "api"
        assert status["target"] == 99.9

    def test_unregister_target(self, uptime_monitor):
        """Test unregistering an uptime target."""
        target = UptimeTarget(service_name="api")
        uptime_monitor.register_target(target)

        assert uptime_monitor.unregister_target("api")
        assert not uptime_monitor.unregister_target("nonexistent")

    def test_record_check_healthy(self, uptime_monitor):
        """Test recording a healthy check."""
        uptime_monitor.register_target(UptimeTarget(service_name="api"))

        for _ in range(10):
            uptime_monitor.record_check("api", HealthStatus.HEALTHY)

        status = uptime_monitor.get_service_status("api")
        assert status["uptime_24h"] == 100.0
        assert status["is_meeting_target"]

    def test_record_check_mixed(self, uptime_monitor):
        """Test recording mixed check results."""
        uptime_monitor.register_target(UptimeTarget(service_name="api"))

        # 8 healthy, 2 unhealthy = 80% uptime
        for _ in range(8):
            uptime_monitor.record_check("api", HealthStatus.HEALTHY)
        for _ in range(2):
            uptime_monitor.record_check("api", HealthStatus.UNHEALTHY)

        status = uptime_monitor.get_service_status("api")
        assert status["uptime_24h"] == 80.0

    def test_alert_generation(self, uptime_monitor):
        """Test alert generation when below threshold."""
        target = UptimeTarget(
            service_name="api",
            alert_threshold_percentage=90.0,
        )
        uptime_monitor.register_target(target)

        # Generate enough failures to trigger alert
        for _ in range(15):
            alert = uptime_monitor.record_check("api", HealthStatus.UNHEALTHY)

        # Should have generated at least one alert
        alerts = uptime_monitor.get_recent_alerts(service_name="api")
        assert len(alerts) > 0
        assert alerts[0].severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL)

    def test_alert_cooldown(self, uptime_monitor):
        """Test alert cooldown prevents spam."""
        config = UptimeMonitorConfig(alert_cooldown_seconds=60.0)
        monitor = UptimeMonitor(config)
        monitor.register_target(
            UptimeTarget(
                service_name="api",
                alert_threshold_percentage=99.0,
            )
        )

        # Generate alerts
        for _ in range(20):
            monitor.record_check("api", HealthStatus.UNHEALTHY)

        # Should have limited alerts due to cooldown
        alerts = monitor.get_recent_alerts(service_name="api")
        assert len(alerts) <= 2  # Cooldown should limit alerts

    def test_acknowledge_alert(self, uptime_monitor):
        """Test acknowledging an alert."""
        uptime_monitor.register_target(
            UptimeTarget(
                service_name="api",
                alert_threshold_percentage=99.0,
            )
        )

        # Generate alert
        for _ in range(10):
            uptime_monitor.record_check("api", HealthStatus.UNHEALTHY)

        alerts = uptime_monitor.get_recent_alerts(service_name="api")
        if alerts:
            alert_id = alerts[0].id
            assert uptime_monitor.acknowledge_alert(alert_id, "admin")

            # Check it's acknowledged
            alerts = uptime_monitor.get_recent_alerts(
                service_name="api",
                unacknowledged_only=True,
            )
            if alerts:
                assert alerts[0].id != alert_id

    def test_alert_callbacks(self, uptime_monitor):
        """Test alert callbacks."""
        received_alerts = []

        def callback(alert):
            received_alerts.append(alert)

        uptime_monitor.add_callback(callback)
        uptime_monitor.register_target(
            UptimeTarget(
                service_name="api",
                alert_threshold_percentage=99.0,
            )
        )

        # Generate alert
        for _ in range(10):
            uptime_monitor.record_check("api", HealthStatus.UNHEALTHY)

        # Should have received alerts via callback
        assert len(received_alerts) > 0

    def test_calculate_uptime(self, uptime_monitor):
        """Test uptime calculation over different windows."""
        uptime_monitor.register_target(UptimeTarget(service_name="api"))

        # Record some checks
        for _ in range(100):
            uptime_monitor.record_check("api", HealthStatus.HEALTHY)
        for _ in range(10):
            uptime_monitor.record_check("api", HealthStatus.UNHEALTHY)

        uptime_24h = uptime_monitor.calculate_uptime("api", hours=24)
        assert uptime_24h is not None
        assert 90 < uptime_24h < 91  # ~90.9%

    def test_get_all_status(self, uptime_monitor):
        """Test getting all services status."""
        uptime_monitor.register_target(UptimeTarget(service_name="api"))
        uptime_monitor.register_target(UptimeTarget(service_name="web"))

        for _ in range(10):
            uptime_monitor.record_check("api", HealthStatus.HEALTHY)
            uptime_monitor.record_check("web", HealthStatus.HEALTHY)

        status = uptime_monitor.get_all_status()
        assert status["total_services"] == 2
        assert status["services_meeting_target"] == 2

    def test_get_recent_alerts(self, uptime_monitor):
        """Test getting recent alerts."""
        uptime_monitor.register_target(
            UptimeTarget(
                service_name="api",
                alert_threshold_percentage=99.0,
            )
        )

        # Generate alerts
        for _ in range(10):
            uptime_monitor.record_check("api", HealthStatus.UNHEALTHY)

        alerts = uptime_monitor.get_recent_alerts(hours=24)
        assert len(alerts) > 0

    def test_to_dict(self, uptime_monitor):
        """Test exporting monitor status."""
        uptime_monitor.register_target(UptimeTarget(service_name="api"))

        d = uptime_monitor.to_dict()
        assert "status" in d
        assert "recent_alerts" in d
        assert "config" in d

    @pytest.mark.asyncio
    async def test_start_stop(self, uptime_monitor):
        """Test starting and stopping monitor."""
        await uptime_monitor.start()
        assert uptime_monitor._running

        await uptime_monitor.stop()
        assert not uptime_monitor._running
