"""
Retrieval Quality Evaluation Module.

ST-GOV-007: Retrieval Quality Evaluator

This module provides retrieval quality evaluation capabilities including:
- Retrieval relevance tracking and evaluation
- A/B testing for retrieval strategies
- Automatic threshold tuning for similarity scores
- Metrics export for Prometheus/Grafana

Features:
- Standard IR metrics (precision@k, recall@k, MRR)
- Human validation sampling
- Statistical significance testing for A/B experiments
- Configurable threshold optimization strategies

Story: ST-GOV-007
"""

from .ab_tester import (
    AB_TEST_PREFIX,
    ABTester,
    Experiment,
    ExperimentMetrics,
    ExperimentResult,
    ExperimentStatus,
    StatisticalResult,
    StrategyConfig,
)
from .evaluator import (
    EVALUATOR_PREFIX,
    METRICS_KEY,
    QUERIES_KEY,
    RELEVANCE_KEY,
    QueryEvaluation,
    RelevanceLabel,
    RetrievalEvaluator,
    RetrievalMetrics,
    RetrievalResult,
)
from .metrics import (
    RETRIEVAL_PREFIX,
    RetrievalMetricsExporter,
)
from .threshold_tuner import (
    TUNER_PREFIX,
    AdjustmentStrategy,
    OptimizationGoal,
    ThresholdConfig,
    ThresholdTuner,
    TunerConfig,
    TuningHistory,
    TuningResult,
)

__all__ = [
    # Evaluator
    "RetrievalEvaluator",
    "RetrievalMetrics",
    "RetrievalResult",
    "QueryEvaluation",
    "RelevanceLabel",
    "EVALUATOR_PREFIX",
    "QUERIES_KEY",
    "RELEVANCE_KEY",
    "METRICS_KEY",
    # A/B Tester
    "ABTester",
    "Experiment",
    "ExperimentStatus",
    "ExperimentResult",
    "ExperimentMetrics",
    "StrategyConfig",
    "StatisticalResult",
    "AB_TEST_PREFIX",
    # Threshold Tuner
    "ThresholdTuner",
    "ThresholdConfig",
    "TunerConfig",
    "TuningResult",
    "TuningHistory",
    "OptimizationGoal",
    "AdjustmentStrategy",
    "TUNER_PREFIX",
    # Metrics
    "RetrievalMetricsExporter",
    "RETRIEVAL_PREFIX",
]
