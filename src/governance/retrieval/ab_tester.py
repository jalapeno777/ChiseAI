"""
A/B Testing for Retrieval Strategies.

ST-GOV-007: Retrieval Quality Evaluator

This module provides A/B testing capabilities for comparing different
retrieval strategies. It supports:
- Strategy registration and configuration
- Random assignment to test groups
- Statistical significance testing
- Result tracking and reporting

Story: ST-GOV-007
"""

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Redis key constants
AB_TEST_PREFIX = "governance:retrieval:ab_test"
EXPERIMENTS_KEY = f"{AB_TEST_PREFIX}:experiments"
RESULTS_KEY = f"{AB_TEST_PREFIX}:results"


class ExperimentStatus(Enum):
    """Status of an A/B test experiment."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@runtime_checkable
class RedisClient(Protocol):
    """Protocol for Redis client interface."""

    def hset(self, name: str, key: str, value: Any) -> int: ...

    def hget(self, name: str, key: str) -> bytes | None: ...

    def hgetall(self, name: str) -> dict[bytes, bytes]: ...

    def set(self, name: str, value: Any, ex: int | None = None) -> bool: ...

    def get(self, name: str) -> bytes | None: ...

    def lpush(self, name: str, *values: Any) -> int: ...

    def lrange(self, name: str, start: int, end: int) -> list[bytes]: ...


@runtime_checkable
class RetrievalStrategy(Protocol):
    """Protocol for retrieval strategy implementation."""

    name: str

    def retrieve(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> list[dict[str, Any]]: ...


@dataclass
class StrategyConfig:
    """Configuration for a retrieval strategy."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    weight: float = 0.5  # Traffic allocation weight

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            weight=data.get("weight", 0.5),
        )


