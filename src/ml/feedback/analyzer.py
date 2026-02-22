"""Feedback Analyzer for ML Model Performance Analysis.

This module provides functionality to analyze prediction accuracy,
detect model drift, and calculate feature importance changes over time.

Features:
- Analyze accuracy by signal type, timeframe, and market regime
- Calculate feature importance changes between model versions
- Detect model drift indicators
- Generate performance reports for feedback loop

Usage:
    from ml.feedback.analyzer import FeedbackAnalyzer, AnalysisConfig

    config = AnalysisConfig()
    analyzer = FeedbackAnalyzer(config)
    report = await analyzer.analyze_matches(matches)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ml.feedback.matcher import PredictionOutcomeMatch

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


class DriftSeverity(Enum):
    """Severity level for model drift detection."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AnalysisConfig:
    """Configuration for feedback analysis.

    Attributes:
        min_samples_for_analysis: Minimum samples needed for reliable analysis
        confidence_threshold: Minimum confidence for including matches
        accuracy_degradation_threshold: Threshold for flagging accuracy drop
        drift_detection_window_days: Days to look back for drift detection
        feature_importance_threshold: Threshold for significant feature change
        enable_regime_analysis: Whether to analyze by market regime
    """

    min_samples_for_analysis: int = 30
    confidence_threshold: float = 0.5
    accuracy_degradation_threshold: float = 0.1  # 10% drop
    drift_detection_window_days: int = 7
    feature_importance_threshold: float = 0.05  # 5% change
    enable_regime_analysis: bool = True


@dataclass
class AccuracyBySignalType:
    """Accuracy metrics grouped by signal type.

    Attributes:
        signal_type: Type identifier (e.g., "LONG_rsi_macd")
        total_signals: Total number of signals
        correct_predictions: Number of correct predictions
        accuracy: Accuracy ratio (0.0-1.0)
        avg_pnl: Average PnL
        confidence: Average confidence level
    """

    signal_type: str
    total_signals: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    avg_pnl: float = 0.0
    confidence: float = 0.0

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        if self.total_signals > 0:
            self.accuracy = self.correct_predictions / self.total_signals

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type,
            "total_signals": self.total_signals,
            "correct_predictions": self.correct_predictions,
            "accuracy": round(self.accuracy, 4),
            "avg_pnl": round(self.avg_pnl, 8),
            "confidence": round(self.confidence, 4),
        }


@dataclass
class AccuracyByTimeframe:
    """Accuracy metrics grouped by timeframe.

    Attributes:
        timeframe: Timeframe identifier (e.g., "1h", "4h")
        total_signals: Total number of signals
        correct_predictions: Number of correct predictions
        accuracy: Accuracy ratio (0.0-1.0)
        avg_pnl: Average PnL
    """

    timeframe: str
    total_signals: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    avg_pnl: float = 0.0

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        if self.total_signals > 0:
            self.accuracy = self.correct_predictions / self.total_signals

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timeframe": self.timeframe,
            "total_signals": self.total_signals,
            "correct_predictions": self.correct_predictions,
            "accuracy": round(self.accuracy, 4),
            "avg_pnl": round(self.avg_pnl, 8),
        }


@dataclass
class RegimePerformance:
    """Performance metrics for a specific market regime.

    Attributes:
        regime: Market regime classification
        total_signals: Total number of signals
        accuracy: Accuracy in this regime
        avg_pnl: Average PnL
        sharpe_ratio: Risk-adjusted return metric
    """

    regime: MarketRegime
    total_signals: int = 0
    accuracy: float = 0.0
    avg_pnl: float = 0.0
    sharpe_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "regime": self.regime.value,
            "total_signals": self.total_signals,
            "accuracy": round(self.accuracy, 4),
            "avg_pnl": round(self.avg_pnl, 8),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
        }


