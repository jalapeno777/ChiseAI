"""Tests for canary storage."""

from execution.canary.models import CanaryStatus, create_canary_deployment
from execution.canary.monitor import MonitoringCheck
from execution.canary.storage import (
    CanaryRecord,
    InMemoryCanaryStorage,
    create_canary_storage,
)


class TestCanaryRecord:
    """Test CanaryRecord class."""

    def test_from_deployment(self):
        """Test creating record from deployment."""
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)

        record = CanaryRecord.from_deployment(canary)
        assert record.canary_id == "test-001"
        assert record.strategy_id == "strategy-v2"
        assert record.champion_strategy_id == "strategy-v1"
        assert record.status == "running"
        assert record.allocation_pct == 10.0

    def test_to_dict(self):
        """Test serialization to dict."""
        record = CanaryRecord(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
            status="running",
            allocation_pct=10.0,
            start_time=1609459200,
            end_time=1610064000,
            metrics={"start_equity": 10000.0},
        )

        data = record.to_dict()
        assert data["canary_id"] == "test-001"
        assert data["strategy_id"] == "strategy-v2"
        assert data["status"] == "running"
        assert data["metrics"]["start_equity"] == 10000.0


class TestInMemoryCanaryStorage:
    """Test InMemoryCanaryStorage class."""

    def test_save_and_get_deployment(self):
        """Test saving and retrieving a deployment."""
        storage = InMemoryCanaryStorage()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)

        storage.save_deployment(canary)
        record = storage.get_deployment("test-001")

        assert record is not None
        assert record.canary_id == "test-001"
        assert record.strategy_id == "strategy-v2"

    def test_get_nonexistent_deployment(self):
        """Test retrieving a non-existent deployment."""
        storage = InMemoryCanaryStorage()
        record = storage.get_deployment("nonexistent")
        assert record is None

    def test_list_deployments(self):
        """Test listing all deployments."""
        storage = InMemoryCanaryStorage()

        for i in range(3):
            canary = create_canary_deployment(
                canary_id=f"test-{i:03d}",
                strategy_id=f"strategy-v{i}",
            )
            canary.start(initial_equity=10000.0)
            storage.save_deployment(canary)

        records = storage.list_deployments()
        assert len(records) == 3

    def test_list_deployments_with_strategy_filter(self):
        """Test listing deployments with strategy filter."""
        storage = InMemoryCanaryStorage()

        canary1 = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-a",
        )
        canary1.start(initial_equity=10000.0)
        storage.save_deployment(canary1)

        canary2 = create_canary_deployment(
            canary_id="test-002",
            strategy_id="strategy-b",
        )
        canary2.start(initial_equity=10000.0)
        storage.save_deployment(canary2)

        records = storage.list_deployments(strategy_id="strategy-a")
        assert len(records) == 1
        assert records[0].strategy_id == "strategy-a"

    def test_list_deployments_with_status_filter(self):
        """Test listing deployments with status filter."""
        storage = InMemoryCanaryStorage()

        canary1 = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v1",
        )
        canary1.start(initial_equity=10000.0)
        storage.save_deployment(canary1)

        canary2 = create_canary_deployment(
            canary_id="test-002",
            strategy_id="strategy-v2",
        )
        canary2.start(initial_equity=10000.0)
        canary2.status = CanaryStatus.PASSED
        storage.save_deployment(canary2)

        records = storage.list_deployments(status=CanaryStatus.PASSED)
        assert len(records) == 1
        assert records[0].status == "passed"

    def test_list_deployments_with_limit(self):
        """Test listing deployments with limit."""
        storage = InMemoryCanaryStorage()

        for i in range(10):
            canary = create_canary_deployment(
                canary_id=f"test-{i:03d}",
                strategy_id=f"strategy-v{i}",
            )
            canary.start(initial_equity=10000.0)
            storage.save_deployment(canary)

        records = storage.list_deployments(limit=5)
        assert len(records) == 5

    def test_save_monitoring_check(self):
        """Test saving a monitoring check."""
        storage = InMemoryCanaryStorage()
        check = MonitoringCheck(
            canary_id="test-001",
            timestamp=1609459200,
            gate_checks=[],
            status=CanaryStatus.RUNNING,
            action_taken="continue",
            message="Check passed",
        )

        storage.save_monitoring_check(check)
        history = storage.get_monitoring_history("test-001")

        assert len(history) == 1
        assert history[0].canary_id == "test-001"

    def test_get_monitoring_history_with_limit(self):
        """Test getting monitoring history with limit."""
        storage = InMemoryCanaryStorage()

        for i in range(10):
            check = MonitoringCheck(
                canary_id="test-001",
                timestamp=1609459200 + i * 3600,
                gate_checks=[],
                status=CanaryStatus.RUNNING,
                action_taken="continue",
                message=f"Check {i}",
            )
            storage.save_monitoring_check(check)

        history = storage.get_monitoring_history("test-001", limit=5)
        assert len(history) == 5

    def test_get_monitoring_history_sorted(self):
        """Test that monitoring history is sorted by timestamp descending."""
        storage = InMemoryCanaryStorage()

        for i in range(5):
            check = MonitoringCheck(
                canary_id="test-001",
                timestamp=1609459200 + i * 3600,
                gate_checks=[],
                status=CanaryStatus.RUNNING,
                action_taken="continue",
                message=f"Check {i}",
            )
            storage.save_monitoring_check(check)

        history = storage.get_monitoring_history("test-001")
        # Should be sorted descending
        for i in range(len(history) - 1):
            assert history[i].timestamp >= history[i + 1].timestamp

    def test_clear(self):
        """Test clearing all stored data."""
        storage = InMemoryCanaryStorage()

        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)
        storage.save_deployment(canary)

        check = MonitoringCheck(
            canary_id="test-001",
            timestamp=1609459200,
            gate_checks=[],
            status=CanaryStatus.RUNNING,
            action_taken="continue",
            message="Check",
        )
        storage.save_monitoring_check(check)

        assert len(storage._deployments) == 1
        assert len(storage._monitoring_checks) == 1

        storage.clear()

        assert len(storage._deployments) == 0
        assert len(storage._monitoring_checks) == 0


class TestCreateCanaryStorage:
    """Test create_canary_storage factory function."""

    def test_create_without_influxdb(self):
        """Test creating storage without InfluxDB."""
        storage = create_canary_storage()
        assert isinstance(storage, InMemoryCanaryStorage)

    def test_create_with_influxdb(self):
        """Test creating storage with InfluxDB client."""
        # Mock InfluxDB client
        mock_client = object()
        storage = create_canary_storage(influxdb_client=mock_client)
        # Should create storage with persistence capability
        assert storage is not None
