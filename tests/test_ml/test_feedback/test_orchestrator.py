"""Tests for feedback orchestrator module."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import sys

sys.path.insert(0, "src")

from ml.feedback.orchestrator import (
    FeedbackOrchestrator,
    LoopIterationResult,
    LoopStatus,
    OrchestratorConfig,
    TemporalBoundary,
    TemporalSafetyMode,
)


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = OrchestratorConfig()

        assert config.max_loop_duration_hours == 24.0
        assert config.matching_window_hours == 24.0
        assert config.min_samples_for_update == 100
        assert config.temporal_safety_mode == TemporalSafetyMode.STRICT
        assert config.enable_auto_update is True
        assert config.enable_drift_detection is True
        assert config.max_retries == 3

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = OrchestratorConfig(
            max_loop_duration_hours=12.0,
            enable_auto_update=False,
            temporal_safety_mode=TemporalSafetyMode.MODERATE,
        )

        assert config.max_loop_duration_hours == 12.0
        assert config.enable_auto_update is False
        assert config.temporal_safety_mode == TemporalSafetyMode.MODERATE


class TestTemporalBoundary:
    """Tests for TemporalBoundary class."""

    def test_boundary_creation(self) -> None:
        """Test boundary creation."""
        now = datetime.now(timezone.utc)
        boundary = TemporalBoundary(
            data_cutoff_time=now - timedelta(hours=2),
            validation_start_time=now - timedelta(hours=2),
            validation_end_time=now,
            buffer_hours=2.0,
        )

        assert boundary.buffer_hours == 2.0

    def test_is_safe(self) -> None:
        """Test timestamp safety check."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        boundary = TemporalBoundary(
            data_cutoff_time=cutoff,
            validation_start_time=cutoff,
            validation_end_time=datetime.now(timezone.utc),
            buffer_hours=2.0,
        )

        # Timestamp before cutoff is safe
        safe_time = cutoff - timedelta(hours=1)
        assert boundary.is_safe(safe_time) is True

        # Timestamp after cutoff is not safe
        unsafe_time = cutoff + timedelta(hours=1)
        assert boundary.is_safe(unsafe_time) is False

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(timezone.utc)
        boundary = TemporalBoundary(
            data_cutoff_time=now,
            validation_start_time=now,
            validation_end_time=now + timedelta(hours=1),
            buffer_hours=1.0,
        )

        data = boundary.to_dict()

        assert "data_cutoff_time" in data
        assert data["buffer_hours"] == 1.0


class TestLoopIterationResult:
    """Tests for LoopIterationResult class."""

    def test_result_creation(self) -> None:
        """Test result creation."""
        result = LoopIterationResult(
            iteration_id="test-loop-001",
            start_time=datetime.now(timezone.utc),
            status=LoopStatus.RUNNING,
            total_matches=100,
        )

        assert result.iteration_id == "test-loop-001"
        assert result.status == LoopStatus.RUNNING

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = LoopIterationResult(
            iteration_id="test-loop-001",
            start_time=datetime.now(timezone.utc),
            status=LoopStatus.COMPLETED,
            total_matches=100,
            errors=["Test error"],
        )

        data = result.to_dict()

        assert data["iteration_id"] == "test-loop-001"
        assert data["status"] == "completed"
        assert data["errors"] == ["Test error"]


