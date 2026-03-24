"""Unit tests for the learning loop closure system."""

from __future__ import annotations

from datetime import datetime

from autonomous_cognition.metacog.learning_loop import (
    BiasType,
    CalibrationRecord,
    LearningLoop,
    LinkResult,
    OutcomeData,
    PredictionData,
)


class TestLearningLoop:
    """Test suite for LearningLoop class."""

    def test_register_prediction_success(self) -> None:
        """Test successful prediction registration."""
        loop = LearningLoop()

        prediction_data = {
            "prediction_type": "test_type",
            "predicted_value": 100,
            "confidence": 0.8,
            "timestamp": datetime.now(),
            "context": {"key": "value"},
            "expected_outcome": 105,
        }

        result = loop.register_prediction("pred-001", prediction_data)

        assert result is True
        assert "pred-001" in loop._local_predictions
        pred = loop._local_predictions["pred-001"]
        assert pred.prediction_type == "test_type"
        assert pred.confidence == 0.8
        assert pred.predicted_value == 100

    def test_register_prediction_defaults(self) -> None:
        """Test prediction registration with default values."""
        loop = LearningLoop()

        # Minimal data
        prediction_data = {}

        result = loop.register_prediction("pred-002", prediction_data)

        assert result is True
        pred = loop._local_predictions["pred-002"]
        assert pred.prediction_type == "unknown"
        assert pred.confidence == 0.5
        assert pred.context == {}

    def test_record_outcome_success(self) -> None:
        """Test successful outcome recording."""
        loop = LearningLoop()

        # First register a prediction
        loop.register_prediction(
            "pred-003",
            {
                "prediction_type": "test",
                "confidence": 0.7,
            },
        )

        outcome_data = {
            "outcome_id": "out-001",
            "actual_value": 100,
            "timestamp": datetime.now(),
            "metadata": {"source": "test"},
        }

        result = loop.record_outcome("pred-003", outcome_data)

        assert result is True
        assert "out-001" in loop._local_outcomes
        outcome = loop._local_outcomes["out-001"]
        assert outcome.prediction_id == "pred-003"
        assert outcome.actual_value == 100

    def test_record_outcome_auto_generates_id(self) -> None:
        """Test that outcome_id is auto-generated if not provided."""
        loop = LearningLoop()

        loop.register_prediction("pred-004", {"prediction_type": "test"})

        outcome_data = {
            "actual_value": 50,
            "timestamp": datetime.now(),
        }

        loop.record_outcome("pred-004", outcome_data)

        # Should create an outcome with a generated ID
        assert len(loop._local_outcomes) == 1

    def test_link_prediction_to_outcome_success(self) -> None:
        """Test successful prediction-outcome linking."""
        loop = LearningLoop()

        loop.register_prediction("pred-005", {"prediction_type": "test"})
        # Don't record outcome - manually link instead to test explicit linking
        loop._local_outcomes["out-005"] = OutcomeData(
            outcome_id="out-005",
            prediction_id="pred-005",
            actual_value=100,
            timestamp=datetime.now(),
        )

        result = loop.link_prediction_to_outcome("pred-005", "out-005")

        assert result == LinkResult.SUCCESS
        assert loop._local_predictions["pred-005"].linked is True
        assert loop._local_predictions["pred-005"].outcome_id == "out-005"

    def test_link_prediction_not_found(self) -> None:
        """Test linking when prediction doesn't exist."""
        loop = LearningLoop()

        result = loop.link_prediction_to_outcome("nonexistent", "out-001")

        assert result == LinkResult.PREDICTION_NOT_FOUND

    def test_link_outcome_not_found(self) -> None:
        """Test linking when outcome doesn't exist."""
        loop = LearningLoop()

        loop.register_prediction("pred-006", {"prediction_type": "test"})

        result = loop.link_prediction_to_outcome("pred-006", "nonexistent")

        assert result == LinkResult.OUTCOME_NOT_FOUND

    def test_link_already_linked(self) -> None:
        """Test linking when already linked."""
        loop = LearningLoop()

        loop.register_prediction("pred-007", {"prediction_type": "test"})
        loop.record_outcome("pred-007", {"outcome_id": "out-007", "actual_value": 100})
        loop.link_prediction_to_outcome("pred-007", "out-007")

        # Try to link again
        result = loop.link_prediction_to_outcome("pred-007", "out-007")

        assert result == LinkResult.ALREADY_LINKED

    def test_link_mismatch(self) -> None:
        """Test linking when outcome is for different prediction."""
        loop = LearningLoop()

        loop.register_prediction("pred-008", {"prediction_type": "test"})
        loop.register_prediction("pred-009", {"prediction_type": "test"})
        loop.record_outcome("pred-008", {"outcome_id": "out-008", "actual_value": 100})

        # Try to link pred-009 to out-008 (which belongs to pred-008)
        result = loop.link_prediction_to_outcome("pred-009", "out-008")

        assert result == LinkResult.MISMATCH

    def test_calculate_calibration_delta_success(self) -> None:
        """Test calibration delta calculation for successful prediction."""
        loop = LearningLoop()

        # Register prediction with high confidence of success
        loop.register_prediction(
            "pred-010",
            {
                "prediction_type": "test",
                "confidence": 0.9,
                "predicted_value": True,
                "expected_outcome": True,
            },
        )
        loop.record_outcome("pred-010", {"outcome_id": "out-010", "actual_value": True})
        loop.link_prediction_to_outcome("pred-010", "out-010")

        # Prediction was correct with 0.9 confidence, so delta should be |0.9 - 1.0| = 0.1
        delta = loop.calculate_calibration_delta("pred-010")

        assert abs(delta - 0.1) < 0.001

    def test_calculate_calibration_delta_failure(self) -> None:
        """Test calibration delta calculation for failed prediction."""
        loop = LearningLoop()

        # Register prediction with high confidence of success that fails
        loop.register_prediction(
            "pred-011",
            {
                "prediction_type": "test",
                "confidence": 0.9,
                "predicted_value": True,
                "expected_outcome": True,
            },
        )
        loop.record_outcome(
            "pred-011", {"outcome_id": "out-011", "actual_value": False}
        )
        loop.link_prediction_to_outcome("pred-011", "out-011")

        # Prediction was wrong with 0.9 confidence, so delta should be |0.9 - 0.0| = 0.9
        delta = loop.calculate_calibration_delta("pred-011")

        assert abs(delta - 0.9) < 0.001

    def test_calculate_calibration_delta_unlinked(self) -> None:
        """Test calibration delta for unlinked prediction returns 0."""
        loop = LearningLoop()

        loop.register_prediction("pred-012", {"prediction_type": "test"})

        delta = loop.calculate_calibration_delta("pred-012")

        assert delta == 0.0

    def test_update_calibration(self) -> None:
        """Test calibration tracking updates."""
        loop = LearningLoop()

        result = loop.update_calibration("type_a", 0.2)

        assert result is True
        assert "type_a" in loop._local_calibration
        record = loop._local_calibration["type_a"]
        assert record.total_predictions == 1
        assert record.total_error == 0.2
        assert record.average_error == 0.2

    def test_update_calibration_multiple(self) -> None:
        """Test calibration tracking with multiple updates."""
        loop = LearningLoop()

        loop.update_calibration("type_b", 0.2)
        loop.update_calibration("type_b", 0.4)
        loop.update_calibration("type_b", 0.0)

        record = loop._local_calibration["type_b"]
        assert record.total_predictions == 3
        assert abs(record.total_error - 0.6) < 0.001
        assert abs(record.average_error - 0.2) < 0.001

    def test_identify_overconfidence_bias(self) -> None:
        """Test detection of overconfidence bias."""
        loop = LearningLoop()

        # Create multiple predictions with overconfidence pattern
        for i in range(15):
            pred_id = f"pred-over-{i}"
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "risky_type",
                    "confidence": 0.9,  # High confidence
                    "predicted_value": True,
                    "expected_outcome": True,
                },
            )
            # Most fail (low success rate with high confidence = overconfidence)
            success = i < 3  # Only 3 out of 15 succeed
            loop.record_outcome(
                pred_id,
                {"outcome_id": f"out-over-{i}", "actual_value": success},
            )
            loop.link_prediction_to_outcome(pred_id, f"out-over-{i}")

        biases = loop.identify_systematic_biases()

        assert "risky_type" in biases
        assert biases["risky_type"] == BiasType.OVERCONFIDENCE

    def test_identify_underconfidence_bias(self) -> None:
        """Test detection of underconfidence bias."""
        loop = LearningLoop()

        # Create predictions with underconfidence pattern
        for i in range(15):
            pred_id = f"pred-under-{i}"
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "conservative_type",
                    "confidence": 0.3,  # Low confidence
                    "predicted_value": True,
                    "expected_outcome": True,
                },
            )
            # Most succeed (high success rate with low confidence = underconfidence)
            success = i >= 2  # 13 out of 15 succeed
            loop.record_outcome(
                pred_id,
                {"outcome_id": f"out-under-{i}", "actual_value": success},
            )
            loop.link_prediction_to_outcome(pred_id, f"out-under-{i}")

        biases = loop.identify_systematic_biases()

        assert "conservative_type" in biases
        assert biases["conservative_type"] == BiasType.UNDERCONFIDENCE

    def test_identify_no_bias_well_calibrated(self) -> None:
        """Test that well-calibrated predictions show no bias."""
        loop = LearningLoop()

        # Create well-calibrated predictions
        for i in range(20):
            pred_id = f"pred-good-{i}"
            confidence = 0.7
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "calibrated_type",
                    "confidence": confidence,
                    "predicted_value": True,
                    "expected_outcome": True,
                },
            )
            # Approximately match confidence level
            success = i < 14  # ~70% success rate
            loop.record_outcome(
                pred_id,
                {"outcome_id": f"out-good-{i}", "actual_value": success},
            )
            loop.link_prediction_to_outcome(pred_id, f"out-good-{i}")

        biases = loop.identify_systematic_biases()

        assert "calibrated_type" in biases
        assert biases["calibrated_type"] == BiasType.NONE

    def test_identify_not_enough_data(self) -> None:
        """Test that insufficient data returns no bias."""
        loop = LearningLoop()

        # Only 5 predictions (need 10+ for bias detection)
        for i in range(5):
            pred_id = f"pred-few-{i}"
            loop.register_prediction(
                pred_id,
                {"prediction_type": "new_type", "confidence": 0.9},
            )
            loop.record_outcome(
                pred_id,
                {"outcome_id": f"out-few-{i}", "actual_value": False},
            )
            loop.link_prediction_to_outcome(pred_id, f"out-few-{i}")

        biases = loop.identify_systematic_biases()

        assert "new_type" in biases
        assert biases["new_type"] == BiasType.NONE

    def test_recommend_calibration_adjustments_overconfidence(self) -> None:
        """Test recommendations for overconfidence."""
        loop = LearningLoop()

        # Create overconfident predictions
        for i in range(15):
            pred_id = f"pred-rec-{i}"
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "risky_type",
                    "confidence": 0.9,
                    "predicted_value": True,
                    "expected_outcome": True,
                },
            )
            loop.record_outcome(
                pred_id,
                {"outcome_id": f"out-rec-{i}", "actual_value": False},
            )
            loop.link_prediction_to_outcome(pred_id, f"out-rec-{i}")

        recommendations = loop.recommend_calibration_adjustments()

        assert len(recommendations) > 0
        rec = recommendations[0]
        assert rec["prediction_type"] == "risky_type"
        assert rec["issue"] == "overconfidence"
        assert "confidence_offset" in rec
        assert rec["confidence_offset"] < 0  # Should suggest reducing confidence
        assert rec["priority"] in ["high", "medium"]

    def test_recommend_calibration_adjustments_underconfidence(self) -> None:
        """Test recommendations for underconfidence."""
        loop = LearningLoop()

        # Create underconfident predictions
        for i in range(15):
            pred_id = f"pred-rec2-{i}"
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "conservative_type",
                    "confidence": 0.3,
                    "predicted_value": True,
                    "expected_outcome": True,
                },
            )
            loop.record_outcome(
                pred_id,
                {"outcome_id": f"out-rec2-{i}", "actual_value": True},
            )
            loop.link_prediction_to_outcome(pred_id, f"out-rec2-{i}")

        recommendations = loop.recommend_calibration_adjustments()

        # Find the recommendation for conservative_type
        rec = next(
            (r for r in recommendations if r["prediction_type"] == "conservative_type"),
            None,
        )
        assert rec is not None
        assert rec["issue"] == "underconfidence"
        assert rec["confidence_offset"] > 0  # Should suggest increasing confidence

    def test_recommend_calibration_sorted_by_priority(self) -> None:
        """Test that recommendations are sorted by priority."""
        loop = LearningLoop()

        # Create severe overconfidence (high priority)
        for i in range(15):
            pred_id = f"pred-high-{i}"
            loop.register_prediction(
                pred_id, {"prediction_type": "severe", "confidence": 0.95}
            )
            loop.record_outcome(
                pred_id, {"outcome_id": f"out-high-{i}", "actual_value": False}
            )
            loop.link_prediction_to_outcome(pred_id, f"out-high-{i}")

        # Create moderate underconfidence (medium priority)
        for i in range(15):
            pred_id = f"pred-med-{i}"
            loop.register_prediction(
                pred_id, {"prediction_type": "moderate", "confidence": 0.3}
            )
            loop.record_outcome(
                pred_id, {"outcome_id": f"out-med-{i}", "actual_value": True}
            )
            loop.link_prediction_to_outcome(pred_id, f"out-med-{i}")

        recommendations = loop.recommend_calibration_adjustments()

        # High priority items should come first
        if len(recommendations) >= 2:
            assert recommendations[0]["priority"] == "high"

    def test_get_learning_statistics(self) -> None:
        """Test learning statistics generation."""
        loop = LearningLoop()

        # Add some data
        loop.register_prediction("pred-stat-1", {"prediction_type": "type_a"})
        loop.register_prediction("pred-stat-2", {"prediction_type": "type_b"})
        loop.record_outcome(
            "pred-stat-1", {"outcome_id": "out-stat-1", "actual_value": 100}
        )
        loop.link_prediction_to_outcome("pred-stat-1", "out-stat-1")

        stats = loop.get_learning_statistics()

        assert stats["predictions_made"] == 2
        assert stats["outcomes_recorded"] == 1
        assert stats["linked_pairs"] == 1
        assert "average_calibration_error" in stats
        assert "systematic_bias" in stats
        assert "recommendations" in stats
        assert "timestamp" in stats
        assert "calibration_by_type" in stats

    def test_get_learning_statistics_bias_detection(self) -> None:
        """Test that statistics correctly identify systematic bias."""
        loop = LearningLoop()

        # Create overconfident predictions with explicit expected outcomes
        for i in range(15):
            pred_id = f"pred-bias-{i}"
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "biased_type",
                    "confidence": 0.9,
                    "predicted_value": True,
                    "expected_outcome": True,  # Explicitly expect True
                },
            )
            loop.record_outcome(
                pred_id, {"outcome_id": f"out-bias-{i}", "actual_value": False}
            )
            loop.link_prediction_to_outcome(pred_id, f"out-bias-{i}")

        stats = loop.get_learning_statistics()

        assert stats["systematic_bias"] == "over"
        assert stats["average_calibration_error"] > 0.5