@dataclass
class FeatureImportanceChange:
    """Change in feature importance between model versions.

    Attributes:
        feature_name: Name of the feature
        old_importance: Previous importance score
        new_importance: Current importance score
        absolute_change: Absolute change in importance
        relative_change: Relative change percentage
        is_significant: Whether change exceeds threshold
    """

    feature_name: str
    old_importance: float = 0.0
    new_importance: float = 0.0
    absolute_change: float = 0.0
    relative_change: float = 0.0
    is_significant: bool = False

    def __post_init__(self) -> None:
        """Calculate changes."""
        self.absolute_change = abs(self.new_importance - self.old_importance)
        if self.old_importance > 0:
            self.relative_change = (self.absolute_change / self.old_importance) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "feature_name": self.feature_name,
            "old_importance": round(self.old_importance, 4),
            "new_importance": round(self.new_importance, 4),
            "absolute_change": round(self.absolute_change, 4),
            "relative_change": round(self.relative_change, 2),
            "is_significant": self.is_significant,
        }


@dataclass
class DriftIndicator:
    """Model drift detection result.

    Attributes:
        metric_name: Name of the metric showing drift
        baseline_value: Expected/baseline value
        current_value: Current observed value
        deviation: Deviation from baseline
        severity: Drift severity level
        recommendation: Recommended action
    """

    metric_name: str
    baseline_value: float = 0.0
    current_value: float = 0.0
    deviation: float = 0.0
    severity: DriftSeverity = DriftSeverity.NONE
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
            "metric_name": self.metric_name,
            "baseline_value": round(self.baseline_value, 4),
            "current_value": round(self.current_value, 4),
            "deviation": round(self.deviation, 4),
            "severity": self.severity.value,
            "recommendation": self.recommendation,
        }


@dataclass
class FeedbackAnalysisReport:
    """Complete feedback analysis report.

    Attributes:
        analysis_time: Time when analysis was performed
        total_matches: Total number of matches analyzed
        overall_accuracy: Overall prediction accuracy
        accuracy_by_signal_type: Accuracy breakdown by signal type
        accuracy_by_timeframe: Accuracy breakdown by timeframe
        regime_performance: Performance by market regime
        feature_importance_changes: Changes in feature importance
        drift_indicators: Detected drift indicators
        recommendations: List of recommendations
        metadata: Additional metadata
    """

    analysis_time: datetime
    total_matches: int = 0
    overall_accuracy: float = 0.0
    accuracy_by_signal_type: list[AccuracyBySignalType] = field(default_factory=list)
    accuracy_by_timeframe: list[AccuracyByTimeframe] = field(default_factory=list)
    regime_performance: list[RegimePerformance] = field(default_factory=list)
    feature_importance_changes: list[FeatureImportanceChange] = field(
        default_factory=list
    )
    drift_indicators: list[DriftIndicator] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "analysis_time": self.analysis_time.isoformat(),
            "total_matches": self.total_matches,
            "overall_accuracy": round(self.overall_accuracy, 4),
            "accuracy_by_signal_type": [
                a.to_dict() for a in self.accuracy_by_signal_type
            ],
            "accuracy_by_timeframe": [a.to_dict() for a in self.accuracy_by_timeframe],
            "regime_performance": [r.to_dict() for r in self.regime_performance],
            "feature_importance_changes": [
                f.to_dict() for f in self.feature_importance_changes
            ],
            "drift_indicators": [d.to_dict() for d in self.drift_indicators],
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


