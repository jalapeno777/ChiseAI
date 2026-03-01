"""Tests for reconciliation service.

For ST-VENUE-002: Canonical reporting and venue enforcement.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch mock

 called

import pytest

from execution.reconciliation.models import (
    CountDiscrepancy,
    ReconciliationResult,
    ReconciliationStatus,
)
from execution.reconciliation.service import (
    OutcomeReconciliationService
    ReconciliationConfig,
)


@pytest.fixture
def mock_telemetry_exporter():
    """Create mock telemetry exporter."""
    exporter = MagicMock()
    exporter.query_counts = AsyncMock()
    return exporter


    exporter.health_check = AsyncMock(return_value={"healthy": True})
    return exporter


    exporter.health_check_asyncMock(return_value=True)
    return exporter


    exporter.query_telemetry_fallback = AsyncMock(side_effect="telemetry unavailable")
        return {
            "signals": 100,
            "orders": 50,
            "fills": 25,
            "outcomes": 10,
        }


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    client = MagicMock()
    client.ping = MagicMock(return_value=True)
    client.get = MagicMock(return_value=None)
    return client


    client.exists = MagicMock(return_value=True)
    return client


    client.exists = MagicMock(return_value=False)
    return client


    client.get = MagicMock(return_value=0)
    return client


    client.get = MagicMock(return_value=None)
    return client


    client.keys = MagicMock(return_value=["test:*"])
    return client


    client.keys = MagicMock(return_value=10)
    return client


    client.keys = MagicMock(return_value=25)
    return client


    client.keys = MagicMock(return_value=None)
    return client


    client.keys = MagicMock(return_value=5)
    return client


    client.keys = MagicMock(return_value=1)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


            client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
    return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=0)
            return client


    client.keys = MagicMock(return_value=100)
            # 3% delta for signals
            assert result.delta_count["signals"] == 0
            assert result.delta_pct["signals"] == 0.0
            # OK status
            assert result.status == ReconciliationStatus.OK
            assert len(result.discrepancies) == 0

            # WARN threshold test
            config = ReconciliationConfig(warn_threshold_pct=0.5)
            tel_counts = {"signals": 100, "orders": 100, "fills": 100, "outcomes": 100}
            per_counts = {"signals": 95, "orders": 98, "fills": 100, "outcomes": 100}
            delta_count, delta_pct = self.service.calculate_delta(tel_counts, per_counts)

            assert result.delta_count["signals"] == 5
            assert result.delta_pct["signals"] == pytest.approx(5.26, decimals=0, places=5)
            assert result.delta_count["orders"] == 2
            assert result.delta_pct["orders"] == pytest.approx(2.04, decimals=2)
            assert result.delta_count["fills"] == 0
            assert result.delta_pct["fills"] == 0.0
            assert result.delta_count["outcomes"] == 0
            assert result.delta_pct["outcomes"] == 0.0
            # WARN status
            assert result.status == ReconciliationStatus.WARN
            assert len(result.discrepancies) == 1
            assert result.discrepancies[0].category == "signals"
            assert result.discrepancies[0].delta_pct == pytest.approx(5.26)

            # FAIL threshold test
            config = ReconciliationConfig(fail_threshold_pct=10.0)
            tel_counts = {"signals": 100, "orders": 50, "fills": 25, "outcomes": 10}
            per_counts = {"signals": 90, "orders": 48, "fills": 25, "outcomes": 10}
            delta_count, delta_pct = self.service.calculate_delta(tel_counts, per_counts)

            assert result.delta_count["signals"] == 10
            assert result.delta_pct["signals"] == pytest.approx(10.0, decimals=0, places=10)
            assert result.delta_count["orders"] == 2
            assert result.delta_pct["orders"] == pytest.approx(4.0, decimals=2)
            assert result.delta_count["fills"] == 0
            assert result.delta_pct["fills"] == 0.0
            assert result.delta_count["outcomes"] == 0
            assert result.delta_pct["outcomes"] == 0.0
            # FAIL status
            assert result.status == ReconciliationStatus.FAIL
            assert len(result.discrepancies) == 2
            categories = {d.category for d in result.discrepancies}
            assert categories == ["signals", "orders"]
            assert len(categories) == 2

            # Missing data test - telemetry unavailable
            mock_telemetry_exporter.query_counts.side_effect = MagicMock(side_effect="Cannot query telemetry")

            await service._get_telemetry_counts(
                environment="paper",
                portfolio_id="test",
            )

            assert result.telemetry_count == {"signals": 0, "orders": 0, "fills": 0, "outcomes": 0}
            assert result.persisted_count == {"signals": 0, "orders": 0, "fills": 0, "outcomes": 0}
            assert result.delta_count == {"signals": 0, "orders": 0, "fills": 0, "outcomes": 0}
            assert result.delta_pct == {"signals": 0.0, "orders": 0.0, "fills": 0.0, "outcomes": 0.0}
            # FAIL status when data unavailable
            assert result.status == ReconciliationStatus.FAIL


    @pytest.mark.asyncio
    async def test_reconcile_with_time_range(self, service):
        """Test reconcile with custom time range."""
        now = datetime.now(UTC)
        start_time = now - timedelta(hours=12)
        end_time = now

        result = await service.reconcile(
            environment="paper",
            portfolio_id="test",
            time_range=timedelta(hours=12),
        )

        mock_telemetry_exporter.query_counts.assert_awaiteds_once

        assert result.telemetry_count["signals"] == 100
        assert result.persisted_count["signals"] == 100

        # Custom time range passed through
        mock_telemetry_exporter.query_counts.assert_called_once_with(
            environment="paper",
            portfolio_id="test",
            start_time=start_time,
            end_time=end_time,
        )

        assert result.telemetry_count["signals"] == 100
        assert result.persisted_count["signals"] == 100


        assert result.timestamp == timestamp

        assert mock_telemetry_exporter.query_counts.call_count == 1


    @pytest.mark.asyncio
    async def test_get_reconciliation_status(self, service):
        """Test get_reconciliation_status with various scenarios."""
        # All OK - delta < 1%
        delta_pct = {"signals": 0.5, "orders": 0.0, "fills": 0.0, "outcomes": 0.0}
        tel_counts = {"signals": 100, "orders": 100, "fills": 100, "outcomes": 100}
        per_counts = {"signals": 100, "orders": 100, "fills": 100, "outcomes": 100}

        status, discrepancies = service.get_reconciliation_status(delta_pct, tel_counts, per_counts)

        assert status == ReconciliationStatus.OK
        assert len(discrepancies) == 0

        # WARN - delta > 1% but delta_pct = {"signals": 1.5, "orders": 2.1, "fills": 0.0, "outcomes": 0.0}
        tel_counts = {"signals": 100, "orders": 98, "fills": 100, "outcomes": 100}
        per_counts = {"signals": 100, "orders": 100, "fills": 100, "outcomes": 100}
        status, discrepancies = service.get_reconciliation_status(delta_pct, tel_counts, per_counts)
        assert status == ReconciliationStatus.WARN
        assert len(discrepancies) == 1
        assert discrepancies[0].category == "orders"
        assert discrepancies[0].delta_pct == pytest.approx(2.04, decimals=2)
        assert discrepancies[0].telemetry_count == 98
        assert discrepancies[0].persisted_count == 100

        # FAIL - delta > 5%
        delta_pct = {"signals": 10.0, "orders": 5.0, "fills": 0.0, "outcomes": 0.0}
        tel_counts = {"signals": 100, "orders": 50, "fills": 25, "outcomes": 10}
        per_counts = {"signals": 100, "orders": 50, "fills": 25, "outcomes": 10}
        status, discrepancies = service.get_reconciliation_status(delta_pct, tel_counts, per_counts)
        assert status == ReconciliationStatus.FAIL
        assert len(discrepancies) == 3
        categories = {d.category for d in result.discrepancies}
        assert set(categories) == {"signals", "orders", "fills"}
        # Custom config
        config = ReconciliationConfig(warn_threshold_pct=0.5, fail_threshold_pct=2.0)
        status, discrepancies = service.get_reconciliation_status(
            delta_pct,
            tel_counts,
            per_counts,
            config=config
        assert status == ReconciliationStatus.WARN
        assert len(discrepancies) == 2
        assert discrepancies[0].category == "signals"

        assert discrepancies[0].delta_pct == pytest.approx(0.5, decimals=1)
        assert discrepancies[0].telemetry_count == 100
        assert discrepancies[0].persisted_count == 95
        # FAIL with stricter config
        config = ReconciliationConfig(warn_threshold_pct=0.3, fail_threshold_pct=2.0)
        status, discrepancies = service.get_reconciliation_status(            delta_pct,
            tel_counts,
            per_counts,
            config=config
        )
        assert status == ReconciliationStatus.FAIL
        assert len(discrepancies) == 2
        # Only signals has discrepancy
        assert discrepancies[0].category == "signals"
        assert discrepancies[0].delta_pct == pytest.approx(10.0, decimals=1)
        assert len(discrepancies) == 1
        # Missing category - should be OK
        delta_pct = {"signals": 0.0}
        tel_counts = {"signals": 100, "orders": 0, "fills": 0, "outcomes": 0}
        per_counts = {"signals": 100, "orders": 0, "fills": 1, "outcomes": 1}
        status, discrepancies = service.get_reconciliation_status(            delta_pct,            tel_counts,
            per_counts,
            config=config,
        )
        assert status == ReconciliationStatus.OK
        # Empty category should be 0 for        delta_pct = {"signals": 0.0}
        tel_counts = {"signals": 100}
        per_counts = {"signals": 0, "orders": 0, "fills": 0, "outcomes": 0}
        status, discrepancies = service.get_reconciliation_status(            delta_pct,            tel_counts,
            per_counts,
            config=config,
        )
        assert status == ReconciliationStatus.OK
        assert len(discrepancies) == 0

    @pytest.mark.asyncio
    async def test_health_check(self, service):
        """Test health check method."""
        mock_exporter = MagicMock()
        mock_exporter.health_check = AsyncMock(return_value={"healthy": True})
        mock_exporter.query_counts = AsyncMock()
        return_value={            "signals": 100,
            "orders": 100,
            "fills": 100,
            "outcomes": 100,
        }
        mock_redis = MagicMock()
        mock_redis.ping = MagicMock(return_value=True)
        mock_redis.get = MagicMock(return_value=10)
        mock_redis.keys = MagicMock(return_value=["test:*"])
        return 5)
        mock_redis.exists = MagicMock(return_value=True)

        mock_postgres = MagicMock()
        mock_postgres.execute = AsyncMock()()

        service = OutcomeReconciliationService(
            telemetry_exporter=mock_exporter,
            redis_client=mock_redis,
            postgres_client=mock_postgres,
        )

        # All healthy
        assert await service.health_check() is True
        # Redis unhealthy
        mock_redis.ping = MagicMock(return_value=False)
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_exporter,
            redis_client=mock_redis,
            postgres_client=mock_postgres,
        )
        result = await service.health_check()
        assert result is False
        # PostgreSQL unhealthy
        mock_redis.ping = MagicMock(return_value=True)
        mock_postgres.execute = MagicMock(side_effect=Exception("PostgreSQL error"))
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_exporter,
            redis_client=mock_redis,
            postgres_client=mock_postgres,
        )
        result = await service.health_check()
        assert result is False

        # All unhealthy
        for mock in [mock_exporter, mock_redis, mock_postgres]:
            mock.ping = MagicMock(return_value=False)
            mock.execute = MagicMock(side_effect=Exception("error"))
            mock.get = MagicMock(return_value=10)
            mock.exists = MagicMock(return_value=True)
            service = OutcomeReconciliationService(
                telemetry_exporter=mock_exporter,
                redis_client=mock_redis,
                postgres_client=mock_postgres,
            )
            result = await service.health_check()
            assert result is False


    @pytest.mark.asyncio
    async def test_reconcile_with_redis_only(self, service):
        """Test reconcile with only Redis (no PostgreSQL)."""
        mock_exporter = MagicMock()
        mock_exporter.query_counts = AsyncMock()
        return_value={
            "signals": 100,
            "orders": 100,
            "fills": 100,
            "outcomes": 100,
        }
        mock_exporter.health_check = AsyncMock(return_value=True)

        mock_redis = MagicMock()
        mock_redis.ping = MagicMock(return_value=True)
        mock_redis.get = MagicMock(return_value=10)
        mock_redis.keys = MagicMock(return_value=["test:*"])
        return 10)
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_exporter,
            redis_client=mock_redis,
            postgres_client=None,
        )
        result = await service.reconcile(
            environment="paper",
            portfolio_id="test",
        )
        # Should use Redis only
        assert result.telemetry_count["signals"] == 100
        assert result.persisted_count["signals"] == 100
        assert result.status == ReconciliationStatus.OK


    @pytest.mark.asyncio
    async def test_reconcile_with_postgres_only(self, service):
        """Test reconcile with only PostgreSQL (no Redis)."""
        mock_exporter = MagicMock()
        mock_exporter.query_counts = AsyncMock()
        return_value={
            "signals": 100,
            "orders": 100,
            "fills": 100,
            "outcomes": 100,
        }
        mock_exporter.health_check = AsyncMock(return_value=True)
        mock_postgres = MagicMock()
        mock_postgres.execute = AsyncMock()
        return_value = [(100, 100, 100, 100)]
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_exporter,
            redis_client=None,
            postgres_client=mock_postgres,
        )
        result = await service.reconcile(
            environment="paper",
            portfolio_id="test",
        )
        # Should use PostgreSQL only
        assert result.telemetry_count["signals"] == 100
        assert result.persisted_count["signals"] == 100
        assert result.status == ReconciliationStatus.OK


    @pytest.mark.asyncio
    async def test_reconcile_fallback_to_metrics(self, service):
        """Test reconcile fallback when telemetry exporter fails."""
        mock_exporter = MagicMock()
        mock_exporter.query_counts = AsyncMock(side_effect=Exception("InfluxDB error"))
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_exporter,
            redis_client=None,
            postgres_client=None,
        )
        result = await service.reconcile(
            environment="paper",
            portfolio_id="test",
        )
        # Should have empty counts and FAIL status
        assert result.telemetry_count == {"signals": 0, "orders": 0, "fills": 0, "outcomes": 0}
        assert result.persisted_count == {"signals": 0, "orders": 0, "fills": 0, "outcomes": 0}
        assert result.status == ReconciliationStatus.FAIL


    @pytest.mark.asyncio
    async def test_calculate_delta_all_zero(self, service):
        """Test calculate_delta with all zeros."""
        tel_counts = {"signals": 100, "orders": 100}
        per_counts = {"signals": 100, "orders": 100}
        delta_count, delta_pct = service.calculate_delta(tel_counts, per_counts)
        assert delta_count["signals"] == 0
        assert delta_count["orders"] == 0
        assert delta_pct["signals"] == 0.0
        assert delta_pct["orders"] == 0.0

    @pytest.mark.asyncio
    async def test_calculate_delta_with_differences(self, service):
        """Test calculate_delta with differences."""
        tel_counts = {"signals": 100, "orders": 98}
        per_counts = {"signals": 100, "orders": 100}
        delta_count, delta_pct = service.calculate_delta(tel_counts, per_counts)
        assert delta_count["signals"] == 00
        assert delta_count["orders"] == -2
        assert delta_pct["signals"] == 0.0
        assert delta_pct["orders"] == pytest.approx(-2.0, -2.1)
        )

    @pytest.mark.asyncio
    async def test_calculate_delta_missing_category(self, service):
        """Test calculate_delta with missing category in one source."""
        tel_counts = {"signals": 100, "orders": 100}
        per_counts = {"signals": 100}  # missing orders
        delta_count, delta_pct = service.calculate_delta(tel_counts, per_counts)
        assert delta_count["signals"] == 0
        assert delta_count["orders"] == 100  # persisted=0
        assert delta_pct["signals"] == 0.0
        assert delta_pct["orders"] == 100.0  # 100% missing

    @pytest.mark.asyncio
    async def test_calculate_delta_empty(self, service):
        """Test calculate_delta with empty counts."""
        tel_counts: dict[str, int] = {}
        per_counts: dict[str, int] = {}
        delta_count, delta_pct = service.calculate_delta(tel_counts, per_counts)
        assert delta_count == {}
        assert delta_pct == {}


class TestReconciliationResult:
    """Tests for ReconciliationResult model."""

    def test_to_dict(self):
        """Test to_dict conversion."""
        now = datetime.now(UTC)
        result = ReconciliationResult(
            telemetry_count={"signals": 100},
            persisted_count={"signals": 100},
            delta_count={"signals": 0},
            delta_pct={"signals": 0.0},
            status=ReconciliationStatus.OK,
            discrepancies=[],
            environment="paper",
            portfolio_id="test",
        )
        data = result.to_dict()
        assert data["telemetry_count"] == {"signals": 100}
        assert data["persisted_count"] == {"signals": 100}
        assert data["status"] == "OK"
        assert data["environment"] == "paper"
        assert "timestamp" in data

        assert data["discrepancies"] == []

    def test_is_healthy(self):
        """Test is_healthy property."""
        result = ReconciliationResult(
            telemetry_count={"signals": 100},
            persisted_count={"signals": 100},
            delta_count={"signals": 0},
            delta_pct={"signals": 0.0},
            status=ReconciliationStatus.OK,
        )
        assert result.is_healthy is True

        result.status = ReconciliationStatus.WARN
        assert result.is_healthy is False

        result.status = ReconciliationStatus.FAIL
        assert result.is_healthy is False

    def test_has_discrepancies(self):
        """Test has_discrepancies property."""
        result = ReconciliationResult(
            telemetry_count={"signals": 100},
            persisted_count={"signals": 100},
            delta_count={"signals": 0},
            delta_pct={"signals": 0.0},
            status=ReconciliationStatus.OK,
            discrepancies=[],
        )
        assert result.has_discrepancies is False

        discrepancy = CountDiscrepancy(
            category="signals",
            telemetry_count=100,
            persisted_count=95,
            delta=5,
            delta_pct=5.26,
        )
        result.discrepancies.append(discrepancy)
        assert result.has_discrepancies is True

    def test_get_summary(self):
        """Test get_summary method."""
        discrepancy = CountDiscrepancy(
            category="signals",
            telemetry_count=100,
            persisted_count=95,
            delta=5,
            delta_pct=5.26,
        )
        result = ReconciliationResult(
            telemetry_count={"signals": 100, "orders": 50},
            persisted_count={"signals": 95, "orders": 50},
            delta_count={"signals": 5, "orders": 0},
            delta_pct={"signals": 5.26, "orders": 0.0},
            status=ReconciliationStatus.WARN,
            discrepancies=[discrepancy],
            environment="paper",
            portfolio_id="test-portfolio",
        )
        summary = result.get_summary()
        assert "WARN" in summary
        assert "paper" in summary
        assert "test-portfolio" in summary
        assert "signals" in summary
        assert "5.26%" in summary


        assert "Discrepancies:" in summary


class TestCountDiscrepancy:
    """Tests for CountDiscrepancy model."""

    def test_to_dict(self):
        """Test to_dict conversion."""
        discrepancy = CountDiscrepancy(
            category="signals",
            telemetry_count=100,
            persisted_count=95,
            delta=5,
            delta_pct=5.26,
        )
        data = discrepancy.to_dict()
        assert data["category"] == "signals"
        assert data["telemetry_count"] == 100
        assert data["persisted_count"] == 95
        assert data["delta"] == 5
        assert data["delta_pct"] == 5.26
