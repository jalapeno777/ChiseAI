"""Tests for ML evaluation metrics."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import numpy as np

sys.path.insert(0, "src")

from ml.evaluation.metrics import (
    METRIC_CONFIGS,
    EvaluationMetrics,
    MetricCategory,
    MetricConfig,
    MetricResult,
    compute_accuracy,
    compute_all_metrics,
    compute_auc_roc,
    compute_brier_score,
    compute_calibration_error,
    compute_expectancy,
    compute_f1,
    compute_information_ratio,
    compute_kelly_fraction,
    compute_log_loss,
    compute_max_drawdown,
    compute_precision,
    compute_profit_factor,
    compute_recall,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    compute_win_rate,
)


class TestMetricConfig:
    """Tests for MetricConfig dataclass."""

    def test_metric_config_creation(self):
        """Test creating a MetricConfig with all fields."""
        config = MetricConfig(
            name="test_metric",
            category=MetricCategory.CLASSIFICATION,
            description="A test metric",
            higher_is_better=True,
            min_value=0.0,
            max_value=1.0,
        )

        assert config.name == "test_metric"
        assert config.category == MetricCategory.CLASSIFICATION
        assert config.description == "A test metric"
        assert config.higher_is_better is True
        assert config.min_value == 0.0
        assert config.max_value == 1.0

    def test_metric_config_default_values(self):
        """Test MetricConfig with default min/max values."""
        config = MetricConfig(
            name="test",
            category=MetricCategory.TRADING,
            description="Test",
            higher_is_better=False,
        )

        assert config.min_value == 0.0
        assert config.max_value == 1.0


class TestMetricResult:
    """Tests for MetricResult dataclass."""

    def test_metric_result_creation(self):
        """Test creating a MetricResult."""
        result = MetricResult(
            name="accuracy",
            value=0.95,
            category=MetricCategory.CLASSIFICATION,
            metadata={"note": "test"},
        )

        assert result.name == "accuracy"
        assert result.value == 0.95
        assert result.category == MetricCategory.CLASSIFICATION
        assert result.metadata == {"note": "test"}
        assert result.timestamp is not None

    def test_metric_result_to_dict(self):
        """Test converting MetricResult to dictionary."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = MetricResult(
            name="precision",
            value=0.87,
            category=MetricCategory.CLASSIFICATION,
            timestamp=timestamp,
            metadata={"threshold": 0.5},
        )

        data = result.to_dict()

        assert data["name"] == "precision"
        assert data["value"] == 0.87
        assert data["category"] == "classification"
        assert data["timestamp"] == "2024-01-15T12:00:00+00:00"
        assert data["metadata"] == {"threshold": 0.5}

    def test_metric_result_from_dict(self):
        """Test creating MetricResult from dictionary."""
        data = {
            "name": "recall",
            "value": 0.92,
            "category": "classification",
            "timestamp": "2024-01-15T12:00:00+00:00",
            "metadata": {"samples": 100},
        }

        result = MetricResult.from_dict(data)

        assert result.name == "recall"
        assert result.value == 0.92
        assert result.category == MetricCategory.CLASSIFICATION
        assert result.metadata == {"samples": 100}

    def test_metric_result_roundtrip(self):
        """Test roundtrip serialization of MetricResult."""
        original = MetricResult(
            name="f1",
            value=0.88,
            category=MetricCategory.CLASSIFICATION,
            metadata={"model": "test"},
        )

        restored = MetricResult.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.value == original.value
        assert restored.category == original.category
        assert restored.metadata == original.metadata


