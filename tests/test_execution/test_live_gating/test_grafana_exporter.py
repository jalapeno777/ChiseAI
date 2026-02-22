"""Tests for live gating Grafana exporter.

Tests metrics export for Grafana dashboard visibility.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from execution.live_gating.grafana_exporter import (
    LiveGatingGrafanaExporter,
    LiveGatingMetrics,
)


class TestLiveGatingMetrics:
    """Test LiveGatingMetrics dataclass."""

    def test_creation(self):
        """Test metrics creation."""
        now = datetime.now(UTC)
        metrics = LiveGatingMetrics(
            timestamp=now,
            state="active",
            is_enabled=True,
            last_approval_date=now,
            total_trades=100,
            daily_pnl=500.0,
            daily_loss_cap=1000.0,
        )
        assert metrics.state == "active"
        assert metrics.is_enabled is True
        assert metrics.total_trades == 100

    def test_to_dict(self):
        """Test serialization."""
        now = datetime.now(UTC)
        metrics = LiveGatingMetrics(
            timestamp=now,
            state="active",
            is_enabled=True,
            last_approval_date=now,
            total_trades=100,
            daily_pnl=500.0,
            daily_loss_cap=1000.0,
        )
        d = metrics.to_dict()
        assert d["state"] == "active"
        assert d["is_enabled"] is True
        assert d["total_trades"] == 100

    def test_to_dict_no_approval_date(self):
        """Test serialization without approval date."""
        now = datetime.now(UTC)
        metrics = LiveGatingMetrics(
            timestamp=now,
            state="disabled",
            is_enabled=False,
            last_approval_date=None,
            total_trades=0,
            daily_pnl=0.0,
            daily_loss_cap=1000.0,
        )
        d = metrics.to_dict()
        assert d["last_approval_date"] is None


class TestLiveGatingGrafanaExporterInitialization:
    """Test exporter initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        exporter = LiveGatingGrafanaExporter()
        assert exporter._measurement == "live_trading_gating"
        assert exporter._interval == 30.0
        assert exporter._bucket == "chiseai"

    def test_custom_initialization(self):
        """Test custom initialization."""
        mock_manager = MagicMock()
        exporter = LiveGatingGrafanaExporter(
            gate_manager=mock_manager,
            bucket="custom",
            interval=60.0,
        )
        assert exporter._gate_manager == mock_manager
        assert exporter._bucket == "custom"
        assert exporter._interval == 60.0


class TestStatePointCreation:
    """Test state point creation."""

    def test_create_state_point_disabled(self):
        """Test state point for disabled state."""
        exporter = LiveGatingGrafanaExporter()
        now = datetime.now(UTC)

        # Mock ImportError to force dict fallback
        with patch.dict("sys.modules", {"influxdb_client": None}):
            point = exporter._create_state_point(
                state="disabled",
                is_enabled=False,
                last_approval_date=None,
            )

            # Should return a dict fallback (no influxdb_client)
            assert point["measurement"] == "live_trading_gating"
            assert point["tags"]["state"] == "disabled"
            assert point["fields"]["is_enabled"] == 0.0
            assert point["fields"]["state_value"] == 0.0

    def test_create_state_point_active(self):
        """Test state point for active state."""
        exporter = LiveGatingGrafanaExporter()
        now = datetime.now(UTC)

        # Mock ImportError to force dict fallback
        with patch.dict("sys.modules", {"influxdb_client": None}):
            point = exporter._create_state_point(
                state="active",
                is_enabled=True,
                last_approval_date=now,
            )

            assert point["fields"]["is_enabled"] == 1.0
            assert point["fields"]["state_value"] == 3.0
            assert point["fields"]["last_approval_timestamp"] == now.timestamp()

    def test_state_to_numeric_mapping(self):
        """Test state to numeric value mapping."""
        exporter = LiveGatingGrafanaExporter()
        assert exporter._state_to_numeric("disabled") == 0.0
        assert exporter._state_to_numeric("pending_approval") == 1.0
        assert exporter._state_to_numeric("approved") == 2.0
        assert exporter._state_to_numeric("active") == 3.0
        assert exporter._state_to_numeric("unknown") == -1.0


class TestActivityPointCreation:
    """Test activity point creation."""

    def test_create_activity_point(self):
        """Test activity point creation."""
        exporter = LiveGatingGrafanaExporter()

        # Mock ImportError to force dict fallback
        with patch.dict("sys.modules", {"influxdb_client": None}):
            point = exporter._create_activity_point(
                total_trades=100,
                daily_pnl=500.0,
                daily_loss_cap=1000.0,
            )

            assert point["measurement"] == "live_trading_gating"
            assert point["tags"]["metric_type"] == "activity"
            assert point["fields"]["total_trades"] == 100.0
            assert point["fields"]["daily_pnl"] == 500.0
            assert point["fields"]["daily_loss_remaining"] == 1500.0


