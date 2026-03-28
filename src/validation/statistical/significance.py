"""Significance Testing Module for ICT Hypothesis Validation.

Provides decision logic, multiple comparison corrections, and MDE calculations
for the ICT hypothesis testing framework.

Decision Output Format:
- Confirm: p < 0.05 AND effect_size > 0.02 (MDE)
- Partial: p < 0.05 AND 0 < effect_size <= 0.02
- Null: p >= 0.05
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from validation.statistical.hypothesis_framework import (
    two_proportion_z_test,
)

# ---------------------------------------------------------------------------
# Decision Enum
# ---------------------------------------------------------------------------


class SignificanceDecision(Enum):
    """Outcome decision for hypothesis test results.

    Format: "Confirm" / "Partial" / "Null"
    - Confirm: Significant AND meaningful effect (effect_size > MDE)
    - Partial: Significant BUT negligible effect (0 < effect_size <= MDE)
    - Null: Not significant (p >= alpha)
    """

    CONFIRM = "Confirm"
    PARTIAL = "Partial"
    NULL = "Null"
    INSUFFICIENT_SAMPLES = "InsufficientSamples"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MDEParameters:
    """Parameters for Minimum Detectable Effect calculation."""

    mde: float = 0.02  # 2% minimum detectable effect
    alpha: float = 0.05
    power: float = 0.80


@dataclass(frozen=True)
class MultipleComparisonsConfig:
    """Configuration for multiple comparisons correction."""

    num_comparisons: int = 1
    method: str = "bonferroni"  # bonferroni, holm, benjamini-hochberg


@dataclass
class SignificanceTestResult:
    """Complete result of significance testing with decision."""

    decision: SignificanceDecision
    p_value: float
    effect_size: float
    mde: float
    alpha: float
    alpha_corrected: float | None  # None if no correction applied
    num_comparisons: int
    method_used: str
    test_type: str  # z_test, fisher_exact, chi_square
    z_statistic: float | None = None
    odds_ratio: float | None = None
    confidence_interval: tuple[float, float] | None = None
    messages: list[str] | None = None

    @property
    def is_significant(self) -> bool:
        """True if p_value is below the corrected alpha."""
        return self.p_value < (self.alpha_corrected or self.alpha)

    @property
    def exceeds_mde(self) -> bool:
        """True if effect size exceeds the MDE threshold."""
        return abs(self.effect_size) > self.mde


# ---------------------------------------------------------------------------
# MDE (Minimum Detectable Effect) Calculation
# ---------------------------------------------------------------------------


def calculate_mde(
    alpha: float = 0.05,
    power: float = 0.80,
    sample_size: int | None = None,
    ratio: float = 1.0,
) -> float:
    """Calculate Minimum Detectable Effect as proportion.

    MDE is the smallest effect size that the test can detect with given
    power and significance level.

    For two-proportion z-test:
    MDE = (z_alpha/2 + z_beta) * sqrt(p*(1-p)*(1/n1 + 1/n2))

    Where:
    - z_alpha/2: critical z for significance (1.96 at alpha=0.05)
    - z_beta: critical z for power (0.84 at power=0.80)
    - p: baseline proportion (assumed 0.5 if not known)
    - n1, n2: sample sizes

    Args:
        alpha: Significance level (default 0.05)
        power: Desired power (default 0.80)
        sample_size: Optional per-group sample size (if None, returns formula result)
        ratio: Ratio of n2/n1 for unequal allocation (default 1.0)

    Returns:
        MDE as a proportion (e.g., 0.02 for 2%)
    """
    # Z critical values
    z_alpha_2 = 1.96  # Two-tailed at alpha=0.05
    z_beta = _power_to_z(power)

    # If no sample size given, return the formula constant
    # MDE = (z_alpha/2 + z_beta) * sqrt(2*p*(1-p))  when n1=n2
    if sample_size is None:
        # Using p=0.5 for most conservative estimate
        p = 0.5
        constant = (z_alpha_2 + z_beta) * math.sqrt(2 * p * (1 - p))
        return constant

    # With sample size, calculate actual MDE
    p = 0.5  # Conservative baseline
    n1 = sample_size
    n2 = int(sample_size * ratio)

    mde = (z_alpha_2 + z_beta) * math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return mde


def verify_mde_2percent(
    alpha: float = 0.05,
    power: float = 0.80,
    baseline_proportion: float = 0.5,
) -> tuple[bool, float, int]:
    """Verify that 2% MDE is achievable with reasonable sample size.

    Args:
        alpha: Significance level (default 0.05)
        power: Desired power (default 0.80)
        baseline_proportion: Expected baseline success rate

    Returns:
        Tuple of (is_verified, actual_mde, required_n_per_group)
    """
    target_mde = 0.02  # 2%

    # Z critical values
    z_alpha_2 = 1.96
    z_beta = _power_to_z(power)

    # Solve for n: MDE = (z_alpha/2 + z_beta) * sqrt(p*(1-p)*(2/n))
    # Rearranging: n = ((z_alpha/2 + z_beta)^2 * p*(1-p) * 2) / MDE^2
    p = baseline_proportion
    numerator = ((z_alpha_2 + z_beta) ** 2) * p * (1 - p) * 2
    denominator = target_mde**2

    n = math.ceil(numerator / denominator)

    # Verify
    actual_mde = calculate_mde(alpha=alpha, power=power, sample_size=n)
    is_verified = actual_mde <= target_mde

    return is_verified, actual_mde, n


def _power_to_z(power: float) -> float:
    """Convert power to z-beta critical value.

    Args:
        power: Power level (e.g., 0.80 for 80%)

    Returns:
        Z-beta value
    """
    # Pre-computed for common power levels
    if abs(power - 0.80) < 1e-6:
        return 0.8416212335729142
    if abs(power - 0.90) < 1e-6:
        return 1.2815515655446004
    if abs(power - 0.95) < 1e-6:
        return 1.6448536269514722

    # General approximation
    if power <= 0.5:
        return -2.0

    z = 0.5
    for _ in range(20):
        phi_z = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        diff = phi_z - power
        if abs(diff) < 1e-10:
            break
        pdf_z = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        z = z - diff / pdf_z

    return z


# ---------------------------------------------------------------------------
# Multiple Comparisons Correction (Bonferroni, Holm, BH)
# ---------------------------------------------------------------------------


def bonferroni_correction(
    alpha: float,
    num_comparisons: int,
) -> float:
    """Apply Bonferroni correction for multiple comparisons.

    Args:
        alpha: Original significance level
        num_comparisons: Number of comparisons/tests performed

    Returns:
        Corrected alpha threshold

    Raises:
        ValueError: If num_comparisons < 1
    """
    if num_comparisons < 1:
        raise ValueError("num_comparisons must be >= 1")
    if num_comparisons == 1:
        return alpha

    return alpha / num_comparisons


def holm_correction(
    p_values: list[float],
    alpha: float,
) -> list[bool]:
    """Apply Holm-Bonferroni correction for strong control of family-wise error.

    Args:
        p_values: List of uncorrected p-values
        alpha: Original significance level

    Returns:
        List of booleans indicating which null hypotheses are rejected
    """
    if not p_values:
        return []

    n = len(p_values)
    sorted_indices = sorted(range(n), key=lambda i: p_values[i])

    rejected = [False] * n

    for i, idx in enumerate(sorted_indices):
        # Holm critical value: alpha / (n - i)
        threshold = alpha / (n - i)
        if p_values[idx] <= threshold:
            rejected[idx] = True
        else:
            # Once we fail to reject, all subsequent tests also fail
            break

    return rejected


def benjamini_hochberg_correction(
    p_values: list[float],
    alpha: float,
) -> list[bool]:
    """Apply Benjamini-Hochberg FDR correction.

    Controls false discovery rate rather than family-wise error rate.
    More powerful than Bonferroni when many true nulls exist.

    Args:
        p_values: List of uncorrected p-values
        alpha: Desired FDR (e.g., 0.05 for 5% FDR)

    Returns:
        List of booleans indicating which null hypotheses are rejected
    """
    if not p_values:
        return []

    n = len(p_values)
    sorted_indices = sorted(range(n), key=lambda i: p_values[i])

    rejected = [False] * n

    for i, idx in enumerate(sorted_indices):
        # BH critical value: (i+1)/n * alpha
        threshold = (i + 1) / n * alpha
        if p_values[idx] <= threshold:
            rejected[idx] = True
        else:
            # Continue checking but don't break (BH is sequential)
            pass

    # Find the largest k where p[k] <= k/n * alpha
    # Then reject all with rank <= k
    max_reject = 0
    for i, idx in enumerate(sorted_indices):
        threshold = (i + 1) / n * alpha
        if p_values[idx] <= threshold:
            max_reject = i + 1

    for i in range(max_reject):
        rejected[sorted_indices[i]] = True

    return rejected


def apply_multiple_comparisons_correction(
    alpha: float,
    num_comparisons: int,
    method: str = "bonferroni",
) -> float:
    """Apply multiple comparisons correction.

    Args:
        alpha: Original significance level
        num_comparisons: Number of comparisons
        method: Correction method ('bonferroni', 'holm', 'benjamini_hochberg')

    Returns:
        Corrected alpha value

    Note:
        For holm and benjamini_hochberg, this returns the alpha threshold
        for the most significant p-value. Use holm_correction or
        benjamini_hochberg_correction for full per-test decisions.
    """
    if method.lower() == "bonferroni":
        return bonferroni_correction(alpha, num_comparisons)
    elif method.lower() in ("holm", "holm-bonferroni"):
        # Holm uses same threshold formula as Bonferroni for the first test
        return alpha / num_comparisons
    elif method.lower() in ("bh", "benjamini-hochberg", "fdr"):
        # BH doesn't have a single threshold; return nominal for reference
        return alpha
    else:
        raise ValueError(f"Unknown correction method: {method}")


# ---------------------------------------------------------------------------
# Significance Test Protocol
# ---------------------------------------------------------------------------


class SignificanceTestProtocol(Protocol):
    """Protocol for significance test functions."""

    def __call__(
        self,
        treatment_successes: int,
        treatment_total: int,
        control_successes: int,
        control_total: int,
        alpha: float,
    ) -> tuple[float, float]:
        """Execute significance test.

        Returns:
            Tuple of (p_value, test_statistic)
        """
        ...


# ---------------------------------------------------------------------------
# Decision Logic
# ---------------------------------------------------------------------------


def make_decision(
    p_value: float,
    effect_size: float,
    alpha: float,
    mde: float = 0.02,
    num_comparisons: int = 1,
    correction_method: str = "bonferroni",
) -> SignificanceDecision:
    """Make significance decision from test results.

    Decision Thresholds:
    - Confirm: p < alpha_corrected AND |effect_size| > mde
    - Partial: p < alpha_corrected AND 0 < |effect_size| <= mde
    - Null: p >= alpha_corrected

    Args:
        p_value: The p-value from the statistical test
        effect_size: The effect size (Cohen's h or proportion difference)
        alpha: Original significance level
        mde: Minimum Detectable Effect threshold (default 0.02 = 2%)
        num_comparisons: Number of comparisons for correction
        correction_method: Method for multiple comparisons correction

    Returns:
        SignificanceDecision enum value
    """
    # Apply multiple comparisons correction
    alpha_corrected = apply_multiple_comparisons_correction(
        alpha, num_comparisons, correction_method
    )

    # Decision logic
    if p_value >= alpha_corrected:
        return SignificanceDecision.NULL

    # p < alpha_corrected - check effect size and direction
    # effect_size > 0 means treatment is better than control (good)
    # effect_size <= 0 means treatment is worse or equal to control (bad)
    if effect_size <= 0:
        # Treatment is worse than or equal to control - reject the hypothesis
        return SignificanceDecision.NULL

    abs_effect = abs(effect_size)

    if abs_effect > mde:
        return SignificanceDecision.CONFIRM
    else:
        return SignificanceDecision.PARTIAL


def significance_test(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
    alpha: float = 0.05,
    mde: float = 0.02,
    num_comparisons: int = 1,
    correction_method: str = "bonferroni",
    use_fisher_exact: bool = False,
) -> SignificanceTestResult:
    """Perform complete significance test with decision.

    Combines z-test or Fisher exact test with multiple comparisons
    correction and MDE-based decision logic.

    Args:
        treatment_successes: Number of positive outcomes in treatment
        treatment_total: Total observations in treatment
        control_successes: Number of positive outcomes in control
        control_total: Total observations in control
        alpha: Significance level (default 0.05)
        mde: Minimum Detectable Effect (default 0.02 = 2%)
        num_comparisons: Number of comparisons for correction
        correction_method: 'bonferroni' (default) or 'holm'
        use_fisher_exact: Use Fisher exact test for small samples

    Returns:
        SignificanceTestResult with full details
    """
    messages = []

    # Determine which test to use
    small_sample = (treatment_total < 30 or control_total < 30) or (
        treatment_successes < 5
        or (treatment_total - treatment_successes) < 5
        or control_successes < 5
        or (control_total - control_successes) < 5
    )

    if use_fisher_exact or small_sample:
        # Use Fisher exact test
        from validation.statistical.analysis import fisher_exact_test

        result = fisher_exact_test(
            treatment_successes,
            treatment_total,
            control_successes,
            control_total,
        )
        p_value = result.p_value
        test_stat = 0.0  # Fisher doesn't have z-like statistic
        test_type = "fisher_exact"
        odds_ratio = result.odds_ratio
        ci = result.confidence_interval

        # Calculate effect size as proportion difference
        p1 = treatment_successes / treatment_total
        p2 = control_successes / control_total
        effect_size = p1 - p2
    else:
        # Use two-proportion z-test
        p_value, z_stat = two_proportion_z_test(
            treatment_successes,
            treatment_total,
            control_successes,
            control_total,
            alpha,
        )
        p1 = treatment_successes / treatment_total
        p2 = control_successes / control_total
        effect_size = p1 - p2  # Use raw difference as effect size

        test_stat = z_stat
        test_type = "z_test"
        odds_ratio = None
        ci = None

    # Apply multiple comparisons correction
    alpha_corrected = apply_multiple_comparisons_correction(
        alpha, num_comparisons, correction_method
    )

    # Make decision
    decision = make_decision(
        p_value,
        effect_size,
        alpha,
        mde,
        num_comparisons,
        correction_method,
    )

    # Build messages
    messages.append(f"Test type: {test_type}")
    messages.append(f"P-value: {p_value:.6f}")
    messages.append(f"Effect size: {effect_size:.6f}")
    messages.append(f"MDE threshold: {mde:.4f}")
    if num_comparisons > 1:
        messages.append(f"Bonferroni correction: {num_comparisons} comparisons")
        messages.append(f"Corrected alpha: {alpha_corrected:.6f}")
    messages.append(f"Decision: {decision.value}")

    return SignificanceTestResult(
        decision=decision,
        p_value=p_value,
        effect_size=effect_size,
        mde=mde,
        alpha=alpha,
        alpha_corrected=alpha_corrected if num_comparisons > 1 else None,
        num_comparisons=num_comparisons,
        method_used=correction_method,
        test_type=test_type,
        z_statistic=test_stat if test_type == "z_test" else None,
        odds_ratio=odds_ratio,
        confidence_interval=ci,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# Power Analysis Integration
# ---------------------------------------------------------------------------


def required_sample_size_for_mde(
    mde: float = 0.02,
    alpha: float = 0.05,
    power: float = 0.80,
    baseline_proportion: float = 0.5,
) -> int:
    """Calculate required sample size per group to detect MDE.

    Args:
        mde: Minimum Detectable Effect to detect
        alpha: Significance level
        power: Desired power
        baseline_proportion: Expected baseline success rate

    Returns:
        Required sample size per group
    """
    z_alpha_2 = 1.96
    z_beta = _power_to_z(power)

    p = baseline_proportion
    q = 1 - p

    # For equal group sizes: n = 2 * ((z_alpha/2 + z_beta)^2 * p * q) / MDE^2
    numerator = 2 * ((z_alpha_2 + z_beta) ** 2) * p * q
    denominator = mde**2

    return math.ceil(numerator / denominator)


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------


def generate_significance_report(result: SignificanceTestResult) -> str:
    """Generate human-readable significance test report.

    Args:
        result: SignificanceTestResult from significance_test

    Returns:
        Formatted report string
    """
    lines = [
        "ICT Significance Test Report",
        "=" * 50,
        f"Test Type: {result.test_type}",
        f"Decision: {result.decision.value}",
        "",
        "Test Results:",
        f"  P-value: {result.p_value:.6f}",
        f"  Effect Size: {result.effect_size:.6f} ({abs(result.effect_size) * 100:.2f}%)",
        f"  MDE Threshold: {result.mde:.4f} ({result.mde * 100:.2f}%)",
        "",
    ]

    if result.num_comparisons > 1:
        lines.extend(
            [
                "Multiple Comparisons Correction:",
                f"  Method: {result.method_used}",
                f"  Number of comparisons: {result.num_comparisons}",
                f"  Corrected alpha: {result.alpha_corrected:.6f}",
                "",
            ]
        )

    lines.extend(
        [
            "Interpretation:",
        ]
    )

    for msg in result.messages or []:
        lines.append(f"  {msg}")

    lines.append("")
    lines.append("Decision Criteria:")
    lines.append("  Confirm: p < alpha AND |effect| > MDE (2%)")
    lines.append("  Partial: p < alpha AND 0 < |effect| <= MDE (2%)")
    lines.append("  Null: p >= alpha")

    return "\n".join(lines)
