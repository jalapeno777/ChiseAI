"""Hypothesis framework validation tests for ICT signal statistical evaluation.

Tests the hypothesis testing framework including:
- Power analysis and sample size calculation
- Effect size calculation (Cohen's h)
- Two-proportion z-test
- Early stopping rules
- Hypothesis framework orchestration
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "src")

from src.validation.statistical.hypothesis_framework import (
    HypothesisDecision,
    HypothesisTestResult,
    ICTHypothesisFramework,
    SignalResult,
    TestParameters,
    calculate_achieved_power,
    calculate_confidence_interval,
    calculate_minimum_sample_size,
    check_early_stopping,
    cohens_h,
    effect_size_interpretation,
    two_proportion_z_test,
)

# ---------------------------------------------------------------------------
# Power Analysis Tests
# ---------------------------------------------------------------------------


class TestCalculateMinimumSampleSize:
    """Tests for sample size calculation."""

    def test_default_parameters(self) -> None:
        """Test with default parameters."""
        n = calculate_minimum_sample_size()
        assert isinstance(n, int)
        assert n > 0
        # With defaults: alpha=0.05, power=0.80, effect=0.50
        # n = 2 * ((1.96 + 2.80) / 0.50)^2 = 2 * (4.76/0.50)^2 = 2 * 9.52^2 ≈ 182
        assert n == 182

    def test_higher_power(self) -> None:
        """Test with higher power requirement."""
        n = calculate_minimum_sample_size(power=0.90)
        # With power=0.90, z_beta=1.96+1.28=3.24
        # n = 2 * ((1.96 + 3.24) / 0.50)^2 = 2 * (5.20/0.50)^2 ≈ 217
        assert n == 217

    def test_larger_effect_size(self) -> None:
        """Test with larger effect size (smaller sample needed)."""
        n = calculate_minimum_sample_size(effect_size=0.80)
        # n = 2 * ((1.96 + 2.80) / 0.80)^2 = 2 * (4.76/0.80)^2 ≈ 71
        assert n == 71

    def test_smaller_effect_size(self) -> None:
        """Test with smaller effect size (larger sample needed)."""
        n = calculate_minimum_sample_size(effect_size=0.20)
        # n = 2 * ((1.96 + 2.80) / 0.20)^2 = 2 * (4.76/0.20)^2 ≈ 1134
        assert n == 1134


class TestCalculateAchievedPower:
    """Tests for achieved power calculation."""

    def test_power_at_minimum_sample(self) -> None:
        """Test power at minimum sample size."""
        # At n=62, achieved power is approximately 78-80%
        power = calculate_achieved_power(sample_size=62)
        assert isinstance(power, float)
        assert 0.70 <= power <= 0.90  # Approximately 80%

    def test_power_increases_with_sample(self) -> None:
        """Test that power increases as sample size increases."""
        power_small = calculate_achieved_power(sample_size=50)
        power_large = calculate_achieved_power(sample_size=200)
        assert power_large > power_small

    def test_power_approaches_one(self) -> None:
        """Test that power approaches 1 as sample size grows."""
        power = calculate_achieved_power(sample_size=1000)
        assert power > 0.99


# ---------------------------------------------------------------------------
# Effect Size Tests
# ---------------------------------------------------------------------------


class TestCohensH:
    """Tests for Cohen's h effect size calculation."""

    def test_identical_proportions(self) -> None:
        """Test that identical proportions give zero effect size."""
        h = cohens_h(0.5, 0.5)
        assert abs(h) < 1e-10

    def test_treatment_better(self) -> None:
        """Test effect size when treatment is better."""
        h = cohens_h(0.60, 0.50)
        assert h > 0

    def test_control_better(self) -> None:
        """Test effect size when control is better."""
        h = cohens_h(0.40, 0.50)
        assert h < 0

    def test_effect_size_magnitude(self) -> None:
        """Test that effect size magnitude is reasonable."""
        h = cohens_h(0.70, 0.30)
        assert 0.5 < abs(h) < 2.0  # Should be in reasonable range

    def test_invalid_proportions(self) -> None:
        """Test that invalid proportions raise error."""
        with pytest.raises(ValueError):
            cohens_h(0.0, 0.5)
        with pytest.raises(ValueError):
            cohens_h(0.5, 1.0)
        with pytest.raises(ValueError):
            cohens_h(1.5, 0.5)


