"""Tests for ECE scheduler module.

Tests cover:
- Scheduling logic and timing
- Manual trigger functionality
- ECE calculation and storage
- Error handling and retries
- Graceful start/stop
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from confidence import ECEHistoryTracker, SignalType
from confidence.ece_scheduler import (
    ECEUpdateResult,
    ECEScheduler,
    InMemoryPredictionOutcomeStore,
    SchedulerConfig,
)

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_history_tracker():
    """Create a mock ECEHistoryTracker."""
    tracker = AsyncMock(spec=ECEHistoryTracker)
    tracker.record_ece.return_value = True
    return tracker


@pytest.fixture
def sample_data_store():
    """Create an in-memory data store with sample data."""
    store = InMemoryPredictionOutcomeStore()

    # Add sample data for strategy_1
    for i in range(50):
        confidence = 0.7 + (i % 20) * 0.01
        outcome = 1 if i % 3 == 0 else 0
        store.add_prediction_outcome("strategy_1", confidence, outcome)

    # Add sample data for strategy_2
    for i in range(30):
        confidence = 0.6 + (i % 15) * 0.02
        outcome = 1 if i % 2 == 0 else 0
        store.add_prediction_outcome("strategy_2", confidence, outcome)

    store.set_active_strategies(["strategy_1", "strategy_2"])
    return store


@pytest.fixture
def scheduler(mock_history_tracker, sample_data_store):
    """Create a scheduler with mock dependencies."""
    config = SchedulerConfig(
        update_time_utc="00:00",
        min_samples=20,
    )
    return ECEScheduler(
        history_tracker=mock_history_tracker,
        data_store=sample_data_store,
        config=config,
    )


class TestSchedulerInitialization:
    """Tests for scheduler initialization."""

    def test_default_initialization(self):
        """Test scheduler with default configuration."""
        scheduler = ECEScheduler()

        assert scheduler.config.update_time_utc == "00:00"
        assert scheduler.config.min_samples == 30
        assert scheduler.is_running() is False

    def test_custom_initialization(self, mock_history_tracker, sample_data_store):
        """Test scheduler with custom configuration."""
        config = SchedulerConfig(
            update_time_utc="06:30",
            min_samples=50,
            retry_attempts=5,
        )
        scheduler = ECEScheduler(
            history_tracker=mock_history_tracker,
            data_store=sample_data_store,
            config=config,
        )

        assert scheduler.config.update_time_utc == "06:30"
        assert scheduler.config.min_samples == 50
        assert scheduler.config.retry_attempts == 5

    def test_invalid_time_format(self):
        """Test error on invalid time format."""
        config = SchedulerConfig(update_time_utc="invalid")
        scheduler = ECEScheduler(config=config)

        with pytest.raises(ValueError, match="Invalid update_time_utc"):
            scheduler._parse_update_time()

    def test_out_of_range_time(self):
        """Test error on out-of-range time values."""
        config = SchedulerConfig(update_time_utc="25:00")
        scheduler = ECEScheduler(config=config)

        with pytest.raises(ValueError, match="Invalid update_time_utc"):
            scheduler._parse_update_time()


class TestSchedulerTiming:
    """Tests for scheduler timing calculations."""

    def test_parse_update_time(self, scheduler):
        """Test time parsing."""
        hour, minute = scheduler._parse_update_time()
        assert hour == 0
        assert minute == 0

    def test_get_next_run_time_today(self, scheduler):
        """Test next run time when time hasn't passed today."""
        # Set time to 23:00 to ensure 00:00 tomorrow
        scheduler.config.update_time_utc = "23:00"

        next_run = scheduler._get_next_run_time()
        now = datetime.now(UTC)

        assert next_run.hour == 23
        assert next_run.minute == 0

        # Should be today if before 23:00, tomorrow if after
        if now.hour < 23:
            assert next_run.date() == now.date()
        else:
            assert next_run.date() == (now + timedelta(days=1)).date()

    def test_get_next_run_time_tomorrow(self, scheduler):
        """Test next run time when time has passed today."""
        # Set time to 00:00 which has likely passed today
        scheduler.config.update_time_utc = "00:00"

        next_run = scheduler._get_next_run_time()
        now = datetime.now(UTC)

        assert next_run.hour == 0
        assert next_run.minute == 0

        # If current time is after 00:00, next run should be tomorrow
        if now.hour > 0 or (now.hour == 0 and now.minute > 0):
            expected_date = (now + timedelta(days=1)).date()
        else:
            expected_date = now.date()

        assert next_run.date() == expected_date

    def test_get_seconds_until_next_run(self, scheduler):
        """Test seconds calculation."""
        scheduler.config.update_time_utc = "23:59"
        seconds = scheduler._get_seconds_until_next_run()

        # Should be positive and reasonable (less than 24 hours)
        assert 0 < seconds < 86400