class TestClassificationMetrics:
    """Tests for classification metric functions."""

    def test_accuracy_computation(self):
        """Test accuracy computation with known inputs."""
        predictions = np.array([1, 0, 1, 1])
        labels = np.array([1, 0, 0, 1])

        accuracy = compute_accuracy(predictions, labels)

        # 3 correct out of 4 = 0.75
        assert accuracy == 0.75

    def test_accuracy_perfect(self):
        """Test accuracy with perfect predictions."""
        predictions = np.array([1, 0, 1, 0, 1])
        labels = np.array([1, 0, 1, 0, 1])

        accuracy = compute_accuracy(predictions, labels)

        assert accuracy == 1.0

    def test_accuracy_all_wrong(self):
        """Test accuracy with all wrong predictions."""
        predictions = np.array([1, 1, 0, 0])
        labels = np.array([0, 0, 1, 1])

        accuracy = compute_accuracy(predictions, labels)

        assert accuracy == 0.0

    def test_precision_computation(self):
        """Test precision computation with known inputs."""
        predictions = np.array([1, 1, 1, 0])
        labels = np.array([1, 0, 1, 1])

        precision = compute_precision(predictions, labels)

        # TP=2 (indices 0,2), FP=1 (index 1)
        # precision = 2/(2+1) = 0.667
        assert abs(precision - 0.667) < 0.01

    def test_precision_no_positives(self):
        """Test precision when no positive predictions."""
        predictions = np.array([0, 0, 0])
        labels = np.array([1, 0, 1])

        precision = compute_precision(predictions, labels)

        assert precision == 0.0

    def test_recall_computation(self):
        """Test recall computation with known inputs."""
        predictions = np.array([1, 1, 0, 0])
        labels = np.array([1, 0, 1, 1])

        recall = compute_recall(predictions, labels)

        # TP=1 (index 0), FN=2 (indices 2,3)
        # recall = 1/(1+2) = 0.333
        assert abs(recall - 0.333) < 0.01

    def test_recall_no_positives_in_labels(self):
        """Test recall when no positive labels."""
        predictions = np.array([1, 1, 0])
        labels = np.array([0, 0, 0])

        recall = compute_recall(predictions, labels)

        assert recall == 0.0

    def test_f1_computation(self):
        """Test F1 score computation with known inputs."""
        predictions = np.array([1, 1, 1, 0])
        labels = np.array([1, 0, 1, 1])

        f1 = compute_f1(predictions, labels)

        # precision = 2/3 ≈ 0.667, recall = 1/3 ≈ 0.333
        # f1 = 2 * (0.667 * 0.333) / (0.667 + 0.333) ≈ 0.444
        assert abs(f1 - 0.667) < 0.01

    def test_f1_perfect(self):
        """Test F1 with perfect predictions."""
        predictions = np.array([1, 0, 1, 0])
        labels = np.array([1, 0, 1, 0])

        f1 = compute_f1(predictions, labels)

        assert f1 == 1.0

    def test_f1_no_positives(self):
        """Test F1 when no true positives."""
        predictions = np.array([0, 0, 0, 0])
        labels = np.array([1, 1, 1, 1])

        f1 = compute_f1(predictions, labels)

        assert f1 == 0.0

    def test_auc_roc_computation(self):
        """Test AUC-ROC computation with simple case."""
        scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2])
        labels = np.array([1, 1, 1, 1, 0, 0, 0, 0])

        auc = compute_auc_roc(scores, labels)

        # Perfect separation: all positives have higher scores than negatives
        assert auc == 1.0

    def test_auc_roc_reverse(self):
        """Test AUC-ROC with reverse ordering."""
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        labels = np.array([1, 1, 1, 1, 0, 0, 0, 0])

        auc = compute_auc_roc(scores, labels)

        # Worst separation: all positives have lower scores
        assert auc == 0.0

    def test_auc_roc_random(self):
        """Test AUC-ROC with random predictions."""
        np.random.seed(42)
        scores = np.random.rand(100)
        labels = np.array([1] * 50 + [0] * 50)

        auc = compute_auc_roc(scores, labels)

        # Random should be around 0.5
        assert 0.4 < auc < 0.6

    def test_auc_roc_all_same_labels(self):
        """Test AUC-ROC when all labels are the same."""
        scores = np.array([0.1, 0.5, 0.9])
        labels = np.array([1, 1, 1])

        auc = compute_auc_roc(scores, labels)

        assert auc == 0.5

    def test_log_loss_computation(self):
        """Test log loss computation with known inputs."""
        probabilities = np.array([0.9, 0.1, 0.8, 0.2])
        labels = np.array([1, 0, 1, 0])

        logloss = compute_log_loss(probabilities, labels)

        # Perfect predictions should give low log loss
        assert logloss < 0.5

    def test_log_loss_perfect(self):
        """Test log loss with perfect predictions."""
        probabilities = np.array([1.0, 0.0, 1.0, 0.0])
        labels = np.array([1, 0, 1, 0])

        logloss = compute_log_loss(probabilities, labels)

        assert logloss < 1e-10

    def test_log_loss_random(self):
        """Test log loss with random predictions."""
        probabilities = np.array([0.5, 0.5, 0.5, 0.5])
        labels = np.array([1, 0, 1, 0])

        logloss = compute_log_loss(probabilities, labels)

        # 50% predictions should give log loss of -log(0.5) ≈ 0.693
        assert abs(logloss - 0.693) < 0.01


