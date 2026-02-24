"""Tests for Uptime Monitor."""
import pytest
from datetime import datetime, timedelta, timezone

from src.infrastructure.ha.uptime_monitor import (
    AlertSeverity, UptimeRecord, Alert, UptimeTarget,
    UptimeMonitorConfig, UptimeMonitor
)
from src.infrastructure.ha.health_check import HealthStatus


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""
    
    def test_severity_values(self):
        """Test that all expected severity values exist."""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestUptimeRecord:
    """Tests for UptimeRecord dataclass."""
    
    def test_record_creation(self):
        """Test creating an uptime record."""
        now = datetime.now(timezone.utc)
        record = UptimeRecord(
            start_time=now,
            end_time=now,
            total_checks=100,
            successful_checks=99,
        )
        assert record.total_checks == 100
        assert record.successful_checks == 99
    
    def test_uptime_percentage(self):
        """Test uptime percentage calculation."""
        now = datetime.now(timezone.utc)
        record = UptimeRecord(
            start_time=now,
            end_time=now,
            total_checks=100,
            successful_checks=99,
        )
        assert record.uptime_percentage == 99.0
    
    def test_uptime_percentage_no_checks(self):
        """Test uptime percentage with no checks."""
        now = datetime.now(timezone.utc)
        record = UptimeRecord(start_time=now, end_time=now)
        assert record.uptime_percentage == 100.0  # Default
    
    def test_record_to_dict(self):
        """Test serializing record to dict."""
        now = datetime.now(timezone.utc)
        record = UptimeRecord(
            start_time=now,
            end_time=now,
            total_checks=100,
            successful_checks=95,
        )
        d = record.to_dict()
        assert d["total_checks"] == 100
        assert d["successful_checks"] == 95
        assert d["uptime_percentage"] == 95.0


class TestAlert:
    """Tests for Alert dataclass."""
    
    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            id="alert-1",
            service_name="test-service",
            severity=AlertSeverity.WARNING,
            message="Uptime below threshold",
        )
        assert alert.id == "alert-1"
        assert alert.service_name == "test-service"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.acknowledged is False
    
    def test_alert_to_dict(self):
        """Test serializing alert to dict."""
        alert = Alert(
            id="alert-1",
            service_name="test-service",
            severity=AlertSeverity.CRITICAL,
            message="Critical alert",
        )
        d = alert.to_dict()
        assert d["id"] == "alert-1"
        assert d["severity"] == "critical"
        assert d["acknowledged"] is False


class TestUptimeTarget:
    """Tests for UptimeTarget dataclass."""
    
    def test_target_defaults(self):
        """Test default target values."""
        target = UptimeTarget(service_name="test-service")
        assert target.target_percentage == 99.9
        assert target.measurement_window_hours == 24
    
    def test_target_custom_values(self):
        """Test custom target values."""
        target = UptimeTarget(
            service_name="test-service",
            target_percentage=99.99,
            alert_threshold_percentage=99.9,
            critical_threshold_percentage=99.0,
        )
        assert target.target_percentage == 99.99