class TestPredictionData:
    """Test suite for PredictionData class."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        pred = PredictionData(
            prediction_id="test-001",
            prediction_type="test",
            predicted_value=100,
            confidence=0.8,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            context={"key": "value"},
            expected_outcome=True,
        )

        data = pred.to_dict()

        assert data["prediction_id"] == "test-001"
        assert data["prediction_type"] == "test"
        assert data["predicted_value"] == 100
        assert data["confidence"] == 0.8
        assert data["timestamp"] == "2024-01-01T12:00:00"
        assert data["context"] == {"key": "value"}
        assert data["expected_outcome"] is True

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "prediction_id": "test-002",
            "prediction_type": "test",
            "predicted_value": 200,
            "confidence": 0.9,
            "timestamp": "2024-01-01T12:00:00",
            "context": {"foo": "bar"},
            "expected_outcome": False,
            "outcome_id": "out-002",
            "linked": True,
        }

        pred = PredictionData.from_dict(data)

        assert pred.prediction_id == "test-002"
        assert pred.prediction_type == "test"
        assert pred.predicted_value == 200
        assert pred.confidence == 0.9
        assert pred.timestamp == datetime(2024, 1, 1, 12, 0, 0)
        assert pred.context == {"foo": "bar"}
        assert pred.expected_outcome is False
        assert pred.outcome_id == "out-002"
        assert pred.linked is True

    def test_serialize_complex_value(self) -> None:
        """Test serialization of complex nested values."""
        pred = PredictionData(
            prediction_id="test-003",
            prediction_type="test",
            predicted_value={"nested": [1, 2, {"deep": "value"}]},
            confidence=0.5,
            timestamp=datetime.now(),
        )

        data = pred.to_dict()

        assert data["predicted_value"] == {"nested": [1, 2, {"deep": "value"}]}


class TestOutcomeData:
    """Test suite for OutcomeData class."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        outcome = OutcomeData(
            outcome_id="out-001",
            prediction_id="pred-001",
            actual_value=150,
            timestamp=datetime(2024, 1, 1, 14, 0, 0),
            metadata={"source": "test"},
        )

        data = outcome.to_dict()

        assert data["outcome_id"] == "out-001"
        assert data["prediction_id"] == "pred-001"
        assert data["actual_value"] == 150
        assert data["timestamp"] == "2024-01-01T14:00:00"
        assert data["metadata"] == {"source": "test"}

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "outcome_id": "out-002",
            "prediction_id": "pred-002",
            "actual_value": 250,
            "timestamp": "2024-01-01T15:00:00",
            "metadata": {"key": "value"},
        }

        outcome = OutcomeData.from_dict(data)

        assert outcome.outcome_id == "out-002"
        assert outcome.prediction_id == "pred-002"
        assert outcome.actual_value == 250
        assert outcome.timestamp == datetime(2024, 1, 1, 15, 0, 0)
        assert outcome.metadata == {"key": "value"}


