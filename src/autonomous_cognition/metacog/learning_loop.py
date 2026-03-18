"""Learning loop closure system for autonomous cognition.

This module implements the complete learning loop: prediction → action →
outcome → calibration update, enabling continuous improvement of agent decision
quality through systematic bias detection and calibration adjustment.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LinkResult(Enum):
    """Result of linking a prediction to an outcome."""

    SUCCESS = "success"
    PREDICTION_NOT_FOUND = "prediction_not_found"
    OUTCOME_NOT_FOUND = "outcome_not_found"
    ALREADY_LINKED = "already_linked"
    MISMATCH = "mismatch"


class BiasType(Enum):
    """Types of systematic bias detected."""

    NONE = "none"
    OVERCONFIDENCE = "overconfidence"
    UNDERCONFIDENCE = "underconfidence"


@dataclass
class PredictionData:
    """Data structure for predictions."""

    prediction_id: str
    prediction_type: str
    predicted_value: Any
    confidence: float
    timestamp: datetime
    context: dict = field(default_factory=dict)
    expected_outcome: Any = None
    outcome_id: str | None = None
    linked: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "prediction_id": self.prediction_id,
            "prediction_type": self.prediction_type,
            "predicted_value": self._serialize_value(self.predicted_value),
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "expected_outcome": self._serialize_value(self.expected_outcome),
            "outcome_id": self.outcome_id,
            "linked": self.linked,
        }

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """Serialize a value for storage."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [PredictionData._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: PredictionData._serialize_value(v) for k, v in value.items()}
        return str(value)

    @classmethod
    def from_dict(cls, data: dict) -> PredictionData:
        """Create from dictionary."""
        return cls(
            prediction_id=data["prediction_id"],
            prediction_type=data["prediction_type"],
            predicted_value=data["predicted_value"],
            confidence=data["confidence"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            context=data.get("context", {}),
            expected_outcome=data.get("expected_outcome"),
            outcome_id=data.get("outcome_id"),
            linked=data.get("linked", False),
        )


@dataclass
class OutcomeData:
    """Data structure for outcomes."""

    outcome_id: str
    prediction_id: str
    actual_value: Any
    timestamp: datetime
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "outcome_id": self.outcome_id,
            "prediction_id": self.prediction_id,
            "actual_value": PredictionData._serialize_value(self.actual_value),
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OutcomeData:
        """Create from dictionary."""
        return cls(
            outcome_id=data["outcome_id"],
            prediction_id=data["prediction_id"],
            actual_value=data["actual_value"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CalibrationRecord:
    """Record of calibration for a prediction type."""

    prediction_type: str
    total_predictions: int = 0
    total_error: float = 0.0
    adjustments: list[dict] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def average_error(self) -> float:
        """Calculate average calibration error."""
        if self.total_predictions == 0:
            return 0.0
        return self.total_error / self.total_predictions

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "prediction_type": self.prediction_type,
            "total_predictions": self.total_predictions,
            "total_error": self.total_error,
            "average_error": self.average_error,
            "adjustments": self.adjustments,
            "last_updated": self.last_updated.isoformat(),
        }


class LearningLoop:
    """
    Learning loop closure system for autonomous cognition.

    Implements the complete feedback loop:
    1. Register predictions with confidence levels
    2. Record actual outcomes
    3. Automatically link predictions to outcomes
    4. Calculate calibration deltas
    5. Update calibration tracking
    6. Identify systematic biases
    7. Generate calibration recommendations

    Storage:
    - Predictions and outcomes stored in Qdrant (long-term)
    - Recent predictions cached in Redis (fast lookup)
    - Calibration records stored in Redis
    - Learning statistics in Redis: bmad:chiseai:autocog:learning_stats
    """

    # Redis key prefixes
    PREDICTION_PREFIX = "bmad:chiseai:learning:prediction"
    OUTCOME_PREFIX = "bmad:chiseai:learning:outcome"
    CALIBRATION_PREFIX = "bmad:chiseai:learning:calibration"
    STATS_KEY = "bmad:chiseai:autocog:learning_stats"

    def __init__(
        self,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
    ) -> None:
        """Initialize the learning loop.

        Args:
            redis_client: Optional Redis client for caching
            qdrant_client: Optional Qdrant client for long-term storage
        """
        self._redis = redis_client
        self._qdrant = qdrant_client
        self._local_predictions: dict[str, PredictionData] = {}
        self._local_outcomes: dict[str, OutcomeData] = {}
        self._local_calibration: dict[str, CalibrationRecord] = {}

    def _get_redis(self) -> Any:
        """Get Redis client with fallback to tools import."""
        if self._redis is not None:
            return self._redis

        try:
            from tools import redis_state_get, redis_state_hget, redis_state_hset

            return {
                "hset": redis_state_hset,
                "hget": redis_state_hget,
                "get": redis_state_get,
            }
        except ImportError:
            return None

    def _get_qdrant(self) -> Any:
        """Get Qdrant client with fallback to tools import."""
        if self._qdrant is not None:
            return self._qdrant

        # Note: qdrant_qdrant-store and qdrant_qdrant-find are MCP tools
        # accessed via function calls, not direct imports
        return None

    def _store_prediction(self, prediction: PredictionData) -> bool:
        """Store prediction in Redis and Qdrant."""
        # Store locally
        self._local_predictions[prediction.prediction_id] = prediction

        # Store in Redis
        redis = self._get_redis()
        if redis:
            with contextlib.suppress(Exception):
                redis["hset"](
                    f"{self.PREDICTION_PREFIX}:{prediction.prediction_id}",
                    "data",
                    json.dumps(prediction.to_dict()),
                )

        # Store in Qdrant
        qdrant = self._get_qdrant()
        if qdrant:
            with contextlib.suppress(Exception):
                qdrant["store"](
                    information=f"Prediction: {prediction.prediction_id}",
                    metadata={
                        "type": "prediction",
                        "prediction_id": prediction.prediction_id,
                        "prediction_type": prediction.prediction_type,
                        "confidence": prediction.confidence,
                        "project": "crypto-chise-bmad",
                        "timestamp": prediction.timestamp.isoformat(),
                    },
                )

        return True

    def _store_outcome(self, outcome: OutcomeData) -> bool:
        """Store outcome in Redis and Qdrant."""
        # Store locally
        self._local_outcomes[outcome.outcome_id] = outcome

        # Store in Redis
        redis = self._get_redis()
        if redis:
            with contextlib.suppress(Exception):
                redis["hset"](
                    f"{self.OUTCOME_PREFIX}:{outcome.outcome_id}",
                    "data",
                    json.dumps(outcome.to_dict()),
                )

        # Store in Qdrant
        qdrant = self._get_qdrant()
        if qdrant:
            with contextlib.suppress(Exception):
                qdrant["store"](
                    information=f"Outcome: {outcome.outcome_id}",
                    metadata={
                        "type": "outcome",
                        "outcome_id": outcome.outcome_id,
                        "prediction_id": outcome.prediction_id,
                        "project": "crypto-chise-bmad",
                        "timestamp": outcome.timestamp.isoformat(),
                    },
                )

        return True

    def register_prediction(
        self,
        prediction_id: str,
        prediction_data: dict[str, Any],
    ) -> bool:
        """Register a new prediction.

        Args:
            prediction_id: Unique identifier for the prediction
            prediction_data: Dictionary containing prediction details

        Returns:
            True if registration successful
        """
        prediction = PredictionData(
            prediction_id=prediction_id,
            prediction_type=prediction_data.get("prediction_type", "unknown"),
            predicted_value=prediction_data.get("predicted_value"),
            confidence=float(prediction_data.get("confidence", 0.5)),
            timestamp=prediction_data.get("timestamp", datetime.now()),
            context=prediction_data.get("context", {}),
            expected_outcome=prediction_data.get("expected_outcome"),
        )

        return self._store_prediction(prediction)

    def record_outcome(
        self,
        prediction_id: str,
        outcome_data: dict[str, Any],
    ) -> bool:
        """Record an outcome for a prediction.

        Args:
            prediction_id: ID of the associated prediction
            outcome_data: Dictionary containing outcome details

        Returns:
            True if recording successful
        """
        outcome_id = outcome_data.get("outcome_id", f"outcome-{prediction_id}")

        outcome = OutcomeData(
            outcome_id=outcome_id,
            prediction_id=prediction_id,
            actual_value=outcome_data.get("actual_value"),
            timestamp=outcome_data.get("timestamp", datetime.now()),
            metadata=outcome_data.get("metadata", {}),
        )

        success = self._store_outcome(outcome)

        # Attempt automatic linking
        if success:
            self.link_prediction_to_outcome(prediction_id, outcome_id)

        return success

    def link_prediction_to_outcome(
        self,
        prediction_id: str,
        outcome_id: str,
    ) -> LinkResult:
        """Link a prediction to its outcome.

        Args:
            prediction_id: ID of the prediction
            outcome_id: ID of the outcome

        Returns:
            LinkResult indicating success or failure reason
        """
        # Get prediction
        prediction = self._local_predictions.get(prediction_id)
        if prediction is None:
            return LinkResult.PREDICTION_NOT_FOUND

        # Get outcome
        outcome = self._local_outcomes.get(outcome_id)
        if outcome is None:
            return LinkResult.OUTCOME_NOT_FOUND

        # Check if already linked
        if prediction.linked:
            return LinkResult.ALREADY_LINKED

        # Check prediction_id match
        if outcome.prediction_id != prediction_id:
            return LinkResult.MISMATCH

        # Perform linking
        prediction.outcome_id = outcome_id
        prediction.linked = True

        # Update storage
        self._store_prediction(prediction)

        # Calculate and store calibration delta
        delta = self.calculate_calibration_delta(prediction_id)
        self.update_calibration(prediction.prediction_type, delta)

        return LinkResult.SUCCESS

    def calculate_calibration_delta(self, prediction_id: str) -> float:
        """Calculate calibration error for a prediction-outcome pair.

        Args:
            prediction_id: ID of the prediction

        Returns:
            Calibration error (difference between confidence and actual accuracy)
        """
        prediction = self._local_predictions.get(prediction_id)
        if prediction is None or not prediction.linked:
            return 0.0

        if prediction.outcome_id is None:
            return 0.0

        outcome = self._local_outcomes.get(prediction.outcome_id)
        if outcome is None:
            return 0.0

        # Calculate success indicator (1.0 if correct, 0.0 if incorrect)
        success = self._evaluate_success(prediction, outcome)

        # Calibration error is |confidence - actual_accuracy|
        # where actual_accuracy is 1.0 for success, 0.0 for failure
        return abs(prediction.confidence - success)

    def _evaluate_success(
        self,
        prediction: PredictionData,
        outcome: OutcomeData,
    ) -> float:
        """Evaluate if the prediction was successful.

        Returns 1.0 for success, 0.0 for failure, or 0.5 for partial.
        """
        # Binary outcome
        if isinstance(prediction.expected_outcome, bool):
            return 1.0 if outcome.actual_value == prediction.expected_outcome else 0.0

        # Numeric outcome (within tolerance)
        if isinstance(prediction.predicted_value, (int, float)) and isinstance(
            outcome.actual_value, (int, float)
        ):
            # Use 10% tolerance for numeric predictions
            tolerance = abs(float(prediction.predicted_value)) * 0.1
            if tolerance == 0:
                tolerance = 0.1
            diff = abs(float(prediction.predicted_value) - float(outcome.actual_value))
            if diff <= tolerance:
                return 1.0
            elif diff <= tolerance * 2:
                return 0.5
            else:
                return 0.0

        # String/category outcome (exact match)
        if prediction.expected_outcome is not None:
            return 1.0 if outcome.actual_value == prediction.expected_outcome else 0.0

        # Default: assume success
        return 1.0

    def update_calibration(self, prediction_type: str, delta: float) -> bool:
        """Update calibration tracking for a prediction type.

        Args:
            prediction_type: Type of prediction
            delta: Calibration error to add

        Returns:
            True if update successful
        """
        # Get or create calibration record
        if prediction_type not in self._local_calibration:
            self._local_calibration[prediction_type] = CalibrationRecord(
                prediction_type=prediction_type
            )

        record = self._local_calibration[prediction_type]
        record.total_predictions += 1
        record.total_error += delta
        record.last_updated = datetime.now()

        # Store in Redis
        redis = self._get_redis()
        if redis:
            with contextlib.suppress(Exception):
                redis["hset"](
                    self.CALIBRATION_PREFIX,
                    prediction_type,
                    json.dumps(record.to_dict()),
                )

        # Update learning statistics
        self._update_learning_stats()

        return True

    def _update_learning_stats(self) -> None:
        """Update aggregate learning statistics in Redis."""
        stats = self.get_learning_statistics()

        redis = self._get_redis()
        if redis:
            with contextlib.suppress(Exception):
                redis["hset"](
                    self.STATS_KEY,
                    "stats",
                    json.dumps(stats),
                )

    def identify_systematic_biases(self) -> dict[str, BiasType]:
        """Identify systematic biases in predictions.

        Returns:
            Dictionary mapping prediction types to detected bias types
        """
        biases: dict[str, BiasType] = {}

        for pred_type, record in self._local_calibration.items():
            if record.total_predictions < 10:
                # Not enough data
                biases[pred_type] = BiasType.NONE
                continue

            avg_error = record.average_error

            # Interpret average error as bias indicator
            # High error suggests either over or under confidence
            if avg_error > 0.3:
                # Analyze individual errors to determine direction
                over_confident_count = 0
                under_confident_count = 0

                # Check linked predictions of this type
                for pred in self._local_predictions.values():
                    if pred.prediction_type == pred_type and pred.linked:
                        if pred.outcome_id is None:
                            continue
                        outcome = self._local_outcomes.get(pred.outcome_id)
                        if outcome:
                            success = self._evaluate_success(pred, outcome)
                            if pred.confidence > 0.7 and success < 0.5:
                                over_confident_count += 1
                            elif pred.confidence < 0.4 and success > 0.5:
                                under_confident_count += 1

                if over_confident_count > under_confident_count:
                    biases[pred_type] = BiasType.OVERCONFIDENCE
                elif under_confident_count > over_confident_count:
                    biases[pred_type] = BiasType.UNDERCONFIDENCE
                else:
                    biases[pred_type] = BiasType.NONE
            else:
                biases[pred_type] = BiasType.NONE

        return biases

    def recommend_calibration_adjustments(self) -> list[dict[str, Any]]:
        """Generate calibration adjustment recommendations.

        Returns:
            List of recommendation dictionaries
        """
        recommendations = []
        biases = self.identify_systematic_biases()

        for pred_type, bias in biases.items():
            if bias == BiasType.NONE:
                continue

            record = self._local_calibration.get(pred_type)
            if not record:
                continue

            avg_error = record.average_error

            if bias == BiasType.OVERCONFIDENCE:
                # Suggest reducing confidence
                adjustment = min(avg_error * 0.5, 0.2)  # Cap at 0.2
                recommendations.append(
                    {
                        "prediction_type": pred_type,
                        "issue": "overconfidence",
                        "current_avg_error": avg_error,
                        "recommendation": f"Reduce confidence ratings by ~{adjustment:.1%}",
                        "confidence_offset": -adjustment,
                        "sample_size": record.total_predictions,
                        "priority": "high" if avg_error > 0.4 else "medium",
                    }
                )
            elif bias == BiasType.UNDERCONFIDENCE:
                # Suggest increasing confidence
                adjustment = min(avg_error * 0.5, 0.15)  # Cap at 0.15
                recommendations.append(
                    {
                        "prediction_type": pred_type,
                        "issue": "underconfidence",
                        "current_avg_error": avg_error,
                        "recommendation": f"Increase confidence ratings by ~{adjustment:.1%}",
                        "confidence_offset": adjustment,
                        "sample_size": record.total_predictions,
                        "priority": "medium",
                    }
                )

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(
            key=lambda x: priority_order.get(x.get("priority", "low"), 3)
        )

        return recommendations

    def get_learning_statistics(self) -> dict[str, Any]:
        """Get aggregate learning statistics.

        Returns:
            Dictionary with learning metrics
        """
        predictions_made = len(self._local_predictions)
        outcomes_recorded = len(self._local_outcomes)
        linked_pairs = sum(1 for p in self._local_predictions.values() if p.linked)

        # Calculate average calibration error
        total_error = sum(
            record.total_error for record in self._local_calibration.values()
        )
        total_predictions = sum(
            record.total_predictions for record in self._local_calibration.values()
        )
        avg_calibration_error = (
            total_error / total_predictions if total_predictions > 0 else 0.0
        )

        # Determine systematic bias
        biases = self.identify_systematic_biases()
        bias_counts = {"over": 0, "under": 0, "none": 0}
        for bias in biases.values():
            if bias == BiasType.OVERCONFIDENCE:
                bias_counts["over"] += 1
            elif bias == BiasType.UNDERCONFIDENCE:
                bias_counts["under"] += 1
            else:
                bias_counts["none"] += 1

        if bias_counts["over"] > bias_counts["under"]:
            systematic_bias = "over"
        elif bias_counts["under"] > bias_counts["over"]:
            systematic_bias = "under"
        else:
            systematic_bias = "none"

        # Get recommendations
        recommendations = self.recommend_calibration_adjustments()

        return {
            "predictions_made": predictions_made,
            "outcomes_recorded": outcomes_recorded,
            "linked_pairs": linked_pairs,
            "average_calibration_error": round(avg_calibration_error, 4),
            "systematic_bias": systematic_bias,
            "recommendations": recommendations,
            "calibration_by_type": {
                pred_type: record.to_dict()
                for pred_type, record in self._local_calibration.items()
            },
            "timestamp": datetime.now().isoformat(),
        }