class TestCalibrationMetrics:
    """Tests for calibration metric functions."""

    def test_calibration_error_perfect(self):
        """Test calibration error with perfectly calibrated predictions."""
        # Perfect calibration: probability = label mean
        probabilities = np.array([0.0, 0.5, 1.0, 0.5])
        labels = np.array([0, 1, 1, 0])

        ece = compute_calibration_error(probabilities, labels)

        # Should be close to 0
        assert ece < 0.1

    def test_calibration_error_misaligned(self):
        """Test calibration error with misaligned predictions."""
        probabilities = np.array([0.9, 0.9, 0.9, 0.1])
        labels = np.array([0, 0, 0, 1])

        ece = compute_calibration_error(probabilities, labels)

        # High miscalibration
        assert ece > 0.3

    def test_brier_score_computation(self):
        """Test Brier score computation with known inputs."""
        probabilities = np.array([0.9, 0.1, 0.8, 0.2])
        labels = np.array([1, 0, 1, 0])

        brier = compute_brier_score(probabilities, labels)

        # (0.1)^2 + (0.1)^2 + (0.2)^2 + (0.2)^2 = 0.01 + 0.01 + 0.04 + 0.04 = 0.1
        assert abs(brier - 0.025) < 0.01

    def test_brier_score_perfect(self):
        """Test Brier score with perfect predictions."""
        probabilities = np.array([1.0, 0.0, 1.0, 0.0])
        labels = np.array([1, 0, 1, 0])

        brier = compute_brier_score(probabilities, labels)

        assert brier == 0.0


class TestTradingMetrics:
    """Tests for trading metric functions."""

    def test_sharpe_ratio_computation(self):
        """Test Sharpe ratio computation with known returns."""
        returns = np.array([0.01, -0.005, 0.02, 0.015, -0.01])

        sharpe = compute_sharpe_ratio(returns)

        # Should compute a valid value
        assert isinstance(sharpe, float)

    def test_sharpe_ratio_zero_returns(self):
        """Test Sharpe ratio with zero returns."""
        returns = np.array([0.0, 0.0, 0.0])

        sharpe = compute_sharpe_ratio(returns)

        assert sharpe == 0.0

    def test_sharpe_ratio_consistent(self):
        """Test Sharpe ratio is consistent for same returns."""
        returns = np.array([0.01, -0.005, 0.02, 0.015])

        sharpe1 = compute_sharpe_ratio(returns)
        sharpe2 = compute_sharpe_ratio(returns.copy())

        assert sharpe1 == sharpe2

    def test_max_drawdown_computation(self):
        """Test maximum drawdown computation with known returns."""
        returns = np.array([0.05, -0.10, 0.03, 0.02, -0.15])

        mdd = compute_max_drawdown(returns)

        # Should be positive and between 0 and 1
        assert mdd >= 0.0
        assert mdd <= 1.0

    def test_max_drawdown_positive_returns(self):
        """Test max drawdown with only positive returns."""
        returns = np.array([0.01, 0.02, 0.03, 0.01, 0.02])

        mdd = compute_max_drawdown(returns)

        assert mdd == 0.0

    def test_max_drawdown_large_drop(self):
        """Test max drawdown with large drop."""
        returns = np.array([0.10, -0.50, 0.01])

        mdd = compute_max_drawdown(returns)

        # Should capture the 50% drop
        assert mdd > 0.4

    def test_win_rate_computation(self):
        """Test win rate computation with known trades."""
        trades = np.array([100, -50, 150, 80, -30])

        win_rate = compute_win_rate(trades)

        # 3 winning trades out of 5 = 0.6
        assert win_rate == 0.6

    def test_win_rate_all_winners(self):
        """Test win rate with all winning trades."""
        trades = np.array([100, 50, 150, 80])

        win_rate = compute_win_rate(trades)

        assert win_rate == 1.0

    def test_win_rate_all_losers(self):
        """Test win rate with all losing trades."""
        trades = np.array([-100, -50, -150, -80])

        win_rate = compute_win_rate(trades)

        assert win_rate == 0.0

    def test_profit_factor_computation(self):
        """Test profit factor computation with known trades."""
        trades = np.array([100, -50, 150, 80, -30])

        pf = compute_profit_factor(trades)

        # gross profit = 100 + 150 + 80 = 330
        # gross loss = 50 + 30 = 80
        # profit factor = 330/80 = 4.125
        assert pf == 4.125

    def test_profit_factor_no_losses(self):
        """Test profit factor with no losing trades."""
        trades = np.array([100, 50, 150])

        pf = compute_profit_factor(trades)

        assert pf == float("inf")

    def test_profit_factor_no_wins(self):
        """Test profit factor with no winning trades."""
        trades = np.array([-100, -50, -150])

        pf = compute_profit_factor(trades)

        assert pf == 0.0

    def test_expectancy_computation(self):
        """Test expectancy computation with known trades."""
        trades = np.array([100, -50, 150, 80, -30])

        expectancy = compute_expectancy(trades)

        # (100 - 50 + 150 + 80 - 30) / 5 = 250 / 5 = 50
        assert expectancy == 50.0

    def test_expectancy_negative(self):
        """Test expectancy with negative average."""
        trades = np.array([-100, -50, -20])

        expectancy = compute_expectancy(trades)

        assert expectancy == -56.666666666666664

    def test_kelly_fraction_computation(self):
        """Test Kelly criterion computation."""
        kelly = compute_kelly_fraction(win_rate=0.6, avg_win=100, avg_loss=50)

        # p=0.6, q=0.4, b=100/50=2
        # kelly = 0.6 - 0.4/2 = 0.6 - 0.2 = 0.4
        assert abs(kelly - 0.4) < 0.01

    def test_kelly_fraction_zero_win_rate(self):
        """Test Kelly fraction with zero win rate."""
        kelly = compute_kelly_fraction(win_rate=0.0, avg_win=100, avg_loss=50)

        assert kelly == 0.0

    def test_kelly_fraction_perfect_win_rate(self):
        """Test Kelly fraction with 100% win rate."""
        kelly = compute_kelly_fraction(win_rate=1.0, avg_win=100, avg_loss=50)

        assert kelly == 0.0  # win_rate >= 1 returns 0 per implementation