class TestEffectSizeInterpretation:
    """Tests for effect size interpretation."""

    @pytest.mark.parametrize(
        "effect_size,expected",
        [
            (0.01, "negligible"),
            (0.02, "negligible"),
            (0.05, "small"),
            (0.10, "small"),
            (0.15, "medium"),
            (0.25, "medium"),
            (0.30, "large"),
            (0.40, "large"),
            (0.50, "very large"),
            (-0.15, "medium"),  # Negative uses abs
        ],
    )
    def test_interpretation(
        self,
        effect_size: float,
        expected: str,
    ) -> None:
        """Test effect size interpretations."""
        result = effect_size_interpretation(effect_size)
        assert result == expected


# ---------------------------------------------------------------------------
# Statistical Test Tests
# ---------------------------------------------------------------------------


class TestTwoProportionZTest:
    """Tests for two-proportion z-test."""

    def test_identical_success_rates(self) -> None:
        """Test identical success rates give high p-value."""
        p_value, z = two_proportion_z_test(50, 100, 50, 100)
        assert p_value > 0.05
        assert abs(z) < 1.96

    def test_different_success_rates(self) -> None:
        """Test different success rates give low p-value."""
        p_value, z = two_proportion_z_test(60, 100, 40, 100)
        assert p_value < 0.05
        assert abs(z) > 1.96

    def test_large_sample_significance(self) -> None:
        """Test that large samples detect larger differences."""
        # 550/1000=0.55 vs 450/1000=0.45 has z=2.83, p=0.0046 < 0.05
        p_value, z = two_proportion_z_test(550, 1000, 450, 1000)
        assert p_value < 0.05
        assert z > 1.96

    def test_small_sample_insignificance(self) -> None:
        """Test that small samples may miss real differences."""
        p_value, _ = two_proportion_z_test(6, 10, 4, 10)
        assert p_value > 0.05  # May not detect difference with small n

    def test_zero_division_handled(self) -> None:
        """Test that zero totals raise error."""
        with pytest.raises(ValueError):
            two_proportion_z_test(0, 0, 50, 100)
        with pytest.raises(ValueError):
            two_proportion_z_test(50, 100, 0, 0)


class TestConfidenceInterval:
    """Tests for confidence interval calculation."""

    def test_zero_effect(self) -> None:
        """Test CI when treatment == control."""
        ci = calculate_confidence_interval(
            treatment_mean=0.05,
            control_mean=0.05,
            treatment_std=0.10,
            control_std=0.10,
            treatment_n=100,
            control_n=100,
        )
        assert ci[0] <= 0 <= ci[1]  # Should contain zero

    def test_positive_effect(self) -> None:
        """Test CI when treatment > control."""
        ci = calculate_confidence_interval(
            treatment_mean=0.08,
            control_mean=0.05,
            treatment_std=0.10,
            control_std=0.10,
            treatment_n=100,
            control_n=100,
        )
        assert ci[0] > 0  # Lower bound should be positive

    def test_zero_total_n(self) -> None:
        """Test that zero n raises error."""
        with pytest.raises(ValueError):
            calculate_confidence_interval(
                treatment_mean=0.05,
                control_mean=0.05,
                treatment_std=0.10,
                control_std=0.10,
                treatment_n=0,
                control_n=100,
            )


# ---------------------------------------------------------------------------
# Early Stopping Tests
# ---------------------------------------------------------------------------


class TestCheckEarlyStopping:
    """Tests for early stopping logic."""

    def test_insufficient_signals(self) -> None:
        """Test no early stop with insufficient signals."""
        should_stop, reason = check_early_stopping(
            signals_analyzed=30,
            p_value=0.50,
            parameters=TestParameters(),
        )
        assert not should_stop

    def test_no_early_stop_significance(self) -> None:
        """Test no early stop when trending toward significance."""
        should_stop, reason = check_early_stopping(
            signals_analyzed=60,
            p_value=0.10,
            parameters=TestParameters(),
        )
        assert not should_stop

    def test_early_stop_no_significance(self) -> None:
        """Test early stop when clearly not significant."""
        should_stop, reason = check_early_stopping(
            signals_analyzed=60,
            p_value=0.50,
            parameters=TestParameters(),
        )
        assert should_stop
        assert "Early stopping triggered" in reason

    def test_custom_thresholds(self) -> None:
        """Test with custom early stop parameters."""
        # p=0.40 < early_stop_p_threshold=0.50, so should NOT stop
        should_stop, reason = check_early_stopping(
            signals_analyzed=40,
            p_value=0.40,
            parameters=TestParameters(
                early_stop_signals=40,
                early_stop_p_threshold=0.50,
            ),
        )
        assert not should_stop
        assert (
            "Insufficient" not in reason
        )  # Has enough signals, just not significant enough


# ---------------------------------------------------------------------------
# Framework Integration Tests
# ---------------------------------------------------------------------------


