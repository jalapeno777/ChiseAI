"""Tests for kill-switch state management.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

from datetime import UTC, datetime

from execution.kill_switch.state import (
    CloseResult,
    CloseStatus,
    KillSwitchConfig,
    KillSwitchLogEntry,
    KillSwitchResult,
    KillSwitchState,
)


class TestKillSwitchState:
    """Test KillSwitchState enum."""

    def test_state_values(self):
        """Test state enum values."""
        assert KillSwitchState.ARMED.value == "armed"
        assert KillSwitchState.TRIGGERED.value == "triggered"
        assert KillSwitchState.DISABLED.value == "disabled"

    def test_state_str(self):
        """Test state string representation."""
        assert str(KillSwitchState.ARMED) == "armed"
        assert str(KillSwitchState.TRIGGERED) == "triggered"
        assert str(KillSwitchState.DISABLED) == "disabled"


class TestCloseStatus:
    """Test CloseStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert CloseStatus.SUCCESS.value == "success"
        assert CloseStatus.FAILED.value == "failed"
        assert CloseStatus.PENDING.value == "pending"
        assert CloseStatus.PARTIAL.value == "partial"

    def test_status_str(self):
        """Test status string representation."""
        assert str(CloseStatus.SUCCESS) == "success"
        assert str(CloseStatus.FAILED) == "failed"


class TestCloseResult:
    """Test CloseResult dataclass."""

    def test_basic_creation(self):
        """Test basic CloseResult creation."""
        result = CloseResult(
            symbol="BTCUSDT",
            side="sell",
            quantity=1.5,
            price=50000.0,
        )

        assert result.symbol == "BTCUSDT"
        assert result.side == "sell"
        assert result.quantity == 1.5
        assert result.price == 50000.0
        assert result.status == CloseStatus.PENDING
        assert result.order_id is None
        assert result.error is None
        assert result.pnl == 0.0

    def test_full_creation(self):
        """Test CloseResult with all fields."""
        ts = datetime.now(UTC)
        result = CloseResult(
            symbol="ETHUSDT",
            side="buy",
            quantity=10.0,
            price=3000.0,
            status=CloseStatus.SUCCESS,
            order_id="order123",
            error=None,
            timestamp=ts,
            pnl=150.5,
        )

        assert result.order_id == "order123"
        assert result.pnl == 150.5

    def test_to_dict(self):
        """Test CloseResult serialization."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = CloseResult(
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=50000.0,
            status=CloseStatus.SUCCESS,
            order_id="abc123",
            pnl=100.0,
            timestamp=ts,
        )

        d = result.to_dict()
        assert d["symbol"] == "BTCUSDT"
        assert d["side"] == "sell"
        assert d["quantity"] == 1.0
        assert d["price"] == 50000.0
        assert d["status"] == "success"
        assert d["order_id"] == "abc123"
        assert d["pnl"] == 100.0
        assert d["timestamp"] == "2024-01-15T12:00:00+00:00"


class TestKillSwitchResult:
    """Test KillSwitchResult dataclass."""

    def test_default_creation(self):
        """Test KillSwitchResult with defaults."""
        result = KillSwitchResult()

        assert result.success is False
        assert result.positions_closed == 0
        assert result.total_pnl == 0.0
        assert result.reason == ""
        assert result.triggered_by == ""
        assert result.environment == ""
        assert result.close_results == []
        assert result.metadata == {}

    def test_full_creation(self):
        """Test KillSwitchResult with all fields."""
        ts = datetime.now(UTC)
        close_results = [
            CloseResult(
                symbol="BTCUSDT",
                side="sell",
                quantity=1.0,
                price=50000.0,
                status=CloseStatus.SUCCESS,
                pnl=100.0,
            ),
            CloseResult(
                symbol="ETHUSDT",
                side="buy",
                quantity=5.0,
                price=3000.0,
                status=CloseStatus.FAILED,
                error="API error",
            ),
        ]

        result = KillSwitchResult(
            success=True,
            positions_closed=1,
            total_pnl=100.0,
            timestamp=ts,
            reason="manual trigger",
            triggered_by="cli",
            environment="paper",
            close_results=close_results,
            metadata={"drawdown_pct": 15.5},
        )

        assert result.success is True
        assert result.positions_closed == 1
        assert result.total_pnl == 100.0
        assert result.reason == "manual trigger"
        assert len(result.close_results) == 2
        assert result.metadata["drawdown_pct"] == 15.5

    def test_to_dict(self):
        """Test KillSwitchResult serialization."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = KillSwitchResult(
            success=True,
            positions_closed=2,
            total_pnl=250.0,
            timestamp=ts,
            reason="drawdown threshold",
            triggered_by="monitor",
            environment="live",
            metadata={"drawdown_pct": 15.0},
        )

        d = result.to_dict()
        assert d["success"] is True
        assert d["positions_closed"] == 2
        assert d["total_pnl"] == 250.0
        assert d["timestamp"] == "2024-01-15T12:00:00+00:00"
        assert d["reason"] == "drawdown threshold"
        assert d["triggered_by"] == "monitor"
        assert d["environment"] == "live"
        assert d["metadata"]["drawdown_pct"] == 15.0


