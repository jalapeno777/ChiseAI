"""Tests for quality_gates module."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ml.data.quality_gates import QualityGate, QualityScore


class TestQualityScore:
    """Tests for QualityScore dataclass."""

    def test_quality_score_creation(self) -> None:
        """Test creating a QualityScore."""
        score = QualityScore(
            overall_score=85.0,
            category_scores={
                "completeness": 90.0,
                "validity": 85.0,
                "consistency": 80.0,
                "timeliness": 95.0,
                "uniqueness": 88.0,
            },
            validation_pass_rate=0.9,
            anomaly_score=0.1,
            dataset_id="test_dataset",
        )

        assert score.overall_score == 85.0
        assert score.validation_pass_rate == 0.9
        assert score.dataset_id == "test_dataset"
        assert score.anomaly_score == 0.1

    def test_quality_score_clamping(self) -> None:
        """Test that scores are clamped to valid ranges."""
        score = QualityScore(
            overall_score=150.0,  # Should be clamped to 100
            category_scores={"completeness": -10.0},  # Should be clamped to 0
            validation_pass_rate=1.5,  # Should be clamped to 1.0
            anomaly_score=-0.5,  # Should be clamped to 0.0
        )

        assert score.overall_score == 100.0
        assert score.category_scores["completeness"] == 0.0
        assert score.validation_pass_rate == 1.0
        assert score.anomaly_score == 0.0

    def test_quality_score_to_dict(self) -> None:
        """Test serialization to dictionary."""
        score = QualityScore(
            overall_score=85.0,
            category_scores={"completeness": 90.0},
            validation_pass_rate=0.9,
            anomaly_score=0.1,
            dataset_id="test",
        )

        result = score.to_dict()

        assert result["overall_score"] == 85.0
        assert result["dataset_id"] == "test"
        assert "timestamp" in result


class TestQualityGate:
    """Tests for QualityGate class."""

    def test_quality_gate_creation(self) -> None:
        """Test creating a QualityGate."""
        gate = QualityGate(min_score=80.0)

        assert gate.min_score == 80.0
        assert "completeness" in gate.weights

    def test_custom_weights(self) -> None:
        """Test custom weights are normalized."""
        weights = {"completeness": 50.0, "validity": 50.0}
        gate = QualityGate(weights=weights)

        total = sum(gate.weights.values())
        assert abs(total - 1.0) < 0.01

    def test_check_threshold(self) -> None:
        """Test threshold checking."""
        assert QualityGate.check_threshold(85.0, 80.0) is True
        assert QualityGate.check_threshold(80.0, 80.0) is True
        assert QualityGate.check_threshold(79.0, 80.0) is False

    def test_evaluate_empty_dataset(self) -> None:
        """Test evaluating an empty dataset."""
        gate = QualityGate()
        score = gate.evaluate([], dataset_id="empty")

        # Empty dataset passes validation (no errors), but has no data
        # Score is based on validation pass rate which is 100% for empty
        assert score.dataset_id == "empty"
        # Overall score reflects validation pass rate
        assert score.validation_pass_rate == 1.0

    def test_evaluate_valid_dataset(self) -> None:
        """Test evaluating a valid dataset."""
        gate = QualityGate()

        # Create valid test data
        data = [
            {"timestamp": 1700000000, "feature": 1.0, "label": 0},
            {"timestamp": 1700000001, "feature": 2.0, "label": 1},
            {"timestamp": 1700000002, "feature": 3.0, "label": 0},
        ]

        score = gate.evaluate(data, dataset_id="valid_data")

        assert score.overall_score >= 0.0
        assert score.dataset_id == "valid_data"
        assert "completeness" in score.category_scores
        assert "validity" in score.category_scores

    def test_evaluate_with_missing_values(self) -> None:
        """Test evaluating dataset with missing values."""
        gate = QualityGate()

        data = [
            {"timestamp": 1700000000, "feature": 1.0, "label": 0},
            {"timestamp": 1700000001, "feature": None, "label": 1},  # Missing feature
            {"timestamp": 1700000002, "feature": 3.0},  # Missing label
        ]

        score = gate.evaluate(data)

        # Should have lower completeness score due to missing values
        assert score.category_scores["completeness"] < 100.0

    def test_generate_report(self) -> None:
        """Test generating a quality report."""
        gate = QualityGate(min_score=80.0)

        score = QualityScore(
            overall_score=85.0,
            category_scores={
                "completeness": 90.0,
                "validity": 85.0,
                "consistency": 80.0,
                "timeliness": 95.0,
                "uniqueness": 88.0,
            },
            validation_pass_rate=0.9,
            anomaly_score=0.1,
            dataset_id="test",
        )

        report = gate.generate_report(score)

        assert report["overall_score"] == 85.0
        assert report["threshold"] == 80.0
        assert report["passed"] is True
        assert "category_scores" in report
        assert "recommendations" in report

    def test_generate_report_below_threshold(self) -> None:
        """Test report for score below threshold."""
        gate = QualityGate(min_score=80.0)

        score = QualityScore(
            overall_score=70.0,
            category_scores={
                "completeness": 60.0,
                "validity": 70.0,
                "consistency": 80.0,
                "timeliness": 90.0,
                "uniqueness": 85.0,
            },
            validation_pass_rate=0.7,
            anomaly_score=0.3,
            dataset_id="test",
        )

        report = gate.generate_report(score)

        assert report["passed"] is False
        assert len(report["recommendations"]) > 0

    def test_recommendations_for_issues(self) -> None:
        """Test that recommendations are generated for issues."""
        gate = QualityGate(min_score=80.0)

        score = QualityScore(
            overall_score=50.0,
            category_scores={
                "completeness": 50.0,  # Below 80
                "validity": 90.0,
                "consistency": 90.0,
                "timeliness": 90.0,
                "uniqueness": 90.0,
            },
            validation_pass_rate=0.5,
            anomaly_score=0.6,  # High anomaly score
            dataset_id="test",
        )

        report = gate.generate_report(score)

        # Should have recommendations for completeness and anomaly
        rec_text = " ".join(report["recommendations"])
        assert "missing" in rec_text.lower() or "completeness" in rec_text.lower()


class TestQualityGateIntegration:
    """Integration tests for QualityGate."""

    def test_full_evaluation_flow(self) -> None:
        """Test complete evaluation flow."""
        gate = QualityGate(min_score=75.0)

        # Create test dataset
        data = [
            {
                "timestamp": datetime.now(UTC).timestamp(),
                "feature_1": 1.5,
                "feature_2": 2.5,
                "label": 0,
            }
            for _ in range(20)
        ]

        # Evaluate
        score = gate.evaluate(data, dataset_id="integration_test")

        # Check threshold
        passed = gate.check_threshold(score.overall_score, gate.min_score)

        # Generate report
        report = gate.generate_report(score)

        assert "overall_score" in report
        assert "passed" in report
        assert isinstance(passed, bool)