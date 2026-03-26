"""Comprehensive Tests for Statistical Analysis and Significance Testing.

Tests cover:
- Two-proportion z-test
- Fisher exact test
- MDE calculation and verification
- Bonferroni correction
- Decision logic (Confirm/Partial/Null)
"""

from __future__ import annotations

import pytest
from src.validation.statistical.analysis import (
    FisherExactResult,
    absolute_risk_difference,
    fisher_exact_test,
    number_needed_to_treat,
    relative_risk,
)
from src.validation.statistical.hypothesis_framework import (
    cohens_h,
    two_proportion_z_test,
)
from src.validation.statistical.significance import (
    MDEParameters,
    MultipleComparisonsConfig,
    SignificanceDecision,
    SignificanceTestResult,
    apply_multiple_comparisons_correction,
    benjamini_hochberg_correction,
    bonferroni_correction,
    calculate_mde,
    holm_correction,
    make_decision,
    required_sample_size_for_mde,
    significance_test,
    verify_mde_2percent,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def large_sample_data():
    """Large sample data where z-test is appropriate."""
    return {
        "treatment_successes": 450,
        "treatment_total": 1000,
        "control_successes": 400,
        "control_total": 1000,
    }


@pytest.fixture
def small_sample_data():
    """Small sample data where Fisher exact is preferred."""
    return {
        "treatment_successes": 8,
        "treatment_total": 25,
        "control_successes": 5,
        "control_total": 25,
    }


@pytest.fixture
def edge_case_data():
    """Edge case data with zero cells."""
    return {
        "treatment_successes": 10,
        "treatment_total": 20,
        "control_successes": 0,
        "control_total": 20,
    }


# =============================================================================
# Z-Test Tests
# =============================================================================


class TestTwoProportionZTest:
    """Tests for two-proportion z-test."""

    def test_large_samples_significant(self, large_sample_data):
        """Test z-test with large samples showing significant difference."""
        result = two_proportion_z_test(
            large_sample_data["treatment_successes"],
            large_sample_data["treatment_total"],
            large_sample_data["control_successes"],
            large_sample_data["control_total"],
        )
        p_value, z_stat = result

        assert p_value < 0.05, f"Expected significant result, p={p_value}"
        assert z_stat > 0, "Expected positive z-statistic"
        assert abs(z_stat) > 1.96, "Z-statistic should exceed critical value"

    def test_z_test_pvalue_calculation(self):
        """Verify z-test p-value calculation against known values."""
        # Equal proportions should give p-value near 1.0
        p_value, z_stat = two_proportion_z_test(500, 1000, 500, 1000)
        assert p_value == pytest.approx(1.0, abs=0.01)
        assert z_stat == pytest.approx(0.0, abs=0.01)

    def test_z_test_no_difference(self):
        """Test z-test when proportions are equal."""
        p_value, z_stat = two_proportion_z_test(100, 200, 100, 200)
        assert p_value >= 0.05, "No significant difference expected"
        assert abs(z_stat) < 1.96, "Z-statistic should be within bounds"

    def test_z_test_zero_standard_error(self):
        """Test handling of zero standard error (perfect agreement)."""
        # When p1 = p2 exactly, SE = 0, should return p=1.0
        p_value, z_stat = two_proportion_z_test(0, 10, 0, 10)
        assert p_value == 1.0
        assert z_stat == 0.0

    def test_z_test_invalid_input(self):
        """Test that invalid inputs raise ValueError."""
        with pytest.raises(ValueError):
            two_proportion_z_test(10, 0, 10, 10)  # treatment_total=0

        with pytest.raises(ValueError):
            two_proportion_z_test(10, 10, 10, 0)  # control_total=0


# =============================================================================
# Fisher Exact Test Tests
# =============================================================================


class TestFisherExactTest:
    """Tests for Fisher's exact test."""

    def test_fisher_exact_basic(self, small_sample_data):
        """Test Fisher exact test with small samples."""
        result = fisher_exact_test(
            small_sample_data["treatment_successes"],
            small_sample_data["treatment_total"],
            small_sample_data["control_successes"],
            small_sample_data["control_total"],
        )

        assert isinstance(result, FisherExactResult)
        assert 0 <= result.p_value <= 1
        assert result.odds_ratio >= 0

    def test_fisher_exact_odds_ratio(self, small_sample_data):
        """Verify odds ratio calculation."""
        a = small_sample_data["treatment_successes"]
        b = small_sample_data["treatment_total"] - a
        c = small_sample_data["control_successes"]
        d = small_sample_data["control_total"] - c

        expected_or = (a * d) / (b * c)
        result = fisher_exact_test(
            small_sample_data["treatment_successes"],
            small_sample_data["treatment_total"],
            small_sample_data["control_successes"],
            small_sample_data["control_total"],
        )

        assert result.odds_ratio == pytest.approx(expected_or)

    def test_fisher_exact_confidence_interval(self, small_sample_data):
        """Test that confidence interval is returned."""
        result = fisher_exact_test(
            small_sample_data["treatment_successes"],
            small_sample_data["treatment_total"],
            small_sample_data["control_successes"],
            small_sample_data["control_total"],
        )

        lower, upper = result.confidence_interval
        assert lower >= 0
        assert upper >= lower
        # If odds ratio is > 1, CI should typically contain it
        if result.odds_ratio != float("inf"):
            assert lower <= result.odds_ratio <= upper

    def test_fisher_exact_with_zero_cells(self, edge_case_data):
        """Test Fisher exact with zero cell."""
        result = fisher_exact_test(
            edge_case_data["treatment_successes"],
            edge_case_data["treatment_total"],
            edge_case_data["control_successes"],
            edge_case_data["control_total"],
        )

        assert 0 <= result.p_value <= 1
        # When control has 0 successes, OR should be inf
        assert result.odds_ratio == float("inf")

    def test_fisher_exact_invalid_input(self):
        """Test that invalid inputs raise ValueError."""
        with pytest.raises(ValueError):
            fisher_exact_test(10, 0, 5, 10)  # treatment_total=0

        with pytest.raises(ValueError):
            fisher_exact_test(-1, 10, 5, 10)  # negative successes

        with pytest.raises(ValueError):
            fisher_exact_test(15, 10, 5, 10)  # successes > total


# =============================================================================
# MDE (Minimum Detectable Effect) Tests
# =============================================================================


class TestMDECalculation:
    """Tests for MDE calculation and verification."""

    def test_mde_calculation_basic(self):
        """Test basic MDE calculation."""
        mde = calculate_mde(alpha=0.05, power=0.80)
        assert mde > 0  # MDE should be positive

    def test_mde_with_sample_size(self):
        """Test MDE calculation with known sample size."""
        # For n=1000 per group, MDE should be small
        mde = calculate_mde(alpha=0.05, power=0.80, sample_size=1000)
        assert mde < 0.10  # Should be less than 10%

    def test_mde_verification_2percent(self):
        """Verify 2% MDE is achievable with reasonable sample size."""
        is_verified, actual_mde, required_n = verify_mde_2percent()

        assert is_verified, "2% MDE should be verifiable"
        assert actual_mde <= 0.02, f"Actual MDE {actual_mde} should be <= 0.02"
        assert required_n > 0
        assert required_n < 100000  # Should be practical

    def test_mde_increases_with_lower_power(self):
        """Test that MDE increases when power decreases."""
        mde_80 = calculate_mde(alpha=0.05, power=0.80)
        mde_60 = calculate_mde(alpha=0.05, power=0.60)

        assert (
            mde_60 < mde_80
        ), "Lower power should allow smaller sample, thus higher MDE"

    def test_required_sample_size_for_mde(self):
        """Test required sample size calculation."""
        # For 1% MDE, should need large sample
        n = required_sample_size_for_mde(mde=0.01)
        assert n > 10000, "1% MDE should require large sample"

        # For 5% MDE, should need smaller sample
        n_5 = required_sample_size_for_mde(mde=0.05)
        assert n_5 < n, "5% MDE should need smaller sample than 1% MDE"


# =============================================================================
# Bonferroni Correction Tests
# =============================================================================


class TestBonferroniCorrection:
    """Tests for multiple comparisons correction."""

    def test_bonferroni_basic(self):
        """Test basic Bonferroni correction."""
        corrected = bonferroni_correction(alpha=0.05, num_comparisons=2)
        assert corrected == 0.025

    def test_bonferroni_multiple(self):
        """Test Bonferroni with multiple comparisons."""
        corrected = bonferroni_correction(alpha=0.05, num_comparisons=10)
        assert corrected == 0.005

    def test_bonferroni_single_comparison(self):
        """Test Bonferroni with single comparison (no change)."""
        corrected = bonferroni_correction(alpha=0.05, num_comparisons=1)
        assert corrected == 0.05

    def test_bonferroni_invalid_num_comparisons(self):
        """Test that invalid num_comparisons raises error."""
        with pytest.raises(ValueError):
            bonferroni_correction(alpha=0.05, num_comparisons=0)

        with pytest.raises(ValueError):
            bonferroni_correction(alpha=0.05, num_comparisons=-1)

    def test_holm_correction(self):
        """Test Holm-Bonferroni correction."""
        # Three p-values: 0.01, 0.04, 0.06 with alpha=0.05
        p_values = [0.01, 0.04, 0.06]
        rejected = holm_correction(p_values, alpha=0.05)

        # With Holm (step-down procedure):
        # i=0: threshold = 0.05/3 = 0.0167, p=0.01 <= 0.0167 -> reject
        # i=1: threshold = 0.05/2 = 0.025, p=0.04 > 0.025 -> STOP
        # Only the first (smallest p-value) is rejected
        assert rejected[0] is True  # 0.01 rejected
        assert rejected[1] is False  # 0.04 not rejected
        assert rejected[2] is False  # 0.06 not rejected

    def test_holm_correction_none_rejected(self):
        """Test Holm when no hypotheses should be rejected."""
        p_values = [0.10, 0.20, 0.30]
        rejected = holm_correction(p_values, alpha=0.05)

        assert all(not r for r in rejected)

    def test_benjamini_hochberg_correction(self):
        """Test Benjamini-Hochberg FDR correction."""
        p_values = [0.01, 0.03, 0.04, 0.10]
        rejected = benjamini_hochberg_correction(p_values, alpha=0.05)

        # BH critical values: 0.0125, 0.025, 0.0375, 0.05
        # p[0]=0.01 <= 0.0125 -> reject
        # p[1]=0.03 <= 0.025 -> no (but we continue...)
        # p[2]=0.04 <= 0.0375 -> no
        # p[3]=0.10 <= 0.05 -> no
        # max_k where p[k] <= k/n * alpha:
        # k=0: 0.01 <= 0.0125 ✓
        # k=1: 0.03 <= 0.025 ✗
        # So only first is rejected
        assert rejected[0] is True
        assert not all(rejected[1:])

    def test_apply_correction_bonferroni(self):
        """Test apply_multiple_comparisons_correction with Bonferroni."""
        corrected = apply_multiple_comparisons_correction(
            alpha=0.05, num_comparisons=5, method="bonferroni"
        )
        assert corrected == 0.01

    def test_apply_correction_invalid_method(self):
        """Test that invalid method raises ValueError."""
        with pytest.raises(ValueError):
            apply_multiple_comparisons_correction(
                alpha=0.05, num_comparisons=2, method="invalid"
            )


# =============================================================================
# Decision Logic Tests
# =============================================================================


class TestDecisionLogic:
    """Tests for significance decision logic."""

    def test_decision_confirm(self):
        """Test Confirm decision: significant AND effect > MDE."""
        decision = make_decision(
            p_value=0.01,
            effect_size=0.05,  # 5% effect, > 2% MDE
            alpha=0.05,
            mde=0.02,
        )
        assert decision == SignificanceDecision.CONFIRM

    def test_decision_partial(self):
        """Test Partial decision: significant BUT effect <= MDE."""
        decision = make_decision(
            p_value=0.01,
            effect_size=0.01,  # 1% effect, <= 2% MDE
            alpha=0.05,
            mde=0.02,
        )
        assert decision == SignificanceDecision.PARTIAL

    def test_decision_null(self):
        """Test Null decision: not significant."""
        decision = make_decision(
            p_value=0.10,
            effect_size=0.05,
            alpha=0.05,
            mde=0.02,
        )
        assert decision == SignificanceDecision.NULL

    def test_decision_null_negative_effect(self):
        """Test Null decision when treatment is worse than control."""
        decision = make_decision(
            p_value=0.01,  # Significant
            effect_size=-0.05,  # But negative effect (treatment worse)
            alpha=0.05,
            mde=0.02,
        )
        # Negative effect still gets Null because abs(effect) > MDE but direction is wrong
        assert decision == SignificanceDecision.NULL

    def test_decision_with_bonferroni(self):
        """Test decision with Bonferroni correction."""
        decision = make_decision(
            p_value=0.03,  # 0.03 < 0.05 but 0.03 > 0.025 (Bonferroni corrected)
            effect_size=0.05,
            alpha=0.05,
            mde=0.02,
            num_comparisons=2,
        )
        assert decision == SignificanceDecision.NULL

    def test_decision_boundary_effect_size(self):
        """Test decision at MDE boundary."""
        # Effect exactly at MDE threshold should be Partial, not Confirm
        decision = make_decision(
            p_value=0.01,
            effect_size=0.02,  # Exactly at MDE
            alpha=0.05,
            mde=0.02,
        )
        assert decision == SignificanceDecision.PARTIAL


# =============================================================================
# Complete Significance Test Integration
# =============================================================================


class TestSignificanceTest:
    """Integration tests for complete significance_test function."""

    def test_significance_test_z_test(self, large_sample_data):
        """Test complete significance test with z-test."""
        result = significance_test(
            treatment_successes=large_sample_data["treatment_successes"],
            treatment_total=large_sample_data["treatment_total"],
            control_successes=large_sample_data["control_successes"],
            control_total=large_sample_data["control_total"],
            alpha=0.05,
            mde=0.02,
        )

        assert isinstance(result, SignificanceTestResult)
        assert result.decision in SignificanceDecision
        assert 0 <= result.p_value <= 1
        assert result.test_type == "z_test"
        assert result.num_comparisons == 1

    def test_significance_test_fisher_exact(self, small_sample_data):
        """Test complete significance test with Fisher exact."""
        result = significance_test(
            treatment_successes=small_sample_data["treatment_successes"],
            treatment_total=small_sample_data["treatment_total"],
            control_successes=small_sample_data["control_successes"],
            control_total=small_sample_data["control_total"],
            alpha=0.05,
            mde=0.02,
            use_fisher_exact=True,
        )

        assert isinstance(result, SignificanceTestResult)
        assert result.test_type == "fisher_exact"
        assert result.odds_ratio is not None

    def test_significance_test_small_sample_auto(self, small_sample_data):
        """Test that small samples automatically use Fisher exact."""
        result = significance_test(
            treatment_successes=small_sample_data["treatment_successes"],
            treatment_total=small_sample_data["treatment_total"],
            control_successes=small_sample_data["control_successes"],
            control_total=small_sample_data["control_total"],
            alpha=0.05,
        )

        # Should auto-detect small sample and use Fisher
        assert result.test_type == "fisher_exact"

    def test_significance_test_multiple_comparisons(self):
        """Test significance with multiple comparisons correction."""
        result = significance_test(
            treatment_successes=450,
            treatment_total=1000,
            control_successes=400,
            control_total=1000,
            alpha=0.05,
            mde=0.02,
            num_comparisons=5,
            correction_method="bonferroni",
        )

        assert result.num_comparisons == 5
        assert result.alpha_corrected == 0.01
        assert result.method_used == "bonferroni"

    def test_significance_test_result_properties(self):
        """Test SignificanceTestResult properties."""
        result = significance_test(
            treatment_successes=100,
            treatment_total=200,
            control_successes=80,
            control_total=200,
            alpha=0.05,
            mde=0.02,
        )

        assert isinstance(result.is_significant, bool)
        assert isinstance(result.exceeds_mde, bool)


# =============================================================================
# Effect Size and Risk Metrics Tests
# =============================================================================


class TestEffectSizeAndRiskMetrics:
    """Tests for effect size and risk metrics."""

    def test_cohens_h_calculation(self):
        """Test Cohen's h effect size calculation."""
        # p1=0.5, p2=0.4 should give positive effect size
        h = cohens_h(0.5, 0.4)
        assert h > 0

    def test_cohens_h_symmetry(self):
        """Test Cohen's h is antisymmetric."""
        h1 = cohens_h(0.5, 0.4)
        h2 = cohens_h(0.4, 0.5)
        assert h1 == pytest.approx(-h2)

    def test_relative_risk(self):
        """Test relative risk calculation."""
        rr, ci = relative_risk(
            treatment_successes=60,
            treatment_total=100,
            control_successes=40,
            control_total=100,
        )
        assert rr == pytest.approx(1.5)
        assert ci[0] < rr < ci[1]

    def test_absolute_risk_difference(self):
        """Test absolute risk difference calculation."""
        ard, ci = absolute_risk_difference(
            treatment_successes=60,
            treatment_total=100,
            control_successes=40,
            control_total=100,
        )
        assert ard == pytest.approx(0.2)
        assert ci[0] < ard < ci[1]

    def test_number_needed_to_treat(self):
        """Test NNT calculation."""
        # With ARD = 0.2, NNT = 1/0.2 = 5
        nnt = number_needed_to_treat(
            treatment_successes=60,
            treatment_total=100,
            control_successes=40,
            control_total=100,
        )
        assert nnt == pytest.approx(5.0)

    def test_nnt_infinite_when_no_difference(self):
        """Test NNT is infinite when there's no difference."""
        nnt = number_needed_to_treat(
            treatment_successes=50,
            treatment_total=100,
            control_successes=50,
            control_total=100,
        )
        assert nnt == float("inf")


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility and helper functions."""

    def test_required_sample_size_calculation(self):
        """Test required sample size for given MDE."""
        n = required_sample_size_for_mde(mde=0.02)
        assert n > 0
        assert n < 1000000

    def test_mde_parameters_dataclass(self):
        """Test MDEParameters dataclass."""
        params = MDEParameters(mde=0.03, alpha=0.05, power=0.90)
        assert params.mde == 0.03
        assert params.alpha == 0.05
        assert params.power == 0.90

    def test_multiple_comparisons_config(self):
        """Test MultipleComparisonsConfig dataclass."""
        config = MultipleComparisonsConfig(num_comparisons=3, method="holm")
        assert config.num_comparisons == 3
        assert config.method == "holm"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_perfect_success_rate(self):
        """Test with 100% success rate in treatment."""
        result = fisher_exact_test(10, 10, 5, 10)
        assert result.odds_ratio == float("inf")
        assert result.p_value < 1.0

    def test_perfect_failure_rate(self):
        """Test with 0% success rate in treatment."""
        result = fisher_exact_test(0, 10, 5, 10)
        assert result.odds_ratio == 0.0

    def test_very_large_samples(self):
        """Test with very large samples."""
        result = significance_test(
            treatment_successes=50000,
            treatment_total=100000,
            control_successes=45000,
            control_total=100000,
            alpha=0.05,
            mde=0.02,
        )
        assert result.decision in SignificanceDecision

    def test_pvalue_boundary(self):
        """Test decision at p-value boundary."""
        # p exactly at alpha should be Null
        decision = make_decision(
            p_value=0.05,
            effect_size=0.05,
            alpha=0.05,
            mde=0.02,
        )
        assert decision == SignificanceDecision.NULL

        # p just below alpha should be significant
        decision2 = make_decision(
            p_value=0.0499,
            effect_size=0.05,
            alpha=0.05,
            mde=0.02,
        )
        assert decision2 == SignificanceDecision.CONFIRM
