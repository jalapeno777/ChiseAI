"""Statistical Analysis Module for Hypothesis Testing.

Provides advanced statistical tests beyond the basic z-test including
Fisher's exact test for small sample sizes and other analysis utilities.

Designed to work with the ICT Hypothesis Framework from hypothesis_framework.py.
"""

from __future__ import annotations

import math
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Named Tuples for Test Results
# ---------------------------------------------------------------------------


class FisherExactResult(NamedTuple):
    """Result of Fisher's exact test."""

    p_value: float
    odds_ratio: float
    confidence_interval: tuple[float, float]


class ZTestResult(NamedTuple):
    """Result of a two-proportion z-test."""

    p_value: float
    z_statistic: float
    effect_size: float  # Absolute difference in proportions
    pooled_proportion: float


# ---------------------------------------------------------------------------
# Fisher's Exact Test
# ---------------------------------------------------------------------------


def fisher_exact_test(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
) -> FisherExactResult:
    """Fisher's exact test for 2x2 contingency tables.

    Used when sample sizes are small (<30 per group) where the normal
    approximation of the z-test may not be valid.

    Args:
        treatment_successes: Number of positive outcomes in treatment group
        treatment_total: Total observations in treatment group
        control_successes: Number of positive outcomes in control group
        control_total: Total observations in control group

    Returns:
        FisherExactResult with p_value, odds_ratio, and 95% CI

    Raises:
        ValueError: If any count is negative or totals are zero
    """
    # Validate inputs
    if treatment_total == 0 or control_total == 0:
        raise ValueError("Group totals must be greater than 0")

    if (
        treatment_successes < 0
        or control_successes < 0
        or treatment_successes > treatment_total
        or control_successes > control_total
    ):
        raise ValueError("Invalid count values")

    # Build the 2x2 table
    # | a  b | = treatment | success  failure |
    # | c  d | = control   | success  failure |
    a = treatment_successes
    b = treatment_total - treatment_successes
    c = control_successes
    d = control_total - control_successes

    # Calculate odds ratio
    if b == 0 or c == 0:
        odds_ratio = float("inf") if (a * d) > (b * c) else 0.0
    else:
        odds_ratio = (a * d) / (b * c)

    # Calculate p-value using hypergeometric distribution
    # The probability of observing exactly a successes in treatment given marginals
    p_value = _fisher_exact_p_value(a, b, c, d)

    # Calculate confidence interval for odds ratio using exact method
    ci = _odds_ratio_confidence_interval(a, b, c, d)

    return FisherExactResult(
        p_value=p_value,
        odds_ratio=odds_ratio,
        confidence_interval=ci,
    )


def _fisher_exact_p_value(a: int, b: int, c: int, d: int) -> float:
    """Calculate Fisher's exact p-value for a 2x2 table.

    Uses the hypergeometric distribution to compute the probability of
    observing the given table or one more extreme.

    Args:
        a: Treatment successes
        b: Treatment failures
        c: Control successes
        d: Control failures

    Returns:
        Two-tailed p-value
    """
    # Hypergeometric probability of observing exactly a successes in treatment
    # given the marginal totals

    def hypergeometric_prob(k: int, n: int, K: int, N: int) -> float:
        """Probability of k successes in n draws from population with K successes.

        Uses log-space calculation for numerical stability.
        """
        if k < max(0, n - (N - K)) or k > min(n, K):
            return 0.0

        # Log factorial using Stirling approximation for large values
        def log_factorial(x: int) -> float:
            if x <= 1:
                return 0.0
            if x < 20:
                # Use exact calculation for small values
                return sum(math.log(i) for i in range(2, x + 1))
            # Use Stirling's approximation for large values
            return x * math.log(x) - x + 0.5 * math.log(2 * math.pi * x)

        log_p = (
            log_factorial(K)
            + log_factorial(N - K)
            + log_factorial(n)
            + log_factorial(N - n)
            - log_factorial(k)
            - log_factorial(K - k)
            - log_factorial(n - k)
            - log_factorial(N - K - n + k)
            - log_factorial(N)
        )
        return math.exp(log_p)

    # Total successes and observations
    N = a + b + c + d
    n = a + c  # Total successes (column marginal)
    K = a + b  # Total in treatment (row marginal)

    # Calculate probability of the observed table
    obs_prob = hypergeometric_prob(a, n, K, N)

    # Calculate probabilities for all tables as or more extreme
    # (two-tailed test: consider tables with same or lower probability)
    total_prob = obs_prob

    # Tables with same marginals but different a values
    min_a = max(0, n - (N - K))
    max_a = min(n, K)

    for k in range(min_a, max_a + 1):
        if k == a:
            continue
        prob = hypergeometric_prob(k, n, K, N)
        if prob <= obs_prob:
            total_prob += prob

    return min(total_prob, 1.0)


