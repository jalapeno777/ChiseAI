"""Statistical Analysis for A/B Tests.

Provides statistical significance testing with 95% confidence intervals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SignificanceResult:
    """Result of statistical significance test.

    Attributes:
        is_significant: Whether difference is statistically significant
        p_value: P-value of the test
        confidence_interval: Tuple of (lower, upper) bounds
        effect_size: Effect size (difference in means)
        control_mean: Control group mean
        treatment_mean: Treatment group mean
        control_std: Control group standard deviation
        treatment_std: Treatment group standard deviation
        control_n: Control group sample size
        treatment_n: Treatment group sample size
    """

    is_significant: bool
    p_value: float
    confidence_interval: tuple[float, float]
    effect_size: float
    control_mean: float
    treatment_mean: float
    control_std: float
    treatment_std: float
    control_n: int
    treatment_n: int

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_significant": self.is_significant,
            "p_value": round(self.p_value, 6),
            "confidence_interval": (
                round(self.confidence_interval[0], 4),
                round(self.confidence_interval[1], 4),
            ),
            "effect_size": round(self.effect_size, 4),
            "control_mean": round(self.control_mean, 4),
            "treatment_mean": round(self.treatment_mean, 4),
            "control_std": round(self.control_std, 4),
            "treatment_std": round(self.treatment_std, 4),
            "control_n": self.control_n,
            "treatment_n": self.treatment_n,
        }


class StatisticalAnalyzer:
    """Performs statistical analysis for A/B tests."""

    def __init__(self, confidence_level: float = 0.95) -> None:
        """Initialize analyzer.

        Args:
            confidence_level: Confidence level for intervals (default: 0.95)
        """
        if not (0 < confidence_level < 1):
            raise ValueError("confidence_level must be between 0 and 1")
        self.confidence_level = confidence_level
        self.alpha = round(1 - confidence_level, 10)

    def two_sample_t_test(
        self,
        control_values: list[float],
        treatment_values: list[float],
        equal_variance: bool = False,
    ) -> SignificanceResult:
        """Perform two-sample t-test for difference in means.

        Args:
            control_values: Values from control group
            treatment_values: Values from treatment group
            equal_variance: Whether to assume equal variance

        Returns:
            SignificanceResult with test results
        """
        if not control_values or not treatment_values:
            return SignificanceResult(
                is_significant=False,
                p_value=1.0,
                confidence_interval=(0.0, 0.0),
                effect_size=0.0,
                control_mean=0.0,
                treatment_mean=0.0,
                control_std=0.0,
                treatment_std=0.0,
                control_n=0,
                treatment_n=0,
            )

        # Calculate statistics
        control_mean = sum(control_values) / len(control_values)
        treatment_mean = sum(treatment_values) / len(treatment_values)

        control_var = self._variance(control_values, control_mean)
        treatment_var = self._variance(treatment_values, treatment_mean)

        control_std = math.sqrt(control_var)
        treatment_std = math.sqrt(treatment_var)

        control_n = len(control_values)
        treatment_n = len(treatment_values)

        # Calculate t-statistic
        if equal_variance:
            # Pooled variance
            pooled_var = (
                (control_n - 1) * control_var + (treatment_n - 1) * treatment_var
            ) / (control_n + treatment_n - 2)
            se_diff = math.sqrt(pooled_var * (1 / control_n + 1 / treatment_n))
            df = float(control_n + treatment_n - 2)
        else:
            # Welch's t-test (unequal variance)
            se_diff = math.sqrt(control_var / control_n + treatment_var / treatment_n)
            df = self._welch_df(control_var, control_n, treatment_var, treatment_n)

        if se_diff == 0:
            t_stat = 0.0
        else:
            t_stat = (treatment_mean - control_mean) / se_diff

        # Calculate p-value (two-tailed)
        p_value = 2 * (1 - self._t_cdf(abs(t_stat), df))

        # Calculate confidence interval
        margin_error = self._t_critical(df) * se_diff
        effect_size = treatment_mean - control_mean
        ci_lower = effect_size - margin_error
        ci_upper = effect_size + margin_error

        # Determine significance
        is_significant = p_value < self.alpha

        return SignificanceResult(
            is_significant=is_significant,
            p_value=p_value,
            confidence_interval=(ci_lower, ci_upper),
            effect_size=effect_size,
            control_mean=control_mean,
            treatment_mean=treatment_mean,
            control_std=control_std,
            treatment_std=treatment_std,
            control_n=control_n,
            treatment_n=treatment_n,
        )

    def chi_square_test(
        self,
        control_conversions: int,
        control_total: int,
        treatment_conversions: int,
        treatment_total: int,
    ) -> SignificanceResult:
        """Perform chi-square test for conversion rates.

        Args:
            control_conversions: Conversions in control group
            control_total: Total users in control group
            treatment_conversions: Conversions in treatment group
            treatment_total: Total users in treatment group

        Returns:
            SignificanceResult with test results
        """
        if control_total == 0 or treatment_total == 0:
            return SignificanceResult(
                is_significant=False,
                p_value=1.0,
                confidence_interval=(0.0, 0.0),
                effect_size=0.0,
                control_mean=0.0,
                treatment_mean=0.0,
                control_std=0.0,
                treatment_std=0.0,
                control_n=0,
                treatment_n=0,
            )

        # Calculate rates
        control_rate = control_conversions / control_total
        treatment_rate = treatment_conversions / treatment_total

        # Create contingency table
        # [[control_conversions, control_total - control_conversions],
        #  [treatment_conversions, treatment_total - treatment_conversions]]

        # Calculate chi-square statistic
        total_conversions = control_conversions + treatment_conversions
        total_non_conversions = (control_total - control_conversions) + (
            treatment_total - treatment_conversions
        )
        total_users = control_total + treatment_total

        # Expected values
        exp_control_conv = total_conversions * control_total / total_users
        exp_control_non_conv = total_non_conversions * control_total / total_users
        exp_treatment_conv = total_conversions * treatment_total / total_users
        exp_treatment_non_conv = total_non_conversions * treatment_total / total_users

        # Chi-square statistic
        chi_square = 0.0
        chi_square += (control_conversions - exp_control_conv) ** 2 / exp_control_conv
        chi_square += (
            control_total - control_conversions - exp_control_non_conv
        ) ** 2 / exp_control_non_conv
        chi_square += (
            treatment_conversions - exp_treatment_conv
        ) ** 2 / exp_treatment_conv
        chi_square += (
            treatment_total - treatment_conversions - exp_treatment_non_conv
        ) ** 2 / exp_treatment_non_conv

        # Degrees of freedom for 2x2 table
        df = 1

        # P-value
        p_value = 1 - self._chi_square_cdf(chi_square, df)

        # Effect size (difference in proportions)
        effect_size = treatment_rate - control_rate

        # Confidence interval for difference in proportions
        se_diff = math.sqrt(
            control_rate * (1 - control_rate) / control_total
            + treatment_rate * (1 - treatment_rate) / treatment_total
        )
        margin_error = self._z_critical() * se_diff
        ci_lower = effect_size - margin_error
        ci_upper = effect_size + margin_error

        # Determine significance
        is_significant = p_value < self.alpha

        return SignificanceResult(
            is_significant=is_significant,
            p_value=p_value,
            confidence_interval=(ci_lower, ci_upper),
            effect_size=effect_size,
            control_mean=control_rate,
            treatment_mean=treatment_rate,
            control_std=math.sqrt(control_rate * (1 - control_rate)),
            treatment_std=math.sqrt(treatment_rate * (1 - treatment_rate)),
            control_n=control_total,
            treatment_n=treatment_total,
        )

    def _variance(self, values: list[float], mean: float) -> float:
        """Calculate variance."""
        if len(values) <= 1:
            return 0.0
        return sum((x - mean) ** 2 for x in values) / (len(values) - 1)

    def _welch_df(self, var1: float, n1: int, var2: float, n2: int) -> float:
        """Calculate degrees of freedom for Welch's t-test."""
        numerator = (var1 / n1 + var2 / n2) ** 2
        denominator = (var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1)
        if denominator == 0:
            return 1.0
        return numerator / denominator

    def _t_critical(self, df: float) -> float:
        """Calculate t-critical value for given degrees of freedom.

        Uses approximation for t-distribution critical value at alpha/2.
        """
        # For large df, t approximates z
        if df > 1000:
            return self._z_critical()

        # Common critical values (approximate)
        # These are approximations for 95% confidence
        critical_values = {
            1: 12.706,
            2: 4.303,
            3: 3.182,
            4: 2.776,
            5: 2.571,
            6: 2.447,
            7: 2.365,
            8: 2.306,
            9: 2.262,
            10: 2.228,
            11: 2.201,
            12: 2.179,
            13: 2.160,
            14: 2.145,
            15: 2.131,
            16: 2.120,
            17: 2.110,
            18: 2.101,
            19: 2.093,
            20: 2.086,
            21: 2.080,
            22: 2.074,
            23: 2.069,
            24: 2.064,
            25: 2.060,
            26: 2.056,
            27: 2.052,
            28: 2.048,
            29: 2.045,
            30: 2.042,
        }

        # Use closest df or approximation
        df_rounded = int(round(df))
        if df_rounded in critical_values:
            return critical_values[df_rounded]

        # Approximation for larger df
        return 1.96 + 2.4 / df

    def _z_critical(self) -> float:
        """Calculate z-critical value for 95% confidence."""
        return 1.96

    def _t_cdf(self, t: float, df: float) -> float:
        """Approximate CDF of t-distribution.

        This is a simplified approximation. In production, use scipy.stats.t.cdf
        """
        # For large df, approximate with normal
        if df > 100:
            return self._normal_cdf(t)

        # Simplified approximation
        # This is not perfectly accurate but sufficient for demonstration
        return self._normal_cdf(t * (1 - 1 / (4 * df)))

    def _normal_cdf(self, x: float) -> float:
        """Approximate CDF of standard normal distribution."""
        # Using error function approximation
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def _chi_square_cdf(self, x: float, df: int) -> float:
        """Approximate CDF of chi-square distribution.

        This is a simplified approximation. In production, use scipy.stats.chi2.cdf
        """
        # For df=1, use approximation
        if df == 1:
            return 1 - 2 * (1 - self._normal_cdf(math.sqrt(x)))

        # General approximation (not perfectly accurate)
        return 1 - math.exp(-x / 2) if x > 0 else 0.0


# Alias for backward compatibility
StatisticalResult = SignificanceResult
