"""Provisional Accuracy Assessment Module.

Provides provisional accuracy assessment for BOS/CHoCH signals with provisional
thresholds (not final). This assessment is used for EP-ICT-008 Real Data Validation
epic with provisional gating.

CRITICAL: This assessment returns outcome_label="provisional_pass" ONLY.
Final BOS/CHoCH enablement (outcome_label="final_pass") is blocked pending
EP-ICT-006 Part-B completion.

For ST-ICT-033: Provisional Accuracy Assessment
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Redis key patterns
REDIS_KEY_PREFIX = "ict:provisional:assessment"

# Provisional thresholds (NOT final thresholds)
PROVISIONAL_DIRECTIONAL_ACCURACY_THRESHOLD = 55.0  # >= 55% for provisional pass
PROVISIONAL_BEARISH_ACCURACY_THRESHOLD = 45.0  # >= 45% for bearish detection
FINAL_DIRECTIONAL_ACCURACY_THRESHOLD = (
    60.0  # Final threshold (blocked by EP-ICT-006 Part-B)
)


@dataclass
class AssessmentResult:
    """Result of a single accuracy assessment.

    Attributes:
        timestamp: When assessment was performed
        total_signals: Total signals assessed
        correct_predictions: Number of correct predictions
        incorrect_predictions: Number of incorrect predictions
        directional_accuracy: Percentage of correct directional predictions
        bearish_accuracy: Percentage of correct bearish predictions
        bullish_accuracy: Percentage of correct bullish predictions
        statistical_confidence: Confidence interval for the accuracy
        outcome_label: Assessment outcome - MUST be "provisional_pass"
        meets_provisional_threshold: Whether provisional threshold is met
        meets_final_threshold: Whether final threshold is met (currently blocked)
        blocked_reason: Reason if final threshold is blocked
        signals_by_type: Breakdown of signals by type
    """

    timestamp: datetime
    total_signals: int
    correct_predictions: int
    incorrect_predictions: int
    directional_accuracy: float
    bearish_accuracy: float
    bullish_accuracy: float
    statistical_confidence: float
    outcome_label: str  # CRITICAL: This is "provisional_pass" only
    meets_provisional_threshold: bool
    meets_final_threshold: bool
    blocked_reason: str | None
    signals_by_type: dict[str, int] = field(default_factory=dict)
    additional_metrics: dict[str, Any] = field(default_factory=dict)


class ProvisionalAssessor:
    """Provisional assessor for BOS/CHoCH signal accuracy.

    This assessor implements PROVISIONAL accuracy assessment only.
    It does NOT grant final_pass - that is blocked pending EP-ICT-006 Part-B.

    Provisional thresholds:
        - Directional accuracy >= 55%
        - Bearish detection accuracy >= 45%

    Final thresholds (blocked by EP-ICT-006 Part-B):
        - Directional accuracy >= 60%

    For ST-ICT-033: Provisional Accuracy Assessment
    """

    DEFAULT_REDIS_HOST = "host.docker.internal"
    DEFAULT_REDIS_PORT = 6380
    DEFAULT_REDIS_DB = 1
    ASSESSMENT_KEY_TTL = 604800  # 7 days

    def __init__(
        self,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int | None = None,
    ):
        """Initialize ProvisionalAssessor.

        Args:
            redis_host: Redis host (defaults to host.docker.internal)
            redis_port: Redis port (defaults to 6380)
            redis_db: Redis database number (defaults to 1)
        """
        self.redis_host = redis_host or self.DEFAULT_REDIS_HOST
        self.redis_port = redis_port or self.DEFAULT_REDIS_PORT
        self.redis_db = redis_db if redis_db is not None else self.DEFAULT_REDIS_DB
        self._redis_client: Any = None
        self._shadow_tester_data: dict[str, Any] = {}

    def _get_redis_client(self) -> Any:
        """Get or create Redis client.

        Returns:
            Redis client instance
        """
        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis

            self._redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True,
            )
            self._redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            return self._redis_client
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            return None

    def _redis_key(self, suffix: str) -> str:
        """Generate Redis key.

        Args:
            suffix: Key suffix

        Returns:
            Full Redis key
        """
        return f"{REDIS_KEY_PREFIX}:{suffix}"

    @property
    def outcome_label(self) -> str:
        """
        Returns the assessment outcome label.

        CRITICAL: This is PROVISIONAL only - NOT final_pass.
        Final BOS/CHoCH enablement blocked pending EP-ICT-006 Part-B.

        Returns:
            "provisional_pass" - This is the ONLY valid outcome for this assessment
        """
        return "provisional_pass"  # NOT final_pass

    def check_final_gate_dependency(self) -> dict[str, Any]:
        """Check if final gate dependency (EP-ICT-006 Part-B) is complete.

        This method checks whether EP-ICT-006 Part-B has been completed,
        which would enable switching from provisional_pass to final_pass.

        Returns:
            Dictionary with dependency status:
                - is_blocked: True if final_pass is blocked
                - blocking_item: "EP-ICT-006 Part-B"
                - current_status: Current status of the blocking item
        """
        # For now, EP-ICT-006 Part-B status is unknown to this module
        # In production, this would check the actual epic/story status
        return {
            "is_blocked": True,
            "blocking_item": "EP-ICT-006 Part-B",
            "current_status": "not_completed",
            "message": (
                "Final BOS/CHoCH enablement blocked pending EP-ICT-006 Part-B. "
                "Use provisional_pass outcome_label only."
            ),
        }

    def assess_directional_accuracy(
        self,
        total_signals: int,
        correct_predictions: int,
        threshold: float = PROVISIONAL_DIRECTIONAL_ACCURACY_THRESHOLD,
    ) -> dict[str, Any]:
        """Assess directional accuracy against threshold.

        Args:
            total_signals: Total number of signals
            correct_predictions: Number of correct predictions
            threshold: Accuracy threshold (default 55% for provisional)

        Returns:
            Dictionary with assessment result
        """
        if total_signals == 0:
            return {
                "threshold": threshold,
                "total_signals": 0,
                "correct_predictions": 0,
                "accuracy": 0.0,
                "meets_threshold": False,
                "message": "No signals to assess",
            }

        accuracy = (correct_predictions / total_signals) * 100
        meets_threshold = accuracy >= threshold

        return {
            "threshold": threshold,
            "total_signals": total_signals,
            "correct_predictions": correct_predictions,
            "accuracy": round(accuracy, 2),
            "meets_threshold": meets_threshold,
            "message": (
                f"Directional accuracy: {accuracy:.2f}% "
                f"({'PASS' if meets_threshold else 'FAIL'} vs {threshold}% threshold)"
            ),
        }

    def assess_bearish_accuracy(
        self,
        total_bearish: int,
        correct_bearish: int,
        threshold: float = PROVISIONAL_BEARISH_ACCURACY_THRESHOLD,
    ) -> dict[str, Any]:
        """Assess bearish detection accuracy against threshold.

        Args:
            total_bearish: Total number of bearish signals
            correct_bearish: Number of correct bearish predictions
            threshold: Bearish accuracy threshold (default 45% for provisional)

        Returns:
            Dictionary with assessment result
        """
        if total_bearish == 0:
            return {
                "threshold": threshold,
                "total_bearish": 0,
                "correct_bearish": 0,
                "accuracy": 0.0,
                "meets_threshold": False,
                "message": "No bearish signals to assess",
            }

        accuracy = (correct_bearish / total_bearish) * 100
        meets_threshold = accuracy >= threshold

        return {
            "threshold": threshold,
            "total_bearish": total_bearish,
            "correct_bearish": correct_bearish,
            "accuracy": round(accuracy, 2),
            "meets_threshold": meets_threshold,
            "message": (
                f"Bearish accuracy: {accuracy:.2f}% "
                f"({'PASS' if meets_threshold else 'FAIL'} vs {threshold}% threshold)"
            ),
        }

    def calculate_statistical_confidence(
        self,
        total_signals: int,
        correct_predictions: int,
        confidence_level: float = 0.95,
    ) -> dict[str, Any]:
        """Calculate statistical confidence interval for accuracy.

        Uses binomial confidence interval (Wilson score interval) for
        accurate confidence estimation with small sample sizes.

        Args:
            total_signals: Total number of signals
            correct_predictions: Number of correct predictions
            confidence_level: Confidence level (default 0.95 for 95% CI)

        Returns:
            Dictionary with confidence metrics
        """
        if total_signals == 0:
            return {
                "confidence_level": confidence_level,
                "total_signals": 0,
                "accuracy": 0.0,
                "lower_bound": 0.0,
                "upper_bound": 0.0,
                "margin_of_error": 0.0,
                "is_significant": False,
            }

        # Calculate sample proportion
        p_hat = correct_predictions / total_signals
        z = 1.96 if confidence_level == 0.95 else 1.645  # z-score for 95% or 90%

        # Wilson score interval
        denominator = 1 + z**2 / total_signals
        center = p_hat + z**2 / (2 * total_signals)
        spread = z * math.sqrt(
            (p_hat * (1 - p_hat) + z**2 / (4 * total_signals)) / total_signals
        )

        lower_bound = max(0.0, (center - spread) / denominator)
        upper_bound = min(1.0, (center + spread) / denominator)
        margin_of_error = (upper_bound - lower_bound) / 2

        # Check if accuracy is significantly different from 0.5 (random)
        # by checking if confidence interval excludes 0.5
        is_significant = lower_bound > 0.5 or upper_bound < 0.5

        return {
            "confidence_level": confidence_level,
            "total_signals": total_signals,
            "accuracy": round(p_hat * 100, 2),
            "lower_bound": round(lower_bound * 100, 2),
            "upper_bound": round(upper_bound * 100, 2),
            "margin_of_error": round(margin_of_error * 100, 2),
            "is_significant": is_significant,
        }

    def generate_provisional_report(
        self,
        total_signals: int,
        correct_predictions: int,
        total_bearish: int,
        correct_bearish: int,
        signals_by_type: dict[str, int] | None = None,
        additional_metrics: dict[str, Any] | None = None,
    ) -> AssessmentResult:
        """Generate a complete provisional assessment report.

        This method generates a full provisional assessment with all metrics
        and the CRITICAL outcome_label="provisional_pass".

        Args:
            total_signals: Total number of signals assessed
            correct_predictions: Number of correct predictions
            total_bearish: Total bearish signals
            correct_bearish: Correct bearish predictions
            signals_by_type: Optional breakdown by signal type
            additional_metrics: Optional additional metrics

        Returns:
            AssessmentResult with outcome_label="provisional_pass"
        """
        # Calculate directional accuracy
        directional_pct = (
            (correct_predictions / total_signals * 100) if total_signals > 0 else 0.0
        )

        # Calculate bearish accuracy
        bearish_pct = (
            (correct_bearish / total_bearish * 100) if total_bearish > 0 else 0.0
        )

        # Calculate bullish accuracy
        total_bullish = total_signals - total_bearish
        correct_bullish = correct_predictions - correct_bearish
        bullish_pct = (
            (correct_bullish / total_bullish * 100) if total_bullish > 0 else 0.0
        )

        # Calculate statistical confidence
        confidence = self.calculate_statistical_confidence(
            total_signals, correct_predictions
        )

        # Check final gate dependency
        final_gate = self.check_final_gate_dependency()

        # Determine if provisional threshold is met
        meets_provisional = (
            directional_pct >= PROVISIONAL_DIRECTIONAL_ACCURACY_THRESHOLD
            and bearish_pct >= PROVISIONAL_BEARISH_ACCURACY_THRESHOLD
        )

        # Final threshold is blocked (EP-ICT-006 Part-B not complete)
        meets_final = (
            directional_pct >= FINAL_DIRECTIONAL_ACCURACY_THRESHOLD
            and bearish_pct >= PROVISIONAL_BEARISH_ACCURACY_THRESHOLD
            and not final_gate["is_blocked"]
        )

        result = AssessmentResult(
            timestamp=datetime.now(UTC),
            total_signals=total_signals,
            correct_predictions=correct_predictions,
            incorrect_predictions=total_signals - correct_predictions,
            directional_accuracy=round(directional_pct, 2),
            bearish_accuracy=round(bearish_pct, 2),
            bullish_accuracy=round(bullish_pct, 2),
            statistical_confidence=round(confidence["lower_bound"], 2),
            outcome_label=self.outcome_label,  # CRITICAL: "provisional_pass" only
            meets_provisional_threshold=meets_provisional,
            meets_final_threshold=meets_final,
            blocked_reason=(
                "EP-ICT-006 Part-B not complete" if final_gate["is_blocked"] else None
            ),
            signals_by_type=signals_by_type or {},
            additional_metrics=additional_metrics or {},
        )

        # Store in Redis
        self._store_assessment_result(result)

        logger.info(
            f"Provisional assessment complete: "
            f"directional={directional_pct:.2f}%, bearish={bearish_pct:.2f}%, "
            f"outcome={self.outcome_label}"
        )

        return result

    def _store_assessment_result(self, result: AssessmentResult) -> None:
        """Store assessment result to Redis.

        Args:
            result: AssessmentResult to store
        """
        client = self._get_redis_client()
        if not client:
            return

        try:
            timestamp_str = result.timestamp.strftime("%Y%m%d_%H%M%S")
            key = f"{REDIS_KEY_PREFIX}:{timestamp_str}"

            client.setex(
                key,
                self.ASSESSMENT_KEY_TTL,
                json.dumps(
                    {
                        "timestamp": result.timestamp.isoformat(),
                        "total_signals": result.total_signals,
                        "correct_predictions": result.correct_predictions,
                        "incorrect_predictions": result.incorrect_predictions,
                        "directional_accuracy": result.directional_accuracy,
                        "bearish_accuracy": result.bearish_accuracy,
                        "bullish_accuracy": result.bullish_accuracy,
                        "statistical_confidence": result.statistical_confidence,
                        "outcome_label": result.outcome_label,
                        "meets_provisional_threshold": result.meets_provisional_threshold,
                        "meets_final_threshold": result.meets_final_threshold,
                        "blocked_reason": result.blocked_reason,
                        "signals_by_type": result.signals_by_type,
                    },
                    indent=2,
                ),
            )
            logger.info(f"Stored provisional assessment to Redis: {key}")
        except Exception as e:
            logger.warning(f"Failed to store assessment result: {e}")

    def get_latest_assessment(self) -> AssessmentResult | None:
        """Retrieve the latest assessment result from Redis.

        Returns:
            AssessmentResult if found, None otherwise
        """
        client = self._get_redis_client()
        if not client:
            return None

        try:
            # Find the latest assessment key
            pattern = f"{REDIS_KEY_PREFIX}:*"
            keys = []
            for key in client.scan_iter(match=pattern, count=100):
                keys.append(key)

            if not keys:
                return None

            # Sort by timestamp (newest first)
            keys.sort(reverse=True)
            latest_key = keys[0]

            data = client.get(latest_key)
            if not data:
                return None

            parsed = json.loads(data)
            return AssessmentResult(
                timestamp=datetime.fromisoformat(parsed["timestamp"]),
                total_signals=parsed["total_signals"],
                correct_predictions=parsed["correct_predictions"],
                incorrect_predictions=parsed["incorrect_predictions"],
                directional_accuracy=parsed["directional_accuracy"],
                bearish_accuracy=parsed["bearish_accuracy"],
                bullish_accuracy=parsed["bullish_accuracy"],
                statistical_confidence=parsed["statistical_confidence"],
                outcome_label=parsed["outcome_label"],
                meets_provisional_threshold=parsed["meets_provisional_threshold"],
                meets_final_threshold=parsed["meets_final_threshold"],
                blocked_reason=parsed.get("blocked_reason"),
                signals_by_type=parsed.get("signals_by_type", {}),
                additional_metrics=parsed.get("additional_metrics", {}),
            )
        except Exception as e:
            logger.warning(f"Failed to retrieve latest assessment: {e}")
            return None

    def assess_from_shadow_tester(
        self,
        shadow_tester: Any,
    ) -> AssessmentResult:
        """Generate assessment from BOSCHoCHShadowTester data.

        This is a convenience method that extracts data from a shadow tester
        instance and generates a provisional assessment.

        Args:
            shadow_tester: BOSCHoCHShadowTester instance with recorded signals

        Returns:
            AssessmentResult with outcome_label="provisional_pass"
        """
        # Get shadow signals and outcomes
        signals = shadow_tester.get_shadow_signals()
        outcomes = shadow_tester._outcomes

        # Count signals by type
        signals_by_type: dict[str, int] = {}
        correct = 0
        incorrect = 0
        bearish_total = 0
        bearish_correct = 0

        for signal in signals:
            sig_type = signal.signal_type.value
            signals_by_type[sig_type] = signals_by_type.get(sig_type, 0) + 1

            # Check if signal is bearish
            is_bearish = "bear" in sig_type.lower()

            # Get outcome if available
            outcome = outcomes.get(signal.signal_id)
            if outcome:
                if outcome.result.value == "correct":
                    correct += 1
                    if is_bearish:
                        bearish_correct += 1
                else:
                    incorrect += 1

                if is_bearish:
                    bearish_total += 1

        return self.generate_provisional_report(
            total_signals=len(signals),
            correct_predictions=correct,
            total_bearish=bearish_total,
            correct_bearish=bearish_correct,
            signals_by_type=signals_by_type,
        )
