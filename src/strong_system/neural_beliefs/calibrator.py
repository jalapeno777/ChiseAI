"""Confidence Calibrator with Bayesian updating.

Provides Bayesian updating for confidence scores, evidence accumulation,
uncertainty quantification, and calibration metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from src.strong_system.belief_embeddings import ValidationError

if TYPE_CHECKING:
    from .belief import NeuralBelief


@dataclass
class ReliabilityBin:
    """A bin for reliability diagram computation.

    Tracks predictions and outcomes within a confidence interval
    to assess calibration.

    Attributes:
        lower_bound: Lower confidence bound of this bin
        upper_bound: Upper confidence bound of this bin
        count: Number of samples in this bin
        correct_count: Number of correct predictions
        avg_confidence: Average confidence in this bin
    """

    lower_bound: float
    upper_bound: float
    count: int = 0
    correct_count: int = 0
    sum_confidence: float = field(default=0.0, repr=False)

    def add_sample(self, confidence: float, correct: bool) -> None:
        """Add a sample to this bin.

        Args:
            confidence: Predicted confidence
            correct: Whether the prediction was correct
        """
        self.count += 1
        self.sum_confidence += confidence
        if correct:
            self.correct_count += 1

    @property
    def avg_confidence(self) -> float:
        """Average confidence in this bin."""
        if self.count == 0:
            return (self.lower_bound + self.upper_bound) / 2
        return self.sum_confidence / self.count

    @property
    def accuracy(self) -> float:
        """Accuracy (fraction correct) in this bin."""
        if self.count == 0:
            return 0.0
        return self.correct_count / self.count

    @property
    def calibration_gap(self) -> float:
        """Difference between confidence and accuracy."""
        return self.avg_confidence - self.accuracy

    def to_dict(self) -> dict[str, Any]:
        """Convert bin to dictionary."""
        return {
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "count": self.count,
            "correct_count": self.correct_count,
            "avg_confidence": self.avg_confidence,
            "accuracy": self.accuracy,
            "calibration_gap": self.calibration_gap,
        }


@dataclass
class CalibrationMetrics:
    """Metrics for confidence calibration assessment.

    Attributes:
        ece: Expected Calibration Error
        mce: Maximum Calibration Error
        reliability_bins: List of reliability bins
        num_samples: Total number of samples evaluated
        timestamp: When metrics were computed
    """

    ece: float
    mce: float
    reliability_bins: list[ReliabilityBin]
    num_samples: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "ece": self.ece,
            "mce": self.mce,
            "reliability_bins": [b.to_dict() for b in self.reliability_bins],
            "num_samples": self.num_samples,
            "timestamp": self.timestamp.isoformat(),
        }


class BetaDistribution:
    """Beta distribution for Bayesian confidence updating.

    The Beta distribution is the conjugate prior for Bernoulli/binomial
    likelihood, making it ideal for modeling confidence in binary outcomes.

    Attributes:
        alpha: Shape parameter (pseudo-count of successes)
        beta: Shape parameter (pseudo-count of failures)
    """

    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        """Initialize Beta distribution.

        Args:
            alpha: Success pseudo-count (default 1.0 = uniform prior)
            beta: Failure pseudo-count (default 1.0 = uniform prior)
        """
        if alpha <= 0 or beta <= 0:
            raise ValidationError("Alpha and beta must be positive")

        self.alpha = float(alpha)
        self.beta = float(beta)

    @property
    def mean(self) -> float:
        """Mean of the Beta distribution."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        """Variance of the Beta distribution."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total**2 * (total + 1))

    @property
    def mode(self) -> float:
        """Mode of the Beta distribution."""
        if self.alpha <= 1 and self.beta <= 1:
            # Bimodal or uniform, return mean
            return self.mean
        if self.alpha < 1:
            return 0.0
        if self.beta < 1:
            return 1.0
        return (self.alpha - 1) / (self.alpha + self.beta - 2)

    def update(self, successes: int, failures: int) -> BetaDistribution:
        """Update distribution with new evidence.

        Args:
            successes: Number of successful outcomes
            failures: Number of failed outcomes

        Returns:
            New Beta distribution with updated parameters
        """
        return BetaDistribution(
            alpha=self.alpha + successes,
            beta=self.beta + failures,
        )

    def pdf(self, x: float) -> float:
        """Probability density function at x.

        Args:
            x: Value in [0, 1]

        Returns:
            PDF value
        """
        from scipy.special import beta as beta_func

        if x < 0 or x > 1:
            return 0.0

        # Beta PDF: x^(alpha-1) * (1-x)^(beta-1) / B(alpha, beta)
        numerator = (x ** (self.alpha - 1)) * ((1 - x) ** (self.beta - 1))
        denominator = beta_func(self.alpha, self.beta)

        return float(numerator / denominator)

    def sample(self, size: int = 1) -> np.ndarray:
        """Sample from the Beta distribution.

        Args:
            size: Number of samples

        Returns:
            Array of samples
        """
        return np.random.beta(self.alpha, self.beta, size=size)

    def credible_interval(self, level: float = 0.95) -> tuple[float, float]:
        """Compute credible interval.

        Args:
            level: Credible level (e.g., 0.95 for 95%)

        Returns:
            Tuple of (lower, upper) bounds
        """
        from scipy import stats

        alpha = (1 - level) / 2
        lower = stats.beta.ppf(alpha, self.alpha, self.beta)
        upper = stats.beta.ppf(1 - alpha, self.alpha, self.beta)

        return float(lower), float(upper)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alpha": self.alpha,
            "beta": self.beta,
            "mean": self.mean,
            "variance": self.variance,
        }


