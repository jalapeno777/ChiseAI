"""ICT Hypothesis Framework for Statistical Validation.

Defines the hypothesis testing framework for evaluating whether ICT signals
provide statistically significant alpha over a non-ICT baseline.

Framework Design:
- H0 (Null): ICT signals do NOT add statistically significant alpha
- H1 (Alternative): ICT signals add alpha with p<0.05, effect size >2%

Control: Non-ICT baseline signals (random entry, fixed rules, etc.)
Treatment: ICT-enhanced signals (CVD, FVG, Order Block)

Power Analysis:
- Minimum 100 signals required for 80% power at alpha=0.05
- Effect size: Cohen's h = 0.5 (medium effect)
- Early stopping: p>0.3 after 50 signals triggers evaluation pause
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class SignalProtocol(Protocol):
    """Minimal protocol for a trading signal."""

    @property
    def timestamp(self) -> int: ...


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HypothesisDecision(Enum):
    """Outcome of a hypothesis test."""

    CONTINUE = "continue"
    ACCEPT_H0 = "accept_h0"
    REJECT_H0 = "reject_h0"
    INCONCLUSIVE = "inconclusive"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectSizeThresholds:
    """Thresholds for interpreting effect size magnitude."""

    negligible: float = 0.02  # 2% - minimum meaningful alpha
    small: float = 0.10
    medium: float = 0.25
    large: float = 0.40


@dataclass(frozen=True)
class TestParameters:
    """Parameters for the hypothesis test."""

    alpha: float = 0.05
    power: float = 0.80
    minimum_signals: int = 100
    early_stop_signals: int = 50
    early_stop_p_threshold: float = 0.30
    effect_size: float = 0.50  # Cohen's h for medium effect


@dataclass
class SignalResult:
    """Result of a single signal evaluation."""

    signal_id: str
    timestamp: int
    treatment_return: float  # Return when ICT signal was active
    control_return: float  # Return from baseline/control
    alpha: float = 0.0  # treatment_return - control_return

    def __post_init__(self) -> None:
        self.alpha = self.treatment_return - self.control_return


@dataclass
class HypothesisTestResult:
    """Result of a hypothesis test evaluation."""

    decision: HypothesisDecision
    p_value: float
    effect_size: float
    signals_analyzed: int
    treatment_mean: float
    control_mean: float
    confidence_interval: tuple[float, float]
    power_achieved: float
    messages: list[str] = field(default_factory=list)

    @property
    def has_significant_alpha(self) -> bool:
        return (
            self.decision == HypothesisDecision.REJECT_H0
            and self.effect_size >= EffectSizeThresholds.negligible
        )


# ---------------------------------------------------------------------------
# Power Analysis
# ---------------------------------------------------------------------------


def _power_to_z_beta(power: float) -> float:
    """Convert statistical power to z-beta critical value.

    z_beta is the z-value such that power = Φ(z_beta).
    Therefore: z_beta = Φ^{-1}(power)

    Standard z_beta values:
    - power=0.80 → z_beta≈0.8416
    - power=0.90 → z_beta≈1.2816
    - power=0.95 → z_beta≈1.6449

    Args:
        power: Desired power (e.g., 0.80 for 80% power)

    Returns:
        z-beta critical value (always positive)
    """
    # Use pre-computed values for common power levels for accuracy
    # For other values, use approximation
    if abs(power - 0.80) < 1e-6:
        return 0.8416212335729142
    if abs(power - 0.90) < 1e-6:
        return 1.2815515655446004
    if abs(power - 0.95) < 1e-6:
        return 1.6448536269514722

    # General approximation using Newton's method
    # Start with rough estimate
    if power < 0.5:
        z = -2.0
    else:
        z = 0.5

    # Refine using Newton-Raphson: z_new = z - (Φ(z) - p) / φ(z)
    for _ in range(10):
        phi_z = _normal_cdf(z)
        diff = phi_z - power
        if abs(diff) < 1e-10:
            break
        # pdf of standard normal = φ(z) = (1/√(2π)) * exp(-z²/2)
        pdf_z = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        z = z - diff / pdf_z

    return z


def _normal_inverse_cdf(p: float) -> float:
    """Inverse of standard normal CDF using lookup table and interpolation.

    Args:
        p: Probability (0 < p < 1)

    Returns:
        z value such that Φ(z) = p
    """
    if p <= 0.0:
        return -float("inf")
    if p >= 1.0:
        return float("inf")
    if p == 0.5:
        return 0.0

    # Use symmetry: Φ(-z) = 1 - Φ(z)
    if p < 0.5:
        p = 1.0 - p
        sign = -1.0
    else:
        sign = 1.0

    # Lookup table for common p values and their z-scores
    # Based on known values of the inverse normal CDF
    table = [
        (0.50, 0.000000),
        (0.55, 0.125661),
        (0.60, 0.253347),
        (0.65, 0.385320),
        (0.70, 0.524400),
        (0.75, 0.674490),
        (0.80, 0.841621),
        (0.85, 1.036433),
        (0.90, 1.281552),
        (0.925, 1.439531),
        (0.95, 1.644854),
        (0.975, 1.959964),
        (0.99, 2.326348),
        (0.995, 2.575829),
        (0.9995, 3.290527),
    ]

    # Find the two entries to interpolate between
    for i in range(len(table) - 1):
        p_lo, z_lo = table[i]
        p_hi, z_hi = table[i + 1]
        if p_lo <= p <= p_hi:
            # Linear interpolation
            if p_hi == p_lo:
                z = z_lo
            else:
                z = z_lo + (p - p_lo) * (z_hi - z_lo) / (p_hi - p_lo)
            return sign * z

    # If p is beyond table range, use extrapolation
    p_lo, z_lo = table[-2]
    p_hi, z_hi = table[-1]
    z = z_hi + (p - p_hi) * (z_hi - z_lo) / (p_hi - p_lo)
    return sign * z


def calculate_minimum_sample_size(
    alpha: float = 0.05,
    power: float = 0.80,
    effect_size: float = 0.50,
) -> int:
    """Calculate minimum sample size using normal approximation.

    Uses the formula for comparing two proportions:
    n = 2 * ((z_alpha + z_beta) / Cohen_h)^2

    Where:
    - z_alpha: critical value for significance level
    - z_beta: critical value for power
    - Cohen_h: effect size

    Args:
        alpha: Significance level (default 0.05)
        power: Desired statistical power (default 0.80)
        effect_size: Cohen's h effect size (default 0.50 medium)

    Returns:
        Minimum number of signals required per group
    """
    # Standard normal critical value for alpha (two-tailed)
    z_alpha = 1.96  # Two-tailed at alpha=0.05

    # Convert power to z_beta
    z_beta = _power_to_z_beta(power)

    # Sample size formula for two proportions
    numerator = 2 * ((z_alpha + z_beta) ** 2)
    denominator = effect_size**2

    n = math.ceil(numerator / denominator)
    return n


def calculate_achieved_power(
    sample_size: int,
    alpha: float = 0.05,
    effect_size: float = 0.50,
) -> float:
    """Calculate achieved power for a given sample size.

    Args:
        sample_size: Number of signals per group
        alpha: Significance level
        effect_size: Cohen's h effect size

    Returns:
        Achieved statistical power (0 to 1)
    """
    z_alpha = 1.96
    z_beta = effect_size * math.sqrt(sample_size / 2) - z_alpha
    power = _normal_cdf(z_beta)
    return power


def _normal_cdf(z: float) -> float:
    """Approximate normal CDF using error function."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Effect Size Calculation
