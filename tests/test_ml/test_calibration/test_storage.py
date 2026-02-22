"""Unit tests for calibration data storage backends."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, "src")

from ml.calibration.models import CalibrationConfig, CalibrationRecord, SignalType
from ml.calibration.storage import (
    InMemoryCalibrationStorage,
    RedisCalibrationStorage,
)


class TestInMemoryCalibrationStorage:
    """Tests for InMemoryCalibrationStorage."""

    @pytest.fixture
    def storage(self):
        """Create a fresh in-memory storage for each test."""
        return InMemoryCalibrationStorage()

    @pytest.fixture
    def sample_record(self):
        """Create a sample calibration record."""
        return CalibrationRecord(
            timestamp=datetime.now(UTC),
            signal_id="test-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type=SignalType.LONG,
            confidence_bin=7,
        )

    @pytest.mark.asyncio
    async def test_store_single_record(self, storage, sample_record):
        """Test storing a single record."""
        success = await storage.store(sample_record)
        assert success is True

        records = storage.get_all_records()
        assert len(records) == 1
        assert records[0].signal_id == "test-sig-001"

    @pytest.mark.asyncio
    async def test_store_multiple_records(self, storage):
        """Test storing multiple records."""
        records = [
            CalibrationRecord(
                timestamp=datetime.now(UTC) - timedelta(hours=i),
                signal_id=f"test-sig-{i:03d}",
                predicted_prob=0.5 + i * 0.05,
                actual_outcome=i % 2,
                signal_type=SignalType.LONG if i % 2 == 0 else SignalType.SHORT,
                confidence_bin=5 + i,
            )
            for i in range(5)
        ]

        for record in records:
            await storage.store(record)

        all_records = storage.get_all_records()
        assert len(all_records) == 5

    @pytest.mark.asyncio
    async def test_store_batch(self, storage):
        """Test batch storage."""
        records = [
            CalibrationRecord(
                timestamp=datetime.now(UTC) - timedelta(hours=i),
                signal_id=f"batch-sig-{i:03d}",
                predicted_prob=0.6,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=6,
            )
            for i in range(10)
        ]

        stored_count = await storage.store_batch(records)
        assert stored_count == 10

        all_records = storage.get_all_records()
        assert len(all_records) == 10

    @pytest.mark.asyncio
    async def test_get_records_by_time_range(self, storage):
        """Test retrieving records by time range."""
        now = datetime.now(UTC)

        # Create records at different times
        records = [
            CalibrationRecord(
                timestamp=now - timedelta(hours=2),
                signal_id="old-sig-001",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            ),
            CalibrationRecord(
                timestamp=now - timedelta(minutes=30),
                signal_id="recent-sig-001",
                predicted_prob=0.8,
                actual_outcome=0,
                signal_type=SignalType.SHORT,
                confidence_bin=8,
            ),
            CalibrationRecord(
                timestamp=now - timedelta(minutes=5),
                signal_id="very-recent-sig-001",
                predicted_prob=0.9,
                actual_outcome=1,
                signal_type=SignalType.SCALP,
                confidence_bin=9,
            ),
        ]

        for record in records:
            await storage.store(record)

        # Query last hour
        start_time = now - timedelta(hours=1)
        end_time = now
        results = await storage.get_records(start_time, end_time)

        assert len(results) == 2
        assert all(r.signal_id != "old-sig-001" for r in results)

    @pytest.mark.asyncio
    async def test_get_records_by_signal_type(self, storage):
        """Test retrieving records filtered by signal type."""
        now = datetime.now(UTC)

        records = [
            CalibrationRecord(
                timestamp=now,
                signal_id="long-sig-001",
                predicted_prob=0.75,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            ),
            CalibrationRecord(
                timestamp=now,
                signal_id="short-sig-001",
                predicted_prob=0.65,
                actual_outcome=0,
                signal_type=SignalType.SHORT,
                confidence_bin=6,
            ),
            CalibrationRecord(
                timestamp=now,
                signal_id="long-sig-002",
                predicted_prob=0.85,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=8,
            ),
        ]

        for record in records:
            await storage.store(record)

        # Query only LONG signals
        results = await storage.get_records(
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            signal_type=SignalType.LONG,
        )

        assert len(results) == 2
        assert all(r.signal_type == SignalType.LONG for r in results)

    @pytest.mark.asyncio
    async def test_get_records_limit(self, storage):
        """Test record retrieval with limit."""
        now = datetime.now(UTC)

        # Create 20 records
        records = [
            CalibrationRecord(
                timestamp=now - timedelta(minutes=i),
                signal_id=f"sig-{i:03d}",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            )
            for i in range(20)
        ]

        await storage.store_batch(records)

        # Query with limit
        results = await storage.get_records(
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            limit=5,
        )

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_delete_old_records(self, storage):
        """Test deleting old records."""
        now = datetime.now(UTC)

        records = [
            CalibrationRecord(
                timestamp=now - timedelta(days=10),
                signal_id="old-sig-001",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            ),
            CalibrationRecord(
                timestamp=now - timedelta(days=5),
                signal_id="medium-sig-001",
                predicted_prob=0.8,
                actual_outcome=0,
                signal_type=SignalType.SHORT,
                confidence_bin=8,
            ),
            CalibrationRecord(
                timestamp=now - timedelta(hours=1),
                signal_id="recent-sig-001",
                predicted_prob=0.9,
                actual_outcome=1,
                signal_type=SignalType.SCALP,
                confidence_bin=9,
            ),
        ]

        for record in records:
            await storage.store(record)

        assert len(storage.get_all_records()) == 3

        # Delete records older than 7 days
        deleted = await storage.delete_old_records(now - timedelta(days=7))
        assert deleted == 1

        remaining = storage.get_all_records()
        assert len(remaining) == 2
        assert all(r.signal_id != "old-sig-001" for r in remaining)

    @pytest.mark.asyncio
    async def test_get_record_count(self, storage):
        """Test getting record count."""
        now = datetime.now(UTC)

        records = [
            CalibrationRecord(
                timestamp=now - timedelta(hours=i),
                signal_id=f"sig-{i:03d}",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            )
            for i in range(10)
        ]

        await storage.store_batch(records)

        # Total count
        total = await storage.get_record_count()
        assert total == 10

        # Count with time filter (records from hours 0-5 ago, inclusive)
        count = await storage.get_record_count(
            start_time=now - timedelta(hours=5),
            end_time=now,
        )
        # Should include records at hours 0, 1, 2, 3, 4, 5 = 6 records
        assert count == 6

    @pytest.mark.asyncio
    async def test_close_storage(self, storage, sample_record):
        """Test closing storage clears records."""
        await storage.store(sample_record)
        assert len(storage.get_all_records()) == 1

        await storage.close()
        assert len(storage.get_all_records()) == 0

    @pytest.mark.asyncio
    async def test_store_after_close(self, storage, sample_record):
        """Test storing after close fails gracefully."""
        await storage.close()

        success = await storage.store(sample_record)
        assert success is False

    @pytest.mark.asyncio
    async def test_clear_storage(self, storage):
        """Test clearing storage."""
        now = datetime.now(UTC)

        records = [
            CalibrationRecord(
                timestamp=now,
                signal_id=f"sig-{i:03d}",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            )
            for i in range(5)
        ]

        await storage.store_batch(records)
        assert len(storage.get_all_records()) == 5

        storage.clear()
        assert len(storage.get_all_records()) == 0


class TestRedisCalibrationStorage:
    """Tests for RedisCalibrationStorage (requires Redis)."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CalibrationConfig(
            redis_host="host.docker.internal",
            redis_port=6380,
            redis_db=15,  # Use separate DB for tests
            retention_days=1,
        )

    @pytest.fixture
    async def storage(self, config):
        """Create Redis storage and clean up after test."""
        try:
            storage = RedisCalibrationStorage(config)
            yield storage
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
        finally:
            # Clean up
            try:
                await storage.close()
            except:
                pass

    @pytest.fixture
    def sample_record(self):
        """Create a sample calibration record."""
        return CalibrationRecord(
            timestamp=datetime.now(UTC),
            signal_id="test-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type=SignalType.LONG,
            confidence_bin=7,
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_redis_store_and_retrieve(self, storage, sample_record):
        """Test storing and retrieving from Redis."""
        # Store
        success = await storage.store(sample_record)
        assert success is True

        # Retrieve
        now = datetime.now(UTC)
        records = await storage.get_records(
            now - timedelta(hours=1),
            now + timedelta(hours=1),
        )

        assert len(records) >= 1
        assert any(r.signal_id == "test-sig-001" for r in records)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_redis_store_batch(self, storage):
        """Test batch storage in Redis."""
        now = datetime.now(UTC)

        records = [
            CalibrationRecord(
                timestamp=now,
                signal_id=f"batch-sig-{i:03d}",
                predicted_prob=0.6 + i * 0.03,
                actual_outcome=i % 2,
                signal_type=SignalType.LONG,
                confidence_bin=6 + i,
            )
            for i in range(5)
        ]

        stored_count = await storage.store_batch(records)
        assert stored_count == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_redis_get_by_signal_type(self, storage):
        """Test filtering by signal type in Redis."""
        now = datetime.now(UTC)

        records = [
            CalibrationRecord(
                timestamp=now,
                signal_id="long-sig-001",
                predicted_prob=0.75,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            ),
            CalibrationRecord(
                timestamp=now,
                signal_id="short-sig-001",
                predicted_prob=0.65,
                actual_outcome=0,
                signal_type=SignalType.SHORT,
                confidence_bin=6,
            ),
        ]

        await storage.store_batch(records)

        # Query only LONG signals
        results = await storage.get_records_by_signal_type(
            SignalType.LONG,
            now - timedelta(hours=1),
            now + timedelta(hours=1),
        )

        assert len(results) >= 1
        assert all(r.signal_type == SignalType.LONG for r in results)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_redis_record_count(self, storage):
        """Test getting record count from Redis."""
        now = datetime.now(UTC)

        # Get initial count
        initial_count = await storage.get_record_count()

        # Add records
        records = [
            CalibrationRecord(
                timestamp=now,
                signal_id=f"count-sig-{i:03d}",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            )
            for i in range(3)
        ]

        await storage.store_batch(records)

        # Get new count
        new_count = await storage.get_record_count()
        assert new_count >= initial_count + 3
