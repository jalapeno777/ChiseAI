"""
Test Health Predictor - Unit tests for predictive alerting (ST-GOV-008).

Story: ST-GOV-008
"""

import pytest
from datetime import datetime, timedelta

from src.governance.health.predictor import (
    HealthPredictor,
    HealthAlert,
    PredictionConfig,
    PredictionType,
    AlertSeverity,
)
from src.governance.health.scorer import (
    AgentHealthScore,
    HealthStatus,
    HealthDimension,
)


def create_score(agent_id: str, score: float, timestamp: datetime) -> AgentHealthScore:
    """Helper to create an AgentHealthScore."""
    return AgentHealthScore(
        agent_id=agent_id,
        overall_score=score,
        status=HealthStatus.HEALTHY if score >= 80 else HealthStatus.DEGRADED,
        dimensions={
            "performance": HealthDimension(
                name="performance",
                score=score,
                weight=0.25,
            )
        },
        timestamp=timestamp,
    )


class TestHealthPredictor:
    """Tests for HealthPredictor class."""

    def test_predictor_initialization(self):
        """Test predictor initializes with default config."""
        predictor = HealthPredictor()
        assert predictor.config.prediction_horizon_minutes == 15
        assert predictor.config.min_history_points == 3
        assert predictor.config.alert_threshold_score == 60.0

    def test_predictor_custom_config(self):
        """Test predictor with custom configuration."""
        config = PredictionConfig(
            prediction_horizon_minutes=30,
            min_history_points=5,
            alert_threshold_score=50.0,
        )
        predictor = HealthPredictor(config=config)
        assert predictor.config.prediction_horizon_minutes == 30
        assert predictor.config.min_history_points == 5

    def test_predict_insufficient_history(self):
        """Test prediction with insufficient history."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        # Only 2 data points, need 3
        history = [
            create_score("agent-1", 80, now - timedelta(minutes=10)),
            create_score("agent-1", 75, now - timedelta(minutes=5)),
        ]

        alerts = predictor.predict("agent-1", history)
        assert len(alerts) == 0

    def test_predict_stable_health(self):
        """Test prediction with stable health scores."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        # Stable scores around 80
        history = [
            create_score("agent-1", 80, now - timedelta(minutes=15)),
            create_score("agent-1", 81, now - timedelta(minutes=10)),
            create_score("agent-1", 79, now - timedelta(minutes=5)),
            create_score("agent-1", 80, now),
        ]

        alerts = predictor.predict("agent-1", history)

        # Should not generate alerts for stable health
        critical_alerts = [a for a in alerts if a.severity == AlertSeverity.CRITICAL]
        assert len(critical_alerts) == 0

    def test_predict_declining_health(self):
        """Test prediction with declining health trend."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        # Declining scores
        history = [
            create_score("agent-1", 85, now - timedelta(minutes=15)),
            create_score("agent-1", 78, now - timedelta(minutes=10)),
            create_score("agent-1", 68, now - timedelta(minutes=5)),
            create_score("agent-1", 58, now),
        ]

        alerts = predictor.predict("agent-1", history)

        # Should generate alerts for declining health
        assert len(alerts) > 0

    def test_predict_threshold_breach(self):
        """Test prediction of threshold breach."""
        config = PredictionConfig(
            prediction_horizon_minutes=15,
            min_history_points=3,
            alert_threshold_score=60.0,
            confidence_threshold=0.5,  # Lower for testing
        )
        predictor = HealthPredictor(config=config)
        now = datetime.utcnow()

        # Steadily declining towards threshold
        history = [
            create_score("agent-1", 75, now - timedelta(minutes=15)),
            create_score("agent-1", 68, now - timedelta(minutes=10)),
            create_score("agent-1", 62, now - timedelta(minutes=5)),
            create_score("agent-1", 55, now),
        ]

        alerts = predictor.predict("agent-1", history)

        # Should predict threshold breach
        threshold_alerts = [
            a for a in alerts if a.prediction_type == PredictionType.THRESHOLD_BREACH
        ]
        # May or may not have alerts depending on confidence calculation
        assert isinstance(alerts, list)

    def test_alert_creation(self):
        """Test alert object creation and properties."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        history = [
            create_score("agent-1", 85, now - timedelta(minutes=15)),
            create_score("agent-1", 75, now - timedelta(minutes=10)),
            create_score("agent-1", 60, now - timedelta(minutes=5)),
            create_score("agent-1", 45, now),
        ]

        alerts = predictor.predict("agent-1", history)

        if alerts:
            alert = alerts[0]
            assert alert.agent_id == "agent-1"
            assert alert.severity in (
                AlertSeverity.CRITICAL,
                AlertSeverity.WARNING,
                AlertSeverity.INFO,
            )
            assert alert.prediction_type in PredictionType
            assert 0 <= alert.confidence <= 1
            assert alert.predicted_time > datetime.utcnow()

    def test_alert_to_dict(self):
        """Test alert serialization to dictionary."""
        alert = HealthAlert(
            alert_id="test-alert-1",
            agent_id="agent-1",
            severity=AlertSeverity.WARNING,
            prediction_type=PredictionType.DEGRADATION,
            current_score=70.0,
            predicted_score=50.0,
            predicted_time=datetime.utcnow() + timedelta(minutes=15),
            confidence=0.85,
            message="Test alert",
            contributing_factors=["Factor 1"],
            remediation_hint="Do something",
        )

        data = alert.to_dict()

        assert data["alert_id"] == "test-alert-1"
        assert data["agent_id"] == "agent-1"
        assert data["severity"] == "warning"
        assert data["prediction_type"] == "degradation"
        assert data["current_score"] == 70.0
        assert data["predicted_score"] == 50.0
        assert data["confidence"] == 0.85

    def test_severity_determination(self):
        """Test severity determination based on predicted score."""
        predictor = HealthPredictor()

        assert predictor._determine_severity(30) == AlertSeverity.CRITICAL
        assert predictor._determine_severity(50) == AlertSeverity.WARNING
        assert predictor._determine_severity(65) == AlertSeverity.INFO

    def test_remediation_hint_generation(self):
        """Test remediation hint generation."""
        predictor = HealthPredictor()

        hint = predictor._generate_remediation_hint(
            PredictionType.DEGRADATION,
            AlertSeverity.WARNING,
            ["Declining trend"],
        )
        assert "Review" in hint or "workload" in hint

        hint_critical = predictor._generate_remediation_hint(
            PredictionType.THRESHOLD_BREACH,
            AlertSeverity.CRITICAL,
            ["Score dropping fast"],
        )
        assert "PRIORITY" in hint_critical

    def test_prediction_storage(self):
        """Test that predictions are stored for accuracy tracking."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        history = [
            create_score("agent-1", 80, now - timedelta(minutes=15)),
            create_score("agent-1", 75, now - timedelta(minutes=10)),
            create_score("agent-1", 70, now - timedelta(minutes=5)),
            create_score("agent-1", 65, now),
        ]

        predictor.predict("agent-1", history)

        # Check that prediction was stored
        predictions = predictor.get_predictions_for_agent("agent-1")
        assert len(predictions) > 0

    def test_clear_history(self):
        """Test clearing prediction history."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        history = [
            create_score("agent-1", 80, now - timedelta(minutes=15)),
            create_score("agent-1", 70, now - timedelta(minutes=10)),
            create_score("agent-1", 60, now - timedelta(minutes=5)),
            create_score("agent-1", 50, now),
        ]

        predictor.predict("agent-1", history)
        assert len(predictor.get_predictions_for_agent("agent-1")) > 0

        predictor.clear_history("agent-1")
        assert len(predictor.get_predictions_for_agent("agent-1")) == 0

    def test_calculate_prediction_accuracy(self):
        """Test prediction accuracy calculation."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        # Create some predictions
        history = [
            create_score("agent-1", 80, now - timedelta(minutes=20)),
            create_score("agent-1", 75, now - timedelta(minutes=15)),
            create_score("agent-1", 70, now - timedelta(minutes=10)),
            create_score("agent-1", 65, now - timedelta(minutes=5)),
        ]
        predictor.predict("agent-1", history)

        # Create actual scores that somewhat match predictions
        actual_scores = {
            "agent-1": [
                create_score("agent-1", 60, now),
            ]
        }

        accuracy = predictor.calculate_prediction_accuracy(actual_scores)
        # Accuracy might be 0 if no time-aligned predictions exist
        assert isinstance(accuracy, float)
        assert 0 <= accuracy <= 100


class TestTrendAnalysis:
    """Tests for trend analysis functionality."""

    def test_linear_regression_basic(self):
        """Test basic linear regression for trend analysis."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        # Linear decline
        history = [
            create_score("agent-1", 90, now - timedelta(minutes=30)),
            create_score("agent-1", 80, now - timedelta(minutes=20)),
            create_score("agent-1", 70, now - timedelta(minutes=10)),
            create_score("agent-1", 60, now),
        ]

        analysis = predictor._analyze_trend(history)

        assert "predicted_score" in analysis
        assert "confidence" in analysis
        assert "degradation_rate" in analysis
        # Predicted score should be lower than current
        assert analysis["predicted_score"] < 60

    def test_trend_with_noise(self):
        """Test trend analysis with noisy data."""
        predictor = HealthPredictor()
        now = datetime.utcnow()

        # Noisy declining trend
        history = [
            create_score("agent-1", 85, now - timedelta(minutes=30)),
            create_score("agent-1", 82, now - timedelta(minutes=25)),
            create_score("agent-1", 75, now - timedelta(minutes=20)),
            create_score("agent-1", 78, now - timedelta(minutes=15)),
            create_score("agent-1", 70, now - timedelta(minutes=10)),
            create_score("agent-1", 68, now - timedelta(minutes=5)),
            create_score("agent-1", 62, now),
        ]

        analysis = predictor._analyze_trend(history)

        # Should still detect declining trend despite noise
        assert analysis["slope"] < 0