# ---------------------------------------------------------------------------


def cohens_h(proportion1: float, proportion2: float) -> float:
    """Calculate Cohen's h effect size between two proportions.

    Cohen's h = 2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))

    Args:
        proportion1: First proportion (e.g., treatment success rate)
        proportion2: Second proportion (e.g., control success rate)

    Returns:
        Cohen's h effect size
    """
    if not (0 < proportion1 < 1) or not (0 < proportion2 < 1):
        raise ValueError("Proportions must be between 0 and 1 exclusive")
    return 2 * math.asin(math.sqrt(proportion1)) - 2 * math.asin(math.sqrt(proportion2))


def effect_size_interpretation(effect_size: float) -> str:
    """Interpret Cohen's h effect size magnitude.

    Args:
        effect_size: Calculated Cohen's h

    Returns:
        Human-readable interpretation
    """
    abs_effect = abs(effect_size)
    if abs_effect <= EffectSizeThresholds.negligible:
        return "negligible"
    if abs_effect <= EffectSizeThresholds.small:
        return "small"
    if abs_effect <= EffectSizeThresholds.medium:
        return "medium"
    if abs_effect <= EffectSizeThresholds.large:
        return "large"
    return "very large"


# ---------------------------------------------------------------------------
# Statistical Tests
# ---------------------------------------------------------------------------


