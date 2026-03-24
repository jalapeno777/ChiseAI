"""Tests for anomaly_detection module."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ml.data.anomaly_detection import AnomalyDetector, DriftReport


class TestDriftReport:
    """Tests for DriftReport dataclass."""

    def test_drift_report_creation(self) -> None:
        """Test creating a DriftReport."""
        report = DriftReport(
            drift_detected=True,
            drift_score=0.5,
            affected_features=["feature_1", "feature_2"],
            severity="medium",
            recommendations=["Retrain model"],
        )

        assert report.drift_detected is True
        assert report.drift_score == 0.5
        assert len(report.affected_features) == 2
        assert report.severity == "medium"

    def test_drift_report_clamping(self) -> None:
        """Test that drift_score is clamped to valid range."""
        report = DriftReport(
            drift_detected=True,
            drift_score=1.5,  # Should be clamped to 1.0
        )

        assert report.drift_score == 1.0

        report2 = DriftReport(
            drift_detected=False,
            drift_score=-0.5,  # Should be clamped to 0.0
        )

        assert report2.drift_score == 0.0

    def test_drift_report_severity_validation(self) -> None:
        """Test severity level validation."""
        report = DriftReport(
            drift_detected=True,
            drift_score=0.5,
            severity="invalid",  # Should be converted to "low"
        )

        assert report.severity == "low"

    def test_drift_report_to_dict(self) -> None:
        """Test serialization to dictionary."""
        report = DriftReport(
            drift_detected=True,
            drift_score=0.5,
            affected_features=["feature_1"],
            severity="medium",
            recommendations=["Test"],
            details={"extra": "info"},
        )

        result = report.to_dict()

        assert result["drift_detected"] is True
        assert result["drift_score"] == 0.5
        assert result["severity"] == "medium"


class TestAnomalyDetector:
    """Tests for AnomalyDetector class."""

    def test_detector_creation(self) -> None:
        """Test creating an AnomalyDetector."""
        detector = AnomalyDetector()

        assert detector.psi_threshold == 0.2
        assert detector.ks_threshold == 0.3
        assert detector.zscore_threshold == 3.0

    def test_custom_thresholds(self) -> None:
        """Test custom threshold configuration."""
        detector = AnomalyDetector(
            psi_threshold=0.3,
            ks_threshold=0.4,
            zscore_threshold=2.5,
        )

        assert detector.psi_threshold == 0.3
        assert detector.ks_threshold == 0.4
        assert detector.zscore_threshold == 2.5

    def test_detect_drift_empty_data(self) -> None:
        """Test drift detection with empty data."""
        detector = AnomalyDetector()

        report = detector.detect_drift([], [])

        assert report.drift_detected is False
        assert report.drift_score == 0.0

    def test_detect_drift_identical_data(self) -> None:
        """Test drift detection with identical distributions."""
        detector = AnomalyDetector()

        # Create identical distributions
        baseline = [{"value": v} for v in range(100)]
        current = [{"value": float(v)} for v in range(100)]

        report = detector.detect_drift(current, baseline)

        # Should have minimal or no drift
        assert report.drift_score < 0.1

    def test_detect_drift_significant(self) -> None:
        """Test drift detection with significantly different distributions."""
        detector = AnomalyDetector()

        # Create different distributions
        baseline = [{"value": v} for v in range(100)]
        current = [{"value": v + 1000} for v in range(100)]  # Shifted values

        report = detector.detect_drift(current, baseline)

        # Should detect drift
        assert report.drift_score > 0.0

    def test_detect_drift_single_record(self) -> None:
        """Test drift detection with single record."""
        detector = AnomalyDetector()

        baseline = [{"value": 1.0}]
        current = [{"value": 2.0}]

        report = detector.detect_drift(current, baseline)

        # Should handle gracefully
        assert report.drift_score >= 0.0

    def test_detect_outliers_none(self) -> None:
        """Test outlier detection with no outliers."""
        detector = AnomalyDetector()

        data = [{"value": v} for v in range(100)]

        outliers = detector.detect_outliers(data, "value")

        # Should have no outliers in normal distribution
        assert len(outliers) == 0

    def test_detect_outliers_with_anomalies(self) -> None:
        """Test outlier detection with clear outliers."""
        detector = AnomalyDetector()

        # Create data with clear outliers
        data = [{"value": 1.0} for _ in range(50)]
        data.append({"value": 100.0})  # Outlier
        data.append({"value": -100.0})  # Outlier

        outliers = detector.detect_outliers(data, "value")

        # Should detect outliers
        assert len(outliers) > 0

    def test_detect_outliers_insufficient_data(self) -> None:
        """Test outlier detection with insufficient data."""
        detector = AnomalyDetector()

        data = [{"value": 1.0}]

        outliers = detector.detect_outliers(data, "value")

        assert len(outliers) == 0

    def test_detect_concept_drift_no_drift(self) -> None:
        """Test concept drift detection with identical label distribution."""
        detector = AnomalyDetector()

        baseline = [{"label": 0} for _ in range(50)] + [{"label": 1} for _ in range(50)]
        current = [{"label": 0} for _ in range(50)] + [{"label": 1} for _ in range(50)]

        report = detector.detect_concept_drift(current, baseline)

        assert report.drift_detected is False
        assert report.drift_score < 0.2

    def test_detect_concept_drift_significant(self) -> None:
        """Test concept drift detection with different label distribution."""
        detector = AnomalyDetector()

        # 90% label 0 in baseline
        baseline = [{"label": 0} for _ in range(90)] + [{"label": 1} for _ in range(10)]
        # 90% label 1 in current
        current = [{"label": 1} for _ in range(90)] + [{"label": 0} for _ in range(10)]

        report = detector.detect_concept_drift(current, baseline)

        # Should detect significant concept drift
        assert report.drift_detected is True
        assert report.drift_score > 0.5

    def test_detect_concept_drift_empty_data(self) -> None:
        """Test concept drift with empty data."""
        detector = AnomalyDetector()

        report = detector.detect_concept_drift([], [])

        assert report.drift_detected is False


class TestAnomalyDetectorPSI:
    """Tests for PSI calculation."""

    def test_psi_identical_distributions(self) -> None:
        """Test PSI with identical distributions."""
        detector = AnomalyDetector()

        baseline = list(range(100))
        current = list(range(100))

        psi = detector._calculate_psi(baseline, current)

        assert psi < 0.01  # Should be very close to 0

    def test_psi_different_distributions(self) -> None:
        """Test PSI with different distributions."""
        detector = AnomalyDetector()

        baseline = list(range(100))
        current = [v + 50 for v in range(100)]  # Shifted

        psi = detector._calculate_psi(baseline, current)

        assert psi > 0.0

    def test_psi_empty_data(self) -> None:
        """Test PSI with empty data."""
        detector = AnomalyDetector()

        psi = detector._calculate_psi([], [1, 2, 3])

        assert psi == 0.0


class TestAnomalyDetectorKS:
    """Tests for KS test calculation."""

    def test_ks_identical_distributions(self) -> None:
        """Test KS with identical distributions."""
        detector = AnomalyDetector()

        baseline = list(range(100))
        current = list(range(100))

        ks = detector._calculate_ks(baseline, current)

        assert ks < 0.1

    def test_ks_different_distributions(self) -> None:
        """Test KS with different distributions."""
        detector = AnomalyDetector()

        baseline = list(range(100))
        current = [v + 50 for v in range(100)]

        ks = detector._calculate_ks(baseline, current)

        assert ks > 0.0


class TestAnomalyDetectorIntegration:
    """Integration tests for AnomalyDetector."""

    def test_full_drift_analysis(self) -> None:
        """Test complete drift analysis workflow."""
        detector = AnomalyDetector()

        # Create baseline with normal distribution
        np.random.seed(42)
        baseline = [{"feature": v} for v in np.random.normal(0, 1, 100)]

        # Create current with shifted distribution
        current = [{"feature": v} for v in np.random.normal(2, 1, 100)]

        # Detect drift
        report = detector.detect_drift(current, baseline)

        # Check report structure
        assert "drift_detected" in report.to_dict()
        assert "drift_score" in report.to_dict()
        assert "affected_features" in report.to_dict()
        assert "severity" in report.to_dict()

    def test_recommendations_generation(self) -> None:
        """Test that recommendations are generated correctly."""
        detector = AnomalyDetector()

        # Create data with drift
        baseline = [{"value": v} for v in range(100)]
        current = [{"value": v + 1000} for v in range(100)]

        report = detector.detect_drift(current, baseline)

        # Should have recommendations
        assert len(report.recommendations) > 0

        # Check recommendation content
        rec_text = " ".join(report.recommendations).lower()
        assert "drift" in rec_text or "retrain" in rec_text or "data" in rec_text