class TestCountsPointCreation:
    """Test counts point creation."""

    def test_create_counts_point(self):
        """Test counts point creation."""
        exporter = LiveGatingGrafanaExporter()

        # Mock ImportError to force dict fallback
        with patch.dict("sys.modules", {"influxdb_client": None}):
            point = exporter._create_counts_point(
                approval_count=5,
                rejection_count=2,
                state_change_count=10,
            )

            assert point["measurement"] == "live_trading_gating"
            assert point["tags"]["metric_type"] == "counts"
            assert point["fields"]["approval_count"] == 5.0
            assert point["fields"]["rejection_count"] == 2.0
            assert point["fields"]["state_change_count"] == 10.0


class TestExportMetrics:
    """Test metrics export."""

    @pytest.mark.asyncio
    async def test_export_metrics_with_gate_manager(self):
        """Test exporting with gate manager."""
        mock_manager = MagicMock()
        mock_manager.get_status.return_value = {
            "state": "active",
            "is_live_enabled": True,
            "last_approval": {
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "daily_pnl": 500.0,
            "config": {"daily_loss_cap": 1000.0},
            "state_history_count": 5,
        }

        exporter = LiveGatingGrafanaExporter(gate_manager=mock_manager)

        with patch.object(exporter, "_get_write_api", return_value=None):
            result = await exporter.export_metrics()
            assert result is True
            assert exporter._export_count == 1

    @pytest.mark.asyncio
    async def test_export_metrics_without_gate_manager(self):
        """Test exporting without gate manager."""
        exporter = LiveGatingGrafanaExporter()

        with patch.object(exporter, "_get_write_api", return_value=None):
            result = await exporter.export_metrics()
            assert result is True
            # Should use default values
            assert exporter._export_count == 1

    @pytest.mark.asyncio
    async def test_export_metrics_failure(self):
        """Test export failure handling."""
        mock_manager = MagicMock()
        mock_manager.get_status.side_effect = Exception("Status error")

        exporter = LiveGatingGrafanaExporter(gate_manager=mock_manager)

        result = await exporter.export_metrics()
        assert result is False
        assert exporter._failed_exports == 1


class TestCounterRecording:
    """Test counter recording methods."""

    def test_record_trade(self):
        """Test trade recording."""
        exporter = LiveGatingGrafanaExporter()
        assert exporter._trade_count == 0
        exporter.record_trade()
        assert exporter._trade_count == 1
        exporter.record_trade()
        assert exporter._trade_count == 2

    def test_record_approval(self):
        """Test approval recording."""
        exporter = LiveGatingGrafanaExporter()
        assert exporter._approval_count == 0
        exporter.record_approval()
        assert exporter._approval_count == 1

    def test_record_rejection(self):
        """Test rejection recording."""
        exporter = LiveGatingGrafanaExporter()
        assert exporter._rejection_count == 0
        exporter.record_rejection()
        assert exporter._rejection_count == 1


class TestStatistics:
    """Test statistics methods."""

    def test_get_stats(self):
        """Test getting statistics."""
        exporter = LiveGatingGrafanaExporter()
        exporter._export_count = 10
        exporter._failed_exports = 2
        exporter._trade_count = 100
        exporter._approval_count = 5
        exporter._rejection_count = 1

        stats = exporter.get_stats()
        assert stats["export_count"] == 10
        assert stats["failed_exports"] == 2
        assert stats["trade_count"] == 100
        assert stats["approval_count"] == 5
        assert stats["rejection_count"] == 1
        assert stats["measurement"] == "live_trading_gating"


class TestGetMetrics:
    """Test get_metrics method."""

    def test_get_metrics_with_gate_manager(self):
        """Test getting metrics with gate manager."""
        now = datetime.now(UTC)
        mock_manager = MagicMock()
        mock_manager.get_status.return_value = {
            "state": "active",
            "is_live_enabled": True,
            "last_approval": {
                "timestamp": now.isoformat(),
            },
            "daily_pnl": 500.0,
            "config": {"daily_loss_cap": 1000.0},
            "state_history_count": 5,
        }

        exporter = LiveGatingGrafanaExporter(gate_manager=mock_manager)
        exporter._trade_count = 100
        exporter._approval_count = 5
        exporter._rejection_count = 1

        metrics = exporter.get_metrics()
        assert metrics is not None
        assert metrics.state == "active"
        assert metrics.is_enabled is True
        assert metrics.total_trades == 100
        assert metrics.approval_count == 5

    def test_get_metrics_without_gate_manager(self):
        """Test getting metrics without gate manager."""
        exporter = LiveGatingGrafanaExporter()
        metrics = exporter.get_metrics()
        assert metrics is None

    def test_get_metrics_error(self):
        """Test getting metrics with error."""
        mock_manager = MagicMock()
        mock_manager.get_status.side_effect = Exception("Status error")

        exporter = LiveGatingGrafanaExporter(gate_manager=mock_manager)
        metrics = exporter.get_metrics()
        assert metrics is None


class TestStartStop:
    """Test start and stop methods."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping exporter."""
        exporter = LiveGatingGrafanaExporter()

        with patch.object(exporter, "export_metrics", return_value=True):
            await exporter.start()
            assert exporter._running is True

            await exporter.stop()
            assert exporter._running is False

    @pytest.mark.asyncio
    async def test_stop_final_export(self):
        """Test final export on stop."""
        exporter = LiveGatingGrafanaExporter()

        with patch.object(exporter, "export_metrics") as mock_export:
            await exporter.stop()
            mock_export.assert_called_once()