class TestRiskAdjustedMetrics:
    """Tests for risk-adjusted metric functions."""

    def test_information_ratio_computation(self):
        """Test information ratio computation."""
        returns = np.array([0.01, -0.005, 0.02, 0.015, -0.01])
        benchmark = np.array([0.008, -0.003, 0.015, 0.01, -0.008])

        ir = compute_information_ratio(returns, benchmark)

        assert isinstance(ir, float)

    def test_information_ratio_zero_benchmark(self):
        """Test information ratio with zero benchmark."""
        returns = np.array([0.01, -0.005, 0.02, 0.015])
        benchmark = np.array([0.0, 0.0, 0.0, 0.0])

        ir = compute_information_ratio(returns, benchmark)

        # Should be same as sharpe ratio with zero benchmark
        assert isinstance(ir, float)

    def test_sortino_ratio_computation(self):
        """Test Sortino ratio computation."""
        returns = np.array([0.01, -0.005, 0.02, 0.015, -0.01])

        sortino = compute_sortino_ratio(returns)

        assert isinstance(sortino, float)

    def test_sortino_ratio_all_positive(self):
        """Test Sortino ratio with all positive returns."""
        returns = np.array([0.01, 0.02, 0.03, 0.015])

        sortino = compute_sortino_ratio(returns)

        # All positive returns should give infinite sortino
        assert sortino == float("inf")

    def test_sortino_ratio_all_negative(self):
        """Test Sortino ratio with all negative returns."""
        returns = np.array([-0.01, -0.02, -0.03, -0.015])

        sortino = compute_sortino_ratio(returns)

        # All negative should give 0 or negative
        assert sortino <= 0.0