class TestSchedulerStartStop:
    """Tests for scheduler start/stop functionality."""

    @pytest.mark.asyncio
    async def test_start_stop(self, scheduler):
        """Test basic start and stop."""
        assert scheduler.is_running() is False

        await scheduler.start()
        assert scheduler.is_running() is True

        await scheduler.stop()
        assert scheduler.is_running() is False

    @pytest.mark.asyncio
    async def test_double_start(self, scheduler):
        """Test starting an already running scheduler."""
        await scheduler.start()

        # Should not raise or create duplicate tasks
        await scheduler.start()
        assert scheduler.is_running() is True

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start(self, scheduler):
        """Test stopping a non-running scheduler."""
        # Should not raise
        await scheduler.stop()
        assert scheduler.is_running() is False

    @pytest.mark.asyncio
    async def test_get_next_run_while_running(self, scheduler):
        """Test getting next run time while scheduler is running."""
        await scheduler.start()

        next_run = scheduler.get_next_run()
        assert next_run is not None
        assert next_run.tzinfo == UTC

        await scheduler.stop()

    def test_get_next_run_when_not_running(self, scheduler):
        """Test getting next run time when not running."""
        next_run = scheduler.get_next_run()
        assert next_run is None


class TestManualTrigger:
    """Tests for manual trigger functionality."""

    @pytest.mark.asyncio
    async def test_trigger_all_strategies(self, scheduler, mock_history_tracker):
        """Test manual trigger for all strategies."""
        results = await scheduler.trigger_update()

        # Should have results for 2 strategies x (1 aggregate + 4 signal types)
        assert len(results) == 10  # 2 strategies x 5 calculations each

        # Check success
        successful = [r for r in results if r.success]
        assert len(successful) == 10

        # Verify history tracker was called
        assert mock_history_tracker.record_ece.call_count == 10

    @pytest.mark.asyncio
    async def test_trigger_specific_strategies(self, scheduler, mock_history_tracker):
        """Test manual trigger for specific strategies."""
        results = await scheduler.trigger_update(strategy_ids=["strategy_1"])

        # Should have results for 1 strategy x 5 calculations
        assert len(results) == 5

        # All should be for strategy_1
        for result in results:
            assert result.strategy_id == "strategy_1"

    @pytest.mark.asyncio
    async def test_trigger_no_data_store(self, mock_history_tracker):
        """Test trigger without data store configured."""
        scheduler = ECEScheduler(
            history_tracker=mock_history_tracker,
            data_store=None,
        )

        results = await scheduler.trigger_update(strategy_ids=["strategy_1"])

        # Should return 5 results (1 aggregate + 4 signal types) all with errors
        assert len(results) == 5
        for result in results:
            assert result.success is False
            assert "No data store configured" in result.error


class TestECECalculation:
    """Tests for ECE calculation during updates."""

    @pytest.mark.asyncio
    async def test_calculate_ece_success(self, scheduler, mock_history_tracker):
        """Test successful ECE calculation."""
        result = await scheduler._calculate_and_store_ece(
            strategy_id="strategy_1",
            signal_type=None,
        )

        assert result.success is True
        assert result.strategy_id == "strategy_1"
        assert result.signal_type is None
        assert result.ece is not None
        assert result.total_samples >= scheduler.config.min_samples
        assert result.error is None

        mock_history_tracker.record_ece.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_ece_insufficient_samples(self, scheduler):
        """Test ECE calculation with insufficient samples."""
        # Create store with few samples
        store = InMemoryPredictionOutcomeStore()
        store.add_prediction_outcome("low_data_strategy", 0.8, 1)
        store.add_prediction_outcome("low_data_strategy", 0.7, 0)
        store.set_active_strategies(["low_data_strategy"])

        scheduler.data_store = store

        result = await scheduler._calculate_and_store_ece(
            strategy_id="low_data_strategy",
            signal_type=None,
        )

        assert result.success is False
        assert "Insufficient samples" in result.error

    @pytest.mark.asyncio
    async def test_calculate_ece_per_signal_type(self, scheduler, mock_history_tracker):
        """Test ECE calculation per signal type."""
        result = await scheduler._calculate_and_store_ece(
            strategy_id="strategy_1",
            signal_type=SignalType.ENTRY,
        )

        assert result.success is True
        assert result.signal_type == SignalType.ENTRY

    @pytest.mark.asyncio
    async def test_calculate_ece_storage_failure(self, scheduler, mock_history_tracker):
        """Test handling of storage failure."""
        mock_history_tracker.record_ece.return_value = False

        result = await scheduler._calculate_and_store_ece(
            strategy_id="strategy_1",
            signal_type=None,
        )

        # Should still succeed calculation but storage failed
        assert result.success is False  # Storage failure means overall failure


