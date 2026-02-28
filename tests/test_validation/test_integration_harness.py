"""Integration tests for IntegratedForensicHarness.

Tests that the IntegratedForensicHarness properly integrates all collectors.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.validation import (
    IntegratedForensicHarness,
    DiscordEvidenceCollector,
    RedisDeltaCollector,
    InfluxEvidenceCollector,
    RecapValidator,
)


class TestIntegratedForensicHarnessInitialization:
    """Test harness initialization."""

    def test_harness_initializes_all_collectors(self):
        """Test that harness initializes all collectors."""
        harness = IntegratedForensicHarness(duration_minutes=30)
        
        assert harness.redis_collector is not None
        assert harness.discord_collector is not None
        assert harness.influx_collector is not None
        assert harness.recap_validator is not None
        
    def test_harness_has_correct_duration(self):
        """Test that harness respects duration parameter."""
        harness = IntegratedForensicHarness(duration_minutes=15)
        assert harness.duration == 15
        
    def test_recap_validator_has_collectors(self):
        """Test that recap validator has references to collectors."""
        harness = IntegratedForensicHarness(duration_minutes=30)
        
        assert harness.recap_validator.redis_collector is harness.redis_collector
        assert harness.recap_validator.influx_collector is harness.influx_collector


class TestIntegratedForensicHarnessMethods:
    """Test harness methods."""

    @pytest.mark.asyncio
    async def test_capture_baseline_structure(self):
        """Test that capture_baseline returns correct structure."""
        harness = IntegratedForensicHarness(duration_minutes=30)
        
        # Mock the collectors to avoid external dependencies
        harness.redis_collector.capture_baseline = AsyncMock(return_value={
            "paper:index:signals": 0,
            "paper:index:orders": 0,
        })
        harness.discord_collector.collect_messages = AsyncMock(return_value=[])
        harness.influx_collector.query_orders = AsyncMock()
        harness.influx_collector.query_fills = AsyncMock()
        
        baseline = await harness.capture_baseline()
        
        assert "timestamp_utc" in baseline
        assert "label" in baseline
        assert baseline["label"] == "T0"
        
    @pytest.mark.asyncio
    async def test_capture_snapshot_structure(self):
        """Test that capture_snapshot returns correct structure."""
        harness = IntegratedForensicHarness(duration_minutes=30)
        
        # Mock the collectors
        harness.redis_collector.get_kill_switch_state = AsyncMock(return_value={})
        harness.discord_collector.collect_messages = AsyncMock(return_value=[])
        harness.influx_collector.query_orders = AsyncMock()
        harness.influx_collector.query_fills = AsyncMock()
        
        snapshot = await harness.capture_snapshot("T5")
        
        assert "timestamp_utc" in snapshot
        assert "label" in snapshot
        assert snapshot["label"] == "T5"
        
    @pytest.mark.asyncio
    async def test_capture_final_structure(self):
        """Test that capture_final returns correct structure."""
        harness = IntegratedForensicHarness(duration_minutes=30)
        
        # Create mock evidence
        mock_evidence = MagicMock()
        mock_evidence.index_name = "paper:index:signals"
        mock_evidence.delta = 5
        mock_evidence.to_dict = MagicMock(return_value={
            "index_name": "paper:index:signals",
            "delta": 5,
        })
        
        # Mock the collectors
        harness.redis_collector.capture_final = AsyncMock(return_value=[mock_evidence])
        harness.discord_collector.collect_messages = AsyncMock(return_value=[])
        harness.influx_collector.query_orders = AsyncMock()
        harness.influx_collector.query_fills = AsyncMock()
        harness.influx_collector.query_canary = AsyncMock()
        
        baseline = {"redis": {"paper:index:signals": 0}}
        final = await harness.capture_final(baseline)
        
        assert "timestamp_utc" in final
        assert "label" in final
        assert final["label"] == "T30"


class TestIntegratedForensicHarnessImports:
    """Test that all imports work correctly."""

    def test_all_classes_importable(self):
        """Test that all classes can be imported from scripts.validation."""
        from scripts.validation import (
            ForensicHarness,
            IntegratedForensicHarness,
            DiscordEvidenceCollector,
            RedisDeltaCollector,
            InfluxEvidenceCollector,
            RecapValidator,
        )
        
        # Just verify they're all classes
        assert isinstance(ForensicHarness, type)
        assert isinstance(IntegratedForensicHarness, type)
        assert isinstance(DiscordEvidenceCollector, type)
        assert isinstance(RedisDeltaCollector, type)
        assert isinstance(InfluxEvidenceCollector, type)
        assert isinstance(RecapValidator, type)
        
    def test_integrated_harness_is_subclass(self):
        """Test that IntegratedForensicHarness is a subclass of ForensicHarness."""
        from scripts.validation import ForensicHarness, IntegratedForensicHarness
        
        assert issubclass(IntegratedForensicHarness, ForensicHarness)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
