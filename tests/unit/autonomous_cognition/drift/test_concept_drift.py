"""Unit tests for concept drift detection system."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from autonomous_cognition.drift.concept_drift import (
    ConceptDriftDetector,
    DriftScore,
    ErrorPattern,
)


class TestFeatureExtraction:
    """Test feature extraction functionality."""

    def test_extract_features_from_predictions(self) -> None:
        """Test extracting features from prediction data."""
        detector = ConceptDriftDetector()

        data = {
            "predictions": [
                {"confidence": 0.9, "label": "A"},
                {"confidence": 0.7, "label": "B"},
                {"confidence": 0.8, "label": "A"},
            ]
        }

        features = detector.extract_features(data)

        assert "prediction_confidence" in features
        assert features["prediction_confidence"]["mean"] == pytest.approx(0.8, abs=0.01)
        assert features["prediction_confidence"]["min"] == 0.7
        assert features["prediction_confidence"]["max"] == 0.9

    def test_extract_features_from_errors(self) -> None:
        """Test extracting error type distribution."""
        detector = ConceptDriftDetector()

        data = {
            "errors": [
                {"type": "validation", "message": "Invalid input"},
                {"type": "timeout", "message": "Request timed out"},
                {"type": "validation", "message": "Missing field"},
            ]
        }

        features = detector.extract_features(data)

        assert "error_type_distribution" in features
        assert features["error_type_distribution"]["validation"] == 2
        assert features["error_type_distribution"]["timeout"] == 1

    def test_extract_features_from_decisions(self) -> None:
        """Test extracting decision type distribution."""
        detector = ConceptDriftDetector()

        data = {
            "decisions": [
                {"type": "approve", "id": 1},
                {"type": "reject", "id": 2},
                {"type": "approve", "id": 3},
            ]
        }

        features = detector.extract_features(data)

        assert "decision_type_distribution" in features
        assert features["decision_type_distribution"]["approve"] == 2
        assert features["decision_type_distribution"]["reject"] == 1

    def test_extract_features_from_risks(self) -> None:
        """Test extracting risk level distribution."""
        detector = ConceptDriftDetector()

        data = {
            "risks": [
                {"level": "high", "score": 0.9},
                {"level": "low", "score": 0.2},
                {"level": "medium", "score": 0.5},
            ]
        }

        features = detector.extract_features(data)

        assert "risk_level_distribution" in features
        assert features["risk_level_distribution"]["high"] == 1
        assert features["risk_level_distribution"]["medium"] == 1
        assert features["risk_level_distribution"]["low"] == 1

    def test_extract_features_empty_data(self) -> None:
        """Test that empty data raises ValueError."""
        detector = ConceptDriftDetector()

        with pytest.raises(ValueError, match="cannot be empty"):
            detector.extract_features({})

    def test_extract_features_includes_timestamp(self) -> None:
        """Test that extracted features include timestamp."""
        detector = ConceptDriftDetector()

        data = {"predictions": [{"confidence": 0.9}]}
        features = detector.extract_features(data)

        assert "timestamp" in features
        # Should be parseable as datetime
        datetime.fromisoformat(features["timestamp"])


class TestDistributionComparison:
    """Test distribution comparison functionality."""

    def test_compare_identical_distributions(self) -> None:
        """Test comparing identical distributions results in zero divergence."""
        detector = ConceptDriftDetector()

        baseline = {"A": 0.5, "B": 0.5}
        current = {"A": 0.5, "B": 0.5}

        score = detector.compare_distributions(baseline, current, "test_feature")

        assert score.kl_divergence == pytest.approx(0.0, abs=0.001)
        assert score.js_divergence == pytest.approx(0.0, abs=0.001)
        assert not score.is_drift

    def test_compare_different_distributions(self) -> None:
        """Test comparing different distributions detects drift."""
        detector = ConceptDriftDetector()

        baseline = {"A": 0.9, "B": 0.1}
        current = {"A": 0.1, "B": 0.9}

        score = detector.compare_distributions(baseline, current, "test_feature")

        assert score.kl_divergence > 0.5
        assert score.js_divergence > 0.2
        assert score.is_drift
        assert score.severity in ["medium", "high"]

    def test_compare_distributions_normalizes_input(self) -> None:
        """Test that input distributions are normalized."""
        detector = ConceptDriftDetector()

        baseline = {"A": 90, "B": 10}  # Not normalized
        current = {"A": 10, "B": 90}  # Not normalized

        score = detector.compare_distributions(baseline, current, "test_feature")

        # Should still work correctly after normalization
        assert score.kl_divergence > 0
        assert score.is_drift

    def test_compare_distributions_empty_raises_error(self) -> None:
        """Test that empty distributions raise ValueError."""
        detector = ConceptDriftDetector()

        with pytest.raises(ValueError, match="cannot be empty"):
            detector.compare_distributions({}, {}, "test")

    def test_compare_distributions_zero_sum_raises_error(self) -> None:
        """Test that zero-sum distributions raise ValueError."""
        detector = ConceptDriftDetector()

        with pytest.raises(ValueError, match="cannot be zero"):
            detector.compare_distributions({"A": 0, "B": 0}, {"A": 1}, "test")


class TestKLDivergenceCalculation:
    """Test KL divergence calculation."""

    def test_kl_divergence_symmetric_reference(self) -> None:
        """Test KL divergence against known values."""
        detector = ConceptDriftDetector()

        # These are two different distributions
        p = {"A": 0.7, "B": 0.3}
        q = {"A": 0.3, "B": 0.7}

        score = detector.compare_distributions(p, q, "test")

        # KL divergence should be positive
        assert score.kl_divergence > 0
        # JS divergence should be bounded [0, 1]
        assert 0 <= score.js_divergence <= 1

    def test_kl_divergence_handles_missing_categories(self) -> None:
        """Test handling distributions with different category sets."""
        detector = ConceptDriftDetector()

        baseline = {"A": 1.0}
        current = {"A": 0.5, "B": 0.5}

        score = detector.compare_distributions(baseline, current, "test")

        # Should handle missing categories gracefully
        assert score.kl_divergence >= 0
        assert score.js_divergence >= 0


class TestNovelPatternDetection:
    """Test novel error pattern detection."""

    def test_detect_novel_error_type(self) -> None:
        """Test detection of a completely new error type."""
        detector = ConceptDriftDetector()

        errors = [
            {
                "type": "new_error",
                "message": "Something new happened",
                "severity": "high",
            },
        ]

        patterns = detector.detect_novel_patterns(errors)

        assert len(patterns) == 1
        assert patterns[0].is_novel is True
        assert patterns[0].error_type == "new_error"

    def test_detect_existing_error_type(self) -> None:
        """Test handling of previously seen error types."""
        detector = ConceptDriftDetector()

        # First detection
        errors1 = [{"type": "known_error", "message": "First occurrence"}]
        detector.detect_novel_patterns(errors1)

        # Second detection of same type
        errors2 = [{"type": "known_error", "message": "Second occurrence"}]
        patterns = detector.detect_novel_patterns(errors2)

        assert len(patterns) == 1
        assert patterns[0].is_novel is False

    def test_detect_multiple_error_patterns(self) -> None:
        """Test detection of multiple error patterns simultaneously."""
        detector = ConceptDriftDetector()

        errors = [
            {"type": "timeout", "message": "Timeout 1", "severity": "medium"},
            {"type": "validation", "message": "Validation 1", "severity": "low"},
            {"type": "timeout", "message": "Timeout 2", "severity": "medium"},
        ]

        patterns = detector.detect_novel_patterns(errors)

        assert len(patterns) == 2  # Two unique types
        timeout_pattern = next(p for p in patterns if p.error_type == "timeout")
        assert timeout_pattern.count == 2

    def test_error_pattern_tracking(self) -> None:
        """Test that error patterns are tracked over time."""
        detector = ConceptDriftDetector()

        errors = [
            {"type": "test_error", "message": "Test message 1"},
            {"type": "test_error", "message": "Test message 2"},
        ]

        detector.detect_novel_patterns(errors)

        # Should be stored in detector
        assert "pattern_test_error" in detector._error_patterns
        assert detector._error_patterns["pattern_test_error"].count == 2

    def test_detect_novel_patterns_invalid_input(self) -> None:
        """Test that invalid input raises appropriate errors."""
        detector = ConceptDriftDetector()

        with pytest.raises(ValueError, match="must be a list"):
            detector.detect_novel_patterns("not a list")  # type: ignore

    def test_detect_novel_patterns_handles_non_dict_errors(self) -> None:
        """Test graceful handling of non-dict error items."""
        detector = ConceptDriftDetector()

        errors = [
            {"type": "valid", "message": "Valid error"},
            "not a dict",  # Should be skipped
            {"type": "another", "message": "Another valid"},
        ]

        patterns = detector.detect_novel_patterns(errors)

        assert len(patterns) == 2


class TestModelAssumptionValidation:
    """Test model assumption validation."""

    def test_check_assumptions_with_no_data(self) -> None:
        """Test assumption checking with no historical data."""
        detector = ConceptDriftDetector()

        result = detector.check_model_assumptions()

        # Should pass when there's no data to check
        assert result is True

    def test_check_assumptions_detects_correlation(self) -> None:
        """Test detection of high feature correlation."""
        detector = ConceptDriftDetector()

        # Add highly correlated features
        for i in range(50):
            detector.update_feature_history("feature_a", i * 1.0)
            detector.update_feature_history(
                "feature_b", i * 1.0 + 0.1
            )  # Highly correlated

        result = detector.check_model_assumptions()

        # High correlation should cause assumption violation
        assert result is False
        assert len(detector._assumption_violations) > 0
        assert (
            detector._assumption_violations[0]["assumption"] == "feature_independence"
        )

    def test_check_assumptions_detects_distribution_drift(self) -> None:
        """Test detection of distribution drift."""
        detector = ConceptDriftDetector()

        # Add baseline data (clustered around 1.0)
        for i in range(50):
            detector.update_feature_history("test_feature", 1.0 + i * 0.01)

        # Add current data (clustered around 100.0 - significant drift)
        for i in range(50):
            detector.update_feature_history("test_feature", 100.0 + i * 0.01)

        result = detector.check_model_assumptions()

        # Should detect distribution drift
        violations = [
            v
            for v in detector._assumption_violations
            if v.get("assumption") == "distribution_stability"
        ]
        assert len(violations) > 0 or not result

    def test_check_assumptions_detects_outliers(self) -> None:
        """Test detection of high outlier frequency."""
        detector = ConceptDriftDetector()

        # Add data with many outliers (15% outlier rate to exceed 10% threshold)
        for i in range(100):
            if i < 85:
                detector.update_feature_history("outlier_feature", 1.0)
            else:
                detector.update_feature_history("outlier_feature", 100.0)  # Outliers

        result = detector.check_model_assumptions()

        # Should detect high outlier rate
        violations = [
            v
            for v in detector._assumption_violations
            if v.get("assumption") == "outlier_frequency"
        ]
        assert len(violations) > 0 or not result


class TestConceptDriftAlert:
    """Test concept drift alerting."""

    def test_drift_report_structure(self) -> None:
        """Test that drift report has correct structure."""
        detector = ConceptDriftDetector()

        # Add some data to generate drift scores
        for i in range(100):
            detector.update_feature_history("feature1", i * 0.01)

        report = detector.get_drift_report()

        assert "timestamp" in report
        assert "drift_scores" in report
        assert "error_patterns" in report
        assert "assumption_violations" in report
        assert "summary" in report

    def test_drift_report_summary(self) -> None:
        """Test drift report summary content."""
        detector = ConceptDriftDetector()

        report = detector.get_drift_report()

        assert "has_drift" in report["summary"]
        assert "has_novel_patterns" in report["summary"]
        assert "has_violations" in report["summary"]
        assert "overall_severity" in report["summary"]
        assert report["summary"]["overall_severity"] in [
            "normal",
            "attention",
            "warning",
            "critical",
        ]

    def test_drift_report_with_detected_drift(self) -> None:
        """Test report generation when drift is detected."""
        detector = ConceptDriftDetector()

        # Add baseline data (clustered around 1.0)
        for i in range(50):
            detector.update_feature_history("drifting_feature", 1.0 + i * 0.01)

        # Add drifted data (clustered around 100.0 - significant drift)
        for i in range(50):
            detector.update_feature_history("drifting_feature", 100.0 + i * 0.01)

        report = detector.get_drift_report()

        assert report["summary"]["has_drift"] is True
        assert report["summary"]["overall_severity"] in ["warning", "critical"]
        assert len(report["drift_scores"]) > 0

    def test_drift_report_with_novel_patterns(self) -> None:
        """Test report when novel patterns are detected."""
        detector = ConceptDriftDetector()

        errors = [{"type": "novel_error", "message": "New error type"}]
        detector.detect_novel_patterns(errors)

        report = detector.get_drift_report()

        assert report["summary"]["has_novel_patterns"] is True


class TestErrorClustering:
    """Test error clustering functionality."""

    def test_cluster_errors_by_type(self) -> None:
        """Test clustering errors by their type."""
        detector = ConceptDriftDetector()

        errors = [
            {"type": "timeout", "message": "Timeout 1"},
            {"type": "timeout", "message": "Timeout 2"},
            {"type": "timeout", "message": "Timeout 3"},
            {"type": "validation", "message": "Validation 1"},
            {"type": "validation", "message": "Validation 2"},
        ]

        clusters = detector.get_error_clusters(errors, n_clusters=2)

        assert len(clusters) > 0
        # Timeout cluster should be first (most frequent)
        assert clusters[0]["error_type"] == "timeout"
        assert clusters[0]["count"] == 3

    def test_cluster_errors_empty_list(self) -> None:
        """Test clustering with empty error list."""
        detector = ConceptDriftDetector()

        clusters = detector.get_error_clusters([])

        assert clusters == []

    def test_cluster_errors_limit_n_clusters(self) -> None:
        """Test that n_clusters parameter limits result size."""
        detector = ConceptDriftDetector()

        errors = [
            {"type": "A", "message": "A1"},
            {"type": "B", "message": "B1"},
            {"type": "C", "message": "C1"},
            {"type": "D", "message": "D1"},
        ]

        clusters = detector.get_error_clusters(errors, n_clusters=2)

        assert len(clusters) <= 2

    def test_cluster_includes_representative_examples(self) -> None:
        """Test that clusters include representative error examples."""
        detector = ConceptDriftDetector()

        errors = [
            {"type": "timeout", "message": "Timeout occurred"},
            {"type": "timeout", "message": "Another timeout"},
        ]

        clusters = detector.get_error_clusters(errors)

        assert len(clusters) > 0
        assert "representative_examples" in clusters[0]
        assert len(clusters[0]["representative_examples"]) > 0


class TestDriftScore:
    """Test DriftScore dataclass."""

    def test_drift_score_creation(self) -> None:
        """Test creating a DriftScore instance."""
        score = DriftScore(
            feature_name="test",
            baseline_distribution={"A": 0.5},
            current_distribution={"A": 0.5},
            kl_divergence=0.0,
            js_divergence=0.0,
            is_drift=False,
            severity="low",
        )

        assert score.feature_name == "test"
        assert not score.is_drift

    def test_drift_score_to_dict(self) -> None:
        """Test converting DriftScore to dictionary."""
        score = DriftScore(
            feature_name="test",
            baseline_distribution={"A": 0.5},
            current_distribution={"A": 0.6},
            kl_divergence=0.1,
            js_divergence=0.05,
            is_drift=True,
            severity="medium",
        )

        d = score.to_dict()

        assert d["feature_name"] == "test"
        assert d["kl_divergence"] == 0.1
        assert d["is_drift"] is True


class TestErrorPattern:
    """Test ErrorPattern dataclass."""

    def test_error_pattern_creation(self) -> None:
        """Test creating an ErrorPattern instance."""
        now = datetime.now()
        pattern = ErrorPattern(
            pattern_id="test_pattern",
            error_type="timeout",
            description="Timeout error",
            first_seen=now,
            last_seen=now,
            count=1,
            severity="medium",
            is_novel=True,
        )

        assert pattern.pattern_id == "test_pattern"
        assert pattern.is_novel is True

    def test_error_pattern_to_dict(self) -> None:
        """Test converting ErrorPattern to dictionary."""
        now = datetime.now()
        pattern = ErrorPattern(
            pattern_id="test_pattern",
            error_type="timeout",
            description="Timeout error",
            first_seen=now,
            last_seen=now,
            count=5,
            severity="high",
            examples=["Example 1", "Example 2"],
            is_novel=False,
        )

        d = pattern.to_dict()

        assert d["pattern_id"] == "test_pattern"
        assert d["count"] == 5
        assert len(d["examples"]) == 2


class TestFeatureHistory:
    """Test feature history tracking."""

    def test_update_feature_history(self) -> None:
        """Test updating feature history."""
        detector = ConceptDriftDetector()

        detector.update_feature_history("test", 1.0)
        detector.update_feature_history("test", 2.0)

        assert len(detector._feature_history["test"]) == 2

    def test_feature_history_max_size(self) -> None:
        """Test that feature history is limited to max size."""
        detector = ConceptDriftDetector()
        detector._max_history_size = 100

        for i in range(150):
            detector.update_feature_history("test", float(i))

        assert len(detector._feature_history["test"]) == 100


class TestBaselineManagement:
    """Test baseline distribution management."""

    def test_set_baseline(self) -> None:
        """Test setting a baseline distribution."""
        detector = ConceptDriftDetector()

        distribution = {"A": 0.7, "B": 0.3}
        detector.set_baseline("test_feature", distribution)

        assert "test_feature" in detector._baseline_distributions
        assert detector._baseline_distributions["test_feature"] == distribution

    def test_set_baseline_creates_copy(self) -> None:
        """Test that set_baseline creates a copy of the distribution."""
        detector = ConceptDriftDetector()

        distribution = {"A": 0.7, "B": 0.3}
        detector.set_baseline("test_feature", distribution)

        # Modify original
        distribution["A"] = 0.5

        # Baseline should be unchanged
        assert detector._baseline_distributions["test_feature"]["A"] == 0.7


class TestIntegration:
    """Integration tests for concept drift detection."""

    def test_full_drift_detection_workflow(self) -> None:
        """Test a complete drift detection workflow."""
        detector = ConceptDriftDetector()

        # Step 1: Extract features from baseline data
        baseline_data = {
            "predictions": [{"confidence": 0.8 + i * 0.01} for i in range(50)],
            "errors": [{"type": "old_error", "message": "Old"} for _ in range(5)],
        }
        baseline_features = detector.extract_features(baseline_data)

        # Update feature history with baseline
        for conf in baseline_data["predictions"]:
            detector.update_feature_history("confidence", conf["confidence"])

        # Step 2: Set baseline
        if "prediction_confidence" in baseline_features:
            detector.set_baseline(
                "confidence", baseline_features["prediction_confidence"]["distribution"]
            )

        # Step 3: Process new (drifted) data
        drifted_data = {
            "predictions": [{"confidence": 0.3 + i * 0.01} for i in range(50)],
            "errors": [
                {"type": "old_error", "message": "Old"},
                {"type": "new_error", "message": "New!"},  # Novel pattern
            ],
        }

        # Update feature history with drifted data
        for conf in drifted_data["predictions"]:
            detector.update_feature_history("confidence", conf["confidence"])

        # Step 4: Detect novel patterns
        patterns = detector.detect_novel_patterns(drifted_data["errors"])

        # Step 5: Check assumptions
        assumptions_valid = detector.check_model_assumptions()

        # Step 6: Generate report
        report = detector.get_drift_report()

        # Verify results
        assert len(patterns) >= 1
        assert report["summary"]["has_novel_patterns"] is True
        assert "monitored_features" in report["summary"]

    def test_detector_with_mock_clients(self) -> None:
        """Test detector initialization with mock clients."""
        mock_redis = MagicMock()
        mock_qdrant = MagicMock()

        detector = ConceptDriftDetector(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        assert detector.redis_client is mock_redis
        assert detector.qdrant_client is mock_qdrant
