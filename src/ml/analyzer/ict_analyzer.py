"""ICT Signal Analyzer for ML Feedback Loop.

This module provides functionality to analyze ICT signal performance
(CVD, FVG, Order Block) and generate reports for model improvement.

Features:
- Analyze ICT signal performance by type
- Generate reports per signal type
- Identify drift or degradation
- Feed back to confluence scorer weights
- Only analyze CVD, FVG, Order Block (BOS/CHoCH excluded)

Usage:
    from ml.analyzer.ict_analyzer import (
        ICTAnalyzer,
        ICTAnalysisConfig,
        ICTAnalysisReport,
    )

    analyzer = ICTAnalyzer()
    report = await analyzer.analyze_ict_signals(matches)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from signal_generation.registry.signal_types import ICTSignalType

if TYPE_CHECKING:
    from ml.feedback.prediction_outcome_matcher_ict import (
        ICTPredictionMatch,
    )

logger = logging.getLogger(__name__)


class ICTDriftSeverity(Enum):
    """Severity level for ICT signal drift detection."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ICTAnalysisConfig:
    """Configuration for ICT signal analysis.

    Attributes:
        min_samples_for_analysis: Minimum samples needed for reliable analysis
        accuracy_degradation_threshold: Threshold for flagging accuracy drop
        confidence_drop_threshold: Threshold for flagging confidence drop
        drift_detection_window_days: Days to look back for drift detection
        enable_drift_detection: Whether to detect drift
    """

    min_samples_for_analysis: int = 30
    accuracy_degradation_threshold: float = 0.1  # 10% drop
    confidence_drop_threshold: float = 0.15  # 15% drop
    drift_detection_window_days: int = 7
    enable_drift_detection: bool = True


@dataclass
class ICTSignalPerformance:
    """Performance metrics for an ICT signal type.

    Attributes:
        signal_type: ICT signal type (CVD, FVG, Order Block)
        total_signals: Total predictions made
        correct_predictions: Correct predictions
        accuracy: Accuracy ratio (0.0-1.0)
        avg_confidence: Average signal confidence
        avg_latency_hours: Average time to outcome
        win_rate: Ratio of wins to total
    """

    signal_type: ICTSignalType
    total_signals: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    avg_confidence: float = 0.0
    avg_latency_hours: float = 0.0
    win_rate: float = 0.0

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        if self.total_signals > 0:
            self.accuracy = self.correct_predictions / self.total_signals
            if self.total_signals > 0:
                self.win_rate = self.correct_predictions / self.total_signals

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "total_signals": self.total_signals,
            "correct_predictions": self.correct_predictions,
            "accuracy": round(self.accuracy, 4),
            "avg_confidence": round(self.avg_confidence, 4),
            "avg_latency_hours": round(self.avg_latency_hours, 2),
            "win_rate": round(self.win_rate, 4),
        }


@dataclass
class ICTDriftIndicator:
    """Drift indicator for an ICT signal type.

    Attributes:
        signal_type: ICT signal type showing drift
        metric_name: Name of the metric showing drift
        baseline_value: Expected/baseline value
        current_value: Current observed value
        deviation: Deviation from baseline
        severity: Drift severity level
        recommendation: Recommended action
    """

    signal_type: ICTSignalType
    metric_name: str
    baseline_value: float = 0.0
    current_value: float = 0.0
    deviation: float = 0.0
    severity: ICTDriftSeverity = ICTDriftSeverity.NONE
    recommendation: str = ""

    def __post_init__(self) -> None:
        """Calculate deviation."""
        if self.baseline_value != 0:
            self.deviation = (self.current_value - self.baseline_value) / abs(
                self.baseline_value
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "metric_name": self.metric_name,
            "baseline_value": round(self.baseline_value, 4),
            "current_value": round(self.current_value, 4),
            "deviation": round(self.deviation, 4),
            "severity": self.severity.value,
            "recommendation": self.recommendation,
        }