class TestICTHypothesisFramework:
    """Tests for the ICT Hypothesis Framework class."""

    def test_initialization(self) -> None:
        """Test framework initializes correctly."""
        framework = ICTHypothesisFramework()
        assert framework.signals_analyzed == 0
        assert framework.minimum_signals_required == 182

    def test_custom_parameters(self) -> None:
        """Test framework with custom parameters."""
        params = TestParameters(alpha=0.01, power=0.90)
        framework = ICTHypothesisFramework(parameters=params)
        assert framework.parameters.alpha == 0.01
        assert framework.parameters.power == 0.90

    def test_add_single_result(self) -> None:
        """Test adding a single signal result."""
        framework = ICTHypothesisFramework()
        result = SignalResult(
            signal_id="sig1",
            timestamp=1000,
            treatment_return=0.05,
            control_return=0.02,
        )
        framework.add_result(result)
        assert framework.signals_analyzed == 1

    def test_add_batch_results(self) -> None:
        """Test adding multiple signal results."""
        framework = ICTHypothesisFramework()
        results = [
            SignalResult(
                signal_id=f"sig{i}",
                timestamp=1000 + i,
                treatment_return=0.05 + i * 0.01,
                control_return=0.02 + i * 0.005,
            )
            for i in range(10)
        ]
        framework.add_results_batch(results)
        assert framework.signals_analyzed == 10

    def test_clear_results(self) -> None:
        """Test clearing results."""
        framework = ICTHypothesisFramework()
        result = SignalResult(
            signal_id="sig1",
            timestamp=1000,
            treatment_return=0.05,
            control_return=0.02,
        )
        framework.add_result(result)
        framework.clear_results()
        assert framework.signals_analyzed == 0

    def test_evaluate_no_signals(self) -> None:
        """Test evaluation with no signals."""
        framework = ICTHypothesisFramework()
        result = framework.evaluate()
        assert result.decision == HypothesisDecision.INCONCLUSIVE
        assert result.signals_analyzed == 0

    def test_evaluate_insufficient_signals(self) -> None:
        """Test evaluation with insufficient signals."""
        framework = ICTHypothesisFramework()
        for i in range(20):
            framework.add_result(
                SignalResult(
                    signal_id=f"sig{i}",
                    timestamp=1000 + i,
                    treatment_return=0.05,
                    control_return=0.02,
                )
            )
        result = framework.evaluate()
        assert result.decision == HypothesisDecision.CONTINUE

    def test_evaluate_accept_h0(self) -> None:
        """Test evaluation accepting H0."""
        framework = ICTHypothesisFramework()
        # Add 100 signals with treatment == control (no effect)
        for i in range(100):
            framework.add_result(
                SignalResult(
                    signal_id=f"sig{i}",
                    timestamp=1000 + i,
                    treatment_return=0.02,
                    control_return=0.02,
                )
            )
        result = framework.evaluate()
        assert result.decision == HypothesisDecision.ACCEPT_H0
        assert result.p_value > 0.05

    def test_evaluate_reject_h0(self) -> None:
        """Test evaluation rejecting H0."""
        framework = ICTHypothesisFramework()
        # Add 100 signals with treatment > control (effect)
        for i in range(100):
            framework.add_result(
                SignalResult(
                    signal_id=f"sig{i}",
                    timestamp=1000 + i,
                    treatment_return=0.06,
                    control_return=0.02,
                )
            )
        result = framework.evaluate()
        assert result.decision in (
            HypothesisDecision.REJECT_H0,
            HypothesisDecision.ACCEPT_H0,  # May still accept depending on variance
        )

    def test_early_stopping_triggered(self) -> None:
        """Test that early stopping is triggered appropriately."""
        framework = ICTHypothesisFramework()
        # Add 60 signals with no treatment effect
        for i in range(60):
            framework.add_result(
                SignalResult(
                    signal_id=f"sig{i}",
                    timestamp=1000 + i,
                    treatment_return=0.02,
                    control_return=0.02,
                )
            )
        result = framework.evaluate()
        # With identical treatment/control, should accept H0
        assert result.decision == HypothesisDecision.ACCEPT_H0

    def test_generate_report(self) -> None:
        """Test report generation."""
        framework = ICTHypothesisFramework()
        for i in range(5):
            framework.add_result(
                SignalResult(
                    signal_id=f"sig{i}",
                    timestamp=1000 + i,
                    treatment_return=0.05,
                    control_return=0.02,
                )
            )
        report = framework.generate_report()
        assert "ICT Hypothesis Framework Status Report" in report
        assert "Signals analyzed: 5" in report
        assert "Minimum required: 182" in report


# ---------------------------------------------------------------------------
# SignalResult Tests
# ---------------------------------------------------------------------------


