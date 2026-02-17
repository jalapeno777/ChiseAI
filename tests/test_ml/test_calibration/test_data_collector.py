"""Unit tests for calibration data collector."""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta

import sys

sys.path.insert(0, "src")

from ml.calibration.data_collector import CalibrationDataCollector, CollectionResult
from ml.calibration.models import (
    CalibrationConfig,
    CalibrationRecord,
    CollectionWindow,
    SignalType,
)
from ml.calibration.storage import InMemoryCalibrationStorage


class TestCalibrationDataCollector:
    """Tests for CalibrationDataCollector."""

    @pytest.fixture
    def storage(self):
        """Create a fresh in-memory storage."""
        return InMemoryCalibrationStorage()

    @pytest.fixture
    def collector(self, storage):
        """Create a collector with in-memory storage."""
        config = CalibrationConfig()
        return CalibrationDataCollector(config=config, storage=storage)

    def test_collect_valid_record(self, collector):
        """Test collecting a valid calibration record."""
        result = collector.collect(
            signal_id="test-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )

        assert isinstance(result, CollectionResult)
        assert result.success is True
        assert result.record is not None
        assert result.record.signal_id == "test-sig-001"
        assert result.record.predicted_prob == 0.75
        assert result.record.actual_outcome == 1
        assert result.record.signal_type == SignalType.LONG
        assert result.record.confidence_bin == 7  # 0.75 falls in bin 7

    def test_collect_with_string_signal_type(self, collector):
        """Test collecting with string signal type."""
        result = collector.collect(
            signal_id="test-sig-002",
            predicted_prob=0.65,
            actual_outcome=0,
            signal_type="SHORT",
        )

        assert result.success is True
        assert result.record.signal_type == SignalType.SHORT

    def test_collect_with_enum_signal_type(self, collector):
        """Test collecting with enum signal type."""
        result = collector.collect(
            signal_id="test-sig-003",
            predicted_prob=0.85,
            actual_outcome=1,
            signal_type=SignalType.SCALP,
        )

        assert result.success is True
        assert result.record.signal_type == SignalType.SCALP

    def test_collect_with_metadata(self, collector):
        """Test collecting with metadata."""
        result = collector.collect(
            signal_id="test-sig-004",
            predicted_prob=0.70,
            actual_outcome=1,
            signal_type="LONG",
            strategy_id="grid_btc_1h",
            metadata={"source": "backtest", "version": "1.0"},
        )

        assert result.success is True
        assert result.record.strategy_id == "grid_btc_1h"
        assert result.record.metadata == {"source": "backtest", "version": "1.0"}

    def test_collect_invalid_probability_high(self, collector):
        """Test collecting with invalid probability (> 1.0)."""
        result = collector.collect(
            signal_id="test-sig-005",
            predicted_prob=1.5,
            actual_outcome=1,
            signal_type="LONG",
        )

        assert result.success is False
        assert result.error_message is not None
        assert "predicted_prob" in result.error_message

    def test_collect_invalid_probability_low(self, collector):
        """Test collecting with invalid probability (< 0.0)."""
        result = collector.collect(
            signal_id="test-sig-006",
            predicted_prob=-0.1,
            actual_outcome=1,
            signal_type="LONG",
        )

        assert result.success is False
        assert result.error_message is not None

    def test_collect_invalid_outcome(self, collector):
        """Test collecting with invalid outcome."""
        result = collector.collect(
            signal_id="test-sig-007",
            predicted_prob=0.5,
            actual_outcome=2,
            signal_type="LONG",
        )

        assert result.success is False
        assert result.error_message is not None
        assert "actual_outcome" in result.error_message

    def test_collect_invalid_signal_type(self, collector):
        """Test collecting with invalid signal type."""
        result = collector.collect(
            signal_id="test-sig-008",
            predicted_prob=0.5,
            actual_outcome=1,
            signal_type="INVALID",
        )

        assert result.success is False
        assert result.error_message is not None

    def test_get_records_default_window(self, collector):
        """Test getting records with default window."""
        # Collect some records
        for i in range(5):
            collector.collect(
                signal_id=f"test-sig-{i:03d}",
                predicted_prob=0.5 + i * 0.1,
                actual_outcome=i % 2,
                signal_type="LONG",
            )

        # Get records
        records = collector.get_records()

        assert len(records) == 5
        assert all(isinstance(r, CalibrationRecord) for r in records)

    def test_get_records_specific_window(self, collector):
        """Test getting records with specific window."""
        # Collect records
        collector.collect(
            signal_id="recent-sig",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )

        # Get records with 1h window
        records = collector.get_records(window="1h")
        assert len(records) == 1

        # Get records with 7d window
        records = collector.get_records(window="7d")
        assert len(records) == 1

    def test_get_records_with_signal_type_filter(self, collector):
        """Test getting records filtered by signal type."""
        # Collect records with different signal types
        collector.collect(
            signal_id="long-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )
        collector.collect(
            signal_id="short-sig-001",
            predicted_prob=0.65,
            actual_outcome=0,
            signal_type="SHORT",
        )
        collector.collect(
            signal_id="long-sig-002",
            predicted_prob=0.85,
            actual_outcome=1,
            signal_type="LONG",
        )

        # Get only LONG records
        records = collector.get_records(signal_type="LONG")

        assert len(records) == 2
        assert all(r.signal_type == SignalType.LONG for r in records)

    def test_get_records_by_confidence_bin(self, collector):
        """Test getting records filtered by confidence bin."""
        # Collect records with different probabilities
        collector.collect(
            signal_id="bin5-sig",
            predicted_prob=0.55,
            actual_outcome=1,
            signal_type="LONG",
        )
        collector.collect(
            signal_id="bin7-sig",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )
        collector.collect(
            signal_id="bin7-sig-2",
            predicted_prob=0.78,
            actual_outcome=0,
            signal_type="LONG",
        )

        # Get records in bin 7 (0.7-0.8 range)
        records = collector.get_records_by_confidence_bin(7)

        assert len(records) == 2
        assert all(r.confidence_bin == 7 for r in records)

    def test_get_statistics(self, collector):
        """Test getting collection statistics."""
        # Collect some records
        collector.collect(
            signal_id="long-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )
        collector.collect(
            signal_id="short-sig-001",
            predicted_prob=0.65,
            actual_outcome=0,
            signal_type="SHORT",
        )
        collector.collect(
            signal_id="long-sig-002",
            predicted_prob=0.85,
            actual_outcome=1,
            signal_type="LONG",
        )

        stats = collector.get_statistics()

        assert stats["total_collected"] == 3
        assert stats["total_failed"] == 0
        assert stats["by_signal_type"]["LONG"] == 2
        assert stats["by_signal_type"]["SHORT"] == 1
        assert stats["success_rate"] == 1.0

    def test_get_statistics_with_failures(self, collector):
        """Test getting statistics with failed collections."""
        # Valid collection
        collector.collect(
            signal_id="valid-sig",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )

        # Invalid collection
        collector.collect(
            signal_id="invalid-sig",
            predicted_prob=1.5,  # Invalid
            actual_outcome=1,
            signal_type="LONG",
        )

        stats = collector.get_statistics()

        assert stats["total_collected"] == 1
        assert stats["total_failed"] == 1
        assert stats["success_rate"] == 0.5

    def test_clear_statistics(self, collector):
        """Test clearing statistics."""
        collector.collect(
            signal_id="test-sig",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )

        stats = collector.get_statistics()
        assert stats["total_collected"] == 1

        collector.clear_statistics()

        stats = collector.get_statistics()
        assert stats["total_collected"] == 0
        assert stats["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_collect_async(self, collector):
        """Test async collection."""
        result = await collector.collect_async(
            signal_id="async-sig-001",
            predicted_prob=0.80,
            actual_outcome=1,
            signal_type="LONG",
        )

        assert result.success is True
        assert result.record.signal_id == "async-sig-001"

    @pytest.mark.asyncio
    async def test_collect_batch(self, collector):
        """Test batch collection."""
        records_data = [
            {
                "signal_id": f"batch-sig-{i:03d}",
                "predicted_prob": 0.5 + i * 0.1,
                "actual_outcome": i % 2,
                "signal_type": "LONG" if i % 2 == 0 else "SHORT",
            }
            for i in range(5)
        ]

        results = await collector.collect_batch(records_data)

        assert len(results) == 5
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_collect_batch_with_validation_errors(self, collector):
        """Test batch collection with some invalid records."""
        records_data = [
            {
                "signal_id": "valid-sig",
                "predicted_prob": 0.75,
                "actual_outcome": 1,
                "signal_type": "LONG",
            },
            {
                "signal_id": "invalid-sig",
                "predicted_prob": 1.5,  # Invalid
                "actual_outcome": 1,
                "signal_type": "LONG",
            },
            {
                "signal_id": "another-valid-sig",
                "predicted_prob": 0.65,
                "actual_outcome": 0,
                "signal_type": "SHORT",
            },
        ]

        results = await collector.collect_batch(records_data)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    @pytest.mark.asyncio
    async def test_get_records_async(self, collector):
        """Test async record retrieval."""
        # Collect records
        for i in range(3):
            await collector.collect_async(
                signal_id=f"async-sig-{i:03d}",
                predicted_prob=0.7 + i * 0.05,
                actual_outcome=1,
                signal_type="LONG",
            )

        # Retrieve async
        records = await collector.get_records_async(window="1h")

        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_cleanup_old_records(self, collector, storage):
        """Test cleaning up old records."""
        now = datetime.now(UTC)

        # Add old records directly to storage
        old_records = [
            CalibrationRecord(
                timestamp=now - timedelta(days=100),
                signal_id="old-sig-001",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=7,
            ),
            CalibrationRecord(
                timestamp=now - timedelta(days=50),
                signal_id="medium-sig-001",
                predicted_prob=0.8,
                actual_outcome=0,
                signal_type=SignalType.SHORT,
                confidence_bin=8,
            ),
        ]
        await storage.store_batch(old_records)

        # Add recent record through collector
        await collector.collect_async(
            signal_id="recent-sig",
            predicted_prob=0.9,
            actual_outcome=1,
            signal_type="LONG",
        )

        # Cleanup (retention is 90 days by default)
        deleted = await collector.cleanup_old_records()

        # Should have deleted the old record
        assert deleted >= 1

    @pytest.mark.asyncio
    async def test_close(self, collector):
        """Test closing the collector."""
        await collector.collect_async(
            signal_id="test-sig",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )

        await collector.close()

        # After close, storage should be None
        assert collector._storage is None


class TestCalibrationDataCollectorIntegration:
    """Integration tests for CalibrationDataCollector."""

    def test_full_workflow(self):
        """Test a complete workflow of collect, query, and statistics."""
        storage = InMemoryCalibrationStorage()
        config = CalibrationConfig()
        collector = CalibrationDataCollector(config=config, storage=storage)

        # Collect various records
        signals = [
            ("sig-001", 0.55, 1, "LONG"),
            ("sig-002", 0.65, 0, "SHORT"),
            ("sig-003", 0.75, 1, "LONG"),
            ("sig-004", 0.85, 1, "SCALP"),
            ("sig-005", 0.95, 0, "LONG"),
        ]

        for sig_id, prob, outcome, sig_type in signals:
            result = collector.collect(
                signal_id=sig_id,
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type=sig_type,
            )
            assert result.success, f"Failed to collect {sig_id}"

        # Query records
        records = collector.get_records()
        assert len(records) == 5

        # Query by signal type
        long_records = collector.get_records(signal_type="LONG")
        assert len(long_records) == 3

        # Query by confidence bin
        high_confidence = collector.get_records_by_confidence_bin(9)  # 0.9-1.0
        assert len(high_confidence) == 1

        # Check statistics
        stats = collector.get_statistics()
        assert stats["total_collected"] == 5
        assert stats["success_rate"] == 1.0

    def test_confidence_bin_calculation(self):
        """Test that confidence bins are calculated correctly."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)

        test_cases = [
            (0.05, 0),  # 0.0-0.1
            (0.15, 1),  # 0.1-0.2
            (0.55, 5),  # 0.5-0.6
            (0.75, 7),  # 0.7-0.8
            (0.95, 9),  # 0.9-1.0
            (1.0, 9),  # Edge case: 1.0 goes to bin 9
        ]

        for prob, expected_bin in test_cases:
            result = collector.collect(
                signal_id=f"test-{prob}",
                predicted_prob=prob,
                actual_outcome=1,
                signal_type="LONG",
            )
            assert result.success
            assert result.record.confidence_bin == expected_bin, (
                f"Expected bin {expected_bin} for prob {prob}, got {result.record.confidence_bin}"
            )