class TestCalibrationRecord:
    """Test suite for CalibrationRecord class."""

    def test_average_error_zero_predictions(self) -> None:
        """Test average error when no predictions."""
        record = CalibrationRecord(prediction_type="test")

        assert record.average_error == 0.0

    def test_average_error_calculation(self) -> None:
        """Test average error calculation."""
        record = CalibrationRecord(
            prediction_type="test",
            total_predictions=5,
            total_error=1.5,
        )

        assert record.average_error == 0.3

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        record = CalibrationRecord(
            prediction_type="test_type",
            total_predictions=10,
            total_error=2.0,
            adjustments=[{"delta": 0.1}],
            last_updated=datetime(2024, 1, 1, 12, 0, 0),
        )

        data = record.to_dict()

        assert data["prediction_type"] == "test_type"
        assert data["total_predictions"] == 10
        assert data["total_error"] == 2.0
        assert data["average_error"] == 0.2
        assert data["adjustments"] == [{"delta": 0.1}]
        assert data["last_updated"] == "2024-01-01T12:00:00"


class TestEndToEndLearningLoop:
    """End-to-end tests for the complete learning loop."""

    def test_end_to_end_learning_loop_success(self) -> None:
        """Test complete learning loop with successful prediction."""
        loop = LearningLoop()

        # Step 1: Register prediction
        loop.register_prediction(
            "e2e-pred-1",
            {
                "prediction_type": "binary",
                "confidence": 0.85,
                "predicted_value": True,
                "expected_outcome": True,
                "context": {"task": "test"},
            },
        )

        # Step 2: Record outcome
        loop.record_outcome(
            "e2e-pred-1",
            {
                "outcome_id": "e2e-out-1",
                "actual_value": True,
                "metadata": {"verified": True},
            },
        )

        # Step 3: Verify automatic linking
        pred = loop._local_predictions["e2e-pred-1"]
        assert pred.linked is True
        assert pred.outcome_id == "e2e-out-1"

        # Step 4: Check calibration
        delta = loop.calculate_calibration_delta("e2e-pred-1")
        assert abs(delta - 0.15) < 0.001  # |0.85 - 1.0| = 0.15

        # Step 5: Verify calibration was updated
        assert "binary" in loop._local_calibration
        assert loop._local_calibration["binary"].total_predictions == 1

        # Step 6: Check statistics
        stats = loop.get_learning_statistics()
        assert stats["predictions_made"] == 1
        assert stats["outcomes_recorded"] == 1
        assert stats["linked_pairs"] == 1

    def test_end_to_end_learning_loop_failure(self) -> None:
        """Test complete learning loop with failed prediction."""
        loop = LearningLoop()

        # High confidence prediction that fails
        loop.register_prediction(
            "e2e-pred-2",
            {
                "prediction_type": "binary",
                "confidence": 0.9,
                "predicted_value": True,
                "expected_outcome": True,
            },
        )

        loop.record_outcome(
            "e2e-pred-2",
            {"outcome_id": "e2e-out-2", "actual_value": False},
        )

        # High calibration error should be recorded
        delta = loop.calculate_calibration_delta("e2e-pred-2")
        assert abs(delta - 0.9) < 0.001  # |0.9 - 0.0| = 0.9

    def test_end_to_end_multiple_predictions(self) -> None:
        """Test learning loop with multiple predictions of different types."""
        loop = LearningLoop()

        # Type A: Well-calibrated (70% confidence, ~70% success)
        for i in range(10):
            pred_id = f"multi-a-{i}"
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "type_a",
                    "confidence": 0.7,
                    "expected_outcome": True,
                },
            )
            loop.record_outcome(
                pred_id, {"outcome_id": f"out-a-{i}", "actual_value": i < 7}
            )
            loop.link_prediction_to_outcome(pred_id, f"out-a-{i}")

        # Type B: Overconfident (90% confidence, ~20% success)
        for i in range(10):
            pred_id = f"multi-b-{i}"
            loop.register_prediction(
                pred_id,
                {
                    "prediction_type": "type_b",
                    "confidence": 0.9,
                    "expected_outcome": True,
                },
            )
            loop.record_outcome(
                pred_id, {"outcome_id": f"out-b-{i}", "actual_value": i < 2}
            )
            loop.link_prediction_to_outcome(pred_id, f"out-b-{i}")

        stats = loop.get_learning_statistics()

        assert stats["predictions_made"] == 20
        assert stats["outcomes_recorded"] == 20
        assert stats["linked_pairs"] == 20

        # Should detect overconfidence in type_b
        biases = loop.identify_systematic_biases()
        assert biases["type_a"] == BiasType.NONE
        assert biases["type_b"] == BiasType.OVERCONFIDENCE

        # Should have recommendation for type_b
        recommendations = loop.recommend_calibration_adjustments()
        type_b_recs = [r for r in recommendations if r["prediction_type"] == "type_b"]
        assert len(type_b_recs) > 0
        assert type_b_recs[0]["issue"] == "overconfidence"

    def test_numeric_prediction_with_tolerance(self) -> None:
        """Test numeric predictions with tolerance-based success evaluation."""
        loop = LearningLoop()

        # Prediction: value of 100
        loop.register_prediction(
            "num-pred-1",
            {
                "prediction_type": "numeric",
                "confidence": 0.8,
                "predicted_value": 100,
            },
        )

        # Outcome: 102 (within 10% tolerance of 100)
        loop.record_outcome(
            "num-pred-1",
            {"outcome_id": "num-out-1", "actual_value": 102},
        )
        loop.link_prediction_to_outcome("num-pred-1", "num-out-1")

        # Should be considered success
        delta = loop.calculate_calibration_delta("num-pred-1")
        assert abs(delta - 0.2) < 0.001  # |0.8 - 1.0| = 0.2

    def test_numeric_prediction_outside_tolerance(self) -> None:
        """Test numeric predictions outside tolerance."""
        loop = LearningLoop()

        # Prediction: value of 100
        loop.register_prediction(
            "num-pred-2",
            {
                "prediction_type": "numeric",
                "confidence": 0.8,
                "predicted_value": 100,
            },
        )

        # Outcome: 150 (outside 10% tolerance of 100)
        loop.record_outcome(
            "num-pred-2",
            {"outcome_id": "num-out-2", "actual_value": 150},
        )
        loop.link_prediction_to_outcome("num-pred-2", "num-out-2")

        # Should be considered failure
        delta = loop.calculate_calibration_delta("num-pred-2")
        assert abs(delta - 0.8) < 0.001  # |0.8 - 0.0| = 0.8


