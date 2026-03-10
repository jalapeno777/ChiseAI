"""Tests for feedback analyzer module."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, "src")

from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
)
from ml.feedback.analyzer import (
    AccuracyBySignalType,
    AccuracyByTimeframe,
    AnalysisConfig,
    DriftIndicator,
    DriftSeverity,
    FeatureImportanceChange,
    FeedbackAnalysisReport,
    FeedbackAnalyzer,
    MarketRegime,
    RegimePerformance,
)
from ml.feedback.matcher import (
    MatchConfidence,
    MatchStatus,
    PredictionOutcomeMatch,
)


class TestAnalysisConfig:
    """Tests for AnalysisConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = AnalysisConfig()

        assert config.min_samples_for_analysis == 30
        assert config.confidence_threshold == 0.5
        assert config.accuracy_degradation_threshold == 0.1
        assert config.drift_detection_window_days == 7
        assert config.feature_importance_threshold == 0.05
        assert config.enable_regime_analysis is True

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = AnalysisConfig(
            min_samples_for_analysis=50,
            confidence_threshold=0.7,
            enable_regime_analysis=False,
        )

        assert config.min_samples_for_analysis == 50
        assert config.confidence_threshold == 0.7
        assert config.enable_regime_analysis is False


class TestAccuracyBySignalType:
    """Tests for AccuracyBySignalType class."""

    def test_accuracy_calculation(self) -> None:
        """Test accuracy calculation."""
        acc = AccuracyBySignalType(
            signal_type="LONG_rsi",
            total_signals=100,
            correct_predictions=75,
        )

        assert acc.accuracy == 0.75

    def test_accuracy_zero_signals(self) -> None:
        """Test accuracy with zero signals."""
        acc = AccuracyBySignalType(
            signal_type="LONG_rsi",
            total_signals=0,
            correct_predictions=0,
        )

        assert acc.accuracy == 0.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        acc = AccuracyBySignalType(
            signal_type="LONG_rsi",
            total_signals=100,
            correct_predictions=75,
            avg_pnl=50.5,
            confidence=0.8,
        )

        data = acc.to_dict()

        assert data["signal_type"] == "LONG_rsi"
        assert data["total_signals"] == 100
        assert data["accuracy"] == 0.75
        assert data["avg_pnl"] == 50.5


class TestAccuracyByTimeframe:
    """Tests for AccuracyByTimeframe class."""

    def test_accuracy_calculation(self) -> None:
        """Test accuracy calculation."""
        acc = AccuracyByTimeframe(
            timeframe="1h",
            total_signals=50,
            correct_predictions=40,
        )

        assert acc.accuracy == 0.8

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        acc = AccuracyByTimeframe(
            timeframe="4h",
            total_signals=100,
            correct_predictions=60,
            avg_pnl=25.0,
        )

        data = acc.to_dict()

        assert data["timeframe"] == "4h"
        assert data["accuracy"] == 0.6


class TestRegimePerformance:
    """Tests for RegimePerformance class."""

    def test_regime_performance_creation(self) -> None:
        """Test regime performance creation."""
        perf = RegimePerformance(
            regime=MarketRegime.BULLISH,
            total_signals=100,
            accuracy=0.75,
            avg_pnl=100.0,
            sharpe_ratio=1.5,
        )

        assert perf.regime == MarketRegime.BULLISH
        assert perf.accuracy == 0.75

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        perf = RegimePerformance(
            regime=MarketRegime.BEARISH,
            total_signals=50,
            accuracy=0.6,
            avg_pnl=-20.0,
            sharpe_ratio=0.8,
        )

        data = perf.to_dict()

        assert data["regime"] == "bearish"
        assert data["accuracy"] == 0.6
        assert data["sharpe_ratio"] == 0.8


class TestFeatureImportanceChange:
    """Tests for FeatureImportanceChange class."""

    def test_change_calculation(self) -> None:
        """Test change calculation."""
        change = FeatureImportanceChange(
            feature_name="rsi",
            old_importance=0.3,
            new_importance=0.4,
        )

        assert change.absolute_change == pytest.approx(0.1, abs=0.0001)
        assert change.relative_change == pytest.approx(33.33, rel=0.01)

    def test_zero_old_importance(self) -> None:
        """Test with zero old importance."""
        change = FeatureImportanceChange(
            feature_name="new_feature",
            old_importance=0.0,
            new_importance=0.2,
        )

        assert change.absolute_change == 0.2
        assert change.relative_change == 0.0  # Division by zero protection

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        change = FeatureImportanceChange(
            feature_name="macd",
            old_importance=0.25,
            new_importance=0.20,
            is_significant=True,
        )

        data = change.to_dict()

        assert data["feature_name"] == "macd"
        assert data["absolute_change"] == 0.05
        assert data["is_significant"] is True