class TestFeedbackOrchestrator:
    """Tests for FeedbackOrchestrator class."""

    @pytest.fixture
    def orchestrator(self) -> FeedbackOrchestrator:
        """Create orchestrator fixture."""
        return FeedbackOrchestrator()

    @pytest.fixture
    def mock_matcher(self) -> MagicMock:
        """Create mock matcher."""
        from ml.feedback.matcher import MatchStatus

        matcher = AsyncMock()
        match_result = MagicMock()
        match_result.matched = 100
        match_result.total_signals = 100
        # Create valid matches with MATCHED status and outcomes
        mock_match = MagicMock()
        mock_match.status = MatchStatus.MATCHED
        mock_match.outcome = MagicMock()
        match_result.matches = [mock_match] * 100
        matcher.match_batch.return_value = match_result
        return matcher

    @pytest.fixture
    def mock_analyzer(self) -> MagicMock:
        """Create mock analyzer."""
        analyzer = AsyncMock()
        report = MagicMock()
        report.overall_accuracy = 0.75
        report.to_dict.return_value = {"overall_accuracy": 0.75}
        analyzer.analyze_matches.return_value = report
        return analyzer

    @pytest.fixture
    def mock_updater(self) -> MagicMock:
        """Create mock updater."""
        updater = AsyncMock()
        result = MagicMock()
        result.validation_metrics = {"accuracy": 0.75}
        result.to_dict.return_value = {"status": "completed"}
        updater.update_from_analysis.return_value = result
        return updater

    def test_orchestrator_creation(self) -> None:
        """Test orchestrator creation."""
        orchestrator = FeedbackOrchestrator()

        assert orchestrator.config is not None
        assert orchestrator._is_running is False

    def test_calculate_temporal_boundary_strict(self) -> None:
        """Test temporal boundary calculation in strict mode."""
        config = OrchestratorConfig(temporal_safety_mode=TemporalSafetyMode.STRICT)
        orchestrator = FeedbackOrchestrator(config)

        boundary = orchestrator._calculate_temporal_boundary()

        assert boundary.buffer_hours == 2.0
        # Cutoff should be 2 hours ago
        now = datetime.now(timezone.utc)
        assert boundary.data_cutoff_time < now
        assert boundary.data_cutoff_time > now - timedelta(hours=3)

    def test_calculate_temporal_boundary_moderate(self) -> None:
        """Test temporal boundary calculation in moderate mode."""
        config = OrchestratorConfig(temporal_safety_mode=TemporalSafetyMode.MODERATE)
        orchestrator = FeedbackOrchestrator(config)

        boundary = orchestrator._calculate_temporal_boundary()

        assert boundary.buffer_hours == 1.0

    def test_enforce_temporal_safety(self, orchestrator) -> None:
        """Test temporal safety enforcement."""
        now = datetime.now(timezone.utc)
        boundary = TemporalBoundary(
            data_cutoff_time=now - timedelta(hours=2),
            validation_start_time=now - timedelta(hours=2),
            validation_end_time=now,
            buffer_hours=2.0,
        )

        # Create mock matches
        safe_match = MagicMock()
        safe_match.signal.timestamp = int((now - timedelta(hours=3)).timestamp() * 1000)

        unsafe_match = MagicMock()
        unsafe_match.signal.timestamp = int(
            (now - timedelta(minutes=30)).timestamp() * 1000
        )
        unsafe_match.signal_id = "unsafe-1"

        matches = [safe_match, unsafe_match]
        filtered = orchestrator._enforce_temporal_safety(matches, boundary)

        assert len(filtered) == 1
        assert filtered[0] == safe_match

    @pytest.mark.asyncio
    async def test_run_feedback_loop_no_matcher(self, orchestrator) -> None:
        """Test loop execution without matcher."""
        result = await orchestrator.run_feedback_loop()

        assert result.status == LoopStatus.COMPLETED
        assert result.total_matches == 0
        assert "No matches found" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_run_feedback_loop_already_running(self, orchestrator) -> None:
        """Test loop execution when already running."""
        orchestrator._is_running = True
        orchestrator._current_iteration = LoopIterationResult(
            iteration_id="existing",
            start_time=datetime.now(timezone.utc),
            status=LoopStatus.RUNNING,
        )

        result = await orchestrator.run_feedback_loop()

        assert result.iteration_id == "existing"

    @pytest.mark.asyncio
    async def test_run_feedback_loop_success(
        self, mock_matcher, mock_analyzer, mock_updater
    ) -> None:
        """Test successful loop execution."""
        # Create mock signal tracker to enable matching phase
        mock_signal = MagicMock()
        mock_signal.signal_id = "test-123"
        mock_signal_tracker = MagicMock()
        mock_signal_tracker.get_signal_history = AsyncMock(return_value=[mock_signal])

        orchestrator = FeedbackOrchestrator(
            matcher=mock_matcher,
            analyzer=mock_analyzer,
            updater=mock_updater,
            signal_tracker=mock_signal_tracker,
        )

        # Pass a mock model to trigger the update phase
        mock_model = MagicMock()
        result = await orchestrator.run_feedback_loop(model=mock_model)

        assert result.status == LoopStatus.COMPLETED
        mock_matcher.match_batch.assert_called_once()
        mock_analyzer.analyze_matches.assert_called_once()
        mock_updater.update_from_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_feedback_loop_disabled_update(
        self, mock_matcher, mock_analyzer, mock_updater
    ) -> None:
        """Test loop with auto-update disabled."""
        config = OrchestratorConfig(enable_auto_update=False)
        orchestrator = FeedbackOrchestrator(
            config=config,
            matcher=mock_matcher,
            analyzer=mock_analyzer,
            updater=mock_updater,
        )

        result = await orchestrator.run_feedback_loop()

        assert result.status == LoopStatus.COMPLETED
        mock_updater.update_from_analysis.assert_not_called()

    def test_get_status_idle(self, orchestrator) -> None:
        """Test getting status when idle."""
        status = orchestrator.get_status()

        assert status["is_running"] is False
        assert status["current_iteration"] is None
        assert status["total_iterations"] == 0

    def test_get_status_running(self, orchestrator) -> None:
        """Test getting status when running."""
        orchestrator._is_running = True
        orchestrator._current_iteration = LoopIterationResult(
            iteration_id="test-001",
            start_time=datetime.now(timezone.utc),
            status=LoopStatus.RUNNING,
        )

        status = orchestrator.get_status()

        assert status["is_running"] is True
        assert status["current_iteration"]["iteration_id"] == "test-001"

    def test_get_iteration_history(self, orchestrator) -> None:
        """Test getting iteration history."""
        # Add some history
        for i in range(5):
            orchestrator._iteration_history.append(
                LoopIterationResult(
                    iteration_id=f"test-{i}",
                    start_time=datetime.now(timezone.utc) - timedelta(hours=i),
                    status=LoopStatus.COMPLETED if i % 2 == 0 else LoopStatus.FAILED,
                )
            )

        history = orchestrator.get_iteration_history(limit=3)

        assert len(history) == 3

    def test_get_iteration_history_filtered(self, orchestrator) -> None:
        """Test getting filtered iteration history."""
        # Add some history
        orchestrator._iteration_history = [
            LoopIterationResult(
                iteration_id="test-1",
                start_time=datetime.now(timezone.utc),
                status=LoopStatus.COMPLETED,
            ),
            LoopIterationResult(
                iteration_id="test-2",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                status=LoopStatus.FAILED,
            ),
        ]

        history = orchestrator.get_iteration_history(status=LoopStatus.COMPLETED)

        assert len(history) == 1
        assert history[0].iteration_id == "test-1"

    @pytest.mark.asyncio
    async def test_start_and_stop_scheduled(self, orchestrator) -> None:
        """Test starting and stopping scheduled execution."""
        # Start scheduled
        await orchestrator.start_scheduled()

        assert orchestrator._scheduled_task is not None
        assert not orchestrator._scheduled_task.done()

        # Stop scheduled
        await orchestrator.stop_scheduled()

        # Task should be cancelled after stopping
        assert orchestrator._scheduled_task.done()
        assert orchestrator._scheduled_task.cancelled()

    @pytest.mark.asyncio
    async def test_start_scheduled_already_running(self, orchestrator) -> None:
        """Test starting scheduled when already running."""
        orchestrator._scheduled_task = AsyncMock()
        orchestrator._scheduled_task.done.return_value = False

        await orchestrator.start_scheduled()

        # Should not create new task
        # (task is still the mock from setup)

    def test_finalize_iteration(self, orchestrator) -> None:
        """Test iteration finalization."""
        result = LoopIterationResult(
            iteration_id="test-001",
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            status=LoopStatus.RUNNING,
        )

        finalized = orchestrator._finalize_iteration(result)

        assert finalized.end_time is not None
        assert finalized.duration_seconds > 0
        assert len(orchestrator._iteration_history) == 1
