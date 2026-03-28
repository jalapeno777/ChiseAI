"""Shared fixtures for brain_eval tests."""

import numpy as np
import pytest

from ml.evaluation.brain_eval import BrainEvalClient, BrainEvalConfig, DataSourceType


@pytest.fixture
def synthetic_config():
    """Create a synthetic data BrainEval config."""
    return BrainEvalConfig(
        data_source=DataSourceType.SYNTHETIC,
        n_samples=500,
        random_seed=42,
    )


@pytest.fixture
def brain_eval_client(synthetic_config):
    """Create a BrainEvalClient with synthetic config."""
    return BrainEvalClient(config=synthetic_config)


@pytest.fixture
def sample_evaluation_data():
    """Create sample evaluation data arrays."""
    rng = np.random.default_rng(42)
    n = 200
    y_true = rng.choice([0, 1], size=n, p=[0.4, 0.6])
    noise = rng.random(n) < 0.25
    y_pred = y_true.copy()
    y_pred[noise] = 1 - y_pred[noise]
    base_proba = y_true.astype(float) * 0.7 + 0.3
    noise_proba = rng.normal(0, 0.1, n)
    y_proba = np.clip(base_proba + noise_proba, 0.05, 0.95)
    returns = rng.normal(0.001, 0.02, n)
    trades = rng.lognormal(mean=2, sigma=1.5, size=n) - 3
    neg_mask = rng.random(n) < 0.4
    trades[neg_mask] = -trades[neg_mask]
    benchmark_returns = returns * 0.8 + rng.normal(0, 0.005, n)

    return {
        "y_true": y_true,
        "y_pred": y_pred,
        "y_proba": y_proba,
        "returns": returns,
        "trades": trades,
        "benchmark_returns": benchmark_returns,
    }
