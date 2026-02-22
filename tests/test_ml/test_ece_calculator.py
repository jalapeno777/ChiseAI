"""Tests for outcome-based ECE calculator and updater.

This module tests the ECE calculator and updater services, ensuring:
- 10-bin calibration (0-10%, 10-20%, ..., 90-100%)
- Per-signal-type ECE (entry, exit, SL, TP)
- Daily updates within 5 minutes
- Historical tracking with degradation >0.15 triggers alert
- API endpoint <200ms response

Coverage target: 80%+
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from confidence.ece import ECECalculator, SignalType
from ml.calibration.ece_calculator import (
    ECECalculationRequest,
    ECECalculationResponse,
    InMemoryOutcomeDataStore,
    OutcomeBasedECECalculator,
    PredictionOutcomeRecord,
    calculate_ece_from_outcomes,
)
from ml.calibration.ece_updater import (
    ECE_CRITICAL_THRESHOLD,
    ECE_DEGRADATION_THRESHOLD,
    ECEUpdateService,
    LoggingAlertHandler,
    MAX_UPDATE_DURATION_SECONDS,
    UpdateConfig,
    create_default_service,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_records():
    """Create sample prediction-outcome records for testing."""
    base_time = datetime.now(UTC) - timedelta(days=1)

    records = []
    # Create records with varying confidence levels and outcomes
    for i in range(100):
        confidence = 0.05 + (i / 100) * 0.9  # 0.05 to 0.95
        # Make predictions somewhat calibrated (higher confidence = higher accuracy)
        outcome = 1 if confidence > 0.5 else 0
        # Add some noise
        if i % 10 == 0:
            outcome = 1 - outcome

        record = PredictionOutcomeRecord(
            prediction_id=f"pred-{i:03d}",
            confidence=confidence,
            outcome=outcome,
            signal_type=SignalType.ENTRY if i < 50 else SignalType.EXIT,
            strategy_id="test_strategy",
            timestamp=base_time + timedelta(minutes=i),
        )
        records.append(record)

    return records


@pytest.fixture
def multi_strategy_records():
    """Create records for multiple strategies."""
    base_time = datetime.now(UTC) - timedelta(days=1)
    strategies = ["strategy_a", "strategy_b", "strategy_c"]
    signal_types = [
        SignalType.ENTRY,
        SignalType.EXIT,
        SignalType.STOP_LOSS,
        SignalType.TAKE_PROFIT,
    ]

    records = []
    for i in range(200):
        confidence = 0.1 + (i % 10) * 0.09  # Spread across bins
        outcome = 1 if confidence > 0.5 else 0

        record = PredictionOutcomeRecord(
            prediction_id=f"pred-{i:03d}",
            confidence=confidence,
            outcome=outcome,
            signal_type=signal_types[i % 4],
            strategy_id=strategies[i % 3],
            timestamp=base_time + timedelta(minutes=i),
        )
        records.append(record)

    return records


@pytest.fixture
async def populated_store(sample_records):
    """Create an in-memory store populated with sample records."""
    store = InMemoryOutcomeDataStore()
    await store.add_records(sample_records)
    return store


@pytest.fixture
async def multi_strategy_store(multi_strategy_records):
    """Create a store with multiple strategies."""
    store = InMemoryOutcomeDataStore()
    await store.add_records(multi_strategy_records)
    return store


@pytest.fixture
def mock_history_tracker():
    """Create a mock history tracker."""
    tracker = MagicMock()
    tracker.record_ece = AsyncMock(return_value=True)
    return tracker


@pytest.fixture
def mock_alert_handler():
    """Create a mock alert handler."""
    handler = MagicMock()
    handler.handle_degradation_alert = AsyncMock()
    return handler


# ============================================================================
# ECECalculator Tests
# ============================================================================


class TestOutcomeBasedECECalculator:
    """Test the OutcomeBasedECECalculator class."""

    @pytest.mark.asyncio
    async def test_calculate_with_valid_data(self, populated_store):
        """Test ECE calculation with valid data."""
        calculator = OutcomeBasedECECalculator(store=populated_store)

        request = ECECalculationRequest(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
            days=2,
            min_samples=10,
        )

        response = await calculator.calculate(request)

        assert response.success is True
        assert response.ece_result is not None
        assert response.sample_count >= 10
        assert response.calculation_time_ms > 0
        assert 0 <= response.ece_result.ece <= 1
        assert response.ece_result.n_bins == 10

    @pytest.mark.asyncio
    async def test_calculate_without_store(self):
        """Test ECE calculation fails without store."""
        calculator = OutcomeBasedECECalculator(store=None)

        request = ECECalculationRequest(strategy_id="test")
        response = await calculator.calculate(request)

        assert response.success is False
        assert response.ece_result is None
        assert "store not initialized" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_calculate_insufficient_samples(self, populated_store):
        """Test ECE calculation with insufficient samples."""
        calculator = OutcomeBasedECECalculator(store=populated_store)

        request = ECECalculationRequest(
            strategy_id="nonexistent_strategy",
            min_samples=1000,  # More than available
        )

        response = await calculator.calculate(request)

        assert response.success is False
        assert "insufficient samples" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_calculate_response_time(self, populated_store):
        """Test ECE calculation completes within 200ms."""
        calculator = OutcomeBasedECECalculator(store=populated_store)

        request = ECECalculationRequest(
            strategy_id="test_strategy",
            days=2,
        )

        response = await calculator.calculate(request)

        # API endpoint should respond in <200ms
        assert response.calculation_time_ms < 200, (
            f"Calculation took {response.calculation_time_ms:.2f}ms, "
            "exceeding 200ms threshold"
        )

    @pytest.mark.asyncio
    async def test_calculate_from_outcomes_convenience(self, populated_store):
        """Test convenience method calculate_from_outcomes."""
        calculator = OutcomeBasedECECalculator(store=populated_store)

        result = await calculator.calculate_from_outcomes(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
            days=2,
            min_samples=10,
        )

        assert result is not None
        assert 0 <= result.ece <= 1
        assert result.n_bins == 10
        assert result.signal_type == SignalType.ENTRY

    @pytest.mark.asyncio
    async def test_calculate_per_signal_type(self, populated_store):
        """Test per-signal-type ECE calculation."""
        calculator = OutcomeBasedECECalculator(store=populated_store)

        results = await calculator.calculate_per_signal_type(
            strategy_id="test_strategy",
            days=2,
            min_samples=5,
        )

        assert len(results) == 4  # All 4 signal types

        # Check that ENTRY and EXIT have results (they have data)
        assert SignalType.ENTRY in results
        assert SignalType.EXIT in results

    @pytest.mark.asyncio
    async def test_calculate_all_strategies(self, multi_strategy_store):
        """Test ECE calculation for all strategies."""
        calculator = OutcomeBasedECECalculator(store=multi_strategy_store)

        results = await calculator.calculate_all_strategies(
            days=2,
            min_samples=5,
        )

        assert len(results) == 3  # 3 strategies
        assert "strategy_a" in results
        assert "strategy_b" in results
        assert "strategy_c" in results

    @pytest.mark.asyncio
    async def test_ten_bin_calibration(self, populated_store):
        """Test that 10-bin calibration is used."""
        calculator = OutcomeBasedECECalculator(store=populated_store, n_bins=10)

        result = await calculator.calculate_from_outcomes(
            strategy_id="test_strategy",
            days=2,
        )

        assert result.n_bins == 10
        assert len(result.bins) == 10

        # Check bin ranges
        for i, bin_obj in enumerate(result.bins):
            expected_start = i * 0.1
            expected_end = (i + 1) * 0.1
            assert abs(bin_obj.bin_start - expected_start) < 0.001
            assert abs(bin_obj.bin_end - expected_end) < 0.001

    @pytest.mark.asyncio
    async def test_set_store(self, populated_store):
        """Test setting store after initialization."""
        calculator = OutcomeBasedECECalculator(store=None)
        calculator.set_store(populated_store)

        request = ECECalculationRequest(strategy_id="test_strategy")
        response = await calculator.calculate(request)

        assert response.success is True


class TestInMemoryOutcomeDataStore:
    """Test the InMemoryOutcomeDataStore class."""

    @pytest.mark.asyncio
    async def test_add_and_fetch_records(self):
        """Test adding and fetching records."""
        store = InMemoryOutcomeDataStore()

        record = PredictionOutcomeRecord(
            prediction_id="pred-001",
            confidence=0.75,
            outcome=1,
            signal_type=SignalType.ENTRY,
            strategy_id="test",
            timestamp=datetime.now(UTC),
        )

        await store.add_record(record)
        records = await store.fetch_prediction_outcomes()

        assert len(records) == 1
        assert records[0].prediction_id == "pred-001"

    @pytest.mark.asyncio
    async def test_fetch_with_filters(self, sample_records):
        """Test fetching with strategy and signal type filters."""
        store = InMemoryOutcomeDataStore()
        await store.add_records(sample_records)

        # Filter by strategy
        records = await store.fetch_prediction_outcomes(strategy_id="test_strategy")
        assert len(records) == len(sample_records)

        # Filter by signal type
        entry_records = await store.fetch_prediction_outcomes(
            signal_type=SignalType.ENTRY
        )
        assert len(entry_records) == 50

        # Filter by time
        since = datetime.now(UTC) - timedelta(hours=12)
        recent_records = await store.fetch_prediction_outcomes(since=since)
        assert len(recent_records) < len(sample_records)

    @pytest.mark.asyncio
    async def test_get_sample_count(self, sample_records):
        """Test sample count method."""
        store = InMemoryOutcomeDataStore()
        await store.add_records(sample_records)

        count = await store.get_sample_count()
        assert count == len(sample_records)

        entry_count = await store.get_sample_count(signal_type=SignalType.ENTRY)
        assert entry_count == 50

    @pytest.mark.asyncio
    async def test_clear(self, sample_records):
        """Test clearing the store."""
        store = InMemoryOutcomeDataStore()
        await store.add_records(sample_records)

        await store.clear()

        records = await store.fetch_prediction_outcomes()
        assert len(records) == 0


# ============================================================================
# ECE Updater Tests
# ============================================================================


class TestUpdateConfig:
    """Test the UpdateConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = UpdateConfig()

        assert config.update_time_utc == "00:00"
        assert config.lookback_days == 30
        assert config.min_samples == 10
        assert config.n_bins == 10
        assert config.ece_alert_threshold == ECE_DEGRADATION_THRESHOLD
        assert config.enable_alerts is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = UpdateConfig(
            update_time_utc="02:30",
            lookback_days=7,
            min_samples=50,
            ece_alert_threshold=0.2,
        )

        assert config.update_time_utc == "02:30"
        assert config.lookback_days == 7
        assert config.min_samples == 50
        assert config.ece_alert_threshold == 0.2

    def test_invalid_time_format(self):
        """Test that invalid time format raises error."""
        with pytest.raises(ValueError, match="Invalid update_time_utc"):
            UpdateConfig(update_time_utc="25:00")

        with pytest.raises(ValueError, match="Invalid update_time_utc"):
            UpdateConfig(update_time_utc="invalid")

    def test_get_next_update_time(self):
        """Test next update time calculation."""
        config = UpdateConfig(update_time_utc="14:00")

        # Test from a specific time
        from_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        next_update = config.get_next_update_time(from_time)

        assert next_update.hour == 14
        assert next_update.minute == 0
        assert next_update.date() == from_time.date()

    def test_get_next_update_time_next_day(self):
        """Test next update time rolls to next day."""
        config = UpdateConfig(update_time_utc="08:00")

        # Test from after the update time
        from_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        next_update = config.get_next_update_time(from_time)

        assert next_update.hour == 8
        assert next_update.date() == from_time.date() + timedelta(days=1)


