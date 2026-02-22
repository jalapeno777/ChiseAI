"""Tests for temporal safety in feedback loop."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, "src")

from market_analysis.signal_storage.models import SignalDirection, SignalRecord
from ml.feedback.orchestrator import (
    FeedbackOrchestrator,
    OrchestratorConfig,
    TemporalBoundary,
    TemporalSafetyMode,
)


class TestTemporalSafety:
    """Tests for temporal safety enforcement."""

    @pytest.fixture
    def strict_orchestrator(self) -> FeedbackOrchestrator:
        """Create orchestrator with strict temporal safety."""
        config = OrchestratorConfig(temporal_safety_mode=TemporalSafetyMode.STRICT)
        return FeedbackOrchestrator(config)

    @pytest.fixture
    def moderate_orchestrator(self) -> FeedbackOrchestrator:
        """Create orchestrator with moderate temporal safety."""
        config = OrchestratorConfig(temporal_safety_mode=TemporalSafetyMode.MODERATE)
        return FeedbackOrchestrator(config)

    def test_strict_boundary_buffer(self, strict_orchestrator) -> None:
        """Test strict mode uses 2-hour buffer."""
        boundary = strict_orchestrator._calculate_temporal_boundary()

        assert boundary.buffer_hours == 2.0

        # Data cutoff should be at least 2 hours ago
        now = datetime.now(timezone.utc)
        min_cutoff = now - timedelta(hours=2, minutes=5)  # Allow 5 min tolerance
        assert boundary.data_cutoff_time <= now - timedelta(hours=2)
        assert boundary.data_cutoff_time >= min_cutoff

    def test_moderate_boundary_buffer(self, moderate_orchestrator) -> None:
        """Test moderate mode uses 1-hour buffer."""
        boundary = moderate_orchestrator._calculate_temporal_boundary()

        assert boundary.buffer_hours == 1.0

        # Data cutoff should be at least 1 hour ago
        now = datetime.now(timezone.utc)
        assert boundary.data_cutoff_time <= now - timedelta(hours=1)

    def test_temporal_boundary_is_safe(self) -> None:
        """Test temporal boundary safety check."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=2)

        boundary = TemporalBoundary(
            data_cutoff_time=cutoff,
            validation_start_time=cutoff,
            validation_end_time=now,
            buffer_hours=2.0,
        )

        # Safe: 3 hours ago (before cutoff)
        safe_time = now - timedelta(hours=3)
        assert boundary.is_safe(safe_time) is True

        # Unsafe: 1 hour ago (after cutoff)
        unsafe_time = now - timedelta(hours=1)
        assert boundary.is_safe(unsafe_time) is False

        # Boundary case: exactly at cutoff
        assert boundary.is_safe(cutoff) is True

    def test_enforce_temporal_safety_filters_future(self, strict_orchestrator) -> None:
        """Test that future data is filtered out."""
        now = datetime.now(timezone.utc)
        boundary = TemporalBoundary(
            data_cutoff_time=now - timedelta(hours=2),
            validation_start_time=now - timedelta(hours=2),
            validation_end_time=now,
            buffer_hours=2.0,
        )

        # Create matches with different timestamps
        safe_match = MagicMock()
        safe_match.signal_id = "safe-1"
        safe_match.signal = SignalRecord(
            signal_id="safe-1",
            token="BTC",
            timestamp=int((now - timedelta(hours=3)).timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        unsafe_match = MagicMock()
        unsafe_match.signal_id = "unsafe-1"
        unsafe_match.signal = SignalRecord(
            signal_id="unsafe-1",
            token="BTC",
            timestamp=int((now - timedelta(minutes=30)).timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        matches = [safe_match, unsafe_match]
        filtered = strict_orchestrator._enforce_temporal_safety(matches, boundary)

        assert len(filtered) == 1
        assert filtered[0].signal_id == "safe-1"

    def test_enforce_temporal_safety_all_safe(self, strict_orchestrator) -> None:
        """Test when all data is within safe window."""
        now = datetime.now(timezone.utc)
        boundary = TemporalBoundary(
            data_cutoff_time=now - timedelta(hours=2),
            validation_start_time=now - timedelta(hours=2),
            validation_end_time=now,
            buffer_hours=2.0,
        )

        # All matches are safe (3+ hours ago)
        matches = []
        for i in range(5):
            match = MagicMock()
            match.signal = SignalRecord(
                signal_id=f"safe-{i}",
                token="BTC",
                timestamp=int((now - timedelta(hours=3 + i)).timestamp() * 1000),
                direction=SignalDirection.LONG,
                confidence=0.8,
                entry_price=50000.0,
                score=75.0,
            )
            matches.append(match)

        filtered = strict_orchestrator._enforce_temporal_safety(matches, boundary)

        assert len(filtered) == 5

    def test_enforce_temporal_safety_all_unsafe(self, strict_orchestrator) -> None:
        """Test when all data is outside safe window."""
        now = datetime.now(timezone.utc)
        boundary = TemporalBoundary(
            data_cutoff_time=now - timedelta(hours=2),
            validation_start_time=now - timedelta(hours=2),
            validation_end_time=now,
            buffer_hours=2.0,
        )

        # All matches are unsafe (within last hour)
        matches = []
        for i in range(5):
            match = MagicMock()
            match.signal_id = f"unsafe-{i}"
            match.signal = SignalRecord(
                signal_id=f"unsafe-{i}",
                token="BTC",
                timestamp=int((now - timedelta(minutes=30 + i * 5)).timestamp() * 1000),
                direction=SignalDirection.LONG,
                confidence=0.8,
                entry_price=50000.0,
                score=75.0,
            )
            matches.append(match)

        filtered = strict_orchestrator._enforce_temporal_safety(matches, boundary)

        assert len(filtered) == 0

    def test_no_data_leakage_in_training_window(self, strict_orchestrator) -> None:
        """Test that no future data leaks into training window."""
        now = datetime.now(timezone.utc)
        boundary = strict_orchestrator._calculate_temporal_boundary()

        # Simulate a prediction made "now" with outcome recorded later
        prediction_time = now - timedelta(hours=4)  # Safe
        outcome_time = now - timedelta(minutes=30)  # Unsafe (after cutoff)

        match = MagicMock()
        match.signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=int(prediction_time.timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        # Signal time is safe, so it should be included
        assert boundary.is_safe(prediction_time) is True

    def test_validation_window_separation(self) -> None:
        """Test that validation window is separate from training window."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=2)

        boundary = TemporalBoundary(
            data_cutoff_time=cutoff,
            validation_start_time=cutoff,
            validation_end_time=now,
            buffer_hours=2.0,
        )

        # Training data must be before cutoff
        training_time = now - timedelta(hours=3)
        assert boundary.is_safe(training_time) is True

        # Validation data is between cutoff and now
        validation_time = now - timedelta(minutes=30)
        assert boundary.is_safe(validation_time) is False

        # This ensures no overlap between training and validation

    def test_temporal_safety_mode_comparison(self) -> None:
        """Test different temporal safety modes."""
        now = datetime.now(timezone.utc)

        # Strict mode: 2 hour buffer
        strict_config = OrchestratorConfig(
            temporal_safety_mode=TemporalSafetyMode.STRICT
        )
        strict_orchestrator = FeedbackOrchestrator(strict_config)
        strict_boundary = strict_orchestrator._calculate_temporal_boundary()

        # Moderate mode: 1 hour buffer
        moderate_config = OrchestratorConfig(
            temporal_safety_mode=TemporalSafetyMode.MODERATE
        )
        moderate_orchestrator = FeedbackOrchestrator(moderate_config)
        moderate_boundary = moderate_orchestrator._calculate_temporal_boundary()

        # Lenient mode: 0.5 hour buffer
        lenient_config = OrchestratorConfig(
            temporal_safety_mode=TemporalSafetyMode.LENIENT
        )
        lenient_orchestrator = FeedbackOrchestrator(lenient_config)
        lenient_boundary = lenient_orchestrator._calculate_temporal_boundary()

        # Verify buffer sizes
        assert strict_boundary.buffer_hours == 2.0
        assert moderate_boundary.buffer_hours == 1.0
        assert lenient_boundary.buffer_hours == 0.5

        # Strict should have earliest cutoff (most conservative)
        assert strict_boundary.data_cutoff_time < moderate_boundary.data_cutoff_time
        assert moderate_boundary.data_cutoff_time < lenient_boundary.data_cutoff_time
