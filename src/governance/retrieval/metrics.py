"""
Retrieval Metrics Exporter for ChiseAI Governance.

ST-GOV-007: Retrieval Quality Evaluator

Exports metrics related to retrieval quality evaluation,
A/B testing, and threshold tuning for monitoring in
Prometheus/Grafana.

Story: ST-GOV-007
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.governance.metrics.base_exporter import (
    BaseMetricsExporter,
    MetricPoint,
    MetricType,
)

logger = logging.getLogger(__name__)

# Redis keys for retrieval metrics
RETRIEVAL_PREFIX = "chise:governance:retrieval"
QUERIES_EVALUATED_KEY = f"{RETRIEVAL_PREFIX}:queries_evaluated"
PRECISION_AT_5_KEY = f"{RETRIEVAL_PREFIX}:precision_at_5"
PRECISION_AT_10_KEY = f"{RETRIEVAL_PREFIX}:precision_at_10"
RECALL_AT_5_KEY = f"{RETRIEVAL_PREFIX}:recall_at_5"
RECALL_AT_10_KEY = f"{RETRIEVAL_PREFIX}:recall_at_10"
MRR_KEY = f"{RETRIEVAL_PREFIX}:mrr"
HUMAN_VALIDATIONS_KEY = f"{RETRIEVAL_PREFIX}:human_validations"
AB_EXPERIMENTS_KEY = f"{RETRIEVAL_PREFIX}:ab_experiments"
THRESHOLD_ADJUSTMENTS_KEY = f"{RETRIEVAL_PREFIX}:threshold_adjustments"


class RetrievalMetricsExporter(BaseMetricsExporter):
    """
    Metrics exporter for retrieval quality evaluation.

    Collects and exports:
    - Queries evaluated (total count)
    - Precision@k metrics
    - Recall@k metrics
    - Mean Reciprocal Rank (MRR)
    - Human validation counts
    - A/B experiment status
    - Threshold tuning adjustments

    Example:
        exporter = RetrievalMetricsExporter(redis_client=redis)
        points = exporter.collect()
        # Returns metrics about retrieval quality
    """

    def __init__(
        self,
        influx_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the retrieval metrics exporter.

        Args:
            influx_client: Optional InfluxDB client
            redis_client: Optional Redis client for reading metrics
        """
        super().__init__(
            feature_name="retrieval",
            influx_client=influx_client,
            redis_client=redis_client,
        )

        # In-memory counters
        self._queries_evaluated = 0
        self._human_validations = 0
        self._ab_experiments_running = 0
        self._threshold_adjustments = 0
        self._last_precision_at_5 = 0.0
        self._last_precision_at_10 = 0.0
        self._last_recall_at_5 = 0.0
        self._last_recall_at_10 = 0.0
        self._last_mrr = 0.0

    def collect(self) -> list[MetricPoint]:
        """
        Collect retrieval quality metrics.

        Returns:
            List of MetricPoint objects with retrieval metrics
        """
        points: list[MetricPoint] = []
        now = datetime.now(UTC)

        # 1. Queries evaluated total
        queries_evaluated = self._get_queries_evaluated()
        points.append(
            MetricPoint(
                name="governance.retrieval.queries.evaluated",
                value=float(queries_evaluated),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "retrieval"},
            )
        )

        # 2. Precision@5
        precision_at_5 = self._get_precision_at_5()
        points.append(
            MetricPoint(
                name="governance.retrieval.precision.at_5",
                value=precision_at_5,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "retrieval", "metric": "precision"},
                fields={"k": 5},
            )
        )

        # 3. Precision@10
        precision_at_10 = self._get_precision_at_10()
        points.append(
            MetricPoint(
                name="governance.retrieval.precision.at_10",
                value=precision_at_10,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "retrieval", "metric": "precision"},
                fields={"k": 10},
            )
        )

        # 4. Recall@5
        recall_at_5 = self._get_recall_at_5()
        points.append(
            MetricPoint(
                name="governance.retrieval.recall.at_5",
                value=recall_at_5,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "retrieval", "metric": "recall"},
                fields={"k": 5},
            )
        )

        # 5. Recall@10
        recall_at_10 = self._get_recall_at_10()
        points.append(
            MetricPoint(
                name="governance.retrieval.recall.at_10",
                value=recall_at_10,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "retrieval", "metric": "recall"},
                fields={"k": 10},
            )
        )

        # 6. Mean Reciprocal Rank
        mrr = self._get_mrr()
        points.append(
            MetricPoint(
                name="governance.retrieval.mrr",
                value=mrr,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "retrieval"},
            )
        )

        # 7. Human validations
        human_validations = self._get_human_validations()
        points.append(
            MetricPoint(
                name="governance.retrieval.human_validations",
                value=float(human_validations),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "retrieval"},
            )
        )

        # 8. A/B experiments running
        ab_experiments = self._get_ab_experiments_running()
        points.append(
            MetricPoint(
                name="governance.retrieval.ab_experiments.running",
                value=float(ab_experiments),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "retrieval"},
            )
        )

        # 9. Threshold adjustments
        threshold_adjustments = self._get_threshold_adjustments()
        points.append(
            MetricPoint(
                name="governance.retrieval.threshold.adjustments",
                value=float(threshold_adjustments),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "retrieval"},
            )
        )

        # 10. Validation gate status
        gates_passed = self._check_validation_gates(precision_at_5, recall_at_10, mrr)
        points.append(
            MetricPoint(
                name="governance.retrieval.validation_gates.passed",
                value=1.0 if gates_passed else 0.0,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "retrieval"},
            )
        )

        # 11. F1 Score (harmonic mean of precision@5 and recall@10)
        if precision_at_5 + recall_at_10 > 0:
            f1_score = (
                2 * (precision_at_5 * recall_at_10) / (precision_at_5 + recall_at_10)
            )
            points.append(
                MetricPoint(
                    name="governance.retrieval.f1_score",
                    value=f1_score,
                    metric_type=MetricType.GAUGE,
                    timestamp=now,
                    tags={"feature": "retrieval"},
                )
            )

        return points

    def _get_queries_evaluated(self) -> int:
        """Get total queries evaluated count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(QUERIES_EVALUATED_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._queries_evaluated

    def _get_precision_at_5(self) -> float:
        """Get precision@5 metric."""
        if self._redis_client:
            try:
                val = self._redis_client.get(PRECISION_AT_5_KEY)
                if val:
                    return float(val)
            except Exception:
                pass
        return self._last_precision_at_5

    def _get_precision_at_10(self) -> float:
        """Get precision@10 metric."""
        if self._redis_client:
            try:
                val = self._redis_client.get(PRECISION_AT_10_KEY)
                if val:
                    return float(val)
            except Exception:
                pass
        return self._last_precision_at_10

    def _get_recall_at_5(self) -> float:
        """Get recall@5 metric."""
        if self._redis_client:
            try:
                val = self._redis_client.get(RECALL_AT_5_KEY)
                if val:
                    return float(val)
            except Exception:
                pass
        return self._last_recall_at_5

    def _get_recall_at_10(self) -> float:
        """Get recall@10 metric."""
        if self._redis_client:
            try:
                val = self._redis_client.get(RECALL_AT_10_KEY)
                if val:
                    return float(val)
            except Exception:
                pass
        return self._last_recall_at_10

    def _get_mrr(self) -> float:
        """Get Mean Reciprocal Rank metric."""
        if self._redis_client:
            try:
                val = self._redis_client.get(MRR_KEY)
                if val:
                    return float(val)
            except Exception:
                pass
        return self._last_mrr

    def _get_human_validations(self) -> int:
        """Get human validation count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(HUMAN_VALIDATIONS_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._human_validations

    def _get_ab_experiments_running(self) -> int:
        """Get count of running A/B experiments."""
        if self._redis_client:
            try:
                val = self._redis_client.get(AB_EXPERIMENTS_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._ab_experiments_running

    def _get_threshold_adjustments(self) -> int:
        """Get threshold adjustment count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(THRESHOLD_ADJUSTMENTS_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._threshold_adjustments

    def _check_validation_gates(
        self, precision_at_5: float, recall_at_10: float, mrr: float
    ) -> bool:
        """
        Check if validation gates are passed.

        Gates:
        - precision_at_5 >= 0.85
        - recall_at_10 >= 0.80
        - mrr >= 0.75

        Returns:
            True if all gates pass
        """
        return precision_at_5 >= 0.85 and recall_at_10 >= 0.80 and mrr >= 0.75

    # Methods for updating metrics
    def record_query_evaluated(self) -> None:
        """Record a query evaluation event."""
        self._queries_evaluated += 1

        if self._redis_client:
            try:
                self._redis_client.incr(QUERIES_EVALUATED_KEY)
            except Exception as e:
                logger.warning(f"Could not record query evaluation to Redis: {e}")

    def record_metrics(
        self,
        precision_at_5: float,
        precision_at_10: float,
        recall_at_5: float,
        recall_at_10: float,
        mrr: float,
    ) -> None:
        """
        Record retrieval quality metrics.

        Args:
            precision_at_5: Precision at k=5
            precision_at_10: Precision at k=10
            recall_at_5: Recall at k=5
            recall_at_10: Recall at k=10
            mrr: Mean Reciprocal Rank
        """
        self._last_precision_at_5 = precision_at_5
        self._last_precision_at_10 = precision_at_10
        self._last_recall_at_5 = recall_at_5
        self._last_recall_at_10 = recall_at_10
        self._last_mrr = mrr

        if self._redis_client:
            try:
                self._redis_client.set(PRECISION_AT_5_KEY, str(precision_at_5))
                self._redis_client.set(PRECISION_AT_10_KEY, str(precision_at_10))
                self._redis_client.set(RECALL_AT_5_KEY, str(recall_at_5))
                self._redis_client.set(RECALL_AT_10_KEY, str(recall_at_10))
                self._redis_client.set(MRR_KEY, str(mrr))
            except Exception as e:
                logger.warning(f"Could not record metrics to Redis: {e}")

    def record_human_validation(self) -> None:
        """Record a human validation event."""
        self._human_validations += 1

        if self._redis_client:
            try:
                self._redis_client.incr(HUMAN_VALIDATIONS_KEY)
            except Exception as e:
                logger.warning(f"Could not record human validation to Redis: {e}")

    def record_ab_experiment_started(self) -> None:
        """Record an A/B experiment started."""
        self._ab_experiments_running += 1

        if self._redis_client:
            try:
                self._redis_client.incr(AB_EXPERIMENTS_KEY)
            except Exception as e:
                logger.warning(f"Could not record A/B experiment to Redis: {e}")

    def record_ab_experiment_completed(self) -> None:
        """Record an A/B experiment completed."""
        self._ab_experiments_running = max(0, self._ab_experiments_running - 1)

        if self._redis_client:
            try:
                current = self._redis_client.get(AB_EXPERIMENTS_KEY)
                if current and int(current) > 0:
                    # Decrement by setting to current - 1
                    self._redis_client.set(AB_EXPERIMENTS_KEY, str(int(current) - 1))
            except Exception as e:
                logger.warning(f"Could not update A/B experiment count in Redis: {e}")

    def record_threshold_adjustment(self) -> None:
        """Record a threshold adjustment event."""
        self._threshold_adjustments += 1

        if self._redis_client:
            try:
                self._redis_client.incr(THRESHOLD_ADJUSTMENTS_KEY)
            except Exception as e:
                logger.warning(f"Could not record threshold adjustment to Redis: {e}")

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of current retrieval metrics.

        Returns:
            Dict with metric summaries
        """
        return {
            "queries_evaluated": self._get_queries_evaluated(),
            "precision_at_5": self._get_precision_at_5(),
            "precision_at_10": self._get_precision_at_10(),
            "recall_at_5": self._get_recall_at_5(),
            "recall_at_10": self._get_recall_at_10(),
            "mrr": self._get_mrr(),
            "human_validations": self._get_human_validations(),
            "ab_experiments_running": self._get_ab_experiments_running(),
            "threshold_adjustments": self._get_threshold_adjustments(),
            "validation_gates_passed": self._check_validation_gates(
                self._get_precision_at_5(),
                self._get_recall_at_10(),
                self._get_mrr(),
            ),
        }
