"""
Health Predictor - Predictive Alerting System (ST-GOV-008).

Implements predictive health analysis with:
- Trend analysis for health degradation prediction
- 15-minute lookahead forecasting
- Alert generation on predicted issues
- Integration with EP-NS-008 (Autonomous Control Plane)

Story: ST-GOV-008
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import logging
import math

from .scorer import AgentHealthScore, HealthStatus

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    CRITICAL = "critical"  # Immediate action required
    WARNING = "warning"  # Attention needed soon
    INFO = "info"  # Informational


class PredictionType(Enum):
    """Types of health predictions."""

    DEGRADATION = "degradation"  # Health score declining
    THRESHOLD_BREACH = "threshold_breach"  # Will cross threshold
    DIMENSION_FAILURE = "dimension_failure"  # Specific dimension failing
    SYSTEMIC_ISSUE = "systemic_issue"  # Multiple agents affected


@dataclass
class HealthAlert:
    """A health alert with prediction details."""

    alert_id: str
    agent_id: str
    severity: AlertSeverity
    prediction_type: PredictionType
    current_score: float
    predicted_score: float
    predicted_time: datetime  # When the issue is predicted to occur
    confidence: float  # 0.0 to 1.0
    message: str
    contributing_factors: list[str] = field(default_factory=list)
    remediation_hint: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert alert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "agent_id": self.agent_id,
            "severity": self.severity.value,
            "prediction_type": self.prediction_type.value,
            "current_score": self.current_score,
            "predicted_score": self.predicted_score,
            "predicted_time": self.predicted_time.isoformat(),
            "confidence": round(self.confidence, 2),
            "message": self.message,
            "contributing_factors": self.contributing_factors,
            "remediation_hint": self.remediation_hint,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class PredictionConfig:
    """Configuration for prediction engine."""

    prediction_horizon_minutes: int = 15  # Look ahead time
    min_history_points: int = 3  # Minimum data points for prediction
    alert_threshold_score: float = 60.0  # Alert if predicted below this
    confidence_threshold: float = 0.75  # Minimum confidence for alerts
    degradation_rate_threshold: float = 5.0  # Score points per hour to trigger
    prediction_interval_seconds: int = 60  # How often to run predictions


class HealthPredictor:
    """
    Predictive health analysis engine.

    Analyzes health trends and generates alerts for predicted
    degradation before it impacts the swarm.
    """

    def __init__(
        self,
        config: Optional[PredictionConfig] = None,
        history_window_hours: int = 2,
    ):
        """
        Initialize health predictor.

        Args:
            config: Prediction configuration
            history_window_hours: Hours of history to analyze
        """
        self.config = config or PredictionConfig()
        self.history_window = timedelta(hours=history_window_hours)
        self._prediction_history: dict[str, list[dict]] = {}
        self._alert_counter = 0

    def predict(
        self,
        agent_id: str,
        score_history: list[AgentHealthScore],
    ) -> list[HealthAlert]:
        """
        Generate predictions for an agent based on score history.

        Args:
            agent_id: Agent identifier
            score_history: Historical health scores for the agent

        Returns:
            List of predicted alerts (empty if no issues predicted)
        """
        if len(score_history) < self.config.min_history_points:
            logger.debug(
                f"Insufficient history for {agent_id}: "
                f"{len(score_history)} < {self.config.min_history_points}"
            )
            return []

        alerts = []
        latest = score_history[-1]
        horizon = timedelta(minutes=self.config.prediction_horizon_minutes)

        # Analyze score trend
        trend_analysis = self._analyze_trend(score_history)
        predicted_score = trend_analysis["predicted_score"]
        confidence = trend_analysis["confidence"]

        # Check for predicted threshold breach
        if (
            predicted_score < self.config.alert_threshold_score
            and confidence >= self.config.confidence_threshold
        ):
            alerts.append(
                self._create_alert(
                    agent_id=agent_id,
                    prediction_type=PredictionType.THRESHOLD_BREACH,
                    severity=self._determine_severity(predicted_score),
                    current_score=latest.overall_score,
                    predicted_score=predicted_score,
                    confidence=confidence,
                    horizon=horizon,
                    factors=trend_analysis.get("factors", []),
                )
            )

        # Check for rapid degradation
        degradation_rate = trend_analysis["degradation_rate"]
        if degradation_rate > self.config.degradation_rate_threshold:
            alerts.append(
                self._create_alert(
                    agent_id=agent_id,
                    prediction_type=PredictionType.DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    current_score=latest.overall_score,
                    predicted_score=predicted_score,
                    confidence=confidence,
                    horizon=horizon,
                    factors=[f"Degradation rate: {degradation_rate:.1f} pts/hr"],
                )
            )

        # Check for dimension-specific issues
        dimension_alerts = self._predict_dimension_issues(agent_id, score_history)
        alerts.extend(dimension_alerts)

        # Store predictions
        self._store_prediction(agent_id, predicted_score, confidence, alerts)

        return alerts

    def _analyze_trend(self, history: list[AgentHealthScore]) -> dict:
        """
        Analyze health score trend using linear regression.

        Args:
            history: List of historical scores

        Returns:
            Dictionary with trend analysis results
        """
        if len(history) < 2:
            return {
                "predicted_score": 50.0,
                "confidence": 0.0,
                "degradation_rate": 0.0,
                "factors": [],
            }

        # Extract scores and timestamps
        scores = [s.overall_score for s in history]
        timestamps = [
            (s.timestamp - history[0].timestamp).total_seconds() / 3600 for s in history
        ]

        # Simple linear regression
        n = len(scores)
        sum_x = sum(timestamps)
        sum_y = sum(scores)
        sum_xy = sum(x * y for x, y in zip(timestamps, scores))
        sum_xx = sum(x * x for x in timestamps)

        # Calculate slope and intercept
        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            slope = 0
            intercept = sum_y / n
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y - slope * sum_x) / n

        # Predict score at horizon
        horizon_hours = self.config.prediction_horizon_minutes / 60.0
        last_time = timestamps[-1]
        predicted_time = last_time + horizon_hours
        predicted_score = slope * predicted_time + intercept

        # Calculate R-squared for confidence
        y_mean = sum_y / n
        ss_tot = sum((y - y_mean) ** 2 for y in scores)
        ss_res = sum(
            (y - (slope * x + intercept)) ** 2 for x, y in zip(timestamps, scores)
        )
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Adjust confidence based on R-squared and recency
        confidence = max(0.0, min(1.0, r_squared))

        # Calculate degradation rate (points per hour)
        degradation_rate = -slope  # Negative slope = degradation

        # Identify factors
        factors = []
        if slope < -1:
            factors.append(f"Declining trend: {slope:.2f} pts/hr")
        if r_squared > 0.7:
            factors.append(f"Strong correlation (R²={r_squared:.2f})")

        return {
            "predicted_score": max(0.0, min(100.0, predicted_score)),
            "confidence": confidence,
            "degradation_rate": degradation_rate,
            "factors": factors,
            "slope": slope,
            "intercept": intercept,
            "r_squared": r_squared,
        }

    def _predict_dimension_issues(
        self,
        agent_id: str,
        history: list[AgentHealthScore],
    ) -> list[HealthAlert]:
        """
        Predict issues in specific health dimensions.

        Args:
            agent_id: Agent identifier
            history: Historical health scores

        Returns:
            List of dimension-specific alerts
        """
        alerts = []

        if len(history) < self.config.min_history_points:
            return alerts

        latest = history[-1]
        horizon = timedelta(minutes=self.config.prediction_horizon_minutes)

        for dim_name, dimension in latest.dimensions.items():
            # Get dimension score history
            dim_scores = []
            for score in history:
                if dim_name in score.dimensions:
                    dim_scores.append(
                        (score.timestamp, score.dimensions[dim_name].score)
                    )

            if len(dim_scores) < self.config.min_history_points:
                continue

            # Analyze dimension trend
            scores_only = [s[1] for s in dim_scores]
            if scores_only[-1] < 50:
                # Already in bad state, predict if getting worse
                if len(scores_only) >= 2 and scores_only[-1] < scores_only[-2] - 5:
                    alerts.append(
                        self._create_alert(
                            agent_id=agent_id,
                            prediction_type=PredictionType.DIMENSION_FAILURE,
                            severity=self._determine_severity(scores_only[-1]),
                            current_score=latest.overall_score,
                            predicted_score=scores_only[-1] - 10,
                            confidence=0.8,
                            horizon=horizon,
                            factors=[
                                f"{dim_name} dimension critical: {scores_only[-1]:.0f}"
                            ],
                            dimension=dim_name,
                        )
                    )

        return alerts

    def _create_alert(
        self,
        agent_id: str,
        prediction_type: PredictionType,
        severity: AlertSeverity,
        current_score: float,
        predicted_score: float,
        confidence: float,
        horizon: timedelta,
        factors: list[str],
        dimension: Optional[str] = None,
    ) -> HealthAlert:
        """Create a health alert with proper formatting."""
        self._alert_counter += 1
        alert_id = (
            f"alert-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{self._alert_counter}"
        )
        predicted_time = datetime.utcnow() + horizon

        # Build message
        if dimension:
            message = f"Predicted {dimension} dimension degradation for {agent_id}"
        else:
            message = f"Predicted health degradation for {agent_id}"

        message += f" (score: {current_score:.0f} → {predicted_score:.0f})"

        # Generate remediation hint
        remediation_hint = self._generate_remediation_hint(
            prediction_type, severity, factors
        )

        return HealthAlert(
            alert_id=alert_id,
            agent_id=agent_id,
            severity=severity,
            prediction_type=prediction_type,
            current_score=current_score,
            predicted_score=predicted_score,
            predicted_time=predicted_time,
            confidence=confidence,
            message=message,
            contributing_factors=factors,
            remediation_hint=remediation_hint,
        )

    def _determine_severity(self, predicted_score: float) -> AlertSeverity:
        """Determine alert severity based on predicted score."""
        if predicted_score < 40:
            return AlertSeverity.CRITICAL
        elif predicted_score < 60:
            return AlertSeverity.WARNING
        else:
            return AlertSeverity.INFO

    def _generate_remediation_hint(
        self,
        prediction_type: PredictionType,
        severity: AlertSeverity,
        factors: list[str],
    ) -> str:
        """Generate a hint for remediation action."""
        hints = {
            PredictionType.DEGRADATION: "Review recent changes and workload distribution",
            PredictionType.THRESHOLD_BREACH: "Consider scaling or load balancing",
            PredictionType.DIMENSION_FAILURE: "Address specific dimension issues identified",
            PredictionType.SYSTEMIC_ISSUE: "Check for shared resource contention",
        }

        base_hint = hints.get(prediction_type, "Investigate health degradation cause")

        if severity == AlertSeverity.CRITICAL:
            base_hint += " [PRIORITY: Immediate action required]"

        return base_hint

    def _store_prediction(
        self,
        agent_id: str,
        predicted_score: float,
        confidence: float,
        alerts: list[HealthAlert],
    ) -> None:
        """Store prediction for accuracy tracking."""
        if agent_id not in self._prediction_history:
            self._prediction_history[agent_id] = []

        prediction = {
            "timestamp": datetime.utcnow().isoformat(),
            "predicted_score": predicted_score,
            "confidence": confidence,
            "alert_count": len(alerts),
            "prediction_horizon_minutes": self.config.prediction_horizon_minutes,
        }

        self._prediction_history[agent_id].append(prediction)

        # Prune old predictions
        cutoff = datetime.utcnow() - self.history_window
        self._prediction_history[agent_id] = [
            p
            for p in self._prediction_history[agent_id]
            if datetime.fromisoformat(p["timestamp"]) >= cutoff
        ]

    def calculate_prediction_accuracy(
        self,
        actual_scores: dict[str, list[AgentHealthScore]],
    ) -> float:
        """
        Calculate prediction accuracy based on historical predictions vs actuals.

        Args:
            actual_scores: Actual scores per agent for comparison

        Returns:
            Accuracy percentage (0-100)
        """
        total_predictions = 0
        accurate_predictions = 0
        tolerance = 10.0  # Within 10 points is considered accurate

        for agent_id, predictions in self._prediction_history.items():
            actuals = actual_scores.get(agent_id, [])
            if not actuals:
                continue

            for pred in predictions:
                pred_time = datetime.fromisoformat(pred["timestamp"])
                target_time = pred_time + timedelta(
                    minutes=self.config.prediction_horizon_minutes
                )

                # Find the closest actual score to the target time
                closest = None
                min_diff = timedelta(hours=1)  # Max 1 hour difference

                for actual in actuals:
                    diff = abs(actual.timestamp - target_time)
                    if diff < min_diff:
                        min_diff = diff
                        closest = actual

                if closest:
                    total_predictions += 1
                    predicted = pred["predicted_score"]
                    actual = closest.overall_score

                    if abs(predicted - actual) <= tolerance:
                        accurate_predictions += 1

        if total_predictions == 0:
            return 0.0

        return (accurate_predictions / total_predictions) * 100.0

    def get_predictions_for_agent(self, agent_id: str) -> list[dict]:
        """Get recent predictions for an agent."""
        return self._prediction_history.get(agent_id, [])

    def clear_history(self, agent_id: Optional[str] = None) -> None:
        """Clear prediction history."""
        if agent_id:
            self._prediction_history.pop(agent_id, None)
        else:
            self._prediction_history.clear()