class TestECEUpdateService:
    """Test the ECEUpdateService class."""

    @pytest.mark.asyncio
    async def test_service_start_stop(self, populated_store, mock_history_tracker):
        """Test service start and stop."""
        config = UpdateConfig()
        service = ECEUpdateService(config, populated_store, mock_history_tracker)

        assert not service.is_running

        await service.start()
        assert service.is_running

        await service.stop()
        assert not service.is_running

    @pytest.mark.asyncio
    async def test_trigger_update(self, populated_store, mock_history_tracker):
        """Test triggering a manual update."""
        config = UpdateConfig(min_samples=5)
        service = ECEUpdateService(config, populated_store, mock_history_tracker)

        result = await service.trigger_update()

        assert result.success is True
        assert result.total_strategies >= 1
        assert "test_strategy" in result.strategy_results

        # Check that ECE results were stored
        assert mock_history_tracker.record_ece.called

    @pytest.mark.asyncio
    async def test_trigger_update_with_alerts(
        self, populated_store, mock_history_tracker, mock_alert_handler
    ):
        """Test that alerts are triggered for high ECE."""
        # Create records with poorly calibrated predictions
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        records = []
        for i in range(100):
            # High confidence but low accuracy (miscalibrated)
            record = PredictionOutcomeRecord(
                prediction_id=f"pred-{i:03d}",
                confidence=0.95,  # Very confident
                outcome=0,  # But wrong
                signal_type=SignalType.ENTRY,
                strategy_id="miscalibrated_strategy",
                timestamp=base_time + timedelta(minutes=i),
            )
            records.append(record)

        await store.add_records(records)

        config = UpdateConfig(
            min_samples=10,
            ece_alert_threshold=0.15,
            enable_alerts=True,
        )
        service = ECEUpdateService(
            config, store, mock_history_tracker, mock_alert_handler
        )

        result = await service.trigger_update()

        # Should have triggered alerts for high ECE
        assert result.alerts_triggered > 0
        assert mock_alert_handler.handle_degradation_alert.called

    @pytest.mark.asyncio
    async def test_update_duration_sla(
        self, multi_strategy_store, mock_history_tracker
    ):
        """Test that update completes within 5 minutes SLA."""
        config = UpdateConfig(min_samples=5)
        service = ECEUpdateService(config, multi_strategy_store, mock_history_tracker)

        result = await service.trigger_update()

        # Should complete within 5 minutes (300 seconds)
        assert result.total_duration_ms < MAX_UPDATE_DURATION_SECONDS * 1000, (
            f"Update took {result.total_duration_ms / 1000:.1f}s, "
            f"exceeding {MAX_UPDATE_DURATION_SECONDS}s SLA"
        )

    @pytest.mark.asyncio
    async def test_per_signal_type_calculation(
        self, multi_strategy_store, mock_history_tracker
    ):
        """Test that ECE is calculated per signal type."""
        config = UpdateConfig(min_samples=5)
        service = ECEUpdateService(config, multi_strategy_store, mock_history_tracker)

        result = await service.trigger_update()

        # Check that each strategy has per-signal-type results
        for strategy_id, strategy_result in result.strategy_results.items():
            if strategy_result.success:
                assert len(strategy_result.per_signal_type) == 4  # All 4 signal types

                for signal_type in SignalType:
                    assert signal_type in strategy_result.per_signal_type
                    signal_ece = strategy_result.per_signal_type[signal_type]
                    assert 0 <= signal_ece.ece <= 1

    @pytest.mark.asyncio
    async def test_no_records_handling(self, mock_history_tracker):
        """Test handling when no records are available."""
        store = InMemoryOutcomeDataStore()
        config = UpdateConfig()
        service = ECEUpdateService(config, store, mock_history_tracker)

        result = await service.trigger_update()

        # Should succeed but with no strategies
        assert result.success is True
        assert result.total_strategies == 0

    @pytest.mark.asyncio
    async def test_get_status(self, populated_store, mock_history_tracker):
        """Test getting service status."""
        config = UpdateConfig(update_time_utc="03:00")
        service = ECEUpdateService(config, populated_store, mock_history_tracker)

        status = service.get_status()

        assert status["running"] is False
        assert status["config"]["update_time_utc"] == "03:00"
        assert "next_update" in status

    @pytest.mark.asyncio
    async def test_get_next_update_time(self, populated_store, mock_history_tracker):
        """Test getting next update time."""
        config = UpdateConfig(update_time_utc="06:00")
        service = ECEUpdateService(config, populated_store, mock_history_tracker)

        next_update = await service.get_next_update_time()

        assert next_update.hour == 6
        assert next_update.minute == 0