class ConfidenceCalibrator:
    """Calibrator for belief confidence scores using Bayesian updating.

    Maintains prior/posterior distributions for confidence and updates
    them based on observed evidence. Provides calibration metrics and
    uncertainty quantification.

    Attributes:
        prior: Prior Beta distribution
        posterior: Current posterior distribution
        evidence_history: History of evidence updates
        temperature: Temperature parameter for confidence sharpening
    """

    def __init__(
        self,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
        temperature: float = 1.0,
    ):
        """Initialize the calibrator.

        Args:
            prior_alpha: Alpha parameter for prior Beta distribution
            prior_beta: Beta parameter for prior Beta distribution
            temperature: Temperature for confidence sharpening (<1 sharpens, >1 softens)
        """
        self.prior = BetaDistribution(prior_alpha, prior_beta)
        self.posterior = BetaDistribution(prior_alpha, prior_beta)
        self.evidence_history: list[dict[str, Any]] = []
        self.temperature = temperature
        self._prediction_history: list[tuple[float, bool]] = []  # (confidence, correct)

    def update_evidence(
        self,
        successes: int,
        failures: int,
        timestamp: datetime | None = None,
    ) -> float:
        """Update confidence with new evidence.

        Args:
            successes: Number of successful outcomes
            failures: Number of failed outcomes
            timestamp: Optional timestamp for the update

        Returns:
            Updated confidence score (posterior mean)
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Update posterior
        self.posterior = self.posterior.update(successes, failures)

        # Record evidence
        self.evidence_history.append(
            {
                "successes": successes,
                "failures": failures,
                "timestamp": timestamp.isoformat(),
                "posterior_mean": self.posterior.mean,
            }
        )

        return self.get_confidence()

    def get_confidence(self, temperature: float | None = None) -> float:
        """Get calibrated confidence score.

        Args:
            temperature: Optional override for temperature parameter

        Returns:
            Calibrated confidence in [0, 1]
        """
        temp = temperature if temperature is not None else self.temperature

        # Apply temperature scaling
        raw_confidence = self.posterior.mean

        if temp == 1.0:
            return raw_confidence

        # Temperature scaling: sharpen or soften confidence
        # Use logit space for temperature scaling
        # logit(p) = log(p / (1-p))
        # scaled = logit(p) / temperature
        # confidence = sigmoid(scaled)

        # Avoid log(0) issues
        eps = 1e-10
        p = np.clip(raw_confidence, eps, 1 - eps)

        logit = np.log(p / (1 - p))
        scaled_logit = logit / temp

        confidence = 1 / (1 + np.exp(-scaled_logit))
        return float(np.clip(confidence, 0.0, 1.0))

    def get_uncertainty(self) -> float:
        """Get uncertainty estimate.

        Returns:
            Standard deviation of posterior (higher = more uncertain)
        """
        return np.sqrt(self.posterior.variance)

    def get_confidence_interval(self, level: float = 0.95) -> tuple[float, float]:
        """Get credible interval for confidence.

        Args:
            level: Credible level (default 0.95)

        Returns:
            Tuple of (lower, upper) bounds
        """
        return self.posterior.credible_interval(level)

    def record_prediction(self, confidence: float, correct: bool) -> None:
        """Record a prediction for calibration assessment.

        Args:
            confidence: Predicted confidence
            correct: Whether the prediction was correct
        """
        self._prediction_history.append((float(confidence), bool(correct)))

    def compute_calibration_metrics(
        self,
        num_bins: int = 10,
    ) -> CalibrationMetrics:
        """Compute calibration metrics.

        Calculates Expected Calibration Error (ECE) and Maximum Calibration
        Error (MCE) using reliability diagrams.

        Args:
            num_bins: Number of bins for reliability diagram

        Returns:
            CalibrationMetrics object
        """
        if not self._prediction_history:
            # Return empty metrics
            bins = [
                ReliabilityBin(i / num_bins, (i + 1) / num_bins)
                for i in range(num_bins)
            ]
            return CalibrationMetrics(
                ece=0.0,
                mce=0.0,
                reliability_bins=bins,
                num_samples=0,
            )

        # Create bins
        bins = [
            ReliabilityBin(i / num_bins, (i + 1) / num_bins) for i in range(num_bins)
        ]

        # Assign predictions to bins
        for confidence, correct in self._prediction_history:
            bin_idx = min(int(confidence * num_bins), num_bins - 1)
            bins[bin_idx].add_sample(confidence, correct)

        # Compute ECE and MCE
        total_samples = len(self._prediction_history)
        ece = 0.0
        mce = 0.0

        for bin_obj in bins:
            if bin_obj.count > 0:
                weight = bin_obj.count / total_samples
                gap = abs(bin_obj.calibration_gap)
                ece += weight * gap
                mce = max(mce, gap)

        return CalibrationMetrics(
            ece=float(ece),
            mce=float(mce),
            reliability_bins=bins,
            num_samples=total_samples,
        )

    def reset(self) -> None:
        """Reset to prior distribution."""
        self.posterior = BetaDistribution(self.prior.alpha, self.prior.beta)
        self.evidence_history.clear()
        self._prediction_history.clear()

    def calibrate_belief(self, belief: NeuralBelief) -> None:
        """Apply calibration to a neural belief.

        Updates the belief's confidence using the calibrated posterior mean.

        Args:
            belief: The NeuralBelief to calibrate
        """
        belief.confidence = self.get_confidence()

    def to_dict(self) -> dict[str, Any]:
        """Convert calibrator to dictionary."""
        return {
            "prior": self.prior.to_dict(),
            "posterior": self.posterior.to_dict(),
            "evidence_history": self.evidence_history,
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfidenceCalibrator:
        """Create calibrator from dictionary."""
        prior_data = data.get("prior", {})
        calibrator = cls(
            prior_alpha=prior_data.get("alpha", 1.0),
            prior_beta=prior_data.get("beta", 1.0),
            temperature=data.get("temperature", 1.0),
        )

        # Restore posterior
        posterior_data = data.get("posterior", {})
        calibrator.posterior = BetaDistribution(
            alpha=posterior_data.get("alpha", calibrator.prior.alpha),
            beta=posterior_data.get("beta", calibrator.prior.beta),
        )

        # Restore evidence history
        calibrator.evidence_history = list(data.get("evidence_history", []))

        return calibrator
