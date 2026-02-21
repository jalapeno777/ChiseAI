"""Tests for threshold history tracking module.

Tests cover:
- InMemoryThresholdTracker
- InfluxDBThresholdTracker (with mocked InfluxDB)
- ThresholdHistoryTracker protocol compliance
- History recording and retrieval
- Edge cases and error handling
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from confidence.threshold import (
    ModeSwitchRecord,
    ThresholdAdjustment,
    ThresholdConfig,
    ThresholdMode,
)
from confidence.threshold_tracker import (
    InMemoryThresholdTracker,
    InfluxDBThresholdTracker,
)

if TYPE_CHECKING:
    pass


@pytest.fixture
def sample_adjustment():
    """Create a sample threshold adjustment."""
    return ThresholdAdjustment(
        timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        strategy_id="grid_btc_1h",
        old_value=0.60,
        new_value=0.65,
        reason="ECE too high",
        ece_before=0.18,
        ece_after=0.12,
        adjustment_type="auto",
        triggered_by="ece_high",
    )


@pytest.fixture
def sample_mode_switch():
    """Create a sample mode switch record."""
    return ModeSwitchRecord(
        timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        strategy_id="grid_btc_1h",
        old_mode=ThresholdMode.DYNAMIC,
        new_mode=ThresholdMode.FIXED,
        reason="Testing manual override",
        old_threshold=0.65,
        new_threshold=0.70,
    )


@pytest.fixture
def sample_config():
    """Create a sample threshold config."""
    return ThresholdConfig(
        strategy_id="grid_btc_1h",
        mode=ThresholdMode.DYNAMIC,
        current_threshold=0.65,
    )


@pytest.fixture
def mock_influx_client():
    """Create a mock InfluxDB client."""
    with patch("influxdb_client.InfluxDBClient") as mock_client_class:
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_query_api = MagicMock()

        mock_client.write_api.return_value = mock_write_api
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        yield {
            "client": mock_client,
            "write_api": mock_write_api,
            "query_api": mock_query_api,
            "client_class": mock_client_class,
        }


class TestInMemoryThresholdTracker:
    """Tests for InMemoryThresholdTracker."""

    @pytest.mark.asyncio
    async def test_record_adjustment(self, sample_adjustment):
        """Test recording an adjustment."""
        tracker = InMemoryThresholdTracker()

        result = await tracker.record_adjustment(sample_adjustment)

        assert result is True

    @pytest.mark.asyncio
    async def test_record_mode_switch(self, sample_mode_switch):
        """Test recording a mode switch."""
        tracker = InMemoryThresholdTracker()

        result = await tracker.record_mode_switch(sample_mode_switch)

        assert result is True

    @pytest.mark.asyncio
    async def test_record_config_change(self, sample_config):
        """Test recording a config change."""
        tracker = InMemoryThresholdTracker()

        result = await tracker.record_config_change(sample_config, "create")

        assert result is True

    @pytest.mark.asyncio
    async def test_get_adjustment_history(self, sample_adjustment):
        """Test retrieving adjustment history."""
        tracker = InMemoryThresholdTracker()
        # Use a recent timestamp instead of the fixture's 2024 timestamp
        recent_adjustment = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="grid_btc_1h",
            old_value=0.60,
            new_value=0.65,
            reason="ECE too high",
            ece_before=0.18,
            ece_after=0.12,
            adjustment_type="auto",
            triggered_by="ece_high",
        )
        await tracker.record_adjustment(recent_adjustment)

        history = await tracker.get_adjustment_history(strategy_id="grid_btc_1h")

        assert len(history) == 1
        assert history[0].strategy_id == "grid_btc_1h"
        assert history[0].old_value == 0.60
        assert history[0].new_value == 0.65

    @pytest.mark.asyncio
    async def test_get_adjustment_history_filtered(self):
        """Test retrieving filtered adjustment history."""
        tracker = InMemoryThresholdTracker()

        # Add adjustments for different strategies
        adj1 = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="strategy_a",
            old_value=0.60,
            new_value=0.65,
            reason="Test",
        )
        adj2 = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="strategy_b",
            old_value=0.70,
            new_value=0.75,
            reason="Test",
        )

        await tracker.record_adjustment(adj1)
        await tracker.record_adjustment(adj2)

        history = await tracker.get_adjustment_history(strategy_id="strategy_a")

        assert len(history) == 1
        assert history[0].strategy_id == "strategy_a"

    @pytest.mark.asyncio
    async def test_get_adjustment_history_by_type(self):
        """Test retrieving adjustment history by type."""
        tracker = InMemoryThresholdTracker()

        adj1 = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="Test",
            adjustment_type="auto",
        )
        adj2 = ThresholdAdjustment(
            timestamp=datetime.now(UTC) + timedelta(minutes=1),
            strategy_id="test",
            old_value=0.65,
            new_value=0.70,
            reason="Test",
            adjustment_type="manual",
        )

        await tracker.record_adjustment(adj1)
        await tracker.record_adjustment(adj2)

        history = await tracker.get_adjustment_history(
            strategy_id="test", adjustment_type="manual"
        )

        assert len(history) == 1
        assert history[0].adjustment_type == "manual"

    @pytest.mark.asyncio
    async def test_get_adjustment_history_time_filtered(self):
        """Test retrieving adjustment history with time filter."""
        tracker = InMemoryThresholdTracker()

        # Old adjustment
        old_adj = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="Old",
        )
        # Recent adjustment
        recent_adj = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="test",
            old_value=0.65,
            new_value=0.70,
            reason="Recent",
        )

        await tracker.record_adjustment(old_adj)
        await tracker.record_adjustment(recent_adj)

        history = await tracker.get_adjustment_history(strategy_id="test", days=7)

        assert len(history) == 1
        assert history[0].reason == "Recent"

    @pytest.mark.asyncio
    async def test_get_mode_switch_history(self, sample_mode_switch):
        """Test retrieving mode switch history."""
        tracker = InMemoryThresholdTracker()
        # Use a recent timestamp instead of the fixture's 2024 timestamp
        recent_switch = ModeSwitchRecord(
            timestamp=datetime.now(UTC),
            strategy_id="grid_btc_1h",
            old_mode=ThresholdMode.DYNAMIC,
            new_mode=ThresholdMode.FIXED,
            reason="Testing manual override",
            old_threshold=0.65,
            new_threshold=0.70,
        )
        await tracker.record_mode_switch(recent_switch)

        history = await tracker.get_mode_switch_history(strategy_id="grid_btc_1h")

        assert len(history) == 1
        assert history[0].old_mode == ThresholdMode.DYNAMIC
        assert history[0].new_mode == ThresholdMode.FIXED

    @pytest.mark.asyncio
    async def test_get_mode_switch_history_filtered(self):
        """Test retrieving filtered mode switch history."""
        tracker = InMemoryThresholdTracker()

        switch1 = ModeSwitchRecord(
            timestamp=datetime.now(UTC),
            strategy_id="strategy_a",
            old_mode=ThresholdMode.DYNAMIC,
            new_mode=ThresholdMode.FIXED,
            reason="Test",
            old_threshold=0.60,
            new_threshold=0.65,
        )
        switch2 = ModeSwitchRecord(
            timestamp=datetime.now(UTC),
            strategy_id="strategy_b",
            old_mode=ThresholdMode.FIXED,
            new_mode=ThresholdMode.DYNAMIC,
            reason="Test",
            old_threshold=0.70,
            new_threshold=0.70,
        )

        await tracker.record_mode_switch(switch1)
        await tracker.record_mode_switch(switch2)

        history = await tracker.get_mode_switch_history(strategy_id="strategy_a")

        assert len(history) == 1
        assert history[0].strategy_id == "strategy_a"

    @pytest.mark.asyncio
    async def test_get_latest_adjustment(self, sample_adjustment):
        """Test getting latest adjustment."""
        tracker = InMemoryThresholdTracker()

        # Add two adjustments
        old_adj = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.50,
            new_value=0.55,
            reason="Old",
        )
        recent_adj = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.55,
            new_value=0.60,
            reason="Recent",
        )

        await tracker.record_adjustment(old_adj)
        await tracker.record_adjustment(recent_adj)

        latest = await tracker.get_latest_adjustment("test")

        assert latest is not None
        assert latest.new_value == 0.60
        assert latest.reason == "Recent"

    @pytest.mark.asyncio
    async def test_get_latest_adjustment_none(self):
        """Test getting latest adjustment when none exists."""
        tracker = InMemoryThresholdTracker()

        latest = await tracker.get_latest_adjustment("unknown")

        assert latest is None

    @pytest.mark.asyncio
    async def test_get_adjustment_count(self):
        """Test getting adjustment count."""
        tracker = InMemoryThresholdTracker()

        for i in range(5):
            adj = ThresholdAdjustment(
                timestamp=datetime.now(UTC) - timedelta(hours=i),
                strategy_id="test",
                old_value=0.60,
                new_value=0.65,
                reason=f"Adj {i}",
            )
            await tracker.record_adjustment(adj)

        count = await tracker.get_adjustment_count(strategy_id="test")

        assert count == 5

    @pytest.mark.asyncio
    async def test_get_adjustment_count_filtered(self):
        """Test getting adjustment count with filter."""
        tracker = InMemoryThresholdTracker()

        # Add adjustments for different strategies
        for i in range(3):
            adj = ThresholdAdjustment(
                timestamp=datetime.now(UTC),
                strategy_id="strategy_a",
                old_value=0.60,
                new_value=0.65,
                reason="Test",
            )
            await tracker.record_adjustment(adj)

        for i in range(2):
            adj = ThresholdAdjustment(
                timestamp=datetime.now(UTC),
                strategy_id="strategy_b",
                old_value=0.70,
                new_value=0.75,
                reason="Test",
            )
            await tracker.record_adjustment(adj)

        count_a = await tracker.get_adjustment_count(strategy_id="strategy_a")
        count_b = await tracker.get_adjustment_count(strategy_id="strategy_b")

        assert count_a == 3
        assert count_b == 2

    @pytest.mark.asyncio
    async def test_get_strategies_with_adjustments(self):
        """Test getting strategies with adjustments."""
        tracker = InMemoryThresholdTracker()

        adj1 = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="strategy_a",
            old_value=0.60,
            new_value=0.65,
            reason="Test",
        )
        adj2 = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="strategy_b",
            old_value=0.70,
            new_value=0.75,
            reason="Test",
        )

        await tracker.record_adjustment(adj1)
        await tracker.record_adjustment(adj2)

        strategies = await tracker.get_strategies_with_adjustments()

        assert len(strategies) == 2
        assert "strategy_a" in strategies
        assert "strategy_b" in strategies

    def test_clear(self, sample_adjustment, sample_mode_switch):
        """Test clearing all history."""
        tracker = InMemoryThresholdTracker()

        # Add some data
        tracker._adjustments.append(sample_adjustment)
        tracker._mode_switches.append(sample_mode_switch)

        tracker.clear()

        assert len(tracker._adjustments) == 0
        assert len(tracker._mode_switches) == 0

    def test_get_stats(self):
        """Test getting statistics."""
        tracker = InMemoryThresholdTracker()

        # Add some data
        adj = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="Test",
        )
        switch = ModeSwitchRecord(
            timestamp=datetime.now(UTC),
            strategy_id="test",
            old_mode=ThresholdMode.DYNAMIC,
            new_mode=ThresholdMode.FIXED,
            reason="Test",
            old_threshold=0.60,
            new_threshold=0.65,
        )

        tracker._adjustments.append(adj)
        tracker._mode_switches.append(switch)

        stats = tracker.get_stats()

        assert stats["adjustments"] == 1
        assert stats["mode_switches"] == 1


class TestInfluxDBThresholdTracker:
    """Tests for InfluxDBThresholdTracker."""

    def test_initialization_defaults(self):
        """Test initialization with default parameters."""
        tracker = InfluxDBThresholdTracker()

        assert tracker.org == "chiseai"
        assert tracker.bucket == "thresholds"
        assert tracker._url == "http://localhost:8086"
        assert tracker._token == ""

    def test_initialization_custom(self):
        """Test initialization with custom parameters."""
        tracker = InfluxDBThresholdTracker(
            url="http://test:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
        )

        assert tracker.org == "test_org"
        assert tracker.bucket == "test_bucket"
        assert tracker._url == "http://test:8086"
        assert tracker._token == "test_token"

    def test_initialization_with_client(self):
        """Test initialization with existing client."""
        mock_client = MagicMock()
        tracker = InfluxDBThresholdTracker(client=mock_client)

        assert tracker._client is mock_client
        assert not tracker._owned_client

    @pytest.mark.asyncio
    async def test_record_adjustment(self, mock_influx_client, sample_adjustment):
        """Test recording adjustment to InfluxDB."""
        tracker = InfluxDBThresholdTracker()

        result = await tracker.record_adjustment(sample_adjustment)

        assert result is True
        mock_influx_client["write_api"].write.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_adjustment_failure(
        self, mock_influx_client, sample_adjustment
    ):
        """Test handling of adjustment write failure."""
        mock_influx_client["write_api"].write.side_effect = Exception("Write failed")

        tracker = InfluxDBThresholdTracker()
        result = await tracker.record_adjustment(sample_adjustment)

        assert result is False

    @pytest.mark.asyncio
    async def test_record_mode_switch(self, mock_influx_client, sample_mode_switch):
        """Test recording mode switch to InfluxDB."""
        tracker = InfluxDBThresholdTracker()

        result = await tracker.record_mode_switch(sample_mode_switch)

        assert result is True
        mock_influx_client["write_api"].write.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_mode_switch_failure(
        self, mock_influx_client, sample_mode_switch
    ):
        """Test handling of mode switch write failure."""
        mock_influx_client["write_api"].write.side_effect = Exception("Write failed")

        tracker = InfluxDBThresholdTracker()
        result = await tracker.record_mode_switch(sample_mode_switch)

        assert result is False

    @pytest.mark.asyncio
    async def test_record_config_change(self, mock_influx_client, sample_config):
        """Test recording config change to InfluxDB."""
        tracker = InfluxDBThresholdTracker()

        result = await tracker.record_config_change(sample_config, "create")

        assert result is True
        mock_influx_client["write_api"].write.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_adjustment_history(self, mock_influx_client):
        """Test retrieving adjustment history from InfluxDB."""
        # Create mock record
        mock_record = MagicMock()
        mock_record.get_time.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_record.values = {
            "strategy_id": "test_strategy",
            "adjustment_type": "auto",
            "triggered_by": "ece_high",
            "old_value": 0.60,
            "new_value": 0.65,
            "reason": "ECE too high",
            "ece_before": 0.18,
            "ece_after": 0.12,
        }

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = InfluxDBThresholdTracker()
        history = await tracker.get_adjustment_history(strategy_id="test_strategy")

        assert len(history) == 1
        assert history[0].strategy_id == "test_strategy"
        assert history[0].old_value == 0.60
        assert history[0].new_value == 0.65

    @pytest.mark.asyncio
    async def test_get_adjustment_history_empty(self, mock_influx_client):
        """Test retrieving empty adjustment history."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = InfluxDBThresholdTracker()
        history = await tracker.get_adjustment_history()

        assert history == []

    @pytest.mark.asyncio
    async def test_get_adjustment_history_query_failure(self, mock_influx_client):
        """Test handling of query failure."""
        mock_influx_client["query_api"].query.side_effect = Exception("Query failed")

        tracker = InfluxDBThresholdTracker()
        history = await tracker.get_adjustment_history()

        assert history == []

    @pytest.mark.asyncio
    async def test_get_mode_switch_history(self, mock_influx_client):
        """Test retrieving mode switch history from InfluxDB."""
        mock_record = MagicMock()
        mock_record.get_time.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_record.values = {
            "strategy_id": "test_strategy",
            "old_mode": "dynamic",
            "new_mode": "fixed",
            "old_threshold": 0.60,
            "new_threshold": 0.65,
            "reason": "Testing",
        }

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = InfluxDBThresholdTracker()
        history = await tracker.get_mode_switch_history(strategy_id="test_strategy")

        assert len(history) == 1
        assert history[0].strategy_id == "test_strategy"
        assert history[0].old_mode == ThresholdMode.DYNAMIC
        assert history[0].new_mode == ThresholdMode.FIXED

    @pytest.mark.asyncio
    async def test_get_latest_adjustment(self, mock_influx_client):
        """Test retrieving latest adjustment from InfluxDB."""
        mock_record = MagicMock()
        mock_record.get_time.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_record.values = {
            "strategy_id": "test_strategy",
            "adjustment_type": "auto",
            "triggered_by": "ece_high",
            "old_value": 0.60,
            "new_value": 0.65,
            "reason": "ECE too high",
        }

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = InfluxDBThresholdTracker()
        latest = await tracker.get_latest_adjustment("test_strategy")

        assert latest is not None
        assert latest.strategy_id == "test_strategy"
        assert latest.new_value == 0.65

    @pytest.mark.asyncio
    async def test_get_latest_adjustment_no_data(self, mock_influx_client):
        """Test retrieving latest adjustment when no data exists."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = InfluxDBThresholdTracker()
        latest = await tracker.get_latest_adjustment("test_strategy")

        assert latest is None

    @pytest.mark.asyncio
    async def test_get_adjustment_count(self, mock_influx_client):
        """Test retrieving adjustment count from InfluxDB."""
        mock_record = MagicMock()
        mock_record.get_value.return_value = 5

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = InfluxDBThresholdTracker()
        count = await tracker.get_adjustment_count(strategy_id="test_strategy")

        assert count == 5

    @pytest.mark.asyncio
    async def test_get_adjustment_count_no_data(self, mock_influx_client):
        """Test retrieving adjustment count when no data exists."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = InfluxDBThresholdTracker()
        count = await tracker.get_adjustment_count()

        assert count == 0

    @pytest.mark.asyncio
    async def test_get_strategies_with_adjustments(self, mock_influx_client):
        """Test retrieving strategies with adjustments."""
        records = []
        for strategy_id in ["strategy_a", "strategy_b", "strategy_c"]:
            mock_record = MagicMock()
            mock_record.values = {"strategy_id": strategy_id}
            records.append(mock_record)

        mock_table = MagicMock()
        mock_table.records = records

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = InfluxDBThresholdTracker()
        strategies = await tracker.get_strategies_with_adjustments()

        assert len(strategies) == 3
        assert "strategy_a" in strategies
        assert "strategy_b" in strategies
        assert "strategy_c" in strategies

    @pytest.mark.asyncio
    async def test_get_strategies_with_adjustments_empty(self, mock_influx_client):
        """Test retrieving strategies when none exist."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = InfluxDBThresholdTracker()
        strategies = await tracker.get_strategies_with_adjustments()

        assert strategies == []

    @pytest.mark.asyncio
    async def test_close_owned_client(self, mock_influx_client):
        """Test closing tracker with owned client."""
        tracker = InfluxDBThresholdTracker()
        await tracker._get_client()  # Initialize client

        await tracker.close()

        mock_influx_client["client"].close.assert_called_once()
        assert tracker._client is None

    @pytest.mark.asyncio
    async def test_close_external_client(self):
        """Test closing tracker with external client."""
        mock_client = MagicMock()
        tracker = InfluxDBThresholdTracker(client=mock_client)

        await tracker.close()

        # External client should not be closed
        mock_client.close.assert_not_called()
        assert tracker._client is None


class TestThresholdTrackerEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_in_memory_empty_history(self):
        """Test retrieving empty history."""
        tracker = InMemoryThresholdTracker()

        history = await tracker.get_adjustment_history(strategy_id="unknown")

        assert history == []

    @pytest.mark.asyncio
    async def test_in_memory_old_data_filtered(self):
        """Test that old data is filtered by days parameter."""
        tracker = InMemoryThresholdTracker()

        # Add old adjustment (40 days ago)
        old_adj = ThresholdAdjustment(
            timestamp=datetime.now(UTC) - timedelta(days=40),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="Old",
        )
        await tracker.record_adjustment(old_adj)

        # Should be filtered out with 30 days
        history = await tracker.get_adjustment_history(strategy_id="test", days=30)
        assert len(history) == 0

        # Should be included with 90 days
        history = await tracker.get_adjustment_history(strategy_id="test", days=90)
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_in_memory_multiple_strategies(self):
        """Test handling multiple strategies."""
        tracker = InMemoryThresholdTracker()

        for i in range(3):
            adj = ThresholdAdjustment(
                timestamp=datetime.now(UTC),
                strategy_id=f"strategy_{i}",
                old_value=0.60,
                new_value=0.65,
                reason="Test",
            )
            await tracker.record_adjustment(adj)

        strategies = await tracker.get_strategies_with_adjustments()

        assert len(strategies) == 3

    @pytest.mark.asyncio
    async def test_in_memory_chronological_order(self):
        """Test that history is returned in chronological order."""
        tracker = InMemoryThresholdTracker()

        # Add adjustments in chronological order (older first)
        adj1 = ThresholdAdjustment(
            timestamp=datetime.now(UTC) - timedelta(hours=2),
            strategy_id="test",
            old_value=0.55,
            new_value=0.60,
            reason="First",
        )
        adj2 = ThresholdAdjustment(
            timestamp=datetime.now(UTC) - timedelta(hours=1),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="Second",
        )

        await tracker.record_adjustment(adj1)
        await tracker.record_adjustment(adj2)

        history = await tracker.get_adjustment_history(strategy_id="test")

        # Should be sorted by timestamp
        assert len(history) == 2
        assert history[0].reason == "First"
        assert history[1].reason == "Second"

    @pytest.mark.asyncio
    async def test_influxdb_adjustment_without_ece(self, mock_influx_client):
        """Test retrieving adjustment without ECE values."""
        mock_record = MagicMock()
        mock_record.get_time.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_record.values = {
            "strategy_id": "test_strategy",
            "adjustment_type": "manual",
            "triggered_by": "manual",
            "old_value": 0.60,
            "new_value": 0.65,
            "reason": "Manual adjustment",
            # No ece_before or ece_after
        }

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = InfluxDBThresholdTracker()
        history = await tracker.get_adjustment_history()

        assert len(history) == 1
        assert history[0].ece_before is None
        assert history[0].ece_after is None

    @pytest.mark.asyncio
    async def test_influxdb_query_with_filters(self, mock_influx_client):
        """Test that query includes correct filters."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = InfluxDBThresholdTracker()
        await tracker.get_adjustment_history(
            strategy_id="test_strategy",
            days=7,
            adjustment_type="auto",
        )

        # Verify query was called
        mock_influx_client["query_api"].query.assert_called_once()

        # Check that the query contains expected elements
        call_args = mock_influx_client["query_api"].query.call_args
        query = call_args[0][0]
        assert "threshold_adjustments" in query
        assert "test_strategy" in query
        assert "auto" in query

    @pytest.mark.asyncio
    async def test_in_memory_stats_empty(self):
        """Test stats on empty tracker."""
        tracker = InMemoryThresholdTracker()

        stats = tracker.get_stats()

        assert stats["adjustments"] == 0
        assert stats["mode_switches"] == 0
        assert stats["config_changes"] == 0

    @pytest.mark.asyncio
    async def test_in_memory_clear_empty(self):
        """Test clearing empty tracker."""
        tracker = InMemoryThresholdTracker()

        # Should not raise
        tracker.clear()

        assert tracker.get_stats()["adjustments"] == 0

    @pytest.mark.asyncio
    async def test_adjustment_count_with_old_data(self):
        """Test adjustment count filters old data."""
        tracker = InMemoryThresholdTracker()

        # Add old adjustment
        old_adj = ThresholdAdjustment(
            timestamp=datetime.now(UTC) - timedelta(days=60),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="Old",
        )
        # Add recent adjustment
        recent_adj = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id="test",
            old_value=0.65,
            new_value=0.70,
            reason="Recent",
        )

        await tracker.record_adjustment(old_adj)
        await tracker.record_adjustment(recent_adj)

        count_30 = await tracker.get_adjustment_count(strategy_id="test", days=30)
        count_90 = await tracker.get_adjustment_count(strategy_id="test", days=90)

        assert count_30 == 1
        assert count_90 == 2