@dataclass
class ICTAnalysisReport:
    """Complete ICT signal analysis report.

    Attributes:
        analysis_time: Time when analysis was performed
        total_signals: Total number of signals analyzed
        overall_accuracy: Overall prediction accuracy
        performance_by_type: Performance breakdown by signal type
        drift_indicators: Detected drift indicators
        recommendations: List of recommendations
        baseline_metrics: Baseline metrics for comparison
        metadata: Additional metadata
    """

    analysis_time: datetime
    total_signals: int = 0
    overall_accuracy: float = 0.0
    performance_by_type: list[ICTSignalPerformance] = field(default_factory=list)
    drift_indicators: list[ICTDriftIndicator] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    baseline_metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "analysis_time": self.analysis_time.isoformat(),
            "total_signals": self.total_signals,
            "overall_accuracy": round(self.overall_accuracy, 4),
            "performance_by_type": [p.to_dict() for p in self.performance_by_type],
            "drift_indicators": [d.to_dict() for d in self.drift_indicators],
            "recommendations": self.recommendations,
            "baseline_metrics": self.baseline_metrics,
            "metadata": self.metadata,
        }


class ICTAnalyzer:
    """Analyzes ICT signal performance for feedback loop.

    This class provides methods to:
    - Analyze ICT signal performance by type (CVD, FVG, Order Block)
    - Detect drift or degradation in signal accuracy
    - Generate actionable recommendations
    - Feed back to confluence scorer weights
    - Exclude BOS/CHoCH signals per BL-BOS-CHOCH-001

    Attributes:
        VALID_SIGNAL_TYPES: ICT signal types that can be analyzed (excludes BOS/CHoCH)
    """

    VALID_SIGNAL_TYPES: list[ICTSignalType] = [
        ICTSignalType.CVD,
        ICTSignalType.FVG,
        ICTSignalType.ORDER_BLOCK,
    ]

    def __init__(
        self,
        config: ICTAnalysisConfig | None = None,
        baseline_metrics: dict[str, float] | None = None,
    ) -> None:
        """Initialize the ICT analyzer.

        Args:
            config: Analysis configuration
            baseline_metrics: Optional baseline metrics for drift detection
        """
        self.config = config or ICTAnalysisConfig()
        self._baseline_metrics = baseline_metrics or {}
        self._last_analysis_time: datetime | None = None
        self._total_analyses: int = 0

    def is_bos_choch(self, signal_type: ICTSignalType) -> bool:
        """Check if a signal type is BOS/CHoCH (excluded).

        Args:
            signal_type: Signal type to check

        Returns:
            True if BOS/CHoCH, False otherwise
        """
        # BOS/CHOCH re-enabled — no longer excluded
        return False

    async def analyze_ict_signals(
        self,
        matches: list[ICTPredictionMatch],
        baseline_metrics: dict[str, float] | None = None,
    ) -> ICTAnalysisReport:
        """Analyze ICT signal performance.

        Args:
            matches: List of ICT prediction matches to analyze
            baseline_metrics: Optional baseline metrics for drift detection

        Returns:
            ICTAnalysisReport with complete analysis
        """
        if baseline_metrics:
            self._baseline_metrics = baseline_metrics

        report = ICTAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_signals=len(matches),
        )

        # Filter valid matches
        valid_matches = self._filter_valid_matches(matches)

        if len(valid_matches) < self.config.min_samples_for_analysis:
            report.recommendations.append(
                f"Insufficient samples for analysis: {len(valid_matches)} "
                f"(minimum {self.config.min_samples_for_analysis})"
            )
            return report

        # Calculate overall accuracy
        report.overall_accuracy = self._calculate_overall_accuracy(valid_matches)

        # Analyze by signal type
        report.performance_by_type = self._analyze_by_signal_type(valid_matches)

        # Detect drift
        if self.config.enable_drift_detection:
            report.drift_indicators = self._detect_drift(valid_matches)

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        # Set baseline for next analysis
        self._set_baseline_metrics(report)

        logger.info(
            f"ICT Analysis complete: {report.total_signals} signals, "
            f"{report.overall_accuracy:.2%} accuracy, "
            f"{len(report.drift_indicators)} drift indicators"
        )

        self._last_analysis_time = datetime.now(UTC)
        self._total_analyses += 1

        return report

    def _filter_valid_matches(
        self,
        matches: list[ICTPredictionMatch],
    ) -> list[ICTPredictionMatch]:
        """Filter to valid matches for analysis.

        Args:
            matches: All matches

        Returns:
            Filtered matches with outcomes
        """
        from ml.feedback.prediction_outcome_matcher_ict import ICTMatchStatus

        valid = []
        for match in matches:
            # Must be matched (not unresolved/expired)
            if match.match_status != ICTMatchStatus.MATCHED:
                continue

            # Must have outcome
            if match.outcome_correct is None:
                continue

            valid.append(match)

        return valid

    def _calculate_overall_accuracy(
        self,
        matches: list[ICTPredictionMatch],
    ) -> float:
        """Calculate overall prediction accuracy.

        Args:
            matches: Valid matches

        Returns:
            Accuracy ratio (0.0-1.0)
        """
        if not matches:
            return 0.0

        correct = sum(1 for m in matches if m.outcome_correct is True)
        return correct / len(matches)

    def _analyze_by_signal_type(
        self,
        matches: list[ICTPredictionMatch],
    ) -> list[ICTSignalPerformance]:
        """Analyze accuracy grouped by signal type.

        Args:
            matches: Valid matches

        Returns:
            List of performance metrics by signal type
        """
        from collections import defaultdict

        # Group by signal type
        by_type: dict[ICTSignalType, list[ICTPredictionMatch]] = defaultdict(list)
        for match in matches:
            by_type[match.signal_type].append(match)

        results = []
        for signal_type, type_matches in by_type.items():
            correct = sum(1 for m in type_matches if m.outcome_correct is True)

            # Calculate average confidence
            confidences = [m.confidence for m in type_matches]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            # Calculate average latency
            latencies = [m.latency_hours for m in type_matches if m.latency_hours > 0]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

            results.append(
                ICTSignalPerformance(
                    signal_type=signal_type,
                    total_signals=len(type_matches),
                    correct_predictions=correct,
                    avg_confidence=avg_confidence,
                    avg_latency_hours=avg_latency,
                )
            )

        # Sort by total signals (descending)
        results.sort(key=lambda x: x.total_signals, reverse=True)
        return results

    def _detect_drift(
        self,
        matches: list[ICTPredictionMatch],
    ) -> list[ICTDriftIndicator]:
        """Detect drift indicators.

        Args:
            matches: Valid matches

        Returns:
            List of drift indicators
        """
        indicators: list[ICTDriftIndicator] = []

        if not self._baseline_metrics:
            return indicators

        # Calculate current metrics by signal type
        from collections import defaultdict

        by_type: dict[ICTSignalType, list[ICTPredictionMatch]] = defaultdict(list)
        for match in matches:
            by_type[match.signal_type].append(match)

        for signal_type, type_matches in by_type.items():
            if not type_matches:
                continue

            # Calculate current accuracy
            correct = sum(1 for m in type_matches if m.outcome_correct is True)
            current_accuracy = correct / len(type_matches)

            # Calculate current average confidence
            current_confidence = sum(m.confidence for m in type_matches) / len(
                type_matches
            )

            # Check accuracy drift
            baseline_key = f"{signal_type.value}_accuracy"
            if baseline_key in self._baseline_metrics:
                baseline_accuracy = self._baseline_metrics[baseline_key]
                accuracy_drop = baseline_accuracy - current_accuracy

                if accuracy_drop > self.config.accuracy_degradation_threshold:
                    severity = self._get_drift_severity(accuracy_drop)
                    indicators.append(
                        ICTDriftIndicator(
                            signal_type=signal_type,
                            metric_name="accuracy",
                            baseline_value=baseline_accuracy,
                            current_value=current_accuracy,
                            severity=severity,
                            recommendation=f"Consider retraining {signal_type.value} model",
                        )
                    )

            # Check confidence drift
            baseline_conf_key = f"{signal_type.value}_confidence"
            if baseline_conf_key in self._baseline_metrics:
                baseline_confidence = self._baseline_metrics[baseline_conf_key]
                confidence_drop = baseline_confidence - current_confidence

                if confidence_drop > self.config.confidence_drop_threshold:
                    severity = self._get_drift_severity(confidence_drop)
                    indicators.append(
                        ICTDriftIndicator(
                            signal_type=signal_type,
                            metric_name="confidence",
                            baseline_value=baseline_confidence,
                            current_value=current_confidence,
                            severity=severity,
                            recommendation=f"Review {signal_type.value} feature inputs",
                        )
                    )

        return indicators

    def _get_drift_severity(self, deviation: float) -> ICTDriftSeverity:
        """Get drift severity from deviation value.

        Args:
            deviation: Deviation value (positive means drop)

        Returns:
            Drift severity level
        """
        if deviation >= 0.3:
            return ICTDriftSeverity.CRITICAL
        elif deviation >= 0.2:
            return ICTDriftSeverity.HIGH
        elif deviation >= 0.1:
            return ICTDriftSeverity.MEDIUM
        elif deviation >= 0.05:
            return ICTDriftSeverity.LOW
        return ICTDriftSeverity.NONE

    def _set_baseline_metrics(self, report: ICTAnalysisReport) -> None:
        """Set baseline metrics from analysis report.

        Args:
            report: Analysis report to extract baselines from
        """
        self._baseline_metrics = {}

        for perf in report.performance_by_type:
            self._baseline_metrics[f"{perf.signal_type.value}_accuracy"] = perf.accuracy
            self._baseline_metrics[f"{perf.signal_type.value}_confidence"] = (
                perf.avg_confidence
            )

    def _generate_recommendations(
        self,
        report: ICTAnalysisReport,
    ) -> list[str]:
        """Generate recommendations based on analysis.

        Args:
            report: Analysis report

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check overall accuracy
        if report.overall_accuracy < 0.5:
            recommendations.append(
                "Overall ICT accuracy below 50% - consider model retraining"
            )
        elif report.overall_accuracy > 0.7:
            recommendations.append(
                "Strong overall ICT performance - consider increasing signal weight"
            )

        # Check signal type performance
        for perf in report.performance_by_type:
            if perf.total_signals >= 10:
                if perf.accuracy < 0.4:
                    recommendations.append(
                        f"Low accuracy for {perf.signal_type.value} ({perf.accuracy:.1%}) - "
                        "consider reducing signal weight in confluence"
                    )
                elif perf.accuracy > 0.75:
                    recommendations.append(
                        f"High accuracy for {perf.signal_type.value} ({perf.accuracy:.1%}) - "
                        "consider increasing signal weight in confluence"
                    )

        # Check drift indicators
        for drift in report.drift_indicators:
            if drift.severity in (ICTDriftSeverity.HIGH, ICTDriftSeverity.CRITICAL):
                recommendations.append(
                    f"Critical drift in {drift.signal_type.value} {drift.metric_name}: "
                    f"{drift.recommendation}"
                )

        return recommendations

    def get_confluence_weight_updates(
        self,
        report: ICTAnalysisReport,
    ) -> dict[str, float]:
        """Get weight updates for confluence scorer.

        Args:
            report: Analysis report

        Returns:
            Dictionary mapping signal type to weight adjustment
        """
        weight_updates: dict[str, float] = {}

        for perf in report.performance_by_type:
            signal_type = perf.signal_type.value

            # Calculate weight adjustment based on accuracy
            if perf.accuracy > 0.7:
                # High accuracy - increase weight
                weight_updates[signal_type] = 1.2
            elif perf.accuracy < 0.4:
                # Low accuracy - decrease weight
                weight_updates[signal_type] = 0.8
            else:
                # Medium accuracy - keep weight
                weight_updates[signal_type] = 1.0

        return weight_updates

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for the analyzer.

        Returns:
            Health status dictionary
        """
        now = datetime.now(UTC)

        is_active = self._last_analysis_time is not None
        is_healthy = True
        reason_parts = []

        if self._last_analysis_time:
            time_since = (now - self._last_analysis_time).total_seconds()
            minutes_ago = int(time_since / 60)
            reason_parts.append(f"Last analysis {minutes_ago} minutes ago")

            if time_since > 86400:
                is_healthy = False
                reason_parts.append("No analysis in 24 hours")
        else:
            reason_parts.append("No analyses recorded")
            is_healthy = False

        reason_parts.append(f"{self._total_analyses} total analyses performed")

        return {
            "component": "ICTAnalyzer",
            "is_active": is_active,
            "last_analysis_time": (
                self._last_analysis_time.isoformat()
                if self._last_analysis_time
                else None
            ),
            "total_analyses": self._total_analyses,
            "is_healthy": is_healthy,
            "reason": "; ".join(reason_parts),
        }