class TestComputeAllMetrics:
    """Tests for compute_all_metrics function."""

    def test_compute_all_metrics(self):
        """Test computing all metrics with valid inputs."""
        metrics = compute_all_metrics(
            y_true=[1, 0, 1, 1, 0],
            y_pred=[1, 0, 1, 0, 0],
            y_proba=[0.9, 0.2, 0.8, 0.4, 0.3],
            returns=[0.01, -0.005, 0.02, 0.015, -0.01],
            trades=[100, -50, 150, 80, -30],
            benchmark_returns=[0.008, -0.003, 0.015, 0.01, -0.008],
        )

        assert isinstance(metrics, EvaluationMetrics)
        assert 0.0 <= metrics.accuracy <= 1.0
        assert 0.0 <= metrics.precision <= 1.0
        assert 0.0 <= metrics.recall <= 1.0
        assert 0.0 <= metrics.f1 <= 1.0
        assert 0.0 <= metrics.auc_roc <= 1.0

    def test_compute_all_metrics_default_benchmark(self):
        """Test compute_all_metrics with default benchmark."""
        metrics = compute_all_metrics(
            y_true=[1, 0, 1],
            y_pred=[1, 0, 1],
            y_proba=[0.9, 0.1, 0.8],
            returns=[0.01, -0.005, 0.02],
            trades=[100, -50, 150],
        )

        assert isinstance(metrics, EvaluationMetrics)
        # Should use zero returns as default benchmark
        assert (
            metrics.information_ratio >= 0.0
        )  # Can be non-zero with default benchmark


class TestEvaluationMetrics:
    """Tests for EvaluationMetrics dataclass."""

    def test_evaluation_metrics_creation(self):
        """Test creating EvaluationMetrics with all values."""
        metrics = EvaluationMetrics(
            accuracy=0.95,
            precision=0.90,
            recall=0.88,
            f1=0.89,
            auc_roc=0.92,
            log_loss=0.15,
            calibration_error=0.05,
            brier_score=0.08,
            sharpe_ratio=1.5,
            max_drawdown=0.12,
            win_rate=0.65,
            profit_factor=2.5,
            expectancy=75.0,
            kelly_fraction=0.35,
            information_ratio=1.2,
            sortino_ratio=2.0,
        )

        assert metrics.accuracy == 0.95
        assert metrics.precision == 0.90
        assert metrics.f1 == 0.89

    def test_evaluation_metrics_to_dict(self):
        """Test converting EvaluationMetrics to dictionary."""
        metrics = EvaluationMetrics(
            accuracy=0.95,
            precision=0.90,
            recall=0.88,
            f1=0.89,
            auc_roc=0.92,
            log_loss=0.15,
            calibration_error=0.05,
            brier_score=0.08,
            sharpe_ratio=1.5,
            max_drawdown=0.12,
            win_rate=0.65,
            profit_factor=2.5,
            expectancy=75.0,
            kelly_fraction=0.35,
            information_ratio=1.2,
            sortino_ratio=2.0,
        )

        data = metrics.to_dict()

        assert len(data) == 16
        assert "accuracy" in data
        assert "precision" in data
        assert "recall" in data
        assert "f1" in data
        assert "auc_roc" in data
        assert "log_loss" in data
        assert "calibration_error" in data
        assert "brier_score" in data
        assert "sharpe_ratio" in data
        assert "max_drawdown" in data
        assert "win_rate" in data
        assert "profit_factor" in data
        assert "expectancy" in data
        assert "kelly_fraction" in data
        assert "information_ratio" in data
        assert "sortino_ratio" in data

    def test_evaluation_metrics_from_dict(self):
        """Test creating EvaluationMetrics from dictionary."""
        data = {
            "accuracy": 0.95,
            "precision": 0.90,
            "recall": 0.88,
            "f1": 0.89,
            "auc_roc": 0.92,
            "log_loss": 0.15,
            "calibration_error": 0.05,
            "brier_score": 0.08,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.12,
            "win_rate": 0.65,
            "profit_factor": 2.5,
            "expectancy": 75.0,
            "kelly_fraction": 0.35,
            "information_ratio": 1.2,
            "sortino_ratio": 2.0,
        }

        metrics = EvaluationMetrics.from_dict(data)

        assert metrics.accuracy == 0.95
        assert metrics.precision == 0.90
        assert metrics.f1 == 0.89

    def test_evaluation_metrics_roundtrip(self):
        """Test roundtrip serialization of EvaluationMetrics."""
        original = EvaluationMetrics(
            accuracy=0.95,
            precision=0.90,
            recall=0.88,
            f1=0.89,
            auc_roc=0.92,
            log_loss=0.15,
            calibration_error=0.05,
            brier_score=0.08,
            sharpe_ratio=1.5,
            max_drawdown=0.12,
            win_rate=0.65,
            profit_factor=2.5,
            expectancy=75.0,
            kelly_fraction=0.35,
            information_ratio=1.2,
            sortino_ratio=2.0,
        )

        restored = EvaluationMetrics.from_dict(original.to_dict())

        assert restored.accuracy == original.accuracy
        assert restored.precision == original.precision
        assert restored.f1 == original.f1


