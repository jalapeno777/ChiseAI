"""BOS/CHoCH Shadow Testing Module.

Provides shadow testing capabilities for BOS/CHoCH signals against live market data.
Tracks signal predictions and actual outcomes without executing trades.

For ST-ICT-032: BOS/CHoCH Live Shadow Testing
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from src.config.ict_feature_flags import get_ict_feature_flags

logger = logging.getLogger(__name__)

# Redis key patterns
REDIS_KEY_PREFIX = "shadow:bos_choch"


class SignalType(Enum):
    """BOS/CHoCH signal types."""

    BOS_BULL = "bos_bull"
    BOS_BEAR = "bos_bear"
    CHOCH_BULL = "choch_bull"
    CHOCH_BEAR = "choch_bear"


class PredictionResult(Enum):
    """Prediction outcome results."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PENDING = "pending"


@dataclass
class ShadowSignal:
    """A shadow test signal record.

    Attributes:
        signal_id: Unique identifier for this shadow signal
        signal_type: Type of BOS/CHoCH signal
        token: Trading pair token
        timestamp: When the signal was recorded
        predicted_direction: Predicted price direction (long/short)
        predicted_target: Predicted price target
        predicted_stop: Predicted stop loss level
        confidence: Signal confidence (0.0-1.0)
        timeframe: Primary timeframe
        metadata: Additional signal metadata
    """

    signal_id: str
    signal_type: SignalType
    token: str
    timestamp: datetime
    predicted_direction: str  # "long" or "short"
    predicted_target: float
    predicted_stop: float
    confidence: float
    timeframe: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ShadowOutcome:
    """Outcome record for a shadow signal.

    Attributes:
        signal_id: Reference to the shadow signal
        recorded_at: When the outcome was recorded
        actual_direction: Actual price direction that occurred
        actual_high: Actual highest price after signal
        actual_low: Actual lowest price after signal
        result: Whether prediction was correct/incorrect/pending
        outcome_price: Price at which outcome was determined
        holding_period_hours: Hours the position would have been held
    """

    signal_id: str
    recorded_at: datetime
    actual_direction: str
    actual_high: float
    actual_low: float
    result: PredictionResult
    outcome_price: float
    holding_period_hours: float


@dataclass
class DailyAccuracyReport:
    """Daily accuracy report for shadow testing.

    Attributes:
        date: Report date
        total_signals: Total signals recorded that day
        resolved_signals: Signals with outcomes recorded
        correct_predictions: Correct predictions count
        incorrect_predictions: Incorrect predictions count
        pending_predictions: Unresolved predictions
        directional_accuracy: Percentage of correct directional predictions
        avg_confidence: Average signal confidence
        signals_by_type: Breakdown by signal type
    """

    date: str
    total_signals: int
    resolved_signals: int
    correct_predictions: int
    incorrect_predictions: int
    pending_predictions: int
    directional_accuracy: float
    avg_confidence: float
    signals_by_type: dict[str, int] = field(default_factory=dict)