class TestThresholdTrackerIntegration:
    """Integration-style tests for threshold tracking."""

    @pytest.mark.asyncio
    async def test_full_tracking_workflow(self):
        """Test complete tracking workflow."""
        tracker = InMemoryThresholdTracker()

        # Record adjustments
        for i in range(5):
            adj = ThresholdAdjustment(
                timestamp=datetime.now(UTC) - timedelta(hours=i),
                strategy_id="grid_btc_1h",
                old_value=0.60 + i * 0.01,
                new_value=0.61 + i * 0.01,
                reason=f"Adjustment {i}",
                adjustment_type="auto",
            )
            await tracker.record_adjustment(adj)

        # Record mode switches
        switch1 = ModeSwitchRecord(
            timestamp=datetime.now(UTC) - timedelta(days=2),
            strategy_id="grid_btc_1h",
            old_mode=ThresholdMode.DYNAMIC,
            new_mode=ThresholdMode.FIXED,
            reason="Testing",
            old_threshold=0.65,
            new_threshold=0.65,
        )
        switch2 = ModeSwitchRecord(
            timestamp=datetime.now(UTC) - timedelta(days=1),
            strategy_id="grid_btc_1h",
            old_mode=ThresholdMode.FIXED,
            new_mode=ThresholdMode.DYNAMIC,
            reason="Resume auto",
            old_threshold=0.65,
            new_threshold=0.65,
        )
        await tracker.record_mode_switch(switch1)
        await tracker.record_mode_switch(switch2)

        # Verify counts
        assert await tracker.get_adjustment_count("grid_btc_1h") == 5

        # Verify history
        adj_history = await tracker.get_adjustment_history("grid_btc_1h")
        assert len(adj_history) == 5

        switch_history = await tracker.get_mode_switch_history("grid_btc_1h")
        assert len(switch_history) == 2

        # Verify latest
        latest = await tracker.get_latest_adjustment("grid_btc_1h")
        assert latest is not None
        assert latest.reason == "Adjustment 0"  # Most recent

    @pytest.mark.asyncio
    async def test_multiple_strategies_tracking(self):
        """Test tracking for multiple strategies."""
        tracker = InMemoryThresholdTracker()

        strategies = ["grid_btc_1h", "grid_eth_1h", "trend_btc_4h"]

        for strategy_id in strategies:
            for i in range(3):
                adj = ThresholdAdjustment(
                    timestamp=datetime.now(UTC) - timedelta(hours=i),
                    strategy_id=strategy_id,
                    old_value=0.60,
                    new_value=0.65,
                    reason="Test",
                )
                await tracker.record_adjustment(adj)

        # Verify each strategy
        for strategy_id in strategies:
            count = await tracker.get_adjustment_count(strategy_id)
            assert count == 3

        # Verify all strategies listed
        all_strategies = await tracker.get_strategies_with_adjustments()
        assert len(all_strategies) == 3
        for strategy_id in strategies:
            assert strategy_id in all_strategies

    @pytest.mark.asyncio
    async def test_time_based_filtering(self):
        """Test time-based filtering of history."""
        tracker = InMemoryThresholdTracker()

        # Add adjustments at different times
        times = [
            datetime.now(UTC) - timedelta(hours=1),  # Within 1 day
            datetime.now(UTC) - timedelta(days=3),  # Within 7 days
            datetime.now(UTC) - timedelta(days=10),  # Within 14 days
            datetime.now(UTC) - timedelta(days=20),  # Within 30 days
            datetime.now(UTC) - timedelta(days=45),  # Within 90 days
        ]

        for i, ts in enumerate(times):
            adj = ThresholdAdjustment(
                timestamp=ts,
                strategy_id="test",
                old_value=0.60,
                new_value=0.65,
                reason=f"Adj {i}",
            )
            await tracker.record_adjustment(adj)

        # Test different day filters
        count_1 = await tracker.get_adjustment_count("test", days=1)
        count_7 = await tracker.get_adjustment_count("test", days=7)
        count_30 = await tracker.get_adjustment_count("test", days=30)
        count_90 = await tracker.get_adjustment_count("test", days=90)

        assert count_1 == 1
        assert count_7 == 2
        assert count_30 == 4
        assert count_90 == 5

    @pytest.mark.asyncio
    async def test_tracker_persistence_simulation(self):
        """Simulate tracker persistence across operations."""
        tracker = InMemoryThresholdTracker()

        # Phase 1: Initial setup
        config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.60,
        )
        await tracker.record_config_change(config, "create")

        # Phase 2: Multiple calibrations
        for i in range(10):
            adj = ThresholdAdjustment(
                timestamp=datetime.now(UTC) - timedelta(hours=10 - i),
                strategy_id="test",
                old_value=0.60 + i * 0.01,
                new_value=0.61 + i * 0.01,
                reason=f"Calibration {i}",
                ece_before=0.15 - i * 0.01,
                adjustment_type="auto",
            )
            await tracker.record_adjustment(adj)

        # Phase 3: Mode switch
        switch = ModeSwitchRecord(
            timestamp=datetime.now(UTC),
            strategy_id="test",
            old_mode=ThresholdMode.DYNAMIC,
            new_mode=ThresholdMode.FIXED,
            reason="Manual override",
            old_threshold=0.70,
            new_threshold=0.70,
        )
        await tracker.record_mode_switch(switch)

        # Verify complete history
        stats = tracker.get_stats()
        assert stats["adjustments"] == 10
        assert stats["mode_switches"] == 1
        assert stats["config_changes"] == 1

        # Verify latest adjustment
        latest = await tracker.get_latest_adjustment("test")
        assert latest is not None
        assert latest.adjustment_type == "auto"
        assert latest.ece_before is not None