class TestMetricConfigs:
    """Tests for METRIC_CONFIGS dictionary."""

    def test_metric_configs_complete(self):
        """Test that METRIC_CONFIGS has exactly 16 entries."""
        assert len(METRIC_CONFIGS) == 16

    def test_metric_configs_all_categories(self):
        """Test that all metric categories are represented."""
        categories = {config.category for config in METRIC_CONFIGS.values()}

        assert MetricCategory.CLASSIFICATION in categories
        assert MetricCategory.CALIBRATION in categories
        assert MetricCategory.TRADING in categories

    def test_metric_configs_accuracy(self):
        """Test accuracy metric config."""
        config = METRIC_CONFIGS["accuracy"]

        assert config.name == "accuracy"
        assert config.category == MetricCategory.CLASSIFICATION
        assert config.higher_is_better is True
        assert config.min_value == 0.0
        assert config.max_value == 1.0

    def test_metric_configs_log_loss(self):
        """Test log_loss metric config (lower is better)."""
        config = METRIC_CONFIGS["log_loss"]

        assert config.name == "log_loss"
        assert config.higher_is_better is False


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_edge_case_empty_arrays(self):
        """Test that empty arrays return 0.0."""
        empty = np.array([])

        assert compute_accuracy(empty, empty) == 0.0
        assert compute_precision(empty, empty) == 0.0
        assert compute_recall(empty, empty) == 0.0
        assert compute_f1(empty, empty) == 0.0
        assert compute_auc_roc(empty, empty) == 0.0
        assert compute_log_loss(empty, empty) == 0.0
        assert compute_calibration_error(empty, empty) == 0.0
        assert compute_brier_score(empty, empty) == 0.0
        assert compute_sharpe_ratio(empty) == 0.0
        assert compute_max_drawdown(empty) == 0.0
        assert compute_win_rate(empty) == 0.0
        assert compute_profit_factor(empty) == 0.0
        assert compute_expectancy(empty) == 0.0
        assert compute_sortino_ratio(empty) == 0.0

    def test_edge_case_all_correct(self):
        """Test that all correct predictions give accuracy=1.0."""
        predictions = np.array([1, 0, 1, 1, 0, 1])
        labels = np.array([1, 0, 1, 1, 0, 1])

        accuracy = compute_accuracy(predictions, labels)

        assert accuracy == 1.0

    def test_edge_case_single_element(self):
        """Test metrics with single element arrays."""
        pred = np.array([1])
        label = np.array([1])
        proba = np.array([0.9])
        trade = np.array([100])
        ret = np.array([0.01])

        assert compute_accuracy(pred, label) == 1.0
        assert compute_precision(pred, label) == 1.0  # TP=1, FP=0 -> precision=1.0
        assert compute_recall(pred, label) == 1.0  # TP=1, FN=0 -> recall=1.0
        assert compute_f1(pred, label) == 1.0  # F1 = 2*1*1/(1+1) = 1.0
        assert compute_auc_roc(proba, label) == 0.5
        assert compute_win_rate(trade) == 1.0
        assert compute_profit_factor(trade) == float("inf")
        assert compute_expectancy(trade) == 100.0

    def test_edge_case_mismatched_lengths(self):
        """Test that mismatched array lengths return 0.0."""
        pred1 = np.array([1, 0, 1])
        pred2 = np.array([1, 0])

        assert compute_accuracy(pred1, pred2) == 0.0
        assert compute_precision(pred1, pred2) == 0.0
        assert compute_recall(pred1, pred2) == 0.0
        assert compute_f1(pred1, pred2) == 0.0

    def test_edge_case_all_same_prediction(self):
        """Test when all predictions are the same."""
        predictions = np.array([1, 1, 1, 1])
        labels = np.array([1, 0, 1, 0])

        precision = compute_precision(predictions, labels)
        recall = compute_recall(predictions, labels)

        # TP=2, FP=2 -> precision = 0.5
        # TP=2, FN=0 -> recall = 1.0
        assert precision == 0.5
        assert recall == 1.0
