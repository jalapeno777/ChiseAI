"""Calibration tracking for GitReviewBot accuracy."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .models import CalibrationMetrics, Decision, ReviewFeedback


@dataclass
class ReviewRecord:
    """Record of a bot review for calibration."""

    pr_number: int
    review_id: str
    decision: str
    confidence: float
    timestamp: datetime
    human_feedback: Optional[str] = None
    human_override: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pr_number": self.pr_number,
            "review_id": self.review_id,
            "decision": self.decision,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "human_feedback": self.human_feedback,
            "human_override": self.human_override,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewRecord":
        return cls(
            pr_number=data["pr_number"],
            review_id=data["review_id"],
            decision=data["decision"],
            confidence=data["confidence"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            human_feedback=data.get("human_feedback"),
            human_override=data.get("human_override"),
        )


class CalibrationTracker:
    """Track bot decisions and human feedback for calibration."""

    def __init__(self, redis_client=None, metrics_prefix: str = "gitreviewbot"):
        self.redis = redis_client
        self.metrics_prefix = metrics_prefix
        self._local_cache: List[ReviewRecord] = []

    def _review_key(self, pr_number: int, review_id: str) -> str:
        """Generate Redis key for review record."""
        return f"{self.metrics_prefix}:review:{pr_number}:{review_id}"

    def _feedback_key(self, pr_number: int) -> str:
        """Generate Redis key for feedback."""
        return f"{self.metrics_prefix}:feedback:{pr_number}"

    def _metrics_key(self, date: datetime) -> str:
        """Generate Redis key for daily metrics."""
        return f"{self.metrics_prefix}:metrics:{date.strftime('%Y-%m-%d')}"

    async def log_review(
        self, decision: Decision, review_id: Optional[str] = None
    ) -> str:
        """Log a review decision for calibration tracking."""
        review_id = review_id or self._generate_review_id(decision)

        record = ReviewRecord(
            pr_number=decision.pr_number,
            review_id=review_id,
            decision=decision.decision.value,
            confidence=decision.confidence,
            timestamp=decision.decided_at,
        )

        # Store in Redis if available
        if self.redis:
            key = self._review_key(decision.pr_number, review_id)
            await self._redis_set(key, record.to_dict())
        else:
            # Fallback to local cache
            self._local_cache.append(record)

        return review_id

    async def record_feedback(
        self,
        pr_number: int,
        review_id: str,
        feedback_type: str,
        reviewer: str,
        comment: Optional[str] = None,
    ) -> None:
        """Record human feedback on a bot review."""
        feedback = ReviewFeedback(
            pr_number=pr_number,
            review_id=review_id,
            feedback_type=feedback_type,
            reviewer=reviewer,
            comment=comment,
        )

        # Store feedback
        if self.redis:
            key = self._feedback_key(pr_number)
            await self._redis_list_push(key, feedback.model_dump())

            # Update review record with feedback
            review_key = self._review_key(pr_number, review_id)
            review_data = await self._redis_get(review_key)
            if review_data:
                review_data["human_feedback"] = feedback_type
                await self._redis_set(review_key, review_data)
        else:
            # Update local cache
            for record in self._local_cache:
                if record.pr_number == pr_number and record.review_id == review_id:
                    record.human_feedback = feedback_type
                    break

    async def record_human_override(
        self,
        pr_number: int,
        review_id: str,
        human_decision: str,
    ) -> None:
        """Record when a human overrides the bot's decision."""
        if self.redis:
            key = self._review_key(pr_number, review_id)
            review_data = await self._redis_get(key)
            if review_data:
                review_data["human_override"] = human_decision
                await self._redis_set(key, review_data)
        else:
            # Update local cache
            for record in self._local_cache:
                if record.pr_number == pr_number and record.review_id == review_id:
                    record.human_override = human_decision
                    break

    async def calculate_metrics(
        self,
        days: int = 7,
        end_date: Optional[datetime] = None,
    ) -> CalibrationMetrics:
        """Calculate calibration metrics for a period."""
        end_date = end_date or datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Get all reviews in period
        reviews = await self._get_reviews_in_period(start_date, end_date)

        if not reviews:
            return CalibrationMetrics(
                total_reviews=0,
                approved_reviews=0,
                commented_reviews=0,
                requested_changes_reviews=0,
                human_overrides=0,
                human_agreements=0,
                accuracy_rate=0.0,
                avg_confidence=0.0,
                false_positive_rate=0.0,
                false_negative_rate=0.0,
                period_start=start_date,
                period_end=end_date,
            )

        # Calculate metrics
        total = len(reviews)
        approved = sum(1 for r in reviews if r.decision == "APPROVE")
        commented = sum(1 for r in reviews if r.decision == "COMMENT")
        requested_changes = sum(1 for r in reviews if r.decision == "REQUEST_CHANGES")

        overrides = sum(1 for r in reviews if r.human_override is not None)
        agreements = sum(1 for r in reviews if r.human_feedback in ("👍", "thumbs_up"))

        # Calculate accuracy
        feedback_count = sum(1 for r in reviews if r.human_feedback is not None)
        accuracy = (agreements / feedback_count * 100) if feedback_count > 0 else 0.0

        # Calculate false positive/negative rates
        false_positives = sum(
            1
            for r in reviews
            if r.decision == "APPROVE" and r.human_override == "REQUEST_CHANGES"
        )
        false_negatives = sum(
            1
            for r in reviews
            if r.decision == "REQUEST_CHANGES" and r.human_override == "APPROVE"
        )

        fp_rate = (false_positives / total * 100) if total > 0 else 0.0
        fn_rate = (false_negatives / total * 100) if total > 0 else 0.0

        avg_confidence = (
            sum(r.confidence for r in reviews) / total if total > 0 else 0.0
        )

        return CalibrationMetrics(
            total_reviews=total,
            approved_reviews=approved,
            commented_reviews=commented,
            requested_changes_reviews=requested_changes,
            human_overrides=overrides,
            human_agreements=agreements,
            accuracy_rate=accuracy,
            avg_confidence=avg_confidence,
            false_positive_rate=fp_rate,
            false_negative_rate=fn_rate,
            period_start=start_date,
            period_end=end_date,
        )

    async def get_recommended_thresholds(self) -> Dict[str, float]:
        """Get recommended confidence thresholds based on calibration."""
        metrics = await self.calculate_metrics(days=30)

        if metrics.total_reviews < 10:
            # Not enough data, use defaults
            return {
                "approve": 90.0,
                "comment": 70.0,
                "auto_merge": 95.0,
            }

        # Adjust thresholds based on accuracy
        if metrics.accuracy_rate >= 95.0:
            # High accuracy, can be more lenient
            return {
                "approve": 85.0,
                "comment": 65.0,
                "auto_merge": 92.0,
            }
        elif metrics.accuracy_rate >= 85.0:
            # Good accuracy, use standard thresholds
            return {
                "approve": 90.0,
                "comment": 70.0,
                "auto_merge": 95.0,
            }
        else:
            # Lower accuracy, be more conservative
            return {
                "approve": 93.0,
                "comment": 75.0,
                "auto_merge": 97.0,
            }

    async def export_to_grafana(self, metrics: CalibrationMetrics) -> Dict[str, Any]:
        """Export metrics in Grafana-compatible format."""
        return {
            "measurement": "gitreviewbot_calibration",
            "tags": {
                "bot": "gitreviewbot",
            },
            "fields": {
                "total_reviews": metrics.total_reviews,
                "accuracy_rate": metrics.accuracy_rate,
                "avg_confidence": metrics.avg_confidence,
                "false_positive_rate": metrics.false_positive_rate,
                "false_negative_rate": metrics.false_negative_rate,
                "human_overrides": metrics.human_overrides,
            },
            "timestamp": metrics.period_end.isoformat(),
        }

    def _generate_review_id(self, decision: Decision) -> str:
        """Generate unique review ID."""
        data = f"{decision.pr_number}:{decision.decided_at.isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    async def _get_reviews_in_period(
        self,
        start: datetime,
        end: datetime,
    ) -> List[ReviewRecord]:
        """Get all reviews within a time period."""
        if self.redis:
            # Scan for reviews in period
            reviews = []
            pattern = f"{self.metrics_prefix}:review:*"
            # Simplified - in production would use Redis scan
            return reviews
        else:
            # Filter local cache
            return [r for r in self._local_cache if start <= r.timestamp <= end]

    # Redis helper methods (async wrappers)
    async def _redis_set(self, key: str, value: Dict[str, Any]) -> None:
        """Set value in Redis."""
        if self.redis:
            try:
                await self.redis.hset(key, mapping=value)
                await self.redis.expire(key, 86400 * 30)  # 30 days
            except Exception:
                pass

    async def _redis_get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from Redis."""
        if self.redis:
            try:
                data = await self.redis.hgetall(key)
                return (
                    {k.decode(): v.decode() for k, v in data.items()} if data else None
                )
            except Exception:
                return None
        return None

    async def _redis_list_push(self, key: str, value: Dict[str, Any]) -> None:
        """Push value to Redis list."""
        if self.redis:
            try:
                await self.redis.lpush(key, json.dumps(value))
                await self.redis.expire(key, 86400 * 30)  # 30 days
            except Exception:
                pass