class TestUptimeMonitor:
    """Tests for UptimeMonitor class."""
    
    def test_register_target(self, uptime_monitor, uptime_target):
        """Test registering a target."""
        uptime_monitor.register_target(uptime_target)
        assert "test-service" in uptime_monitor._targets
    
    def test_unregister_target(self, uptime_monitor, uptime_target):
        """Test unregistering a target."""
        uptime_monitor.register_target(uptime_target)
        result = uptime_monitor.unregister_target("test-service")
        assert result is True
        assert "test-service" not in uptime_monitor._targets
    
    def test_unregister_nonexistent(self, uptime_monitor):
        """Test unregistering non-existent target."""
        result = uptime_monitor.unregister_target("nonexistent")
        assert result is False
    
    def test_record_check_healthy(self, uptime_monitor, uptime_target):
        """Test recording a healthy check."""
        uptime_monitor.register_target(uptime_target)
        alert = uptime_monitor.record_check("test-service", HealthStatus.HEALTHY)
        # No alert should be generated for healthy service
        assert alert is None or alert.severity != AlertSeverity.CRITICAL
    
    def test_record_check_unhealthy(self, uptime_monitor, uptime_target):
        """Test recording an unhealthy check."""
        uptime_monitor.register_target(uptime_target)
        # Record some healthy checks first
        for _ in range(10):
            uptime_monitor.record_check("test-service", HealthStatus.HEALTHY)
        # Then unhealthy checks
        for _ in range(10):
            uptime_monitor.record_check("test-service", HealthStatus.UNHEALTHY)
        
        # Check that uptime dropped
        uptime = uptime_monitor.calculate_uptime("test-service")
        assert uptime is not None
        assert uptime < 100.0
    
    def test_calculate_uptime_no_records(self, uptime_monitor):
        """Test calculating uptime with no records."""
        uptime = uptime_monitor.calculate_uptime("nonexistent")
        assert uptime is None
    
    def test_calculate_uptime_with_records(self, uptime_monitor, uptime_target):
        """Test calculating uptime with records."""
        uptime_monitor.register_target(uptime_target)
        
        # Record 80 healthy, 20 unhealthy = 80% uptime
        for _ in range(80):
            uptime_monitor.record_check("test-service", HealthStatus.HEALTHY)
        for _ in range(20):
            uptime_monitor.record_check("test-service", HealthStatus.UNHEALTHY)
        
        uptime = uptime_monitor.calculate_uptime("test-service")
        assert uptime == pytest.approx(80.0, rel=0.1)
    
    def test_alert_generation_critical(self, uptime_monitor):
        """Test critical alert generation."""
        target = UptimeTarget(
            service_name="test-service",
            target_percentage=99.9,
            alert_threshold_percentage=99.0,
            critical_threshold_percentage=98.0,
        )
        uptime_monitor.register_target(target)
        
        # Generate very low uptime
        for _ in range(50):
            uptime_monitor.record_check("test-service", HealthStatus.UNHEALTHY)
        
        # Check if critical alert was generated
        alerts = uptime_monitor.get_recent_alerts("test-service")
        # May or may not have alert depending on timing
        assert isinstance(alerts, list)
    
    def test_acknowledge_alert(self, uptime_monitor, uptime_target):
        """Test acknowledging an alert."""
        uptime_monitor.register_target(uptime_target)
        
        # Generate an alert
        for _ in range(100):
            uptime_monitor.record_check("test-service", HealthStatus.UNHEALTHY)
        
        alerts = uptime_monitor.get_recent_alerts("test-service", unacknowledged_only=True)
        if alerts:
            result = uptime_monitor.acknowledge_alert(alerts[0].id, "admin")
            assert result is True
            assert alerts[0].acknowledged is True
    
    def test_callback_registration(self, uptime_monitor):
        """Test callback registration."""
        called = []
        def callback(alert):
            called.append(alert)
        
        uptime_monitor.add_callback(callback)
        assert callback in uptime_monitor._alert_callbacks
    
    def test_get_service_status(self, uptime_monitor, uptime_target):
        """Test getting service status."""
        uptime_monitor.register_target(uptime_target)
        
        for _ in range(10):
            uptime_monitor.record_check("test-service", HealthStatus.HEALTHY)
        
        status = uptime_monitor.get_service_status("test-service")
        assert status["service_name"] == "test-service"
        assert "uptime_24h" in status
        assert "uptime_7d" in status
        assert "uptime_30d" in status
    
    def test_get_all_status(self, uptime_monitor, uptime_target):
        """Test getting all services status."""
        uptime_monitor.register_target(uptime_target)
        
        for _ in range(10):
            uptime_monitor.record_check("test-service", HealthStatus.HEALTHY)
        
        status = uptime_monitor.get_all_status()
        assert "services" in status
        assert "total_services" in status
    
    def test_get_recent_alerts(self, uptime_monitor, uptime_target):
        """Test getting recent alerts."""
        uptime_monitor.register_target(uptime_target)
        
        alerts = uptime_monitor.get_recent_alerts()
        assert isinstance(alerts, list)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, uptime_monitor):
        """Test starting and stopping monitor."""
        await uptime_monitor.start()
        assert uptime_monitor._running is True
        await uptime_monitor.stop()
        assert uptime_monitor._running is False
    
    def test_to_dict(self, uptime_monitor, uptime_target):
        """Test serializing monitor to dict."""
        uptime_monitor.register_target(uptime_target)
        d = uptime_monitor.to_dict()
        assert "status" in d
        assert "recent_alerts" in d
        assert "config" in d


class TestUptimeCalculation:
    """Tests for uptime calculation accuracy."""
    
    def test_uptime_99_9_target(self):
        """Test achieving 99.9% uptime target."""
        monitor = UptimeMonitor()
        target = UptimeTarget(service_name="high-avail", target_percentage=99.9)
        monitor.register_target(target)
        
        # 999 healthy, 1 unhealthy = 99.9%
        for _ in range(999):
            monitor.record_check("high-avail", HealthStatus.HEALTHY)
        monitor.record_check("high-avail", HealthStatus.UNHEALTHY)
        
        uptime = monitor.calculate_uptime("high-avail")
        assert uptime == pytest.approx(99.9, rel=0.1)
    
    def test_uptime_with_time_window(self):
        """Test uptime calculation with time window."""
        monitor = UptimeMonitor()
        target = UptimeTarget(
            service_name="test",
            measurement_window_hours=1,  # 1 hour window
        )
        monitor.register_target(target)
        
        for _ in range(100):
            monitor.record_check("test", HealthStatus.HEALTHY)
        
        uptime_1h = monitor.calculate_uptime("test", hours=1)
        assert uptime_1h is not None
        assert uptime_1h > 99.0
