"""Tests for reconciliation service.

For ST-VENUE-002: Canonical reporting and venue enforcement.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.reconciliation.models import (
    CountDiscrepancy,
    ReconciliationResult,
    ReconciliationStatus,
)
from execution.reconciliation.service import (
    OutcomeReconciliationService,
    ReconciliationConfig,
)


@pytest.fixture
def mock_telemetry_exporter():
    """Create mock telemetry exporter."""
    exporter = MagicMock()
    exporter.query_counts = AsyncMock(
        return_value={
            "signals": 100,
            "orders": 50,
            "fills": 25,
            "outcomes": 10,
        }
    )
    exporter.health_check = AsyncMock(return_value={"healthy": True})
    return exporter


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    client = MagicMock()
    client.ping = MagicMock(return_value=True)
    client.get = MagicMock(return_value="10")
    client.keys = MagicMock(return_value=["test:*"])
    return client


@pytest.fixture
def mock_postgres_client():
    """Create mock PostgreSQL client."""
    client = MagicMock()
    client.fetchval = AsyncMock(return_value=10)
    return client


class TestReconciliationConfig:
    """Test ReconciliationConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ReconciliationConfig()
        assert config.warn_threshold_pct == 1.0
        assert config.fail_threshold_pct == 5.0
        assert config.categories == ["signals", "orders", "fills", "outcomes"]

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ReconciliationConfig(
            warn_threshold_pct=2.0,
            fail_threshold_pct=10.0,
            categories=["signals", "orders"],
        )
        assert config.warn_threshold_pct == 2.0
        assert config.fail_threshold_pct == 10.0
        assert config.categories == ["signals", "orders"]


class TestReconciliationResult:
    """Test ReconciliationResult model."""

    def test_result_creation(self):
        """Test creating a reconciliation result."""
        result = ReconciliationResult(
            telemetry_count={"signals": 100},
            persisted_count={"signals": 100},
            delta_count={"signals": 0},
            delta_pct={"signals": 0.0},
            status=ReconciliationStatus.OK,
        )
        assert result.status == ReconciliationStatus.OK
        assert len(result.discrepancies) == 0

    def test_result_with_discrepancies(self):
        """Test result with discrepancies."""
        discrepancy = CountDiscrepancy(
            category="signals",
            telemetry_count=100,
            persisted_count=95,
            delta=5,
            delta_pct=5.0,
        )
        result = ReconciliationResult(
            telemetry_count={"signals": 100},
            persisted_count={"signals": 95},
            delta_count={"signals": 5},
            delta_pct={"signals": 5.0},
            status=ReconciliationStatus.WARN,
            discrepancies=[discrepancy],
        )
        assert result.status == ReconciliationStatus.WARN
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].category == "signals"


class TestOutcomeReconciliationService:
    """Test OutcomeReconciliationService."""

    @pytest.mark.asyncio
    async def test_service_initialization(
        self, mock_telemetry_exporter, mock_redis_client
    ):
        """Test service can be initialized."""
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_telemetry_exporter,
            redis_client=mock_redis_client,
            postgres_client=None,
        )
        assert service is not None
        assert service.telemetry_exporter == mock_telemetry_exporter

    @pytest.mark.asyncio
    async def test_reconcile_basic(self, mock_telemetry_exporter, mock_redis_client):
        """Test basic reconcile operation."""
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_telemetry_exporter,
            redis_client=mock_redis_client,
            postgres_client=None,
        )
        result = await service.reconcile(
            environment="paper",
            portfolio_id="test",
        )
        assert result is not None
        assert isinstance(result, ReconciliationResult)

    @pytest.mark.asyncio
    async def test_reconcile_with_postgres(
        self, mock_telemetry_exporter, mock_redis_client, mock_postgres_client
    ):
        """Test reconcile with PostgreSQL backend."""
        service = OutcomeReconciliationService(
            telemetry_exporter=mock_telemetry_exporter,
            redis_client=mock_redis_client,
            postgres_client=mock_postgres_client,
        )
        result = await service.reconcile(
            environment="paper",
            portfolio_id="test",
        )
        assert result is not None
        assert isinstance(result, ReconciliationResult)


class TestReconciliationStatus:
    """Test ReconciliationStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert ReconciliationStatus.OK.value == "OK"
        assert ReconciliationStatus.WARN.value == "WARN"
        assert ReconciliationStatus.FAIL.value == "FAIL"


class TestCountDiscrepancy:
    """Test CountDiscrepancy model."""

    def test_discrepancy_creation(self):
        """Test creating a count discrepancy."""
        discrepancy = CountDiscrepancy(
            category="orders",
            telemetry_count=100,
            persisted_count=90,
            delta=10,
            delta_pct=10.0,
        )
        assert discrepancy.category == "orders"
        assert discrepancy.telemetry_count == 100
        assert discrepancy.persisted_count == 90
        assert discrepancy.delta == 10
        assert discrepancy.delta_pct == 10.0

    def test_discrepancy_to_dict(self):
        """Test converting discrepancy to dict."""
        discrepancy = CountDiscrepancy(
            category="orders",
            telemetry_count=100,
            persisted_count=90,
            delta=10,
            delta_pct=10.0,
        )
        d = discrepancy.to_dict()
        assert d["category"] == "orders"
        assert d["telemetry_count"] == 100
        assert d["persisted_count"] == 90
        assert d["delta"] == 10
        assert d["delta_pct"] == 10.0


class TestImportVerification:
    """Test that all imports work correctly."""

    def test_import_outcome_reconciliation_service(self):
        """Test OutcomeReconciliationService can be imported."""
        from execution.reconciliation import OutcomeReconciliationService

        assert OutcomeReconciliationService is not None

    def test_import_reconciliation_config(self):
        """Test ReconciliationConfig can be imported."""
        from execution.reconciliation import ReconciliationConfig

        assert ReconciliationConfig is not None

    def test_import_reconciliation_result(self):
        """Test ReconciliationResult can be imported."""
        from execution.reconciliation import ReconciliationResult

        assert ReconciliationResult is not None

    def test_import_reconciliation_status(self):
        """Test ReconciliationStatus can be imported."""
        from execution.reconciliation import ReconciliationStatus

        assert ReconciliationStatus is not None

    def test_import_count_discrepancy(self):
        """Test CountDiscrepancy can be imported."""
        from execution.reconciliation import CountDiscrepancy

        assert CountDiscrepancy is not None