@dataclass
class ExperimentResult:
    """Result of a single experiment query."""

    experiment_id: str
    query_id: str
    strategy_name: str
    results: list[dict[str, Any]]
    metrics: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "query_id": self.query_id,
            "strategy_name": self.strategy_name,
            "results": self.results,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentResult":
        """Create from dictionary."""
        return cls(
            experiment_id=data["experiment_id"],
            query_id=data["query_id"],
            strategy_name=data["strategy_name"],
            results=data["results"],
            metrics=data.get("metrics", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class ExperimentMetrics:
    """Aggregated metrics for a strategy in an experiment."""

    strategy_name: str
    sample_count: int = 0
    avg_precision_at_5: float = 0.0
    avg_precision_at_10: float = 0.0
    avg_recall_at_10: float = 0.0
    avg_mrr: float = 0.0
    avg_latency_ms: float = 0.0
    total_relevant: int = 0
    total_retrieved: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "sample_count": self.sample_count,
            "avg_precision_at_5": self.avg_precision_at_5,
            "avg_precision_at_10": self.avg_precision_at_10,
            "avg_recall_at_10": self.avg_recall_at_10,
            "avg_mrr": self.avg_mrr,
            "avg_latency_ms": self.avg_latency_ms,
            "total_relevant": self.total_relevant,
            "total_retrieved": self.total_retrieved,
        }


@dataclass
class Experiment:
    """
    A/B test experiment configuration and state.

    Attributes:
        experiment_id: Unique experiment identifier
        name: Human-readable name
        description: What is being tested
        control_strategy: The baseline/ control strategy
        treatment_strategy: The experimental/treatment strategy
        status: Current experiment status
        created_at: When experiment was created
        started_at: When experiment started running
        traffic_split: Percentage of traffic to treatment (0-1)
        target_sample_size: Minimum samples before analysis
    """

    experiment_id: str
    name: str
    description: str = ""
    control_strategy: StrategyConfig | None = None
    treatment_strategy: StrategyConfig | None = None
    status: ExperimentStatus = ExperimentStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    traffic_split: float = 0.5
    target_sample_size: int = 1000
    results: list[ExperimentResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "control_strategy": (
                self.control_strategy.to_dict() if self.control_strategy else None
            ),
            "treatment_strategy": (
                self.treatment_strategy.to_dict() if self.treatment_strategy else None
            ),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "traffic_split": self.traffic_split,
            "target_sample_size": self.target_sample_size,
            "results_count": len(self.results),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Experiment":
        """Create from dictionary."""
        return cls(
            experiment_id=data["experiment_id"],
            name=data["name"],
            description=data.get("description", ""),
            control_strategy=(
                StrategyConfig.from_dict(data["control_strategy"])
                if data.get("control_strategy")
                else None
            ),
            treatment_strategy=(
                StrategyConfig.from_dict(data["treatment_strategy"])
                if data.get("treatment_strategy")
                else None
            ),
            status=ExperimentStatus(data.get("status", "draft")),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            traffic_split=data.get("traffic_split", 0.5),
            target_sample_size=data.get("target_sample_size", 1000),
        )


@dataclass
class StatisticalResult:
    """Result of statistical significance test."""

    metric_name: str
    control_mean: float
    treatment_mean: float
    control_std: float
    treatment_std: float
    p_value: float
    is_significant: bool
    confidence_level: float = 0.95
    effect_size: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "control_mean": self.control_mean,
            "treatment_mean": self.treatment_mean,
            "control_std": self.control_std,
            "treatment_std": self.treatment_std,
            "p_value": self.p_value,
            "is_significant": self.is_significant,
            "confidence_level": self.confidence_level,
            "effect_size": self.effect_size,
        }


class ABTester:
    """
    A/B testing framework for retrieval strategies.

    This class provides:
    - Strategy registration and management
    - Experiment creation and configuration
    - Traffic splitting and assignment
    - Statistical significance testing
    - Result aggregation and reporting

    Example:
        tester = ABTester(redis_client=redis)
        tester.register_strategy("baseline", baseline_strategy)
        tester.register_strategy("enhanced", enhanced_strategy)

        exp_id = tester.create_experiment(
            name="Embedding comparison",
            control="baseline",
            treatment="enhanced"
        )
        tester.start_experiment(exp_id)

        # Run queries through the test
        for query in queries:
            strategy_name = tester.get_strategy_for_query(exp_id, query)
            result = tester.run_query(exp_id, query, strategy_name)

        # Analyze results
        results = tester.analyze_experiment(exp_id)
    """

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        default_confidence: float = 0.95,
    ):
        """
        Initialize the A/B tester.

        Args:
            redis_client: Optional Redis client for persistence
            default_confidence: Default confidence level for significance tests
        """
        self._redis = redis_client
        self._default_confidence = default_confidence

        # In-memory storage
        self._strategies: dict[str, RetrievalStrategy] = {}
        self._strategy_configs: dict[str, StrategyConfig] = {}
        self._experiments: dict[str, Experiment] = {}

    def register_strategy(
        self,
        name: str,
        strategy: RetrievalStrategy,
        config: StrategyConfig | None = None,
    ) -> None:
        """
        Register a retrieval strategy.

        Args:
            name: Strategy name
            strategy: Strategy implementation
            config: Optional configuration
        """
        self._strategies[name] = strategy
        self._strategy_configs[name] = config or StrategyConfig(name=name)
        logger.info(f"Registered strategy: {name}")

    def unregister_strategy(self, name: str) -> bool:
        """
        Unregister a retrieval strategy.

        Args:
            name: Strategy name to unregister

        Returns:
            True if strategy was removed
        """
        if name in self._strategies:
            del self._strategies[name]
            del self._strategy_configs[name]
            logger.info(f"Unregistered strategy: {name}")
            return True
        return False

    def get_registered_strategies(self) -> list[str]:
        """Get list of registered strategy names."""
        return list(self._strategies.keys())

    def create_experiment(
        self,
        name: str,
        control: str,
        treatment: str,
        description: str = "",
        traffic_split: float = 0.5,
        target_sample_size: int = 1000,
    ) -> str:
        """
        Create a new A/B test experiment.

        Args:
            name: Experiment name
            control: Control strategy name
            treatment: Treatment strategy name
            description: Experiment description
            traffic_split: Fraction of traffic to treatment (0-1)
            target_sample_size: Minimum samples for analysis

        Returns:
            Experiment ID

        Raises:
            ValueError: If strategies not registered
        """
        if control not in self._strategies:
            raise ValueError(f"Control strategy '{control}' not registered")
        if treatment not in self._strategies:
            raise ValueError(f"Treatment strategy '{treatment}' not registered")

        experiment_id = f"exp-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"

        experiment = Experiment(
            experiment_id=experiment_id,
            name=name,
            description=description,
            control_strategy=self._strategy_configs[control],
            treatment_strategy=self._strategy_configs[treatment],
            traffic_split=traffic_split,
            target_sample_size=target_sample_size,
        )

        self._experiments[experiment_id] = experiment
        self._store_experiment(experiment)

        logger.info(f"Created experiment: {experiment_id} ({control} vs {treatment})")
        return experiment_id

    def start_experiment(self, experiment_id: str) -> bool:
        """
        Start running an experiment.

        Args:
            experiment_id: Experiment to start

        Returns:
            True if started successfully
        """
        if experiment_id not in self._experiments:
            logger.warning(f"Experiment {experiment_id} not found")
            return False

        experiment = self._experiments[experiment_id]
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now(UTC)

        self._store_experiment(experiment)
        logger.info(f"Started experiment: {experiment_id}")
        return True

    def pause_experiment(self, experiment_id: str) -> bool:
        """Pause a running experiment."""
        if experiment_id not in self._experiments:
            return False

        experiment = self._experiments[experiment_id]
        if experiment.status == ExperimentStatus.RUNNING:
            experiment.status = ExperimentStatus.PAUSED
            self._store_experiment(experiment)
            logger.info(f"Paused experiment: {experiment_id}")
            return True
        return False

    def complete_experiment(self, experiment_id: str) -> bool:
        """Mark an experiment as completed."""
        if experiment_id not in self._experiments:
            return False

        experiment = self._experiments[experiment_id]
        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = datetime.now(UTC)

        self._store_experiment(experiment)
        logger.info(f"Completed experiment: {experiment_id}")
        return True

    def get_strategy_for_query(self, experiment_id: str, query: str) -> str:
        """
        Determine which strategy to use for a query.

        Uses consistent hashing to ensure the same query always
        gets the same strategy assignment.

        Args:
            experiment_id: Active experiment
            query: Query text

        Returns:
            Strategy name to use
        """
        if experiment_id not in self._experiments:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.RUNNING:
            # Return control if not running
            return (
                experiment.control_strategy.name if experiment.control_strategy else ""
            )

        # Use hash for consistent assignment
        hash_value = hash(query) % 100 / 100.0

        if hash_value < experiment.traffic_split:
            return (
                experiment.treatment_strategy.name
                if experiment.treatment_strategy
                else ""
            )
        return experiment.control_strategy.name if experiment.control_strategy else ""

    def run_query(
        self,
        experiment_id: str,
        query: str,
        strategy_name: str,
        query_id: str | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> ExperimentResult:
        """
        Run a query through a specific strategy and record results.

        Args:
            experiment_id: Experiment ID
            query: Query text
            strategy_name: Strategy to use
            query_id: Optional query ID
            limit: Result limit
            **kwargs: Additional strategy parameters

        Returns:
            ExperimentResult with query results
        """
        if experiment_id not in self._experiments:
            raise ValueError(f"Experiment {experiment_id} not found")

        if strategy_name not in self._strategies:
            raise ValueError(f"Strategy {strategy_name} not registered")

        import time

        strategy = self._strategies[strategy_name]

        # Run the retrieval
        start_time = time.perf_counter()
        results = strategy.retrieve(query, limit=limit, **kwargs)
        latency_ms = (time.perf_counter() - start_time) * 1000

        query_id = query_id or f"q-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"

        result = ExperimentResult(
            experiment_id=experiment_id,
            query_id=query_id,
            strategy_name=strategy_name,
            results=results,
            metrics={
                "latency_ms": latency_ms,
                "result_count": len(results),
            },
        )

        # Store result
        self._experiments[experiment_id].results.append(result)
        self._store_result(result)

        logger.debug(
            f"Ran query {query_id} via {strategy_name}: {len(results)} results"
        )
        return result

    def record_relevance_feedback(
        self,
        experiment_id: str,
        query_id: str,
        relevant_doc_ids: set[str],
    ) -> bool:
        """
        Record relevance feedback for a query result.

        This updates the metrics for the experiment based on
        human judgment of result relevance.

        Args:
            experiment_id: Experiment ID
            query_id: Query ID
            relevant_doc_ids: Set of relevant doc IDs

        Returns:
            True if feedback recorded
        """
        if experiment_id not in self._experiments:
            return False

        experiment = self._experiments[experiment_id]

        # Find the result
        for result in experiment.results:
            if result.query_id == query_id:
                # Calculate metrics based on feedback
                top_5 = result.results[:5]
                top_10 = result.results[:10]

                relevant_5 = sum(
                    1 for r in top_5 if r.get("doc_id") in relevant_doc_ids
                )
                relevant_10 = sum(
                    1 for r in top_10 if r.get("doc_id") in relevant_doc_ids
                )

                result.metrics["precision_at_5"] = relevant_5 / max(len(top_5), 1)
                result.metrics["precision_at_10"] = relevant_10 / max(len(top_10), 1)
                result.metrics["relevant_count"] = len(relevant_doc_ids)

                self._store_result(result)
                logger.debug(f"Recorded relevance feedback for {query_id}")
                return True

        return False

    def get_experiment_metrics(
        self, experiment_id: str
    ) -> dict[str, ExperimentMetrics]:
        """
        Get aggregated metrics for all strategies in an experiment.

        Args:
            experiment_id: Experiment ID

        Returns:
            Dict mapping strategy names to aggregated metrics
        """
        if experiment_id not in self._experiments:
            return {}

        experiment = self._experiments[experiment_id]
        metrics_by_strategy: dict[str, ExperimentMetrics] = {}

        # Initialize metrics for each strategy
        if experiment.control_strategy:
            metrics_by_strategy[experiment.control_strategy.name] = ExperimentMetrics(
                strategy_name=experiment.control_strategy.name
            )
        if experiment.treatment_strategy:
            metrics_by_strategy[experiment.treatment_strategy.name] = ExperimentMetrics(
                strategy_name=experiment.treatment_strategy.name
            )

        # Aggregate results
        for result in experiment.results:
            if result.strategy_name not in metrics_by_strategy:
                continue

            m = metrics_by_strategy[result.strategy_name]
            n = m.sample_count

            # Running average for metrics
            for metric_name in ["precision_at_5", "precision_at_10", "latency_ms"]:
                if metric_name in result.metrics:
                    current = (
                        getattr(m, f"avg_{metric_name}", 0)
                        if hasattr(m, f"avg_{metric_name}")
                        else 0
                    )
                    # For latency, the attribute is avg_latency_ms
                    if metric_name == "latency_ms":
                        current = m.avg_latency_ms
                        m.avg_latency_ms = (
                            current * n + result.metrics[metric_name]
                        ) / (n + 1)
                    elif metric_name == "precision_at_5":
                        m.avg_precision_at_5 = (
                            m.avg_precision_at_5 * n + result.metrics[metric_name]
                        ) / (n + 1)
                    elif metric_name == "precision_at_10":
                        m.avg_precision_at_10 = (
                            m.avg_precision_at_10 * n + result.metrics[metric_name]
                        ) / (n + 1)

            m.sample_count += 1

        return metrics_by_strategy

    def analyze_experiment(
        self, experiment_id: str, confidence: float | None = None
    ) -> dict[str, StatisticalResult]:
        """
        Perform statistical significance analysis on experiment results.

        Uses a two-sample t-test to determine if differences between
        control and treatment are statistically significant.

        Args:
            experiment_id: Experiment ID
            confidence: Confidence level (uses default if None)

        Returns:
            Dict mapping metric names to statistical results
        """
        import math

        if experiment_id not in self._experiments:
            return {}

        experiment = self._experiments[experiment_id]
        confidence = confidence or self._default_confidence

        # Group results by strategy
        control_name = (
            experiment.control_strategy.name if experiment.control_strategy else ""
        )
        treatment_name = (
            experiment.treatment_strategy.name if experiment.treatment_strategy else ""
        )

        control_results = [
            r for r in experiment.results if r.strategy_name == control_name
        ]
        treatment_results = [
            r for r in experiment.results if r.strategy_name == treatment_name
        ]

        if not control_results or not treatment_results:
            logger.warning("Not enough data for statistical analysis")
            return {}

        # Calculate statistics for each metric
        metrics_to_analyze = ["precision_at_5", "precision_at_10", "latency_ms"]
        statistical_results: dict[str, StatisticalResult] = {}

        for metric_name in metrics_to_analyze:
            control_values = [
                r.metrics.get(metric_name, 0)
                for r in control_results
                if metric_name in r.metrics
            ]
            treatment_values = [
                r.metrics.get(metric_name, 0)
                for r in treatment_results
                if metric_name in r.metrics
            ]

            if not control_values or not treatment_values:
                continue

            # Calculate means and standard deviations
            control_mean = sum(control_values) / len(control_values)
            treatment_mean = sum(treatment_values) / len(treatment_values)

            control_var = sum((x - control_mean) ** 2 for x in control_values) / len(
                control_values
            )
            treatment_var = sum(
                (x - treatment_mean) ** 2 for x in treatment_values
            ) / len(treatment_values)

            control_std = math.sqrt(control_var)
            treatment_std = math.sqrt(treatment_var)

            # Two-sample t-test (simplified)
            n1, n2 = len(control_values), len(treatment_values)
            if control_std + treatment_std == 0:
                p_value = 1.0
            else:
                # Pooled standard error
                se = math.sqrt(control_var / n1 + treatment_var / n2)
                if se == 0:
                    p_value = 1.0
                else:
                    t_stat = (treatment_mean - control_mean) / se
                    # Approximate p-value (using normal approximation)
                    p_value = 2 * (1 - self._normal_cdf(abs(t_stat)))

            # Effect size (Cohen's d)
            pooled_std = math.sqrt((control_var + treatment_var) / 2)
            effect_size = (
                (treatment_mean - control_mean) / pooled_std if pooled_std > 0 else 0
            )

            # Significance threshold
            alpha = 1 - confidence
            is_significant = p_value < alpha

            # Adjust for metric direction (lower is better for latency)
            if metric_name == "latency_ms":
                effect_size = -effect_size

            statistical_results[metric_name] = StatisticalResult(
                metric_name=metric_name,
                control_mean=control_mean,
                treatment_mean=treatment_mean,
                control_std=control_std,
                treatment_std=treatment_std,
                p_value=p_value,
                is_significant=is_significant,
                confidence_level=confidence,
                effect_size=effect_size,
            )

        return statistical_results

    def _normal_cdf(self, x: float) -> float:
        """Approximate cumulative distribution function for standard normal."""
        # Approximation using error function
        import math

        return (1 + math.erf(x / math.sqrt(2))) / 2

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        """Get an experiment by ID."""
        return self._experiments.get(experiment_id)

    def get_all_experiments(
        self, status: ExperimentStatus | None = None
    ) -> list[Experiment]:
        """
        Get all experiments, optionally filtered by status.

        Args:
            status: Optional status filter

        Returns:
            List of experiments
        """
        experiments = list(self._experiments.values())
        if status:
            experiments = [e for e in experiments if e.status == status]
        return experiments

    def _store_experiment(self, experiment: Experiment) -> None:
        """Store experiment to Redis."""
        if self._redis is None:
            return

        try:
            key = f"{EXPERIMENTS_KEY}:{experiment.experiment_id}"
            self._redis.set(key, json.dumps(experiment.to_dict()), ex=90 * 24 * 60 * 60)
        except Exception as e:
            logger.warning(f"Failed to store experiment to Redis: {e}")

    def _store_result(self, result: ExperimentResult) -> None:
        """Store result to Redis."""
        if self._redis is None:
            return

        try:
            key = f"{RESULTS_KEY}:{result.experiment_id}:{result.query_id}"
            self._redis.set(key, json.dumps(result.to_dict()), ex=30 * 24 * 60 * 60)
        except Exception as e:
            logger.warning(f"Failed to store result to Redis: {e}")