class BOSCHoCHShadowTester:
    """Shadow tester for BOS/CHoCH signals.

    Tracks signal predictions and actual outcomes without execution.
    Calculates directional accuracy and generates daily reports.

    For ST-ICT-032: BOS/CHoCH Live Shadow Testing
    """

    DEFAULT_REDIS_HOST = "host.docker.internal"
    DEFAULT_REDIS_PORT = 6380
    DEFAULT_REDIS_DB = 1
    ACCURACY_KEY_TTL = 604800  # 7 days

    def __init__(
        self,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int | None = None,
    ):
        """Initialize BOS/CHoCH shadow tester.

        Args:
            redis_host: Redis host (defaults to host.docker.internal)
            redis_port: Redis port (defaults to 6380)
            redis_db: Redis database number (defaults to 1)
        """
        self.redis_host = redis_host or self.DEFAULT_REDIS_HOST
        self.redis_port = redis_port or self.DEFAULT_REDIS_PORT
        self.redis_db = redis_db if redis_db is not None else self.DEFAULT_REDIS_DB
        self._redis_client: Any = None
        self._active_signals: dict[str, ShadowSignal] = {}
        self._outcomes: dict[str, ShadowOutcome] = {}
        self._test_start_time: datetime | None = None
        self._test_end_time: datetime | None = None
        self._duration_days: int = 7
        self._feature_flags = get_ict_feature_flags()

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

    def _redis_key(self, date: str, suffix: str) -> str:
        """Generate Redis key.

        Args:
            date: Date string (YYYY-MM-DD)
            suffix: Key suffix

        Returns:
            Full Redis key
        """
        return f"{REDIS_KEY_PREFIX}:{date}:{suffix}"

    def start_shadow_test(self, duration_days: int = 7) -> dict[str, Any]:
        """Start a new shadow test period.

        Args:
            duration_days: Duration of shadow test (default 7 days)

        Returns:
            Dictionary with start status

        Raises:
            RuntimeError: If BOS/CHoCH is disabled by feature flag
        """
        if not self._feature_flags.is_bos_choch_enabled():
            raise RuntimeError("BOS/CHoCH shadow testing disabled by feature flag")

        self._test_start_time = datetime.now(UTC)
        self._duration_days = duration_days
        self._test_end_time = self._test_start_time + timedelta(days=duration_days)
        self._active_signals.clear()
        self._outcomes.clear()

        logger.info(
            f"Shadow test started: {self._test_start_time.isoformat()} "
            f"for {duration_days} days, ending {self._test_end_time.isoformat()}"
        )

        return {
            "status": "started",
            "start_time": self._test_start_time.isoformat(),
            "end_time": self._test_end_time.isoformat(),
            "duration_days": duration_days,
        }

    def record_signal_prediction(
        self,
        signal_type: SignalType,
        token: str,
        predicted_direction: str,
        predicted_target: float,
        predicted_stop: float,
        confidence: float,
        timeframe: str,
        current_price: float,
        metadata: dict[str, Any] | None = None,
    ) -> ShadowSignal:
        """Record a signal prediction for shadow testing.

        Args:
            signal_type: Type of BOS/CHoCH signal
            token: Trading pair token
            predicted_direction: Predicted direction ("long" or "short")
            predicted_target: Predicted price target
            predicted_stop: Predicted stop loss
            confidence: Signal confidence (0.0-1.0)
            timeframe: Primary timeframe
            current_price: Current market price
            metadata: Additional metadata

        Returns:
            The recorded ShadowSignal
        """
        signal_id = str(uuid.uuid4())
        signal = ShadowSignal(
            signal_id=signal_id,
            signal_type=signal_type,
            token=token,
            timestamp=datetime.now(UTC),
            predicted_direction=predicted_direction,
            predicted_target=predicted_target,
            predicted_stop=predicted_stop,
            confidence=confidence,
            timeframe=timeframe,
            metadata={
                "current_price": current_price,
                **(metadata or {}),
            },
        )

        self._active_signals[signal_id] = signal

        # Store in Redis for distributed access
        client = self._get_redis_client()
        if client:
            try:
                key = f"{REDIS_KEY_PREFIX}:signals:{signal_id}"
                client.setex(
                    key,
                    self.ACCURACY_KEY_TTL,
                    json.dumps(
                        {
                            "signal_id": signal_id,
                            "signal_type": signal_type.value,
                            "token": token,
                            "timestamp": signal.timestamp.isoformat(),
                            "predicted_direction": predicted_direction,
                            "predicted_target": predicted_target,
                            "predicted_stop": predicted_stop,
                            "confidence": confidence,
                            "timeframe": timeframe,
                            "current_price": current_price,
                            "metadata": metadata or {},
                        }
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to store signal in Redis: {e}")

        logger.info(
            f"Recorded shadow signal: {signal_id} {signal_type.value} "
            f"{token} {predicted_direction} @ {current_price}"
        )

        return signal

    def record_actual_outcome(
        self,
        signal_id: str,
        actual_high: float,
        actual_low: float,
        outcome_price: float,
        holding_period_hours: float,
    ) -> ShadowOutcome | None:
        """Record the actual outcome for a shadow signal.

        Args:
            signal_id: The signal ID to resolve
            actual_high: Actual highest price after signal
            actual_low: Actual lowest price after signal
            outcome_price: Price at which outcome was determined
            holding_period_hours: Hours the position was held

        Returns:
            The ShadowOutcome if signal found, None otherwise
        """
        signal = self._active_signals.get(signal_id)
        if not signal:
            logger.warning(f"Signal not found: {signal_id}")
            return None

        # Determine if prediction was correct based on direction
        if signal.predicted_direction == "long":
            # For long: price went up means correct
            price_move = actual_high - signal.metadata.get(
                "current_price", outcome_price
            )
            result = (
                PredictionResult.CORRECT
                if price_move > 0
                else PredictionResult.INCORRECT
            )
        else:
            # For short: price went down means correct
            # Use outcome_price (closing price proxy) vs entry to determine direction
            price_move = (
                signal.metadata.get("current_price", outcome_price) - outcome_price
            )
            result = (
                PredictionResult.CORRECT
                if price_move > 0
                else PredictionResult.INCORRECT
            )

        outcome = ShadowOutcome(
            signal_id=signal_id,
            recorded_at=datetime.now(UTC),
            actual_direction=(
                "up"
                if actual_high > signal.metadata.get("current_price", outcome_price)
                else "down"
            ),
            actual_high=actual_high,
            actual_low=actual_low,
            result=result,
            outcome_price=outcome_price,
            holding_period_hours=holding_period_hours,
        )

        self._outcomes[signal_id] = outcome

        # Update Redis
        client = self._get_redis_client()
        if client:
            try:
                key = f"{REDIS_KEY_PREFIX}:outcomes:{signal_id}"
                client.setex(
                    key,
                    self.ACCURACY_KEY_TTL,
                    json.dumps(
                        {
                            "signal_id": signal_id,
                            "recorded_at": outcome.recorded_at.isoformat(),
                            "actual_high": actual_high,
                            "actual_low": actual_low,
                            "result": result.value,
                            "outcome_price": outcome_price,
                            "holding_period_hours": holding_period_hours,
                        }
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to store outcome in Redis: {e}")

        logger.info(f"Recorded outcome for {signal_id}: {result.value}")

        return outcome

    def calculate_accuracy(self) -> dict[str, Any]:
        """Calculate directional accuracy of shadow test signals.

        Returns:
            Dictionary with accuracy metrics
        """
        if not self._outcomes:
            return {
                "total_signals": 0,
                "resolved_signals": 0,
                "correct": 0,
                "incorrect": 0,
                "pending": len(self._active_signals),
                "directional_accuracy": 0.0,
            }

        resolved = [
            o for o in self._outcomes.values() if o.result != PredictionResult.PENDING
        ]
        correct = sum(1 for o in resolved if o.result == PredictionResult.CORRECT)
        incorrect = sum(1 for o in resolved if o.result == PredictionResult.INCORRECT)
        pending = sum(
            1
            for s in self._active_signals.values()
            if s.signal_id not in self._outcomes
        )

        total_signals = len(self._active_signals)
        directional_accuracy = (correct / len(resolved) * 100) if resolved else 0.0

        return {
            "total_signals": total_signals,
            "resolved_signals": len(resolved),
            "correct": correct,
            "incorrect": incorrect,
            "pending": pending,
            "directional_accuracy": round(directional_accuracy, 2),
            "correct_pct": round(correct / len(resolved) * 100, 2) if resolved else 0.0,
        }

    def generate_daily_report(self, date: str | None = None) -> DailyAccuracyReport:
        """Generate daily accuracy report.

        Args:
            date: Date for report (YYYY-MM-DD), defaults to today

        Returns:
            DailyAccuracyReport instance
        """
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")

        # Collect signals for this date
        signals_this_day = [
            s
            for s in self._active_signals.values()
            if s.timestamp.strftime("%Y-%m-%d") == date
        ]

        # Collect outcomes for signals from this date
        outcomes_this_day = [
            o
            for o in self._outcomes.values()
            if o.recorded_at.strftime("%Y-%m-%d") == date
        ]

        correct = sum(
            1 for o in outcomes_this_day if o.result == PredictionResult.CORRECT
        )
        incorrect = sum(
            1 for o in outcomes_this_day if o.result == PredictionResult.INCORRECT
        )
        pending = len(signals_this_day) - len(outcomes_this_day)

        signals_by_type: dict[str, int] = {}
        for s in signals_this_day:
            sig_type = s.signal_type.value
            signals_by_type[sig_type] = signals_by_type.get(sig_type, 0) + 1

        avg_confidence = (
            sum(s.confidence for s in signals_this_day) / len(signals_this_day)
            if signals_this_day
            else 0.0
        )

        resolved = len(outcomes_this_day)
        directional_accuracy = (correct / resolved * 100) if resolved else 0.0

        report = DailyAccuracyReport(
            date=date,
            total_signals=len(signals_this_day),
            resolved_signals=resolved,
            correct_predictions=correct,
            incorrect_predictions=incorrect,
            pending_predictions=pending,
            directional_accuracy=round(directional_accuracy, 2),
            avg_confidence=round(avg_confidence, 4),
            signals_by_type=signals_by_type,
        )

        # Store report to Redis
        self._store_daily_report(report)

        return report

    def _store_daily_report(self, report: DailyAccuracyReport) -> None:
        """Store daily report to Redis.

        Args:
            report: DailyAccuracyReport to store
        """
        client = self._get_redis_client()
        if not client:
            return

        try:
            key = self._redis_key(report.date, "accuracy")
            client.setex(
                key,
                self.ACCURACY_KEY_TTL,
                json.dumps(
                    {
                        "date": report.date,
                        "total_signals": report.total_signals,
                        "resolved_signals": report.resolved_signals,
                        "correct_predictions": report.correct_predictions,
                        "incorrect_predictions": report.incorrect_predictions,
                        "pending_predictions": report.pending_predictions,
                        "directional_accuracy": report.directional_accuracy,
                        "avg_confidence": report.avg_confidence,
                        "signals_by_type": report.signals_by_type,
                    }
                ),
            )
            logger.info(f"Stored daily report to Redis: {key}")
        except Exception as e:
            logger.warning(f"Failed to store daily report: {e}")

    def get_daily_report(self, date: str) -> DailyAccuracyReport | None:
        """Retrieve daily report from Redis.

        Args:
            date: Date to retrieve (YYYY-MM-DD)

        Returns:
            DailyAccuracyReport if found, None otherwise
        """
        client = self._get_redis_client()
        if not client:
            return None

        try:
            key = self._redis_key(date, "accuracy")
            data = client.get(key)
            if not data:
                return None

            parsed = json.loads(data)
            return DailyAccuracyReport(
                date=parsed["date"],
                total_signals=parsed["total_signals"],
                resolved_signals=parsed["resolved_signals"],
                correct_predictions=parsed["correct_predictions"],
                incorrect_predictions=parsed["incorrect_predictions"],
                pending_predictions=parsed["pending_predictions"],
                directional_accuracy=parsed["directional_accuracy"],
                avg_confidence=parsed["avg_confidence"],
                signals_by_type=parsed.get("signals_by_type", {}),
            )
        except Exception as e:
            logger.warning(f"Failed to retrieve daily report: {e}")
            return None

    def stop_shadow_test(self) -> dict[str, Any]:
        """Stop the shadow test and return final statistics.

        Returns:
            Dictionary with final test statistics
        """
        self._test_end_time = datetime.now(UTC)

        accuracy = self.calculate_accuracy()

        logger.info(
            f"Shadow test stopped. Final accuracy: {accuracy['directional_accuracy']}% "
            f"({accuracy['correct']}/{accuracy['resolved_signals']} correct)"
        )

        return {
            "status": "stopped",
            "start_time": (
                self._test_start_time.isoformat() if self._test_start_time else None
            ),
            "end_time": self._test_end_time.isoformat(),
            "duration_days": (
                self._duration_days if hasattr(self, "_duration_days") else 0
            ),
            "final_accuracy": accuracy,
        }

    def get_shadow_signals(self) -> list[ShadowSignal]:
        """Get all active shadow signals.

        Returns:
            List of ShadowSignal records
        """
        return list(self._active_signals.values())

    def get_pending_signals(self) -> list[ShadowSignal]:
        """Get signals that don't have outcomes yet.

        Returns:
            List of pending ShadowSignal records
        """
        pending_ids = set(self._active_signals.keys()) - set(self._outcomes.keys())
        return [
            self._active_signals[sid]
            for sid in pending_ids
            if sid in self._active_signals
        ]