class TestUpdateResult:
    """Tests for ECEUpdateResult dataclass."""

    def test_successful_result(self):
        """Test creation of successful result."""
        timestamp = datetime.now(UTC)
        result = ECEUpdateResult(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
            ece=0.05,
            n_bins=10,
            total_samples=100,
            timestamp=timestamp,
            success=True,
        )

        assert result.strategy_id == "test_strategy"
        assert result.signal_type == SignalType.ENTRY
        assert result.ece == 0.05
        assert result.success is True
        assert result.error is None

    def test_failed_result(self):
        """Test creation of failed result."""
        timestamp = datetime.now(UTC)
        result = ECEUpdateResult(
            strategy_id="test_strategy",
            signal_type=None,
            ece=None,
            n_bins=10,
            total_samples=0,
            timestamp=timestamp,
            success=False,
            error="Test error message",
        )

        assert result.success is False
        assert result.error == "Test error message"
        assert result.ece is None


class TestInMemoryDataStore:
    """Tests for InMemoryPredictionOutcomeStore."""

    @pytest.mark.asyncio
    async def test_add_and_retrieve(self):
        """Test adding and retrieving prediction-outcome pairs."""
        store = InMemoryPredictionOutcomeStore()

        store.add_prediction_outcome("strategy_1", 0.8, 1)
        store.add_prediction_outcome("strategy_1", 0.7, 0)
        store.add_prediction_outcome("strategy_1", 0.9, 1)

        pairs = await store.get_prediction_outcome_pairs("strategy_1")

        assert len(pairs) == 3
        assert pairs[0] == (0.8, 1)
        assert pairs[1] == (0.7, 0)
        assert pairs[2] == (0.9, 1)

    @pytest.mark.asyncio
    async def test_get_active_strategies(self):
        """Test retrieving active strategies."""
        store = InMemoryPredictionOutcomeStore()

        store.set_active_strategies(["strategy_a", "strategy_b", "strategy_c"])

        strategies = await store.get_active_strategies()

        assert len(strategies) == 3
        assert "strategy_a" in strategies
        assert "strategy_b" in strategies
        assert "strategy_c" in strategies

    @pytest.mark.asyncio
    async def test_empty_strategy(self):
        """Test retrieving non-existent strategy."""
        store = InMemoryPredictionOutcomeStore()

        pairs = await store.get_prediction_outcome_pairs("non_existent")

        assert pairs == []

    @pytest.mark.asyncio
    async def test_auto_add_to_active(self):
        """Test that adding predictions auto-adds to active strategies."""
        store = InMemoryPredictionOutcomeStore()

        store.add_prediction_outcome("new_strategy", 0.8, 1)

        strategies = await store.get_active_strategies()

        assert "new_strategy" in strategies


class TestSchedulerConfig:
    """Tests for SchedulerConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SchedulerConfig()

        assert config.update_time_utc == "00:00"
        assert config.min_samples == 30
        assert config.retry_attempts == 3
        assert config.retry_delay_seconds == 60
        assert len(config.signal_types) == 4
        assert SignalType.ENTRY in config.signal_types

    def test_custom_config(self):
        """Test custom configuration."""
        config = SchedulerConfig(
            update_time_utc="12:30",
            min_samples=100,
            retry_attempts=5,
            retry_delay_seconds=120,
            signal_types=[SignalType.ENTRY, SignalType.EXIT],
        )

        assert config.update_time_utc == "12:30"
        assert config.min_samples == 100
        assert config.retry_attempts == 5
        assert config.retry_delay_seconds == 120
        assert len(config.signal_types) == 2


class TestErrorHandling:
    """Tests for error handling in scheduler."""

    @pytest.mark.asyncio
    async def test_data_store_exception(self, scheduler):
        """Test handling of data store exception."""
        # Create a data store that raises exceptions
        failing_store = MagicMock()
        failing_store.get_active_strategies = AsyncMock(
            side_effect=Exception("DB error")
        )

        scheduler.data_store = failing_store

        # Should not raise, but return empty results
        results = await scheduler._run_daily_update()

        assert results == []

    @pytest.mark.asyncio
    async def test_calculate_exception(self, scheduler, mock_history_tracker):
        """Test handling of calculation exception."""
        # Create a data store that returns invalid data
        bad_store = InMemoryPredictionOutcomeStore()
        # Add invalid confidence values (outside 0-1 range)
        bad_store._data["bad_strategy"] = [(1.5, 1), (2.0, 0)]
        bad_store.set_active_strategies(["bad_strategy"])

        scheduler.data_store = bad_store

        result = await scheduler._calculate_and_store_ece(
            strategy_id="bad_strategy",
            signal_type=None,
        )

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_update_strategy_with_failures(self, scheduler):
        """Test that partial failures don't stop other updates."""
        # Mix of good and bad strategies
        store = InMemoryPredictionOutcomeStore()

        # Good strategy
        for i in range(30):
            store.add_prediction_outcome("good_strategy", 0.7 + i * 0.01, i % 2)

        # Bad strategy with invalid data
        store._data["bad_strategy"] = [(1.5, 1)]

        store.set_active_strategies(["good_strategy", "bad_strategy"])
        scheduler.data_store = store

        results = await scheduler._update_strategy("good_strategy")

        # Should have 5 results (1 aggregate + 4 signal types)
        assert len(results) == 5

        # Most should succeed (aggregate at least)
        successful = [r for r in results if r.success]
        assert len(successful) >= 1
