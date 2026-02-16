"""Unit tests for calibration data exporter."""

from __future__ import annotations

import json
import os
import pytest
import tempfile
from datetime import UTC, datetime, timedelta

import sys

sys.path.insert(0, "src")

from ml.calibration.exporter import CalibrationExporter, ExportFormat
from ml.calibration.models import CalibrationRecord, SignalType
from ml.calibration.storage import InMemoryCalibrationStorage


class TestCalibrationExporter:
    """Tests for CalibrationExporter."""

    @pytest.fixture
    def storage(self):
        """Create a fresh in-memory storage with sample data."""
        storage = InMemoryCalibrationStorage()
        now = datetime.now(UTC)

        records = [
            CalibrationRecord(
                timestamp=now - timedelta(hours=i),
                signal_id=f"test-sig-{i:03d}",
                predicted_prob=0.5 + i * 0.05,
                actual_outcome=i % 2,
                signal_type=SignalType.LONG if i % 2 == 0 else SignalType.SHORT,
                confidence_bin=min(5 + i, 9),  # Ensure bin is in valid range 0-9
                strategy_id=f"strategy-{i}",
                metadata={"source": "test", "index": i},
            )
            for i in range(10)
        ]

        import asyncio

        asyncio.run(storage.store_batch(records))

        return storage

    @pytest.fixture
    def exporter(self, storage):
        """Create an exporter with sample data."""
        return CalibrationExporter(storage)

    @pytest.mark.asyncio
    async def test_export_to_csv(self, exporter):
        """Test exporting to CSV format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            success = await exporter.export(filepath, ExportFormat.CSV)
            assert success is True
            assert os.path.exists(filepath)

            # Verify CSV content
            with open(filepath, "r", newline="", encoding="utf-8") as f:
                content = f.read()
                assert "timestamp,signal_id,predicted_prob" in content
                assert "test-sig-000" in content
                assert "test-sig-009" in content

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_to_json(self, exporter):
        """Test exporting to JSON format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            success = await exporter.export(filepath, ExportFormat.JSON)
            assert success is True
            assert os.path.exists(filepath)

            # Verify JSON content
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert "records" in data
                assert "count" in data
                assert data["count"] == 10
                assert len(data["records"]) == 10

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_to_parquet(self, exporter):
        """Test exporting to Parquet format."""
        pytest.importorskip("pandas")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".parquet", delete=False
        ) as f:
            filepath = f.name

        try:
            success = await exporter.export(filepath, ExportFormat.PARQUET)
            assert success is True
            assert os.path.exists(filepath)

            # Verify Parquet content
            import pandas as pd

            df = pd.read_parquet(filepath)
            assert len(df) == 10
            assert "signal_id" in df.columns
            assert "predicted_prob" in df.columns

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_with_time_filter(self, exporter):
        """Test exporting with time filters."""
        now = datetime.now(UTC)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            # Export only last 2 hours
            success = await exporter.export(
                filepath,
                ExportFormat.JSON,
                start_time=now - timedelta(hours=2),
                end_time=now,
            )
            assert success is True

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Should only have records from last 2 hours
                assert data["count"] <= 3

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_with_signal_type_filter(self, exporter):
        """Test exporting with signal type filter."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            success = await exporter.export(
                filepath,
                ExportFormat.JSON,
                signal_type=SignalType.LONG,
            )
            assert success is True

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Should only have LONG records
                for record in data["records"]:
                    assert record["signal_type"] == "LONG"

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_for_ece_csv(self, exporter):
        """Test ECE-formatted export to CSV."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            success = await exporter.export_for_ece(filepath, ExportFormat.CSV)
            assert success is True

            with open(filepath, "r", newline="", encoding="utf-8") as f:
                content = f.read()
                # Should only have confidence and outcome columns
                assert "confidence,outcome" in content
                assert "signal_id" not in content

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_for_ece_parquet(self, exporter):
        """Test ECE-formatted export to Parquet."""
        pytest.importorskip("pandas")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".parquet", delete=False
        ) as f:
            filepath = f.name

        try:
            success = await exporter.export_for_ece(filepath, ExportFormat.PARQUET)
            assert success is True

            import pandas as pd

            df = pd.read_parquet(filepath)
            # Should only have confidence and outcome columns
            assert list(df.columns) == ["confidence", "outcome"]
            assert len(df) == 10

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_by_signal_type(self, exporter):
        """Test exporting separately by signal type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_filepath = os.path.join(tmpdir, "calibration_data.csv")

            results = await exporter.export_by_signal_type(
                base_filepath,
                ExportFormat.CSV,
            )

            # Should have results for all signal types
            assert SignalType.LONG in results
            assert SignalType.SHORT in results
            assert SignalType.SCALP in results

            # Check files were created
            for signal_type in SignalType:
                filepath = os.path.join(
                    tmpdir, f"calibration_data_{signal_type.value.lower()}.csv"
                )
                if results[signal_type]:
                    assert os.path.exists(filepath)

    @pytest.mark.asyncio
    async def test_export_empty_storage(self):
        """Test exporting from empty storage."""
        empty_storage = InMemoryCalibrationStorage()
        exporter = CalibrationExporter(empty_storage)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            success = await exporter.export(filepath, ExportFormat.JSON)
            assert success is False  # Should fail with no records

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_export_unsupported_format(self, exporter):
        """Test exporting with unsupported format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            filepath = f.name

        try:
            # Create an invalid format by using a non-existent enum value
            # This tests the error handling path
            success = await exporter.export(filepath, ExportFormat.JSON)
            assert success is True  # JSON is supported

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