class TestEvaluateSuccess:
    """Tests for the _evaluate_success method."""

    def test_evaluate_success_binary_true(self) -> None:
        """Test binary prediction that matches expected outcome."""
        loop = LearningLoop()

        pred = PredictionData(
            prediction_id="test",
            prediction_type="binary",
            predicted_value=True,
            confidence=0.8,
            timestamp=datetime.now(),
            expected_outcome=True,
        )
        outcome = OutcomeData(
            outcome_id="out",
            prediction_id="test",
            actual_value=True,
            timestamp=datetime.now(),
        )

        result = loop._evaluate_success(pred, outcome)
        assert result == 1.0

    def test_evaluate_success_binary_false(self) -> None:
        """Test binary prediction that doesn't match expected outcome."""
        loop = LearningLoop()

        pred = PredictionData(
            prediction_id="test",
            prediction_type="binary",
            predicted_value=True,
            confidence=0.8,
            timestamp=datetime.now(),
            expected_outcome=True,
        )
        outcome = OutcomeData(
            outcome_id="out",
            prediction_id="test",
            actual_value=False,
            timestamp=datetime.now(),
        )

        result = loop._evaluate_success(pred, outcome)
        assert result == 0.0

    def test_evaluate_success_numeric_exact(self) -> None:
        """Test numeric prediction with exact match."""
        loop = LearningLoop()

        pred = PredictionData(
            prediction_id="test",
            prediction_type="numeric",
            predicted_value=100,
            confidence=0.8,
            timestamp=datetime.now(),
        )
        outcome = OutcomeData(
            outcome_id="out",
            prediction_id="test",
            actual_value=100,
            timestamp=datetime.now(),
        )

        result = loop._evaluate_success(pred, outcome)
        assert result == 1.0

    def test_evaluate_success_numeric_partial(self) -> None:
        """Test numeric prediction with partial match (within 2x tolerance)."""
        loop = LearningLoop()

        pred = PredictionData(
            prediction_id="test",
            prediction_type="numeric",
            predicted_value=100,
            confidence=0.8,
            timestamp=datetime.now(),
        )
        outcome = OutcomeData(
            outcome_id="out",
            prediction_id="test",
            actual_value=115,  # Within 2x tolerance (20) of 100
            timestamp=datetime.now(),
        )

        result = loop._evaluate_success(pred, outcome)
        assert result == 0.5

    def test_evaluate_success_string_match(self) -> None:
        """Test string prediction with match."""
        loop = LearningLoop()

        pred = PredictionData(
            prediction_id="test",
            prediction_type="category",
            predicted_value="category_a",
            confidence=0.8,
            timestamp=datetime.now(),
            expected_outcome="category_a",
        )
        outcome = OutcomeData(
            outcome_id="out",
            prediction_id="test",
            actual_value="category_a",
            timestamp=datetime.now(),
        )

        result = loop._evaluate_success(pred, outcome)
        assert result == 1.0

    def test_evaluate_success_no_expected_outcome(self) -> None:
        """Test success evaluation without explicit expected outcome."""
        loop = LearningLoop()

        pred = PredictionData(
            prediction_id="test",
            prediction_type="unknown",
            predicted_value="something",
            confidence=0.8,
            timestamp=datetime.now(),
            expected_outcome=None,
        )
        outcome = OutcomeData(
            outcome_id="out",
            prediction_id="test",
            actual_value="different",
            timestamp=datetime.now(),
        )

        # When no expected outcome is set, assumes success
        result = loop._evaluate_success(pred, outcome)
        assert result == 1.0
