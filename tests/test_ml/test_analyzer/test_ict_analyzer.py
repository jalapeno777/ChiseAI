"""Tests for ICT analyzer module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from ml.analyzer.ict_analyzer import (
    ICTAnalysisConfig,
    ICTAnalysisReport,
    ICTAnalyzer,
    ICTDriftIndicator,
    ICTDriftSeverity,
    ICTSignalPerformance,
)
from ml.feedback.prediction_outcome_matcher_ict import (
    ICTMatchConfidence,
    ICTMatchStatus,
    ICTPredictionMatch,
)
from signal_generation.registry.signal_types import ICTSignalType


@dataclass
class MockICTM黄帝Match:
    """Mock ICT prediction match for testing."""

    signal_id: str
    signal_type: ICTSignalType
    direction: str
    outcome_correct: bool | None = True
    confidence: float = 0.75
    latency_hours: float = 2.0
    match_status: ICTMatchStatus = ICTMatchStatus.MATCHED
    timestamp: datetime = field(default_factory=datetime.now)


class TestICTAnalysisConfig:
    """Tests for ICTAnalysisConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ICTAnalysisConfig()

        assert config.min_samples_for_analysis == 30
        assert config.accuracy_degradation_threshold == 0.1
        assert config.confidence_drop_threshold == 0.15
        assert config.drift_detection_window_days == 7
        assert config.enable_drift_detection is True

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = ICTAnalysisConfig(
            min_samples_for_analysis=50,
            accuracy_degradation_threshold=0.15,
            enable_drift_detection=False,
        )

        assert config.min_samples_for_analysis == 50
        assert config.accuracy_degradation_threshold == 0.15
        assert config.enable_drift_detection is False


class TestICTDriftSeverity:
    """Tests for ICTDriftSeverity enum."""

    def test_values(self) -> None:
        """Test drift severity values."""
        assert ICTDriftSeverity.NONE.value == "none"
        assert ICTDriftSeverity.LOW.value == "low"
        assert ICTDriftSeverity.MEDIUM.value == "medium"
        assert ICTDriftSeverity.HIGH.value == "high"
        assert ICTDriftSeverity.CRITICAL.value == "critical"


class TestICTSignalPerformance:
    """Tests for ICTSignalPerformance class."""

    def test_performance_creation(self) -> None:
        """Test performance creation."""
        perf = ICTSignalPerformance(
            signal_type=ICTSignalType.CVD,
            total_signals=100,
            correct_predictions=75,
        )

        assert perf.signal_type == ICTSignalType.CVD
        assert perf.total_signals == 100
        assert perf.correct_predictions == 75
        assert perf.accuracy == 0.75

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        perf = ICTSignalPerformance(
            signal_type=ICTSignalType.FVG,
            total_signals=50,
            correct_predictions=30,
            avg_confidence=0.8,
        )

        data = perf.to_dict()

        assert data["signal_type"] == "fvg"
        assert data["total_signals"] == 50
        assert data["accuracy"] == 0.6


class TestICTDriftIndicator:
    """Tests for ICTDriftIndicator class."""

    def test_drift_indicator_creation(self) -> None:
        """Test drift indicator creation."""
        indicator = ICTDriftIndicator(
            signal_type=ICTSignalType.CVD,
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.65,
            severity=ICTDriftSeverity.MEDIUM,
            recommendation="Consider retraining",
        )

        assert indicator.signal_type == ICTSignalType.CVD
        assert indicator.metric_name == "accuracy"
        assert indicator.severity == ICTDriftSeverity.MEDIUM

    def test_deviation_calculation(self) -> None:
        """Test deviation calculation."""
        indicator = ICTDriftIndicator(
            signal_type=ICTSignalType.FVG,
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.6,
        )

        # Deviation = (0.6 - 0.8) / 0.8 = -0.25
        assert indicator.deviation == pytest.approx(-0.25, abs=0.01)


class TestICTAnalysisReport:
    """Tests for ICTAnalysisReport class."""

    def test_report_creation(self) -> None:
        """Test report creation."""
        report = ICTAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_signals=100,
            overall_accuracy=0.75,
        )

        assert report.total_signals == 100
        assert report.overall_accuracy == 0.75

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        report = ICTAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_signals=100,
            overall_accuracy=0.75,
            recommendations=["Test recommendation"],
        )

        data = report.to_dict()

        assert data["total_signals"] == 100
        assert data["overall_accuracy"] == 0.75
        assert data["recommendations"] == ["Test recommendation"]