class FeedbackAnalyzer:
    """Analyzes prediction outcomes for model improvement.

    This class provides methods to:
    - Calculate accuracy metrics by signal type and timeframe
    - Detect model drift indicators
    - Analyze feature importance changes
    - Generate actionable recommendations
    """

    def __init__(self, config: AnalysisConfig | None = None):
        """Initialize the analyzer.

        Args:
            config: Analysis configuration
        """
        self.config = config or AnalysisConfig()
        self._baseline_metrics: dict[str, float] = {}

    async def analyze_matches(
        self,
        matches: list[PredictionOutcomeMatch],
        baseline_metrics: dict[str, float] | None = None,
    ) -> FeedbackAnalysisReport:
        """Analyze a batch of prediction-outcome matches.

        Args:
            matches: List of matches to analyze
            baseline_metrics: Optional baseline metrics for drift detection

        Returns:
            FeedbackAnalysisReport with complete analysis
        """
        if baseline_metrics:
            self._baseline_metrics = baseline_metrics

        report = FeedbackAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_matches=len(matches),
        )

        # Filter to high-confidence matches only
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
        report.accuracy_by_signal_type = self._analyze_by_signal_type(valid_matches)

        # Analyze by timeframe
        report.accuracy_by_timeframe = self._analyze_by_timeframe(valid_matches)

        # Analyze by market regime (if enabled)
        if self.config.enable_regime_analysis:
            report.regime_performance = self._analyze_by_regime(valid_matches)

        # Detect drift
        report.drift_indicators = self._detect_drift(valid_matches)

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        logger.info(
            f"Analysis complete: {report.total_matches} matches, "
            f"{report.overall_accuracy:.2%} accuracy, "
            f"{len(report.drift_indicators)} drift indicators"
        )

        return report

    def _filter_valid_matches(
        self,
        matches: list[PredictionOutcomeMatch],
    ) -> list[PredictionOutcomeMatch]:
        """Filter to valid matches for analysis.

        Args:
            matches: All matches

        Returns:
            Filtered matches with outcomes
        """
        from ml.feedback.matcher import MatchStatus

        valid = []
        for match in matches:
            # Must be matched (not unresolved/expired)
            if match.status != MatchStatus.MATCHED:
                continue

            # Must have outcome
            if match.outcome is None:
                continue

            # Must meet confidence threshold
            if match.resolution_quality < self.config.confidence_threshold:
                continue

            valid.append(match)

        return valid

    def _calculate_overall_accuracy(
        self,
        matches: list[PredictionOutcomeMatch],
    ) -> float:
        """Calculate overall prediction accuracy.

        Args:
            matches: Valid matches

        Returns:
            Accuracy ratio (0.0-1.0)
        """
        if not matches:
            return 0.0

        correct = sum(1 for m in matches if self._is_correct_prediction(m))
        return correct / len(matches)

    def _is_correct_prediction(self, match: PredictionOutcomeMatch) -> bool:
        """Determine if a prediction was correct.

        Args:
            match: Prediction-outcome match

        Returns:
            True if prediction was correct
        """
        if match.outcome is None:
            return False

        # Check PnL if available
        if hasattr(match.outcome, "pnl"):
            pnl: float = match.outcome.pnl
            return pnl > 0

        # Check outcome type
        if hasattr(match.outcome, "outcome_type"):
            from market_analysis.signal_storage.models import OutcomeType

            outcome_type = match.outcome.outcome_type
            if outcome_type == OutcomeType.TP_HIT:
                return True
            elif outcome_type == OutcomeType.SL_HIT:
                return False
            elif outcome_type == OutcomeType.MANUAL_CLOSE:
                # For manual close, check PnL
                if hasattr(match.outcome, "pnl"):
                    pnl: float = match.outcome.pnl
                    return pnl > 0

        return False

    def _analyze_by_signal_type(
        self,
        matches: list[PredictionOutcomeMatch],
    ) -> list[AccuracyBySignalType]:
        """Analyze accuracy grouped by signal type.

        Args:
            matches: Valid matches

        Returns:
            List of accuracy metrics by signal type
        """
        from collections import defaultdict

        # Group by signal type
        by_type: dict[str, list[PredictionOutcomeMatch]] = defaultdict(list)
        for match in matches:
            signal_type = match.signal.signal_type
            by_type[signal_type].append(match)

        results = []
        for signal_type, type_matches in by_type.items():
            correct = sum(1 for m in type_matches if self._is_correct_prediction(m))

            # Calculate average PnL
            pnls = [
                m.outcome.pnl
                for m in type_matches
                if m.outcome and hasattr(m.outcome, "pnl")
            ]
            avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0

            # Calculate average confidence
            confidences = [m.signal.confidence for m in type_matches]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            results.append(
                AccuracyBySignalType(
                    signal_type=signal_type,
                    total_signals=len(type_matches),
                    correct_predictions=correct,
                    avg_pnl=avg_pnl,
                    confidence=avg_confidence,
                )
            )

        # Sort by total signals (descending)
        results.sort(key=lambda x: x.total_signals, reverse=True)
        return results

    def _analyze_by_timeframe(
        self,
        matches: list[PredictionOutcomeMatch],
    ) -> list[AccuracyByTimeframe]:
        """Analyze accuracy grouped by timeframe.

        Args:
            matches: Valid matches

        Returns:
            List of accuracy metrics by timeframe
        """
        from collections import defaultdict

        # Group by timeframe (use first timeframe if multiple)
        by_timeframe: dict[str, list[PredictionOutcomeMatch]] = defaultdict(list)
        for match in matches:
            timeframes = match.signal.timeframes_used
            if timeframes:
                # Use the primary (first) timeframe
                primary_tf = timeframes[0]
                by_timeframe[primary_tf].append(match)

        results = []
        for timeframe, tf_matches in by_timeframe.items():
            correct = sum(1 for m in tf_matches if self._is_correct_prediction(m))

            # Calculate average PnL
            pnls = [
                m.outcome.pnl
                for m in tf_matches
                if m.outcome and hasattr(m.outcome, "pnl")
            ]
            avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0

            results.append(
                AccuracyByTimeframe(
                    timeframe=timeframe,
                    total_signals=len(tf_matches),
                    correct_predictions=correct,
                    avg_pnl=avg_pnl,
                )
            )

        # Sort by total signals (descending)
        results.sort(key=lambda x: x.total_signals, reverse=True)
        return results

    def _analyze_by_regime(
        self,
        matches: list[PredictionOutcomeMatch],
    ) -> list[RegimePerformance]:
        """Analyze performance by market regime.

        Args:
            matches: Valid matches

        Returns:
            List of regime performance metrics
        """
        # For now, use a simplified regime classification based on signal metadata
        # In production, this would use actual market regime detection
        from collections import defaultdict

        by_regime: dict[MarketRegime, list[PredictionOutcomeMatch]] = defaultdict(list)

        for match in matches:
            # Try to determine regime from signal metadata
            regime = self._classify_regime(match)
            by_regime[regime].append(match)

        results = []
        for regime, regime_matches in by_regime.items():
            if not regime_matches:
                continue

            correct = sum(1 for m in regime_matches if self._is_correct_prediction(m))
            accuracy = correct / len(regime_matches) if regime_matches else 0.0

            # Calculate average PnL
            pnls = [
                m.outcome.pnl
                for m in regime_matches
                if m.outcome and hasattr(m.outcome, "pnl")
            ]
            avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0

            results.append(
                RegimePerformance(
                    regime=regime,
                    total_signals=len(regime_matches),
                    accuracy=accuracy,
                    avg_pnl=avg_pnl,
                )
            )

        return results

    def _classify_regime(
        self,
        match: PredictionOutcomeMatch,
    ) -> MarketRegime:
        """Classify market regime for a match.

        Args:
            match: Prediction-outcome match

        Returns:
            Market regime classification
        """
        # Check signal metadata for regime hints
        metadata = match.signal.metadata or {}

        if "market_regime" in metadata:
            try:
                return MarketRegime(metadata["market_regime"])
            except ValueError:
                pass

        if "volatility_regime" in metadata:
            vol_regime = metadata["volatility_regime"]
            if vol_regime == "high":
                return MarketRegime.HIGH_VOLATILITY
            elif vol_regime == "low":
                return MarketRegime.LOW_VOLATILITY

        # Default to unknown
        return MarketRegime.UNKNOWN

    def _detect_drift(
        self,
        matches: list[PredictionOutcomeMatch],
    ) -> list[DriftIndicator]:
        """Detect model drift indicators.

        Args:
            matches: Valid matches

        Returns:
            List of drift indicators
        """
        indicators: list[DriftIndicator] = []

        if not self._baseline_metrics:
            return indicators

        # Calculate current metrics
        current_accuracy = self._calculate_overall_accuracy(matches)

        # Check accuracy drift
        baseline_accuracy = self._baseline_metrics.get("accuracy", current_accuracy)
        if baseline_accuracy > 0:
            accuracy_drop = baseline_accuracy - current_accuracy
            if accuracy_drop > self.config.accuracy_degradation_threshold:
                severity = (
                    DriftSeverity.HIGH if accuracy_drop > 0.2 else DriftSeverity.MEDIUM
                )
                indicators.append(
                    DriftIndicator(
                        metric_name="accuracy",
                        baseline_value=baseline_accuracy,
                        current_value=current_accuracy,
                        severity=severity,
                        recommendation="Consider retraining model or adjusting thresholds",
                    )
                )

        # Check prediction confidence drift
        if matches:
            avg_confidence = sum(m.signal.confidence for m in matches) / len(matches)
            baseline_confidence = self._baseline_metrics.get(
                "confidence", avg_confidence
            )
            if baseline_confidence > 0:
                confidence_drop = baseline_confidence - avg_confidence
                if confidence_drop > 0.15:  # 15% confidence drop threshold
                    indicators.append(
                        DriftIndicator(
                            metric_name="confidence",
                            baseline_value=baseline_confidence,
                            current_value=avg_confidence,
                            severity=DriftSeverity.MEDIUM,
                            recommendation="Review feature inputs for data quality issues",
                        )
                    )

        return indicators

    def _generate_recommendations(
        self,
        report: FeedbackAnalysisReport,
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
                "Overall accuracy below 50% - consider model retraining or strategy review"
            )
        elif report.overall_accuracy > 0.7:
            recommendations.append(
                "Strong overall performance - consider increasing position sizes"
            )

        # Check signal type performance
        for acc in report.accuracy_by_signal_type:
            if acc.total_signals >= 10 and acc.accuracy < 0.4:
                recommendations.append(
                    f"Low accuracy for {acc.signal_type} ({acc.accuracy:.1%}) - "
                    "consider disabling or retraining"
                )

        # Check drift indicators
        for drift in report.drift_indicators:
            if drift.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL):
                recommendations.append(
                    f"Critical drift in {drift.metric_name}: {drift.recommendation}"
                )

        # Check regime performance
        if report.regime_performance:
            best_regime = max(report.regime_performance, key=lambda r: r.accuracy)
            worst_regime = min(report.regime_performance, key=lambda r: r.accuracy)
            if best_regime.accuracy - worst_regime.accuracy > 0.3:
                recommendations.append(
                    f"Large performance gap between regimes: "
                    f"{best_regime.regime.value} ({best_regime.accuracy:.1%}) vs "
                    f"{worst_regime.regime.value} ({worst_regime.accuracy:.1%}) - "
                    "consider regime-specific models"
                )

        return recommendations

    def calculate_feature_importance_changes(
        self,
        old_importance: dict[str, float],
        new_importance: dict[str, float],
    ) -> list[FeatureImportanceChange]:
        """Calculate changes in feature importance.

        Args:
            old_importance: Previous feature importance scores
            new_importance: Current feature importance scores

        Returns:
            List of feature importance changes
        """
        changes = []
        all_features = set(old_importance.keys()) | set(new_importance.keys())

        for feature in all_features:
            old_val = old_importance.get(feature, 0.0)
            new_val = new_importance.get(feature, 0.0)

            change = FeatureImportanceChange(
                feature_name=feature,
                old_importance=old_val,
                new_importance=new_val,
            )

            # Mark as significant if absolute change exceeds threshold
            change.is_significant = (
                change.absolute_change > self.config.feature_importance_threshold
            )

            if change.is_significant or change.absolute_change > 0.01:
                changes.append(change)

        # Sort by absolute change (descending)
        changes.sort(key=lambda x: x.absolute_change, reverse=True)
        return changes

    def set_baseline_metrics(self, metrics: dict[str, float]) -> None:
        """Set baseline metrics for drift detection.

        Args:
            metrics: Baseline metric values
        """
        self._baseline_metrics = metrics.copy()

    def get_baseline_metrics(self) -> dict[str, float]:
        """Get current baseline metrics.

        Returns:
            Baseline metrics
        """
        return self._baseline_metrics.copy()