class TestDriftIndicator:
    """Tests for DriftIndicator class."""

    def test_deviation_calculation(self) -> None:
        """Test deviation calculation."""
        drift = DriftIndicator(
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.7,
            severity=DriftSeverity.MEDIUM,
        )

        assert drift.deviation == pytest.approx(-0.125, abs=0.001)

    def test_zero_baseline(self) -> None:
        """Test with zero baseline."""
        drift = DriftIndicator(
            metric_name="accuracy",
            baseline_value=0.0,
            current_value=0.5,
        )

        assert drift.deviation == 0.0  # Division by zero protection

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        drift = DriftIndicator(
            metric_name="precision",
            baseline_value=0.75,
            current_value=0.65,
            severity=DriftSeverity.HIGH,
            recommendation="Retrain model",
        )

        data = drift.to_dict()

        assert data["metric_name"] == "precision"
        assert data["severity"] == "high"
        assert data["recommendation"] == "Retrain model"


class TestFeedbackAnalysisReport:
    """Tests for FeedbackAnalysisReport class."""

    def test_report_creation(self) -> None:
        """Test report creation."""
        report = FeedbackAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_matches=100,
            overall_accuracy=0.75,
        )

        assert report.total_matches == 100
        assert report.overall_accuracy == 0.75

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        report = FeedbackAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_matches=100,
            overall_accuracy=0.75,
            recommendations=["Test recommendation"],
        )

        data = report.to_dict()

        assert data["total_matches"] == 100
        assert data["overall_accuracy"] == 0.75
        assert data["recommendations"] == ["Test recommendation"]