class TestICTAnalyzer:
    """Tests for ICTAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> ICTAnalyzer:
        """Create analyzer fixture."""
        return ICTAnalyzer()

    def test_is_bos_choch(self, analyzer: ICTAnalyzer) -> None:
        """Test BOS/CHoCH detection."""
        assert analyzer.is_bos_choch(ICTSignalType.CVD) is False
        assert analyzer.is_bos_choch(ICTSignalType.FVG) is False
        assert analyzer.is_bos_choch(ICTSignalType.ORDER_BLOCK) is False

    @pytest.fixture
    def sample_matches(self) -> list[ICTPredictionMatch]:
        """Create sample matches fixture."""
        matches = []
        for i in range(50):
            signal_type = (
                ICTSignalType.CVD
                if i % 3 == 0
                else ICTSignalType.FVG if i % 3 == 1 else ICTSignalType.ORDER_BLOCK
            )
            match = ICTPredictionMatch(
                signal_id=f"test-{i}",
                signal_type=signal_type,
                direction="bullish",
                predicted_direction="bullish",
                outcome_correct=(i % 3 != 0),  # 2/3 correct
                confidence=0.7 + (i % 3) * 0.1,
                match_status=ICTMatchStatus.MATCHED,
                match_confidence=ICTMatchConfidence.HIGH,
                latency_hours=2.0 + (i % 5),
            )
            matches.append(match)
        return matches

    @pytest.mark.asyncio
    async def test_analyze_ict_signals_insufficient_samples(
        self, analyzer: ICTAnalyzer
    ) -> None:
        """Test analysis with insufficient samples."""
        matches = []  # Empty list

        report = await analyzer.analyze_ict_signals(matches)

        assert report.total_signals == 0
        assert len(report.recommendations) > 0
        assert "Insufficient samples" in report.recommendations[0]

    @pytest.mark.asyncio
    async def test_analyze_ict_signals_success(
        self, analyzer: ICTAnalyzer, sample_matches: list[ICTPredictionMatch]
    ) -> None:
        """Test successful analysis."""
        report = await analyzer.analyze_ict_signals(sample_matches)

        assert report.total_signals == 50
        assert report.overall_accuracy > 0
        assert len(report.performance_by_type) > 0

    def test_analyze_by_signal_type(
        self, analyzer: ICTAnalyzer, sample_matches: list[ICTPredictionMatch]
    ) -> None:
        """Test analysis by signal type."""
        results = analyzer._analyze_by_signal_type(sample_matches)

        assert len(results) > 0
        # Should have CVD, FVG, and Order Block
        signal_types = [r.signal_type for r in results]
        assert ICTSignalType.CVD in signal_types
        assert ICTSignalType.FVG in signal_types
        assert ICTSignalType.ORDER_BLOCK in signal_types

    def test_calculate_overall_accuracy(
        self, analyzer: ICTAnalyzer, sample_matches: list[ICTPredictionMatch]
    ) -> None:
        """Test overall accuracy calculation."""
        accuracy = analyzer._calculate_overall_accuracy(sample_matches)

        # 2/3 of sample matches are correct
        expected_accuracy = 2 / 3
        assert accuracy == pytest.approx(expected_accuracy, abs=0.01)

    @pytest.mark.asyncio
    async def test_drift_detection_no_baseline(
        self, analyzer: ICTAnalyzer, sample_matches: list[ICTPredictionMatch]
    ) -> None:
        """Test drift detection with no baseline."""
        indicators = analyzer._detect_drift(sample_matches)

        # No baseline, no drift
        assert len(indicators) == 0

    @pytest.mark.asyncio
    async def test_drift_detection_with_baseline(
        self, analyzer: ICTAnalyzer, sample_matches: list[ICTPredictionMatch]
    ) -> None:
        """Test drift detection with baseline."""
        # Set baseline metrics
        analyzer._baseline_metrics = {
            "cvd_accuracy": 0.9,  # High baseline
            "fvg_accuracy": 0.9,
            "order_block_accuracy": 0.9,
        }

        indicators = analyzer._detect_drift(sample_matches)

        # Should detect accuracy drift since baseline is higher than actual
        assert len(indicators) > 0

    def test_generate_recommendations_low_accuracy(self, analyzer: ICTAnalyzer) -> None:
        """Test recommendations for low accuracy."""
        report = ICTAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_signals=100,
            overall_accuracy=0.4,  # Below 50%
        )

        recommendations = analyzer._generate_recommendations(report)

        assert any("below 50%" in r for r in recommendations)

    def test_generate_recommendations_high_accuracy(
        self, analyzer: ICTAnalyzer
    ) -> None:
        """Test recommendations for high accuracy."""
        report = ICTAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_signals=100,
            overall_accuracy=0.8,  # Above 70%
        )

        recommendations = analyzer._generate_recommendations(report)

        assert any("Strong overall" in r for r in recommendations)

    def test_get_confluence_weight_updates(self, analyzer: ICTAnalyzer) -> None:
        """Test getting confluence weight updates."""
        report = ICTAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_signals=100,
            overall_accuracy=0.75,
            performance_by_type=[
                ICTSignalPerformance(
                    signal_type=ICTSignalType.CVD,
                    total_signals=50,
                    correct_predictions=40,  # 80% accuracy
                ),
                ICTSignalPerformance(
                    signal_type=ICTSignalType.FVG,
                    total_signals=30,
                    correct_predictions=10,  # 33% accuracy
                ),
            ],
        )

        weight_updates = analyzer.get_confluence_weight_updates(report)

        assert "cvd" in weight_updates
        assert "fvg" in weight_updates
        assert weight_updates["cvd"] == 1.2  # High accuracy
        assert weight_updates["fvg"] == 0.8  # Low accuracy

    def test_get_drift_severity(self, analyzer: ICTAnalyzer) -> None:
        """Test drift severity determination."""
        assert analyzer._get_drift_severity(0.05) == ICTDriftSeverity.LOW
        assert analyzer._get_drift_severity(0.1) == ICTDriftSeverity.MEDIUM
        assert analyzer._get_drift_severity(0.2) == ICTDriftSeverity.HIGH
        assert analyzer._get_drift_severity(0.3) == ICTDriftSeverity.CRITICAL


class TestICTAnalyzerHealth:
    """Tests for analyzer health status."""

    @pytest.fixture
    def analyzer(self) -> ICTAnalyzer:
        """Create analyzer fixture."""
        return ICTAnalyzer()

    def test_get_health_status_no_analyses(self, analyzer: ICTAnalyzer) -> None:
        """Test health status with no analyses."""
        health = analyzer.get_health_status()

        assert health["component"] == "ICTAnalyzer"
        assert health["is_active"] is False
        assert health["total_analyses"] == 0
        assert health["is_healthy"] is False