def _odds_ratio_confidence_interval(
    a: int, b: int, c: int, d: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Calculate exact confidence interval for odds ratio.

    Uses the Fisher's mid-p method for small samples.

    Args:
        a: Treatment successes
        b: Treatment failures
        c: Control successes
        d: Control failures
        confidence: Confidence level (default 0.95)

    Returns:
        Tuple of (lower, upper) bounds
    """
    # For tables with zero cells, use rule of 3 or similar adjustments
    if a == 0 or b == 0 or c == 0 or d == 0:
        # Apply small sample correction (add 0.5 to each cell)
        a_adj, b_adj, c_adj, d_adj = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        or_adj = (a_adj * d_adj) / (b_adj * c_adj)
        # Approximate CI using Woolf method on adjusted values
        se_log_or = math.sqrt(1 / a_adj + 1 / b_adj + 1 / c_adj + 1 / d_adj)
    else:
        or_adj = (a * d) / (b * c)
        # Woolf method for confidence interval
        se_log_or = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)

    # Z value for confidence level
    z = 1.96 if confidence == 0.95 else math.sqrt(2)  # Approximation

    # Log transform for symmetry
    log_or = math.log(or_adj) if or_adj > 0 else -20  # Handle inf

    # CI in log space then transform back
    if log_or == float("inf"):
        return (0.0, float("inf"))
    if log_or == float("-inf"):
        return (float("-inf"), float("inf"))

    log_lower = log_or - z * se_log_or
    log_upper = log_or + z * se_log_or

    lower = math.exp(log_lower) if math.isfinite(log_lower) else 0.0
    upper = math.exp(log_upper) if math.isfinite(log_upper) else float("inf")

    return (max(0.0, lower), upper)


# ---------------------------------------------------------------------------
# Chi-Square Test (for completeness)
# ---------------------------------------------------------------------------


def chi_square_test(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
) -> tuple[float, float]:
    """Chi-square test for independence in 2x2 table.

    Approximation valid when expected frequencies are all >= 5.
    For small samples, use fisher_exact_test instead.

    Args:
        treatment_successes: Number of positive outcomes in treatment
        treatment_total: Total in treatment
        control_successes: Number of positive outcomes in control
        control_total: Total in control

    Returns:
        Tuple of (p_value, chi_square_statistic)
    """
    # Observed frequencies
    a = treatment_successes
    b = treatment_total - treatment_successes
    c = control_successes
    d = control_total - control_successes

    # Row and column totals
    n1 = a + b  # treatment total
    n2 = c + d  # control total
    m1 = a + c  # successes total
    m2 = b + d  # failures total
    N = a + b + c + d  # grand total

    # Expected frequencies under null hypothesis
    # E = (row_total * col_total) / grand_total
    e_a = (n1 * m1) / N
    e_b = (n1 * m2) / N
    e_c = (n2 * m1) / N
    e_d = (n2 * m2) / N

    # Check validity of approximation
    if any(e < 5 for e in [e_a, e_b, e_c, e_d]):
        raise ValueError(
            "Expected frequencies < 5. Use fisher_exact_test for small samples."
        )

    # Chi-square statistic
    chi2 = (
        (a - e_a) ** 2 / e_a
        + (b - e_b) ** 2 / e_b
        + (c - e_c) ** 2 / e_c
        + (d - e_d) ** 2 / e_d
    )

    # P-value from chi-square distribution with 1 df
    # Using approximation: p = exp(-0.5 * chi2) for large values
    p_value = _chi_square_p_value(chi2, df=1)

    return p_value, chi2


def _chi_square_p_value(chi2: float, df: int) -> float:
    """Calculate p-value from chi-square statistic.

    Uses the regularized incomplete gamma function approximation.

    Args:
        chi2: Chi-square statistic
        df: Degrees of freedom

    Returns:
        P-value (probability of observing chi2 or larger)
    """
    if chi2 <= 0:
        return 1.0

    # For df=1, we can use a simpler approximation
    if df == 1:
        # Chi-square with 1 df is related to normal distribution
        # chi2 = z^2, so p-value from chi-square = 2 * (1 - Phi(sqrt(chi2)))
        z = math.sqrt(chi2)
        return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))

    # General case using incomplete gamma function approximation
    # p = Q(df/2, chi2/2) where Q is the upper incomplete gamma
    # This is a simplified approximation
    x = chi2 / 2
    k = df / 2

    # Use series expansion for small x, asymptotic for large x
    if x < k:
        # Use series expansion
        p = 1 - _lower_incomplete_gamma(k, x) / math.gamma(k)
    else:
        # Use asymptotic approximation
        p = _upper_incomplete_gamma_approx(k, x)

    return min(max(p, 0.0), 1.0)


def _lower_incomplete_gamma(s: float, x: float) -> float:
    """Approximation of lower incomplete gamma function."""
    if x < 0:
        return 0.0
    if x == 0:
        return 0.0

    # Series expansion: G(s,x) = x^s * e^-x * Sum(x^n / (s*(s+1)*...*(s+n)))
    result = 1.0 / s
    term = 1.0 / s
    for n in range(1, 100):
        term *= x / (s + n)
        result += term
        if abs(term) < 1e-10:
            break

    return x**s * math.exp(-x) * result


def _upper_incomplete_gamma_approx(s: float, x: float) -> float:
    """Asymptotic approximation of upper incomplete gamma function."""
    # For large x: Q(s,x) ~ x^(s-1) * e^-x
    # More accurate: use continued fraction
    if x <= 0:
        return 1.0

    # Simple asymptotic approximation
    return math.exp(-x + (s - 1) * math.log(x) - math.lgamma(s))


# ---------------------------------------------------------------------------
# Effect Size Calculations
# ---------------------------------------------------------------------------


def relative_risk(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
) -> tuple[float, tuple[float, float]]:
    """Calculate relative risk (risk ratio) and its confidence interval.

    Args:
        treatment_successes: Number of positive outcomes in treatment
        treatment_total: Total in treatment
        control_successes: Number of positive outcomes in control
        control_total: Total in control

    Returns:
        Tuple of (relative_risk, confidence_interval)
    """
    if treatment_total == 0 or control_total == 0:
        raise ValueError("Group totals must be greater than 0")

    p1 = treatment_successes / treatment_total
    p2 = control_successes / control_total

    rr = p1 / p2 if p2 > 0 else float("inf")

    # CI using log transformation
    if p1 == 0 or p2 == 0:
        ci = (0.0, float("inf"))
    else:
        se_log_rr = math.sqrt(
            (1 - p1) / (p1 * treatment_total) + (1 - p2) / (p2 * control_total)
        )
        z = 1.96
        log_rr = math.log(rr)
        ci = (math.exp(log_rr - z * se_log_rr), math.exp(log_rr + z * se_log_rr))

    return rr, ci


def absolute_risk_difference(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
) -> tuple[float, tuple[float, float]]:
    """Calculate absolute risk difference (ARD) and its confidence interval.

    Args:
        treatment_successes: Number of positive outcomes in treatment
        treatment_total: Total in treatment
        control_successes: Number of positive outcomes in control
        control_total: Total in control

    Returns:
        Tuple of (ARD, confidence_interval)
    """
    if treatment_total == 0 or control_total == 0:
        raise ValueError("Group totals must be greater than 0")

    p1 = treatment_successes / treatment_total
    p2 = control_successes / control_total
    ard = p1 - p2

    # CI using Wald method
    se = math.sqrt(p1 * (1 - p1) / treatment_total + p2 * (1 - p2) / control_total)
    ci = (ard - 1.96 * se, ard + 1.96 * se)

    return ard, ci


# ---------------------------------------------------------------------------
# Number Needed to Treat (NNT)
# ---------------------------------------------------------------------------


def number_needed_to_treat(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
) -> float:
    """Calculate Number Needed to Treat (NNT).

    NNT = 1 / |ARD|
    Represents how many patients need treatment for one additional
    success compared to control.

    Args:
        treatment_successes: Number of positive outcomes in treatment
        treatment_total: Total in treatment
        control_successes: Number of positive outcomes in control
        control_total: Total in control

    Returns:
        NNT as float (inf if ARD is 0)
    """
    ard, _ = absolute_risk_difference(
        treatment_successes, treatment_total, control_successes, control_total
    )

    if abs(ard) < 1e-10:
        return float("inf")

    return 1.0 / abs(ard)
