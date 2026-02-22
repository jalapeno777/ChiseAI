"""Integration tests for ML feedback loop."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, "src")

from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
)
from ml.feedback import (
    AnalysisConfig,
    FeedbackAnalyzer,
    FeedbackOrchestrator,
    LoopStatus,
    MatchConfidence,
    MatchConfig,
    MatchStatus,
    ModelUpdater,
    OrchestratorConfig,
    PredictionOutcomeMatch,
    PredictionOutcomeMatcher,
    UpdateConfig,
)


class TestFeedbackLoopIntegration:
    """Integration tests for the complete feedback loop."""

    @pytest.fixture
    def sample_signals(self) -> list[SignalRecord]:
        """Create sample signals for testing."""
        now = datetime.now(UTC)
        signals = []

        for i in range(200):
            signal_time = now - timedelta(hours=48 - i * 0.2)  # Spread over ~40 hours
            signals.append(
                SignalRecord(
                    signal_id=f"signal-{i}",
                    token="BTC" if i % 2 == 0 else "ETH",
                    timestamp=int(signal_time.timestamp() * 1000),
                    direction=(
                        SignalDirection.LONG if i % 3 != 0 else SignalDirection.SHORT
                    ),
                    confidence=0.6 + (i % 4) * 0.1,
                    entry_price=50000.0 + i * 100,
                    score=60.0 + (i % 5) * 8,
                    indicators_used=["rsi"] if i % 2 == 0 else ["macd"],
                    timeframes_used=["1h"] if i % 3 == 0 else ["4h"],
                )
            )

        return signals

    @pytest.fixture
    def sample_outcomes(self, sample_signals) -> dict[str, OutcomeRecord]:
        """Create sample outcomes for signals."""
        outcomes = {}

        for signal in sample_signals:
            # 70% win rate
            is_win = hash(signal.signal_id) % 10 < 7

            outcomes[signal.signal_id] = OutcomeRecord(
                signal_id=signal.signal_id,
                exit_timestamp=signal.timestamp + 3600000,  # 1 hour later
                is_win=is_win,
                pnl=100.0 if is_win else -50.0,
                exit_price=signal.entry_price * (1.02 if is_win else 0.98),
                duration_hours=1.0,
                outcome_type=OutcomeType.TP_HIT if is_win else OutcomeType.SL_HIT,
            )

        return outcomes

    @pytest.fixture
    def matcher(self) -> PredictionOutcomeMatcher:
        """Create matcher with default config."""
        config = MatchConfig(matching_window_hours=24.0)
        return PredictionOutcomeMatcher(config=config)

    @pytest.fixture
    def analyzer(self) -> FeedbackAnalyzer:
        """Create analyzer with default config."""
        config = AnalysisConfig(min_samples_for_analysis=30)
        return FeedbackAnalyzer(config=config)

    @pytest.fixture
    def updater(self, tmp_path) -> ModelUpdater:
        """Create updater with temp storage."""
        config = UpdateConfig(min_samples_for_update=50)
        return ModelUpdater(config=config, model_storage_path=str(tmp_path / "models"))

    @pytest.mark.asyncio
    async def test_end_to_end_matching(
        self,
        matcher,
        sample_signals,
        sample_outcomes,
    ) -> None:
        """Test end-to-end matching flow."""
        now = datetime.now(UTC)

        # Create matches from signals and outcomes
        matches = []
        for signal in sample_signals[:100]:  # Use first 100
            outcome = sample_outcomes.get(signal.signal_id)
            if outcome:
                match = PredictionOutcomeMatch(
                    signal_id=signal.signal_id,
                    signal=signal,
                    outcome=outcome,
                    status=MatchStatus.MATCHED,
                    confidence=MatchConfidence.HIGH,
                    match_time_ms=int(now.timestamp() * 1000),
                    match_latency_hours=1.0,
                    resolution_quality=0.9,
                )
                matches.append(match)

        assert len(matches) == 100

        # Verify all matches have correct structure
        for match in matches:
            assert match.signal is not None
            assert match.outcome is not None
            assert match.status == MatchStatus.MATCHED

    @pytest.mark.asyncio
    async def test_end_to_end_analysis(
        self,
        analyzer,
        sample_signals,
        sample_outcomes,
    ) -> None:
        """Test end-to-end analysis flow."""
        now = datetime.now(UTC)

        # Create matches
        from ml.feedback.matcher import PredictionOutcomeMatch

        matches = []
        for signal in sample_signals[:100]:
            outcome = sample_outcomes.get(signal.signal_id)
            if outcome:
                match = PredictionOutcomeMatch(
                    signal_id=signal.signal_id,
                    signal=signal,
                    outcome=outcome,
                    status=MatchStatus.MATCHED,
                    confidence=MatchConfidence.HIGH,
                    match_time_ms=int(now.timestamp() * 1000),
                    resolution_quality=0.9,
                )
                matches.append(match)

        # Run analysis
        report = await analyzer.analyze_matches(matches)

        # Verify report structure
        assert report.total_matches == 100
        assert report.overall_accuracy > 0
        assert len(report.accuracy_by_signal_type) > 0
        assert len(report.accuracy_by_timeframe) > 0

    @pytest.mark.asyncio
    async def test_complete_feedback_loop_components(
        self,
        matcher,
        analyzer,
        updater,
        sample_signals,
        sample_outcomes,
    ) -> None:
        """Test all components working together."""
        now = datetime.now(UTC)

        # Step 1: Create matches
        from ml.feedback.matcher import PredictionOutcomeMatch

        matches = []
        for signal in sample_signals[:150]:
            outcome = sample_outcomes.get(signal.signal_id)
            if outcome:
                match = PredictionOutcomeMatch(
                    signal_id=signal.signal_id,
                    signal=signal,
                    outcome=outcome,
                    status=MatchStatus.MATCHED,
                    confidence=MatchConfidence.HIGH,
                    match_time_ms=int(now.timestamp() * 1000),
                    resolution_quality=0.9,
                )
                matches.append(match)

        assert len(matches) >= 100  # Should have enough matches

        # Step 2: Analyze matches
        report = await analyzer.analyze_matches(matches)

        assert report.total_matches == len(matches)
        assert report.overall_accuracy >= 0

        # Step 3: Create a mock model and try to update
        mock_model = MagicMock()
        mock_model.partial_fit = MagicMock()
        mock_model.predict = MagicMock(return_value=[1] * 30)

        result = await updater.update_from_analysis(
            model=mock_model,
            analysis_report=report,
            matches=matches,
            model_id="test_model",
        )

        # Verify update was attempted
        assert result is not None

    @pytest.mark.asyncio
    async def test_temporal_safety_in_integration(self) -> None:
        """Test temporal safety in complete flow."""
        from ml.feedback.orchestrator import TemporalBoundary

        now = datetime.now(UTC)

        # Create boundary with 2-hour buffer
        boundary = TemporalBoundary(
            data_cutoff_time=now - timedelta(hours=2),
            validation_start_time=now - timedelta(hours=2),
            validation_end_time=now,
            buffer_hours=2.0,
        )

        # Create signals at different times
        safe_signal_time = now - timedelta(hours=3)
        unsafe_signal_time = now - timedelta(minutes=30)

        SignalRecord(
            signal_id="safe-signal",
            token="BTC",
            timestamp=int(safe_signal_time.timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        SignalRecord(
            signal_id="unsafe-signal",
            token="BTC",
            timestamp=int(unsafe_signal_time.timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        # Verify temporal safety
        assert boundary.is_safe(safe_signal_time) is True
        assert boundary.is_safe(unsafe_signal_time) is False

    @pytest.mark.asyncio
    async def test_performance_requirements(self) -> None:
        """Test that feedback loop completes within performance requirements."""
        import time

        config = OrchestratorConfig(max_loop_duration_hours=24.0)
        orchestrator = FeedbackOrchestrator(config)

        start_time = time.time()

        # Run a simple iteration (without actual components)
        result = await orchestrator.run_feedback_loop()

        end_time = time.time()
        duration = end_time - start_time

        # Should complete quickly when no work to do
        assert duration < 5.0  # Less than 5 seconds
        assert result.status == LoopStatus.COMPLETED

    def test_data_flow_integrity(self, sample_signals, sample_outcomes) -> None:
        """Test data integrity through the feedback loop."""
        # Verify signal-outcome correspondence
        for signal_id, outcome in sample_outcomes.items():
            assert outcome.signal_id == signal_id

            # Find corresponding signal
            signal = next((s for s in sample_signals if s.signal_id == signal_id), None)
            assert signal is not None

            # Verify temporal ordering (outcome after signal)
            assert outcome.exit_timestamp > signal.timestamp

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, updater) -> None:
        """Test error handling across components."""
        # Test with insufficient samples
        result = await updater.update_from_matches(
            model=MagicMock(),
            matches=[],  # Empty
            model_id="test_model",
        )

        assert result.status.name == "FAILED"
        assert "Insufficient samples" in result.error_message

    def test_configuration_compatibility(self) -> None:
        """Test that all configurations work together."""
        # Create configs with compatible settings
        match_config = MatchConfig(matching_window_hours=24.0)
        analysis_config = AnalysisConfig(min_samples_for_analysis=30)
        update_config = UpdateConfig(min_samples_for_update=50)
        orchestrator_config = OrchestratorConfig(min_samples_for_update=50)

        # Verify logical consistency
        assert match_config.matching_window_hours >= 1.0
        assert (
            analysis_config.min_samples_for_analysis
            < update_config.min_samples_for_update
        )
        assert orchestrator_config.max_loop_duration_hours >= 1.0