class TestFeedbackAnalyzer:
    """Tests for FeedbackAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> FeedbackAnalyzer:
        """Create analyzer fixture."""
        return FeedbackAnalyzer()

    @pytest.fixture
    def sample_matches(self) -> list[PredictionOutcomeMatch]:
        """Create sample matches fixture."""
        matches = []
        for i in range(50):
            signal = SignalRecord(
                signal_id=f"test-{i}",
                token="BTC",
                timestamp=1000000 + i * 1000,
                direction=SignalDirection.LONG if i % 2 == 0 else SignalDirection.SHORT,
                confidence=0.7 + (i % 3) * 0.1,
                entry_price=50000.0,
                score=70.0 + (i % 5) * 5,
                indicators_used=["rsi"] if i % 2 == 0 else ["macd"],
                timeframes_used=["1h"] if i % 3 == 0 else ["4h"],
            )

            outcome = OutcomeRecord(
                signal_id=f"test-{i}",
                exit_timestamp=signal.timestamp + 10000,
                is_win=i % 3 != 0,
                pnl=100.0 if i % 3 != 0 else -50.0,
                exit_price=signal.entry_price * (1.02 if i % 3 != 0 else 0.98),
                duration_hours=2.78,
                outcome_type=OutcomeType.TP_HIT if i % 3 != 0 else OutcomeType.SL_HIT,
            )

            match = PredictionOutcomeMatch(
                signal_id=f"test-{i}",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                resolution_quality=0.9,
            )
            matches.append(match)

        return matches

    @pytest.mark.asyncio
    async def test_analyze_matches_insufficient_samples(self, analyzer) -> None:
        """Test analysis with insufficient samples."""
        matches = []  # Empty list

        report = await analyzer.analyze_matches(matches)

        assert report.total_matches == 0
        assert len(report.recommendations) > 0
        assert "Insufficient samples" in report.recommendations[0]

    @pytest.mark.asyncio
    async def test_analyze_matches_success(self, analyzer, sample_matches) -> None:
        """Test successful analysis."""
        report = await analyzer.analyze_matches(sample_matches)

        assert report.total_matches == 50
        assert report.overall_accuracy > 0
        assert len(report.accuracy_by_signal_type) > 0

    def test_filter_valid_matches(self, analyzer, sample_matches) -> None:
        """Test filtering valid matches."""
        valid = analyzer._filter_valid_matches(sample_matches)

        assert len(valid) == 50  # All sample matches are valid

    def test_filter_valid_matches_excludes_unmatched(self, analyzer) -> None:
        """Test that unmatched signals are filtered out."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        unmatched_match = PredictionOutcomeMatch(
            signal_id="test-1",
            signal=signal,
            status=MatchStatus.UNRESOLVED,
            confidence=MatchConfidence.UNKNOWN,
        )

        valid = analyzer._filter_valid_matches([unmatched_match])

        assert len(valid) == 0

    def test_calculate_overall_accuracy(self, analyzer, sample_matches) -> None:
        """Test overall accuracy calculation."""
        accuracy = analyzer._calculate_overall_accuracy(sample_matches)

        # 2/3 of sample matches are wins (i % 3 != 0)
        expected_accuracy = 2 / 3
        assert accuracy == pytest.approx(expected_accuracy, abs=0.01)

    def test_is_correct_prediction_tp_hit(self, analyzer) -> None:
        """Test correct prediction detection for TP hit."""
        outcome = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1100000,
            is_win=True,
            pnl=100.0,
            exit_price=51000.0,
            duration_hours=1.0,
            outcome_type=OutcomeType.TP_HIT,
        )

        match = MagicMock()
        match.outcome = outcome

        assert analyzer._is_correct_prediction(match) is True

    def test_is_correct_prediction_sl_hit(self, analyzer) -> None:
        """Test correct prediction detection for SL hit."""
        outcome = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1100000,
            is_win=False,
            pnl=-50.0,
            exit_price=49000.0,
            duration_hours=1.0,
            outcome_type=OutcomeType.SL_HIT,
        )

        match = MagicMock()
        match.outcome = outcome

        assert analyzer._is_correct_prediction(match) is False

    def test_analyze_by_signal_type(self, analyzer, sample_matches) -> None:
        """Test analysis by signal type."""
        results = analyzer._analyze_by_signal_type(sample_matches)

        assert len(results) > 0
        # Should have at least LONG_rsi and SHORT_macd types
        signal_types = [r.signal_type for r in results]
        assert any("LONG" in st for st in signal_types)
        assert any("SHORT" in st for st in signal_types)

    def test_analyze_by_timeframe(self, analyzer, sample_matches) -> None:
        """Test analysis by timeframe."""
        results = analyzer._analyze_by_timeframe(sample_matches)

        assert len(results) > 0
        # Should have 1h and 4h timeframes
        timeframes = [r.timeframe for r in results]
        assert "1h" in timeframes or "4h" in timeframes

    def test_classify_regime_unknown(self, analyzer) -> None:
        """Test regime classification with no metadata."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        match = MagicMock()
        match.signal = signal

        regime = analyzer._classify_regime(match)

        assert regime == MarketRegime.UNKNOWN

    def test_classify_regime_from_metadata(self, analyzer) -> None:
        """Test regime classification from metadata."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
            metadata={"market_regime": "bullish"},
        )

        match = MagicMock()
        match.signal = signal

        regime = analyzer._classify_regime(match)

        assert regime == MarketRegime.BULLISH

    def test_detect_drift_no_baseline(self, analyzer, sample_matches) -> None:
        """Test drift detection with no baseline."""
        indicators = analyzer._detect_drift(sample_matches)

        assert len(indicators) == 0  # No baseline, no drift

    def test_detect_drift_with_accuracy_drop(self, analyzer, sample_matches) -> None:
        """Test drift detection with accuracy drop."""
        analyzer.set_baseline_metrics({"accuracy": 0.9})  # High baseline

        indicators = analyzer._detect_drift(sample_matches)

        # Should detect accuracy drop
        accuracy_drift = [i for i in indicators if i.metric_name == "accuracy"]
        assert len(accuracy_drift) > 0

    def test_generate_recommendations_low_accuracy(self, analyzer) -> None:
        """Test recommendations for low accuracy."""
        report = FeedbackAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_matches=100,
            overall_accuracy=0.4,  # Below 50%
        )

        recommendations = analyzer._generate_recommendations(report)

        assert any("below 50%" in r for r in recommendations)

    def test_generate_recommendations_high_accuracy(self, analyzer) -> None:
        """Test recommendations for high accuracy."""
        report = FeedbackAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_matches=100,
            overall_accuracy=0.8,  # Above 70%
        )

        recommendations = analyzer._generate_recommendations(report)

        assert any("Strong overall performance" in r for r in recommendations)

    def test_calculate_feature_importance_changes(self, analyzer) -> None:
        """Test feature importance change calculation."""
        old_importance = {"rsi": 0.3, "macd": 0.2, "bb": 0.1}
        new_importance = {"rsi": 0.35, "macd": 0.15, "bb": 0.1}

        changes = analyzer.calculate_feature_importance_changes(
            old_importance, new_importance
        )

        assert len(changes) > 0
        # RSI changed by 0.05, MACD by 0.05
        rsi_change = next((c for c in changes if c.feature_name == "rsi"), None)
        assert rsi_change is not None
        assert rsi_change.absolute_change == pytest.approx(0.05, abs=0.0001)

    def test_set_and_get_baseline_metrics(self, analyzer) -> None:
        """Test setting and getting baseline metrics."""
        metrics = {"accuracy": 0.75, "precision": 0.8}

        analyzer.set_baseline_metrics(metrics)
        retrieved = analyzer.get_baseline_metrics()

        assert retrieved == metrics


