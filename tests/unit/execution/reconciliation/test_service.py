"""Unit tests for reconciliation service — ReconciliationMonitor and backfill."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.reconciliation.config import ReconciliationConfig
from execution.reconciliation.models import (
    CountDiscrepancy,
    ReconciliationResult,
    ReconciliationStatus,
)
from execution.reconciliation.service import (
    OutcomeReconciliationService,
    ReconciliationMonitor,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_telemetry_exporter():
    return MagicMock()


def _make_service(**kwargs):
    exporter = _make_telemetry_exporter()
    return OutcomeReconciliationService(
        telemetry_exporter=exporter,
        **kwargs,
    )


def _make_result(
    status=ReconciliationStatus.OK,
    discrepancies=None,
    delta_pct=None,
    telemetry_count=None,
    persisted_count=None,
    delta_count=None,
):
    return ReconciliationResult(
        telemetry_count=telemetry_count or {"fills": 10},
        persisted_count=persisted_count or {"fills": 10},
        delta_count=delta_count or {"fills": 0},
        delta_pct=delta_pct or {"fills": 0.0},
        status=status,
        discrepancies=discrepancies or [],
    )


# ---------------------------------------------------------------------------
# ReconciliationMonitor — instantiation
# ---------------------------------------------------------------------------


class TestReconciliationMonitorInstantiation:
    """Verify ReconciliationMonitor can be created with valid args."""

    def test_create_with_defaults(self):
        service = _make_service()
        monitor = ReconciliationMonitor(reconciliation_service=service)
        assert monitor.service is service
        assert monitor.check_interval == 3600
        assert monitor._running is False
        assert monitor._task is None

    def test_create_with_custom_interval(self):
        service = _make_service()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            check_interval_seconds=1800,
        )
        assert monitor.check_interval == 1800

    def test_create_with_redis(self):
        service = _make_service()
        redis_mock = MagicMock()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            redis_client=redis_mock,
        )
        assert monitor.redis is redis_mock


# ---------------------------------------------------------------------------
# ReconciliationMonitor — start / stop lifecycle
# ---------------------------------------------------------------------------


class TestReconciliationMonitorLifecycle:
    """Verify ReconciliationMonitor start/stop async lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running_and_creates_task(self):
        service = _make_service()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            check_interval_seconds=1,
        )
        await monitor.start()
        assert monitor._running is True
        assert monitor._task is not None
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_task(self):
        service = _make_service()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            check_interval_seconds=1,
        )
        await monitor.start()
        await monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self):
        service = _make_service()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            check_interval_seconds=1,
        )
        await monitor.start()
        await monitor.stop()
        # Second stop should not raise
        await monitor.stop()


# ---------------------------------------------------------------------------
# ReconciliationMonitor — alert-only policy
# ---------------------------------------------------------------------------


class TestReconciliationMonitorAlertPolicy:
    """Verify monitor alerts but never auto-closes positions."""

    @pytest.mark.asyncio
    async def test_handle_result_fail_publishes_incident(self):
        service = _make_service()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            check_interval_seconds=1,
        )
        result = _make_result(
            status=ReconciliationStatus.FAIL,
            discrepancies=[
                CountDiscrepancy(
                    category="fills",
                    telemetry_count=100,
                    persisted_count=90,
                    delta=10,
                    delta_pct=11.11,
                )
            ],
            delta_pct={"fills": 11.11},
            telemetry_count={"fills": 100},
            persisted_count={"fills": 90},
            delta_count={"fills": 10},
        )
        with patch(
            "execution.incident_reporter.publish_execution_incident",
            new_callable=AsyncMock,
        ) as mock_publish:
            await monitor._handle_result(result)
            mock_publish.assert_called_once()
            call_kwargs = mock_publish.call_args[1]
            assert call_kwargs["severity"] == "P1"
            assert call_kwargs["incident_type"] == "reconciliation_failure"

    @pytest.mark.asyncio
    async def test_handle_result_ok_does_not_alert(self):
        service = _make_service()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            check_interval_seconds=1,
        )
        result = _make_result(status=ReconciliationStatus.OK)
        with patch(
            "execution.incident_reporter.publish_execution_incident",
            new_callable=AsyncMock,
        ) as mock_publish:
            await monitor._handle_result(result)
            mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_result_warn_logs_warning(self):
        service = _make_service()
        monitor = ReconciliationMonitor(
            reconciliation_service=service,
            check_interval_seconds=1,
        )
        result = _make_result(
            status=ReconciliationStatus.WARN,
            discrepancies=[
                CountDiscrepancy(
                    category="orders",
                    telemetry_count=50,
                    persisted_count=49,
                    delta=1,
                    delta_pct=2.04,
                )
            ],
            delta_pct={"orders": 2.04},
            telemetry_count={"orders": 50},
            persisted_count={"orders": 49},
            delta_count={"orders": 1},
        )
        with patch(
            "execution.incident_reporter.publish_execution_incident",
            new_callable=AsyncMock,
        ) as mock_publish:
            await monitor._handle_result(result)
            # WARN should NOT publish incident (only FAIL does)
            mock_publish.assert_not_called()