class TestKillSwitchConfig:
    """Test KillSwitchConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = KillSwitchConfig()

        assert config.drawdown_threshold_pct == 15.0
        assert config.rolling_window_hours == 24
        assert config.require_reauthorization is True
        assert config.max_close_retries == 3
        assert config.close_retry_delay_seconds == 1.0
        assert config.log_to_influxdb is True
        assert config.influxdb_measurement == "kill_switch"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = KillSwitchConfig(
            drawdown_threshold_pct=10.0,
            rolling_window_hours=12,
            require_reauthorization=False,
            max_close_retries=5,
            close_retry_delay_seconds=2.0,
            log_to_influxdb=False,
            influxdb_measurement="custom_measurement",
        )

        assert config.drawdown_threshold_pct == 10.0
        assert config.rolling_window_hours == 12
        assert config.require_reauthorization is False
        assert config.max_close_retries == 5

    def test_to_dict(self):
        """Test KillSwitchConfig serialization."""
        config = KillSwitchConfig()
        d = config.to_dict()

        assert d["drawdown_threshold_pct"] == 15.0
        assert d["rolling_window_hours"] == 24
        assert d["require_reauthorization"] is True
        assert d["max_close_retries"] == 3
        assert d["close_retry_delay_seconds"] == 1.0
        assert d["log_to_influxdb"] is True
        assert d["influxdb_measurement"] == "kill_switch"


class TestKillSwitchLogEntry:
    """Test KillSwitchLogEntry dataclass."""

    def test_basic_creation(self):
        """Test basic log entry creation."""
        entry = KillSwitchLogEntry(
            event_type="trigger",
            state=KillSwitchState.TRIGGERED,
            message="Kill-switch triggered",
        )

        assert entry.event_type == "trigger"
        assert entry.state == KillSwitchState.TRIGGERED
        assert entry.message == "Kill-switch triggered"
        assert entry.drawdown_pct == 0.0
        assert entry.positions_count == 0
        assert entry.portfolio_value == 0.0

    def test_full_creation(self):
        """Test log entry with all fields."""
        ts = datetime.now(UTC)
        entry = KillSwitchLogEntry(
            event_type="close",
            state=KillSwitchState.TRIGGERED,
            timestamp=ts,
            message="Position closed",
            drawdown_pct=15.5,
            positions_count=3,
            portfolio_value=95000.0,
            metadata={"symbol": "BTCUSDT"},
        )

        assert entry.drawdown_pct == 15.5
        assert entry.positions_count == 3
        assert entry.portfolio_value == 95000.0
        assert entry.metadata["symbol"] == "BTCUSDT"

    def test_to_dict(self):
        """Test KillSwitchLogEntry serialization."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        entry = KillSwitchLogEntry(
            event_type="trigger",
            state=KillSwitchState.TRIGGERED,
            timestamp=ts,
            message="Manual trigger",
            drawdown_pct=15.0,
            positions_count=5,
            portfolio_value=85000.0,
            metadata={"reason": "test"},
        )

        d = entry.to_dict()
        assert d["event_type"] == "trigger"
        assert d["state"] == "triggered"
        assert d["timestamp"] == "2024-01-15T12:00:00+00:00"
        assert d["message"] == "Manual trigger"
        assert d["drawdown_pct"] == 15.0
        assert d["positions_count"] == 5
        assert d["portfolio_value"] == 85000.0
        assert d["metadata"]["reason"] == "test"