class TestLoggingAlertHandler:
    """Test the LoggingAlertHandler class."""

    @pytest.mark.asyncio
    async def test_degradation_alert(self, caplog):
        """Test degradation alert logging."""
        handler = LoggingAlertHandler()

        with caplog.at_level("WARNING"):
            await handler.handle_degradation_alert(
                strategy_id="test",
                signal_type=SignalType.ENTRY,
                ece=0.18,
                threshold=0.15,
            )

        assert "DEGRADATION ALERT" in caplog.text
        assert "test" in caplog.text
        assert "0.18" in caplog.text

    @pytest.mark.asyncio
    async def test_critical_alert(self, caplog):
        """Test critical alert logging."""
        handler = LoggingAlertHandler()

        with caplog.at_level("ERROR"):
            await handler.handle_degradation_alert(
                strategy_id="test",
                signal_type=SignalType.EXIT,
                ece=0.28,
                threshold=0.15,
            )

        assert "CRITICAL ECE ALERT" in caplog.text
        assert "0.28" in caplog.text


# ============================================================================
# Integration Tests
# ============================================================================


class TestECEIntegration:
    """Integration tests for ECE calculator and updater."""

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test complete ECE workflow from records to alerts."""
        # Create store with calibrated data
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        records = []
        # Create well-calibrated predictions
        # For each confidence level, outcome should match that confidence
        for bin_idx in range(10):
            confidence = 0.05 + bin_idx * 0.1  # 0.05, 0.15, ..., 0.95
            # For well-calibrated: accuracy should match confidence
            # Create 20 samples per bin with accuracy ~ confidence
            n_correct = int(20 * confidence)
            n_wrong = 20 - n_correct

            for i in range(20):
                outcome = 1 if i < n_correct else 0

                record = PredictionOutcomeRecord(
                    prediction_id=f"bin{bin_idx}-{i:02d}",
                    confidence=confidence,
                    outcome=outcome,
                    signal_type=SignalType.ENTRY if bin_idx < 5 else SignalType.EXIT,
                    strategy_id="calibrated_strategy",
                    timestamp=base_time + timedelta(minutes=bin_idx * 20 + i),
                )
                records.append(record)

        await store.add_records(records)

        # Calculate ECE
        calculator = OutcomeBasedECECalculator(store=store)
        result = await calculator.calculate_from_outcomes(
            strategy_id="calibrated_strategy",
            days=2,
        )

        # Well-calibrated model should have reasonable ECE
        # Allow for some variance due to sampling
        assert (
            result.ece < 0.3
        ), f"ECE {result.ece:.4f} higher than expected for calibrated model"

    @pytest.mark.asyncio
    async def test_all_signal_types(self):
        """Test ECE calculation for all signal types."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        # Create records for all signal types
        for signal_type in SignalType:
            for i in range(25):
                record = PredictionOutcomeRecord(
                    prediction_id=f"{signal_type.value}-{i:02d}",
                    confidence=0.5 + (i % 5) * 0.1,
                    outcome=i % 2,
                    signal_type=signal_type,
                    strategy_id="multi_signal_strategy",
                    timestamp=base_time + timedelta(minutes=i),
                )
                await store.add_record(record)

        # Calculate per signal type
        calculator = OutcomeBasedECECalculator(store=store)
        results = await calculator.calculate_per_signal_type(
            strategy_id="multi_signal_strategy",
            min_samples=5,
        )

        # All signal types should have results
        for signal_type in SignalType:
            assert signal_type in results
            response = results[signal_type]
            if response.success:
                assert response.ece_result is not None

    @pytest.mark.asyncio
    async def test_convenience_function(self):
        """Test the calculate_ece_from_outcomes convenience function."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        # Add some records
        for i in range(50):
            record = PredictionOutcomeRecord(
                prediction_id=f"pred-{i:02d}",
                confidence=0.5,
                outcome=i % 2,
                signal_type=SignalType.ENTRY,
                strategy_id="test",
                timestamp=base_time + timedelta(minutes=i),
            )
            await store.add_record(record)

        # Use convenience function
        result = await calculate_ece_from_outcomes(
            store=store,
            strategy_id="test",
            signal_type=SignalType.ENTRY,
            days=2,
        )

        assert result is not None
        assert result.n_bins == 10

    @pytest.mark.asyncio
    async def test_scheduled_service(self, populated_store, mock_history_tracker):
        """Test that scheduled service starts and can be stopped."""
        config = UpdateConfig(update_time_utc="23:59")  # Far in the future
        service = ECEUpdateService(config, populated_store, mock_history_tracker)

        # Start service
        await service.start()
        assert service.is_running

        # Check status
        status = service.get_status()
        assert status["running"] is True
        assert status["config"]["update_time_utc"] == "23:59"

        # Stop service
        await service.stop()
        assert not service.is_running

    @pytest.mark.asyncio
    async def test_create_default_service(self, populated_store, mock_history_tracker):
        """Test the create_default_service factory function."""
        service = await create_default_service(
            store=populated_store,
            history_tracker=mock_history_tracker,
            update_time_utc="01:00",
        )

        assert isinstance(service, ECEUpdateService)
        assert service.config.update_time_utc == "01:00"


# ============================================================================
# Acceptance Criteria Tests
# ============================================================================


class TestAcceptanceCriteria:
    """Tests that verify all acceptance criteria are met."""

    @pytest.mark.asyncio
    async def test_acceptance_10_bin_calibration(self):
        """AC1: 10-bin calibration (0-10%, 10-20%, ..., 90-100%)."""
        store = InMemoryOutcomeDataStore()
        calculator = OutcomeBasedECECalculator(store=store, n_bins=10)

        base_time = datetime.now(UTC) - timedelta(days=1)

        # Add records across all confidence ranges
        for bin_idx in range(10):
            confidence = 0.05 + bin_idx * 0.1  # Center of each bin
            for i in range(10):
                record = PredictionOutcomeRecord(
                    prediction_id=f"bin{bin_idx}-{i}",
                    confidence=confidence,
                    outcome=1 if confidence > 0.5 else 0,
                    signal_type=SignalType.ENTRY,
                    strategy_id="test",
                    timestamp=base_time + timedelta(minutes=bin_idx * 10 + i),
                )
                await store.add_record(record)

        result = await calculator.calculate_from_outcomes(
            strategy_id="test",
            days=2,
        )

        # Verify 10 bins with correct ranges
        assert result.n_bins == 10
        assert len(result.bins) == 10

        expected_ranges = [
            (0.0, 0.1),
            (0.1, 0.2),
            (0.2, 0.3),
            (0.3, 0.4),
            (0.4, 0.5),
            (0.5, 0.6),
            (0.6, 0.7),
            (0.7, 0.8),
            (0.8, 0.9),
            (0.9, 1.0),
        ]

        for i, (expected_start, expected_end) in enumerate(expected_ranges):
            bin_obj = result.bins[i]
            assert (
                abs(bin_obj.bin_start - expected_start) < 0.001
            ), f"Bin {i} start should be {expected_start}, got {bin_obj.bin_start}"
            assert (
                abs(bin_obj.bin_end - expected_end) < 0.001
            ), f"Bin {i} end should be {expected_end}, got {bin_obj.bin_end}"

    @pytest.mark.asyncio
    async def test_acceptance_per_signal_type(self):
        """AC2: Per-signal-type ECE (entry, exit, SL, TP)."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        # Add records for all signal types
        for signal_type in SignalType:
            for i in range(20):
                record = PredictionOutcomeRecord(
                    prediction_id=f"{signal_type.value}-{i}",
                    confidence=0.5 + (i % 5) * 0.1,
                    outcome=i % 2,
                    signal_type=signal_type,
                    strategy_id="test",
                    timestamp=base_time + timedelta(minutes=i),
                )
                await store.add_record(record)

        calculator = OutcomeBasedECECalculator(store=store)
        results = await calculator.calculate_per_signal_type(
            strategy_id="test",
            min_samples=5,
        )

        # Verify all 4 signal types
        assert SignalType.ENTRY in results
        assert SignalType.EXIT in results
        assert SignalType.STOP_LOSS in results
        assert SignalType.TAKE_PROFIT in results

        # Each should have a result
        for signal_type in SignalType:
            assert results[signal_type].ece_result is not None

    @pytest.mark.asyncio
    async def test_acceptance_daily_update_duration(self, mock_history_tracker):
        """AC3: Daily updates within 5 minutes."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        # Add substantial data
        signal_types = list(SignalType)
        for i in range(1000):
            record = PredictionOutcomeRecord(
                prediction_id=f"pred-{i:04d}",
                confidence=0.1 + (i % 10) * 0.09,
                outcome=i % 2,
                signal_type=signal_types[i % len(signal_types)],
                strategy_id="test",
                timestamp=base_time + timedelta(minutes=i),
            )
            await store.add_record(record)

        config = UpdateConfig(min_samples=10)
        service = ECEUpdateService(config, store, mock_history_tracker)

        result = await service.trigger_update()

        # Must complete within 5 minutes (300 seconds)
        assert result.total_duration_ms < 300000, (
            f"Update took {result.total_duration_ms / 1000:.1f}s, "
            "exceeding 5 minute SLA"
        )

    @pytest.mark.asyncio
    async def test_acceptance_degradation_alert(self, mock_history_tracker):
        """AC4: Historical tracking with degradation >0.15 triggers alert."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        # Create poorly calibrated predictions (high ECE)
        for i in range(100):
            record = PredictionOutcomeRecord(
                prediction_id=f"pred-{i:03d}",
                confidence=0.95,  # Very confident
                outcome=0,  # But always wrong
                signal_type=SignalType.ENTRY,
                strategy_id="degraded_strategy",
                timestamp=base_time + timedelta(minutes=i),
            )
            await store.add_record(record)

        mock_handler = MagicMock()
        mock_handler.handle_degradation_alert = AsyncMock()

        config = UpdateConfig(
            min_samples=10,
            ece_alert_threshold=0.15,
            enable_alerts=True,
        )
        service = ECEUpdateService(config, store, mock_history_tracker, mock_handler)

        result = await service.trigger_update()

        # Should trigger alerts for degradation
        assert result.alerts_triggered > 0
        assert mock_handler.handle_degradation_alert.called

    @pytest.mark.asyncio
    async def test_acceptance_api_response_time(self):
        """AC5: API endpoint <200ms response."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        # Add test data
        for i in range(100):
            record = PredictionOutcomeRecord(
                prediction_id=f"pred-{i:03d}",
                confidence=0.5,
                outcome=i % 2,
                signal_type=SignalType.ENTRY,
                strategy_id="test",
                timestamp=base_time + timedelta(minutes=i),
            )
            await store.add_record(record)

        calculator = OutcomeBasedECECalculator(store=store)

        request = ECECalculationRequest(
            strategy_id="test",
            days=2,
        )

        response = await calculator.calculate(request)

        # API must respond in less than 200ms
        assert response.calculation_time_ms < 200, (
            f"API response took {response.calculation_time_ms:.2f}ms, "
            "exceeding 200ms threshold"
        )


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_empty_predictions(self):
        """Test handling of empty predictions."""
        store = InMemoryOutcomeDataStore()
        calculator = OutcomeBasedECECalculator(store=store)

        request = ECECalculationRequest(strategy_id="nonexistent")
        response = await calculator.calculate(request)

        assert response.success is False
        assert "insufficient samples" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_single_sample(self):
        """Test handling of single sample."""
        store = InMemoryOutcomeDataStore()

        record = PredictionOutcomeRecord(
            prediction_id="pred-001",
            confidence=0.75,
            outcome=1,
            signal_type=SignalType.ENTRY,
            strategy_id="test",
            timestamp=datetime.now(UTC),
        )
        await store.add_record(record)

        calculator = OutcomeBasedECECalculator(store=store)

        request = ECECalculationRequest(
            strategy_id="test",
            min_samples=10,  # Require more than available
        )
        response = await calculator.calculate(request)

        assert response.success is False
        assert response.sample_count == 1

    @pytest.mark.asyncio
    async def test_invalid_confidence_values(self):
        """Test handling of invalid confidence values."""
        # The underlying ECECalculator should handle validation
        calculator = ECECalculator(n_bins=10)

        # Invalid predictions (outside [0,1])
        with pytest.raises(ValueError, match="Predictions must be in range"):
            calculator.calculate(predictions=[1.5, 0.5], outcomes=[1, 0])

        with pytest.raises(ValueError, match="Predictions must be in range"):
            calculator.calculate(predictions=[-0.5, 0.5], outcomes=[1, 0])

    @pytest.mark.asyncio
    async def test_invalid_outcomes(self):
        """Test handling of invalid outcome values."""
        calculator = ECECalculator(n_bins=10)

        # Invalid outcomes (not 0 or 1)
        with pytest.raises(ValueError, match="Outcomes must be binary"):
            calculator.calculate(predictions=[0.5, 0.7], outcomes=[2, 0])

        with pytest.raises(ValueError, match="Outcomes must be binary"):
            calculator.calculate(predictions=[0.5, 0.7], outcomes=[0, -1])


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance and load tests."""

    @pytest.mark.asyncio
    async def test_large_dataset_performance(self):
        """Test performance with large dataset."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=30)

        # Add 10,000 records
        signal_types = [
            SignalType.ENTRY,
            SignalType.EXIT,
            SignalType.STOP_LOSS,
            SignalType.TAKE_PROFIT,
        ]
        records = []
        for i in range(10000):
            record = PredictionOutcomeRecord(
                prediction_id=f"pred-{i:05d}",
                confidence=0.1 + (i % 10) * 0.09,
                outcome=i % 2,
                signal_type=signal_types[i % 4],
                strategy_id="test",
                timestamp=base_time + timedelta(minutes=i),
            )
            records.append(record)

        await store.add_records(records)

        calculator = OutcomeBasedECECalculator(store=store)

        request = ECECalculationRequest(
            strategy_id="test",
            days=30,
        )

        response = await calculator.calculate(request)

        assert response.success is True
        # Even with 10k records, should complete reasonably fast
        assert (
            response.calculation_time_ms < 1000
        ), f"Large dataset calculation took {response.calculation_time_ms:.2f}ms"

    @pytest.mark.asyncio
    async def test_concurrent_calculations(self):
        """Test concurrent ECE calculations."""
        store = InMemoryOutcomeDataStore()
        base_time = datetime.now(UTC) - timedelta(days=1)

        # Add records for multiple strategies
        strategies = [
            "strategy_a",
            "strategy_b",
            "strategy_c",
            "strategy_d",
            "strategy_e",
        ]
        for i in range(500):
            record = PredictionOutcomeRecord(
                prediction_id=f"pred-{i:03d}",
                confidence=0.5,
                outcome=i % 2,
                signal_type=SignalType.ENTRY,
                strategy_id=strategies[i % 5],
                timestamp=base_time + timedelta(minutes=i),
            )
            await store.add_record(record)

        calculator = OutcomeBasedECECalculator(store=store)

        # Run concurrent calculations
        tasks = [
            calculator.calculate(ECECalculationRequest(strategy_id=s))
            for s in strategies
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        for response in results:
            assert response.success is True
            assert response.ece_result is not None


# ============================================================================
# Constants Tests
# ============================================================================


def test_degradation_threshold_constant():
    """Test that degradation threshold is 0.15."""
    assert ECE_DEGRADATION_THRESHOLD == 0.15


def test_critical_threshold_constant():
    """Test that critical threshold is defined."""
    assert ECE_CRITICAL_THRESHOLD == 0.25


def test_max_update_duration_constant():
    """Test that max update duration is 300 seconds (5 minutes)."""
    assert MAX_UPDATE_DURATION_SECONDS == 300


# ============================================================================
# Coverage Helpers
# ============================================================================


@pytest.mark.asyncio
async def test_calculate_ece_from_outcomes_raises_on_failure():
    """Test that calculate_ece_from_outcomes raises ValueError on failure."""
    store = InMemoryOutcomeDataStore()

    with pytest.raises(ValueError, match="Insufficient samples"):
        await calculate_ece_from_outcomes(
            store=store,
            strategy_id="nonexistent",
        )