# ---------------------------------------------------------------------------
# backfill_missed_fills
# ---------------------------------------------------------------------------


class TestBackfillMissedFills:
    """Verify backfill_missed_fills method exists and returns expected shape."""

    @pytest.mark.asyncio
    async def test_backfill_returns_expected_keys(self):
        service = _make_service()
        result = await service.backfill_missed_fills(
            environment="paper",
            portfolio_id="test",
            lookback_seconds=60,
        )
        assert "fills_found" in result
        assert "fills_backfilled" in result
        assert "errors" in result
        assert "environment" in result
        assert "portfolio_id" in result
        assert result["environment"] == "paper"
        assert result["portfolio_id"] == "test"

    @pytest.mark.asyncio
    async def test_backfill_handles_no_telemetry(self):
        """When telemetry exporter doesn't support query_fills, returns zeros."""
        exporter = MagicMock(spec=[])  # No query_fills attribute
        service = OutcomeReconciliationService(telemetry_exporter=exporter)
        result = await service.backfill_missed_fills()
        assert result["fills_found"] == 0
        assert result["fills_backfilled"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_backfill_detects_missed_fills(self):
        exporter = MagicMock()
        exporter.query_fills = AsyncMock(
            return_value=[
                {"fill_id": "f1", "symbol": "BTC/USDT", "side": "Buy", "qty": 0.001},
                {"fill_id": "f2", "symbol": "ETH/USDT", "side": "Buy", "qty": 0.01},
            ]
        )
        pg = MagicMock()
        pg.execute = AsyncMock(
            return_value=[
                {"id": "f1", "symbol": "BTC/USDT", "side": "Buy", "qty": 0.001},
            ]
        )
        service = OutcomeReconciliationService(
            telemetry_exporter=exporter,
            postgres_client=pg,
        )
        result = await service.backfill_missed_fills()
        assert result["fills_found"] == 2
        assert result["fills_backfilled"] == 1


# ---------------------------------------------------------------------------
# ReconciliationConfig — new alert threshold fields
# ---------------------------------------------------------------------------


class TestReconciliationConfigAlertThresholds:
    """Verify new alert threshold fields exist with correct defaults."""

    def test_default_stale_threshold(self):
        config = ReconciliationConfig()
        assert config.alert_on_stale_threshold_hours == 24.0

    def test_default_discrepancy_alert_threshold(self):
        config = ReconciliationConfig()
        assert config.alert_on_discrepancy_pct == 5.0

    def test_custom_stale_threshold(self):
        config = ReconciliationConfig(alert_on_stale_threshold_hours=48.0)
        assert config.alert_on_stale_threshold_hours == 48.0

    def test_custom_discrepancy_alert_threshold(self):
        config = ReconciliationConfig(alert_on_discrepancy_pct=10.0)
        assert config.alert_on_discrepancy_pct == 10.0