def two_proportion_z_test(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Two-proportion z-test for comparing success rates.

    Args:
        treatment_successes: Number of positive outcomes in treatment
        treatment_total: Total signals in treatment group
        control_successes: Number of positive outcomes in control
        control_total: Total signals in control group
        alpha: Significance level

    Returns:
        Tuple of (p_value, z_statistic)
    """
    if treatment_total == 0 or control_total == 0:
        raise ValueError("Group totals must be greater than 0")

    p1 = treatment_successes / treatment_total
    p2 = control_successes / control_total
    p_pooled = (treatment_successes + control_successes) / (
        treatment_total + control_total
    )

    se = math.sqrt(
        p_pooled * (1 - p_pooled) * (1 / treatment_total + 1 / control_total)
    )
    if se == 0:
        return (1.0, 0.0)

    z_stat = (p1 - p2) / se
    p_value = 2 * (1 - _normal_cdf(abs(z_stat)))

    return p_value, z_stat


def calculate_confidence_interval(
    treatment_mean: float,
    control_mean: float,
    treatment_std: float,
    control_std: float,
    treatment_n: int,
    control_n: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate confidence interval for the difference in means.

    Args:
        treatment_mean: Mean return of treatment group
        control_mean: Mean return of control group
        treatment_std: Standard deviation of treatment group
        control_std: Standard deviation of control group
        treatment_n: Size of treatment group
        control_n: Size of control group
        confidence: Confidence level (default 0.95)

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if treatment_n == 0 or control_n == 0:
        raise ValueError("Group sizes must be greater than 0")

    mean_diff = treatment_mean - control_mean
    se = math.sqrt((treatment_std**2 / treatment_n) + (control_std**2 / control_n))
    if se == 0:
        return (mean_diff, mean_diff)

    # Derive z-critical from confidence level
    alpha = 1 - confidence
    z_critical = _normal_inverse_cdf(1 - alpha / 2)
    margin = z_critical * se

    return (mean_diff - margin, mean_diff + margin)


# ---------------------------------------------------------------------------
# Early Stopping Rules
# ---------------------------------------------------------------------------


def check_early_stopping(
    signals_analyzed: int,
    p_value: float,
    parameters: TestParameters,
) -> tuple[bool, str]:
    """Check if early stopping criteria are met.

    Early stopping triggers when:
    - At least early_stop_signals have been analyzed
    - p_value > early_stop_p_threshold (no significance trending)

    Args:
        signals_analyzed: Number of signals analyzed so far
        p_value: Current p-value from the test
        parameters: TestParameters instance

    Returns:
        Tuple of (should_stop, reason)
    """
    if signals_analyzed < parameters.early_stop_signals:
        return False, "Insufficient signals for early stopping evaluation"

    if p_value > parameters.early_stop_p_threshold:
        return True, (
            f"Early stopping triggered: p={p_value:.4f} > "
            f"{parameters.early_stop_p_threshold} after "
            f"{signals_analyzed} signals. Evidence insufficient to reject H0."
        )

    return False, "Continue collecting signals"


# ---------------------------------------------------------------------------
# Hypothesis Framework
# ---------------------------------------------------------------------------


class ICTHypothesisFramework:
    """Framework for evaluating ICT signal alpha using hypothesis testing.

    Design:
    - H0 (Null): ICT signals do NOT add statistically significant alpha
    - H1 (Alternative): ICT signals add alpha with p<0.05, effect size >2%

    The framework supports:
    - Sequential analysis with early stopping rules
    - Power analysis for sample size determination
    - Effect size calculation and interpretation
    - Confidence interval estimation
    """

    def __init__(
        self,
        parameters: TestParameters | None = None,
        thresholds: EffectSizeThresholds | None = None,
    ) -> None:
        """Initialize the hypothesis framework.

        Args:
            parameters: TestParameters for the hypothesis test
            thresholds: EffectSizeThresholds for interpretation
        """
        self.parameters = parameters or TestParameters()
        self.thresholds = thresholds or EffectSizeThresholds()
        self._results: list[SignalResult] = []

    @property
    def signals_analyzed(self) -> int:
        """Number of signals analyzed so far."""
        return len(self._results)

    @property
    def minimum_signals_required(self) -> int:
        """Minimum signals needed for full power."""
        return calculate_minimum_sample_size(
            alpha=self.parameters.alpha,
            power=self.parameters.power,
            effect_size=self.parameters.effect_size,
        )

    def add_result(self, result: SignalResult) -> None:
        """Add a signal evaluation result to the framework.

        Args:
            result: SignalResult from a single signal evaluation
        """
        self._results.append(result)

    def add_results_batch(self, results: list[SignalResult]) -> None:
        """Add multiple signal evaluation results.

        Args:
            results: List of SignalResult instances
        """
        self._results.extend(results)

    def clear_results(self) -> None:
        """Clear all stored results."""
        self._results.clear()

    def evaluate(
        self,
        positive_threshold: float = 0.0,
    ) -> HypothesisTestResult:
        """Evaluate the hypothesis using collected signal results.

        Args:
            positive_threshold: Return threshold for considering a signal "positive"
                (e.g., 0.0 means any positive return counts as success)

        Returns:
            HypothesisTestResult with decision and statistics
        """
        messages: list[str] = []
        n = len(self._results)

        if n == 0:
            return HypothesisTestResult(
                decision=HypothesisDecision.INCONCLUSIVE,
                p_value=1.0,
                effect_size=0.0,
                signals_analyzed=0,
                treatment_mean=0.0,
                control_mean=0.0,
                confidence_interval=(0.0, 0.0),
                power_achieved=0.0,
                messages=["No signals analyzed yet"],
            )

        # Calculate returns
        treatment_returns = [r.treatment_return for r in self._results]
        control_returns = [r.control_return for r in self._results]

        treatment_mean = sum(treatment_returns) / n
        control_mean = sum(control_returns) / n

        # Calculate standard deviations
        treatment_var = sum((r - treatment_mean) ** 2 for r in treatment_returns) / (
            n - 1
        )
        control_var = sum((r - control_mean) ** 2 for r in control_returns) / (n - 1)
        treatment_std = math.sqrt(treatment_var) if treatment_var > 0 else 0.0
        control_std = math.sqrt(control_var) if control_var > 0 else 0.0

        # Count successes (returns above threshold)
        treatment_successes = sum(
            1 for r in treatment_returns if r > positive_threshold
        )
        control_successes = sum(1 for r in control_returns if r > positive_threshold)

        # Statistical test
        p_value, z_stat = two_proportion_z_test(
            treatment_successes,
            n,
            control_successes,
            n,
            alpha=self.parameters.alpha,
        )

        # Effect size
        p1 = treatment_successes / n if n > 0 else 0.0
        p2 = control_successes / n if n > 0 else 0.0
        effect_size = (
            cohens_h(p1, p2) if p1 > 0 and p2 > 0 and p1 < 1 and p2 < 1 else 0.0
        )

        # Confidence interval
        ci = calculate_confidence_interval(
            treatment_mean,
            control_mean,
            treatment_std,
            control_std,
            n,
            n,
        )

        # Power achieved
        power = calculate_achieved_power(
            n,
            alpha=self.parameters.alpha,
            effect_size=(
                effect_size if abs(effect_size) > 0 else self.parameters.effect_size
            ),
        )

        # Decision logic
        decision = self._make_decision(
            p_value,
            effect_size,
            n,
            messages,
        )

        # Early stopping check
        should_stop, stop_reason = check_early_stopping(n, p_value, self.parameters)
        if should_stop:
            messages.append(stop_reason)

        messages.insert(
            0,
            f"Analyzed {n} signals: "
            f"treatment_mean={treatment_mean:.4f}, control_mean={control_mean:.4f}",
        )

        return HypothesisTestResult(
            decision=decision,
            p_value=p_value,
            effect_size=effect_size,
            signals_analyzed=n,
            treatment_mean=treatment_mean,
            control_mean=control_mean,
            confidence_interval=ci,
            power_achieved=power,
            messages=messages,
        )

    def _make_decision(
        self,
        p_value: float,
        effect_size: float,
        signals: int,
        messages: list[str],
    ) -> HypothesisDecision:
        """Make the hypothesis decision based on test results."""
        # Check early stopping first - if triggered, accept H0 with evidence
        should_stop, stop_reason = check_early_stopping(
            signals, p_value, self.parameters
        )
        if should_stop:
            messages.append(stop_reason)
            return HypothesisDecision.ACCEPT_H0

        # Insufficient signals for full evaluation
        if signals < self.parameters.minimum_signals:
            messages.append(
                f"Insufficient signals: {signals} < {self.parameters.minimum_signals} minimum"
            )
            return HypothesisDecision.CONTINUE

        # Check significance
        if p_value >= self.parameters.alpha:
            messages.append(
                f"Failed to reject H0: p={p_value:.4f} >= alpha={self.parameters.alpha}"
            )
            return HypothesisDecision.ACCEPT_H0

        # Significant but check effect size
        if abs(effect_size) < self.thresholds.negligible:
            messages.append(
                f"Significant but negligible effect: h={effect_size:.4f} < "
                f"{self.thresholds.negligible} threshold"
            )
            return HypothesisDecision.INCONCLUSIVE

        # Significant with meaningful effect
        interpretation = effect_size_interpretation(effect_size)
        messages.append(
            f"Rejected H0: p={p_value:.4f} < {self.parameters.alpha}, "
            f"effect_size={effect_size:.4f} ({interpretation})"
        )
        return HypothesisDecision.REJECT_H0

    def generate_report(self) -> str:
        """Generate a human-readable status report."""
        result = self.evaluate()
        min_signals = self.minimum_signals_required

        lines = [
            "ICT Hypothesis Framework Status Report",
            "=" * 50,
            f"Signals analyzed: {self.signals_analyzed}",
            f"Minimum required: {min_signals}",
            f"Power target: {self.parameters.power:.0%}",
            "",
            "Test Parameters:",
            f"  Alpha: {self.parameters.alpha}",
            f"  Effect size (Cohen's h): {self.parameters.effect_size}",
            f"  Early stop after {self.parameters.early_stop_signals} signals if p > {self.parameters.early_stop_p_threshold}",
            "",
            "Current Results:",
            f"  Decision: {result.decision.value}",
            f"  P-value: {result.p_value:.4f}",
            f"  Effect size (Cohen's h): {result.effect_size:.4f}",
            f"  Effect interpretation: {effect_size_interpretation(result.effect_size)}",
            f"  Power achieved: {result.power_achieved:.2%}",
            f"  95% CI for mean diff: [{result.confidence_interval[0]:.4f}, {result.confidence_interval[1]:.4f}]",
            "",
        ]

        for msg in result.messages:
            lines.append(f"  {msg}")

        return "\n".join(lines)