class TestAnalyzerHealth:
    """Tests for analyzer health status."""

    @pytest.fixture
    def analyzer(self) -> FeedbackAnalyzer:
        """Create analyzer fixture."""
        return FeedbackAnalyzer()

    @pytest.fixture
    def sample_matches(self) -> list[PredictionOutcomeMatch]:
        """Create sample matches fixture."""
        matches = []
        for i in range(50):
            signal = SignalRecord(
                signal_id=f"test-{i}",
                token="BTC",
                timestamp=1000000 + i * 1000,
                direction=SignalDirection.LONG if i % 2 == 0 else SignalDirection.SHORT,
                confidence=0.7 + (i % 3) * 0.1,
                entry_price=50000.0,
                score=70.0 + (i % 5) * 5,
                indicators_used=["rsi"] if i % 2 == 0 else ["macd"],
                timeframes_used=["1h"] if i % 3 == 0 else ["4h"],
            )

            outcome = OutcomeRecord(
                signal_id=f"test-{i}",
                exit_timestamp=signal.timestamp + 10000,
                is_win=i % 3 != 0,
                pnl=100.0 if i % 3 != 0 else -50.0,
                exit_price=signal.entry_price * (1.02 if i % 3 != 0 else 0.98),
                duration_hours=2.78,
                outcome_type=OutcomeType.TP_HIT if i % 3 != 0 else OutcomeType.SL_HIT,
            )

            match = PredictionOutcomeMatch(
                signal_id=f"test-{i}",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                resolution_quality=0.9,
            )
            matches.append(match)

        return matches

    def test_get_health_status_no_analyses(self, analyzer) -> None:
        """Test health status with no analyses."""
        health = analyzer.get_health_status()

        assert health["component"] == "FeedbackAnalyzer"
        assert health["is_active"] is False
        assert health["total_analyses"] == 0
        assert health["is_healthy"] is False
        assert "No analyses recorded" in health["reason"]
        assert health["last_analysis_time"] is None

    @pytest.mark.asyncio
    async def test_get_health_status_after_analysis(self, analyzer) -> None:
        """Test health status after running analysis."""
        from datetime import UTC, datetime

        # Create sample matches for testing
        sample_matches = []
        for i in range(50):
            signal = SignalRecord(
                signal_id=f"test-{i}",
                token="BTC",
                timestamp=1000000 + i * 1000,
                direction=SignalDirection.LONG if i % 2 == 0 else SignalDirection.SHORT,
                confidence=0.7 + (i % 3) * 0.1,
                entry_price=50000.0,
                score=70.0 + (i % 5) * 5,
                indicators_used=["rsi"] if i % 2 == 0 else ["macd"],
                timeframes_used=["1h"] if i % 3 == 0 else ["4h"],
            )

            outcome = OutcomeRecord(
                signal_id=f"test-{i}",
                exit_timestamp=signal.timestamp + 10000,
                is_win=i % 3 != 0,
                pnl=100.0 if i % 3 != 0 else -50.0,
                exit_price=signal.entry_price * (1.02 if i % 3 != 0 else 0.98),
                duration_hours=2.78,
                outcome_type=OutcomeType.TP_HIT if i % 3 != 0 else OutcomeType.SL_HIT,
            )

            match = PredictionOutcomeMatch(
                signal_id=f"test-{i}",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                resolution_quality=0.9,
            )
            sample_matches.append(match)

        # Run analysis to populate health metrics
        await analyzer.analyze_matches(sample_matches)

        health = analyzer.get_health_status()

        assert health["is_active"] is True
        assert health["total_analyses"] == 1
        assert health["is_healthy"] is True
        assert "Last analysis" in health["reason"]
        assert "1 total analyses performed" in health["reason"]
        assert health["last_analysis_time"] is not None

    def test_get_health_status_tracks_analyses(self, analyzer) -> None:
        """Test that health status tracks multiple analyses."""
        from datetime import UTC, datetime

        # Simulate multiple analyses by directly setting the counters
        analyzer._total_analyses = 5
        analyzer._last_analysis_time = datetime.now(UTC)

        health = analyzer.get_health_status()

        assert health["total_analyses"] == 5
        assert "5 total analyses performed" in health["reason"]