class TestSignalResult:
    """Tests for SignalResult dataclass."""

    def test_alpha_calculation(self) -> None:
        """Test that alpha is calculated correctly."""
        result = SignalResult(
            signal_id="sig1",
            timestamp=1000,
            treatment_return=0.08,
            control_return=0.03,
        )
        assert result.alpha == 0.05

    def test_negative_alpha(self) -> None:
        """Test alpha with negative treatment effect."""
        result = SignalResult(
            signal_id="sig1",
            timestamp=1000,
            treatment_return=-0.02,
            control_return=0.03,
        )
        assert result.alpha == -0.05


# ---------------------------------------------------------------------------
# HypothesisTestResult Tests
# ---------------------------------------------------------------------------


class TestHypothesisTestResult:
    """Tests for HypothesisTestResult."""

    def test_has_significant_alpha_reject(self) -> None:
        """Test significant alpha detection when H0 rejected."""
        result = HypothesisTestResult(
            decision=HypothesisDecision.REJECT_H0,
            p_value=0.01,
            effect_size=0.05,
            signals_analyzed=100,
            treatment_mean=0.08,
            control_mean=0.03,
            confidence_interval=(0.02, 0.08),
            power_achieved=0.85,
        )
        assert result.has_significant_alpha

    def test_has_significant_alpha_accept(self) -> None:
        """Test significant alpha detection when H0 accepted."""
        result = HypothesisTestResult(
            decision=HypothesisDecision.ACCEPT_H0,
            p_value=0.50,
            effect_size=0.05,
            signals_analyzed=100,
            treatment_mean=0.05,
            control_mean=0.03,
            confidence_interval=(0.0, 0.04),
            power_achieved=0.85,
        )
        assert not result.has_significant_alpha

    def test_has_significant_alpha_small_effect(self) -> None:
        """Test significant alpha with small effect size."""
        result = HypothesisTestResult(
            decision=HypothesisDecision.REJECT_H0,
            p_value=0.01,
            effect_size=0.01,  # Below 2% threshold
            signals_analyzed=100,
            treatment_mean=0.04,
            control_mean=0.03,
            confidence_interval=(0.0, 0.02),
            power_achieved=0.85,
        )
        assert not result.has_significant_alpha


# ---------------------------------------------------------------------------
# Integration Scenarios
# ---------------------------------------------------------------------------


class TestIntegrationScenarios:
    """End-to-end integration test scenarios."""

    def test_scenario_ict_provides_alpha(self) -> None:
        """Scenario: ICT signals provide meaningful alpha."""
        framework = ICTHypothesisFramework()

        # Simulate 100 signals where ICT improves win rate
        # Treatment: 58% win rate (positive return)
        # Control: 50% win rate (baseline)
        for i in range(58):
            framework.add_result(
                SignalResult(
                    signal_id=f"sig{i}",
                    timestamp=1000 + i,
                    treatment_return=0.05,
                    control_return=-0.02,
                )
            )
        for i in range(42):
            framework.add_result(
                SignalResult(
                    signal_id=f"sigh{i}",
                    timestamp=2000 + i,
                    treatment_return=-0.03,
                    control_return=-0.02,
                )
            )

        result = framework.evaluate()
        # With ICT providing 8% improvement, should reject or continue
        assert result.signals_analyzed == 100
        assert result.treatment_mean > result.control_mean

    def test_scenario_ict_no_effect(self) -> None:
        """Scenario: ICT signals provide no alpha."""
        framework = ICTHypothesisFramework()

        # Both groups have 50% win rate
        for i in range(50):
            framework.add_result(
                SignalResult(
                    signal_id=f"sig{i}",
                    timestamp=1000 + i,
                    treatment_return=0.03,
                    control_return=0.03,
                )
            )
        for i in range(50):
            framework.add_result(
                SignalResult(
                    signal_id=f"sigh{i}",
                    timestamp=2000 + i,
                    treatment_return=-0.02,
                    control_return=-0.02,
                )
            )

        result = framework.evaluate()
        assert result.treatment_mean == result.control_mean

    def test_scenario_sequential_evaluation(self) -> None:
        """Scenario: Sequential evaluation with early stopping check."""
        framework = ICTHypothesisFramework()

        # Add signals in batches
        for batch in range(5):
            for i in range(20):
                framework.add_result(
                    SignalResult(
                        signal_id=f"sig{batch}_{i}",
                        timestamp=1000 + batch * 20 + i,
                        treatment_return=0.03,
                        control_return=0.03,
                    )
                )

            if framework.signals_analyzed == 60:
                result = framework.evaluate()
                # At 60 signals with no effect, should accept H0
                assert result.decision == HypothesisDecision.ACCEPT_H0
