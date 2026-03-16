"""Tests for ConfidenceCalibrator."""

import numpy as np
import pytest
from src.strong_system.belief_embeddings import ValidationError
from src.strong_system.neural_beliefs import (
    BetaDistribution,
    CalibrationMetrics,
    ConfidenceCalibrator,
    NeuralBelief,
    ReliabilityBin,
)


class TestReliabilityBin:
    """Test cases for ReliabilityBin."""

    def test_init(self) -> None:
        """Test initialization."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.1)

        assert bin_obj.lower_bound == 0.0
        assert bin_obj.upper_bound == 0.1
        assert bin_obj.count == 0
        assert bin_obj.correct_count == 0

    def test_add_sample(self) -> None:
        """Test adding samples."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.1)

        bin_obj.add_sample(confidence=0.05, correct=True)
        bin_obj.add_sample(confidence=0.08, correct=False)

        assert bin_obj.count == 2
        assert bin_obj.correct_count == 1

    def test_avg_confidence(self) -> None:
        """Test average confidence calculation."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.1)

        bin_obj.add_sample(confidence=0.05, correct=True)
        bin_obj.add_sample(confidence=0.07, correct=True)

        assert bin_obj.avg_confidence == pytest.approx(0.06, abs=1e-10)

    def test_avg_confidence_empty(self) -> None:
        """Test average confidence for empty bin."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.2)

        # Should return midpoint when empty
        assert bin_obj.avg_confidence == 0.1

    def test_accuracy(self) -> None:
        """Test accuracy calculation."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.1)

        bin_obj.add_sample(confidence=0.05, correct=True)
        bin_obj.add_sample(confidence=0.06, correct=True)
        bin_obj.add_sample(confidence=0.07, correct=False)

        assert bin_obj.accuracy == pytest.approx(2 / 3, abs=1e-6)

    def test_accuracy_empty(self) -> None:
        """Test accuracy for empty bin."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.1)

        assert bin_obj.accuracy == 0.0

    def test_calibration_gap(self) -> None:
        """Test calibration gap calculation."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.1)

        bin_obj.add_sample(confidence=0.05, correct=True)
        bin_obj.add_sample(confidence=0.05, correct=False)

        # avg confidence = 0.05, accuracy = 0.5
        assert bin_obj.calibration_gap == pytest.approx(0.05 - 0.5, abs=1e-6)

    def test_to_dict(self) -> None:
        """Test serialization."""
        bin_obj = ReliabilityBin(lower_bound=0.0, upper_bound=0.1)
        bin_obj.add_sample(confidence=0.05, correct=True)

        data = bin_obj.to_dict()

        assert data["lower_bound"] == 0.0
        assert data["upper_bound"] == 0.1
        assert data["count"] == 1
        assert data["accuracy"] == 1.0


class TestBetaDistribution:
    """Test cases for BetaDistribution."""

    def test_init_default(self) -> None:
        """Test default initialization (uniform prior)."""
        dist = BetaDistribution()

        assert dist.alpha == 1.0
        assert dist.beta == 1.0

    def test_init_custom(self) -> None:
        """Test custom initialization."""
        dist = BetaDistribution(alpha=5.0, beta=3.0)

        assert dist.alpha == 5.0
        assert dist.beta == 3.0

    def test_init_invalid(self) -> None:
        """Test invalid parameters."""
        with pytest.raises(ValidationError):
            BetaDistribution(alpha=0.0, beta=1.0)

        with pytest.raises(ValidationError):
            BetaDistribution(alpha=1.0, beta=-1.0)

    def test_mean_uniform(self) -> None:
        """Test mean of uniform distribution."""
        dist = BetaDistribution(alpha=1.0, beta=1.0)

        assert dist.mean == 0.5

    def test_mean_skewed(self) -> None:
        """Test mean of skewed distribution."""
        dist = BetaDistribution(alpha=9.0, beta=1.0)

        assert dist.mean == 0.9

    def test_variance(self) -> None:
        """Test variance calculation."""
        dist = BetaDistribution(alpha=2.0, beta=2.0)

        # Variance of Beta(2,2) = (2*2) / ((4^2) * 5) = 4/80 = 0.05
        expected_variance = 0.05
        assert dist.variance == pytest.approx(expected_variance, abs=1e-6)

    def test_mode(self) -> None:
        """Test mode calculation."""
        dist = BetaDistribution(alpha=3.0, beta=2.0)

        # Mode = (alpha - 1) / (alpha + beta - 2) = 2/3
        assert dist.mode == pytest.approx(2 / 3, abs=1e-6)

    def test_mode_uniform(self) -> None:
        """Test mode of uniform distribution."""
        dist = BetaDistribution(alpha=1.0, beta=1.0)

        # Uniform has no mode, returns mean
        assert dist.mode == 0.5

    def test_update(self) -> None:
        """Test Bayesian updating."""
        prior = BetaDistribution(alpha=1.0, beta=1.0)

        # Observe 3 successes, 1 failure
        posterior = prior.update(successes=3, failures=1)

        assert posterior.alpha == 4.0
        assert posterior.beta == 2.0
        assert posterior.mean == pytest.approx(4 / 6, abs=1e-6)

    def test_pdf(self) -> None:
        """Test PDF calculation."""
        dist = BetaDistribution(alpha=2.0, beta=2.0)

        # PDF at center should be higher than at edges for Beta(2,2)
        pdf_center = dist.pdf(0.5)
        pdf_edge = dist.pdf(0.1)

        assert pdf_center > pdf_edge

    def test_pdf_out_of_range(self) -> None:
        """Test PDF outside [0, 1]."""
        dist = BetaDistribution()

        assert dist.pdf(-0.1) == 0.0
        assert dist.pdf(1.1) == 0.0

    def test_sample(self) -> None:
        """Test sampling."""
        dist = BetaDistribution(alpha=2.0, beta=2.0)

        samples = dist.sample(size=100)

        assert len(samples) == 100
        assert np.all(samples >= 0.0)
        assert np.all(samples <= 1.0)

    def test_credible_interval(self) -> None:
        """Test credible interval."""
        dist = BetaDistribution(alpha=5.0, beta=5.0)

        lower, upper = dist.credible_interval(level=0.95)

        assert 0.0 < lower < upper < 1.0
        # For symmetric Beta(5,5), interval should be roughly centered
        assert lower < 0.5 < upper

    def test_to_dict(self) -> None:
        """Test serialization."""
        dist = BetaDistribution(alpha=3.0, beta=2.0)

        data = dist.to_dict()

        assert data["alpha"] == 3.0
        assert data["beta"] == 2.0
        assert "mean" in data
        assert "variance" in data


class TestConfidenceCalibrator:
    """Test cases for ConfidenceCalibrator."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        calibrator = ConfidenceCalibrator()

        assert calibrator.prior.alpha == 1.0
        assert calibrator.prior.beta == 1.0
        assert calibrator.posterior.alpha == 1.0
        assert calibrator.temperature == 1.0

    def test_init_custom(self) -> None:
        """Test custom initialization."""
        calibrator = ConfidenceCalibrator(
            prior_alpha=5.0,
            prior_beta=3.0,
            temperature=0.5,
        )

        assert calibrator.prior.alpha == 5.0
        assert calibrator.prior.beta == 3.0
        assert calibrator.temperature == 0.5

    def test_update_evidence(self) -> None:
        """Test evidence updating."""
        calibrator = ConfidenceCalibrator()

        confidence = calibrator.update_evidence(successes=3, failures=1)

        assert calibrator.posterior.alpha == 4.0
        assert calibrator.posterior.beta == 2.0
        assert confidence == calibrator.posterior.mean
        assert len(calibrator.evidence_history) == 1

    def test_get_confidence(self) -> None:
        """Test getting calibrated confidence."""
        calibrator = ConfidenceCalibrator()
        calibrator.update_evidence(successes=7, failures=3)

        confidence = calibrator.get_confidence()

        # With 7 successes and 3 failures on uniform prior (1,1):
        # posterior is Beta(8, 4), mean = 8/12 = 0.666...
        assert confidence == pytest.approx(8 / 12, abs=1e-6)

    def test_get_confidence_with_temperature(self) -> None:
        """Test temperature scaling."""
        calibrator = ConfidenceCalibrator(temperature=0.5)
        calibrator.update_evidence(successes=6, failures=4)

        # Raw confidence = 7/12 = 0.583... (with uniform prior)
        # With temperature < 1, confidence should be sharpened (moved away from 0.5)
        raw_confidence = 7 / 12
        scaled_confidence = calibrator.get_confidence()

        assert scaled_confidence > raw_confidence

    def test_get_confidence_high_temperature(self) -> None:
        """Test temperature > 1 (softening)."""
        calibrator = ConfidenceCalibrator(temperature=2.0)
        calibrator.update_evidence(successes=7, failures=3)

        # Raw confidence = 0.8
        # With temperature > 1, confidence should be softened (moved toward 0.5)
        raw_confidence = 0.8
        scaled_confidence = calibrator.get_confidence()

        assert scaled_confidence < raw_confidence

    def test_get_uncertainty(self) -> None:
        """Test uncertainty calculation."""
        calibrator = ConfidenceCalibrator()

        # More evidence should reduce uncertainty
        calibrator.update_evidence(successes=10, failures=10)
        uncertainty_with_evidence = calibrator.get_uncertainty()

        calibrator2 = ConfidenceCalibrator()
        uncertainty_without_evidence = calibrator2.get_uncertainty()

        assert uncertainty_with_evidence < uncertainty_without_evidence

    def test_get_confidence_interval(self) -> None:
        """Test credible interval."""
        calibrator = ConfidenceCalibrator()
        calibrator.update_evidence(successes=5, failures=5)

        lower, upper = calibrator.get_confidence_interval(level=0.95)

        assert 0.0 < lower < upper < 1.0

    def test_record_prediction(self) -> None:
        """Test recording predictions."""
        calibrator = ConfidenceCalibrator()

        calibrator.record_prediction(confidence=0.8, correct=True)
        calibrator.record_prediction(confidence=0.6, correct=False)

        assert len(calibrator._prediction_history) == 2

    def test_compute_calibration_metrics(self) -> None:
        """Test calibration metrics computation."""
        calibrator = ConfidenceCalibrator()

        # Record some predictions
        for _ in range(5):
            calibrator.record_prediction(confidence=0.9, correct=True)
        for _ in range(5):
            calibrator.record_prediction(confidence=0.9, correct=False)

        metrics = calibrator.compute_calibration_metrics(num_bins=10)

        assert isinstance(metrics, CalibrationMetrics)
        assert metrics.num_samples == 10
        assert len(metrics.reliability_bins) == 10
        # ECE should be high since confidence (0.9) differs from accuracy (0.5)
        assert metrics.ece > 0.0

    def test_compute_calibration_metrics_empty(self) -> None:
        """Test metrics with no predictions."""
        calibrator = ConfidenceCalibrator()

        metrics = calibrator.compute_calibration_metrics()

        assert metrics.ece == 0.0
        assert metrics.mce == 0.0
        assert metrics.num_samples == 0

    def test_reset(self) -> None:
        """Test reset functionality."""
        calibrator = ConfidenceCalibrator()

        calibrator.update_evidence(successes=5, failures=3)
        calibrator.record_prediction(confidence=0.8, correct=True)

        calibrator.reset()

        assert calibrator.posterior.alpha == calibrator.prior.alpha
        assert calibrator.posterior.beta == calibrator.prior.beta
        assert len(calibrator.evidence_history) == 0
        assert len(calibrator._prediction_history) == 0

    def test_calibrate_belief(self) -> None:
        """Test calibrating a neural belief."""
        calibrator = ConfidenceCalibrator()
        calibrator.update_evidence(successes=8, failures=2)

        belief = NeuralBelief(vector=np.array([0.1, 0.2]), confidence=0.5)

        calibrator.calibrate_belief(belief)

        # Belief confidence should be updated to posterior mean
        # With uniform prior (1,1) + 8 successes + 2 failures = Beta(9, 3)
        # mean = 9/12 = 0.75
        assert belief.confidence == pytest.approx(0.75, abs=1e-6)

    def test_to_dict_from_dict(self) -> None:
        """Test serialization roundtrip."""
        calibrator = ConfidenceCalibrator(
            prior_alpha=2.0, prior_beta=3.0, temperature=0.8
        )
        calibrator.update_evidence(successes=5, failures=2)

        data = calibrator.to_dict()
        restored = ConfidenceCalibrator.from_dict(data)

        assert restored.prior.alpha == 2.0
        assert restored.prior.beta == 3.0
        assert restored.temperature == 0.8
        assert restored.posterior.alpha == calibrator.posterior.alpha
        assert len(restored.evidence_history) == 1

    def test_metrics_to_dict(self) -> None:
        """Test CalibrationMetrics serialization."""
        bins = [ReliabilityBin(0.0, 0.1), ReliabilityBin(0.1, 0.2)]
        metrics = CalibrationMetrics(
            ece=0.05,
            mce=0.1,
            reliability_bins=bins,
            num_samples=100,
        )

        data = metrics.to_dict()

        assert data["ece"] == 0.05
        assert data["mce"] == 0.1
        assert data["num_samples"] == 100
        assert len(data["reliability_bins"]) == 2
