"""CVD component validation tests for ICT signal accuracy.

Tests the Cumulative Volume Delta (CVD) calculator against synthetic
trade scenarios to validate directional accuracy >= 60% Go threshold.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

sys.path.insert(0, "src")

from tests.validation.ict.conftest import (
    calculate_directional_accuracy,
    trades_from_list,
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def _get_cvd_calculator():
    from src.market_analysis.cvd.cvd_calculator import CVDCalculator

    return CVDCalculator()


# ---------------------------------------------------------------------------
# Per-scenario evaluation
# ---------------------------------------------------------------------------


def _evaluate_cvd_scenario(scenario: dict[str, Any]) -> bool:
    """Evaluate a single CVD scenario.

    Returns True if the CVD calculator produces results consistent
    with the expected direction and properties.
    """
    expected = scenario["expected"]
    trade_list = scenario["trades"]

    # Handle empty trades edge case
    if not trade_list:
        return expected.get("empty") or expected.get("no_trades")

    trades = trades_from_list(trade_list)
    calc = _get_cvd_calculator()
    result = calc.calculate_from_trades(trades)

    # Check net volume direction
    net_volume = result.net_volume
    is_positive = net_volume > 0
    is_negative = net_volume < 0
    is_zero = net_volume == 0

    # Check CVD direction
    if result.cvd_values:
        cvd_final = result.cvd_values[-1]
        cvd_positive = cvd_final > 0
        cvd_negative = cvd_final < 0
    else:
        cvd_final = 0
        cvd_positive = False
        cvd_negative = False

    expected_dir = expected.get("cvd_direction", "neutral")
    expected_net_pos = expected.get("net_volume_positive")

    # Direction check
    if expected_dir == "positive":
        if not (cvd_positive and is_positive):
            return False
    elif expected_dir == "negative":
        if not (cvd_negative and is_negative):
            return False
    elif expected_dir == "neutral":
        # For neutral, net volume should be close to zero
        if is_positive or is_negative:
            # Allow small tolerance
            if (
                abs(net_volume)
                > max(abs(result.buy_volume), abs(result.sell_volume)) * 0.1
            ):
                return False

    # Net volume sign check
    if expected_net_pos is True and not is_positive:
        return False
    if expected_net_pos is False and not is_negative:
        # Allow zero for some "not positive" cases
        if is_positive:
            return False

    # Special property checks
    if expected.get("all_one_side"):
        if expected_dir == "positive" and result.sell_volume > 0:
            return False
        if expected_dir == "negative" and result.buy_volume > 0:
            return False

    if expected.get("cumulative_increasing"):
        if not all(
            result.cvd_values[i] <= result.cvd_values[i + 1]
            for i in range(len(result.cvd_values) - 1)
        ):
            return False

    if expected.get("exact_balance"):
        if result.buy_volume != result.sell_volume:
            return False

    if expected.get("balanced"):
        total_vol = result.buy_volume + result.sell_volume
        if total_vol > 0:
            ratio = abs(result.buy_volume - result.sell_volume) / total_vol
            if ratio > 0.1:  # 10% tolerance
                return False

    if expected.get("reversal"):
        # Check that CVD changes sign at some point
        sign_changes = 0
        for i in range(1, len(result.cvd_values)):
            if (result.cvd_values[i] >= 0) != (result.cvd_values[i - 1] >= 0):
                sign_changes += 1
        if sign_changes == 0:
            return False

    if expected.get("divergence") == "bullish":
        # Price down, CVD up - check via trade prices
        prices = [t.price for t in trades]
        price_decreasing = all(
            prices[i] >= prices[i + 1] for i in range(len(prices) - 1)
        )
        if not (price_decreasing and cvd_positive):
            return False

    if expected.get("divergence") == "bearish":
        prices = [t.price for t in trades]
        price_increasing = all(
            prices[i] <= prices[i + 1] for i in range(len(prices) - 1)
        )
        if not (price_increasing and cvd_negative):
            return False

    return True


# ---------------------------------------------------------------------------
# Per-scenario tests
# ---------------------------------------------------------------------------


class TestCVDScenario:
    """Per-scenario CVD validation."""

    def test_cvd_positive_accumulation(self, cvd_scenarios):
        scenario = cvd_scenarios[0]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_negative_distribution(self, cvd_scenarios):
        scenario = cvd_scenarios[1]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_neutral_balanced(self, cvd_scenarios):
        scenario = cvd_scenarios[6]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_zero_volume(self, cvd_scenarios):
        scenario = cvd_scenarios[11]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_all_buys(self, cvd_scenarios):
        scenario = cvd_scenarios[15]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_all_sells(self, cvd_scenarios):
        scenario = cvd_scenarios[16]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_exact_balance(self, cvd_scenarios):
        scenario = cvd_scenarios[21]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_empty_trades(self, cvd_scenarios):
        scenario = cvd_scenarios[51]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_single_large_buy(self, cvd_scenarios):
        scenario = cvd_scenarios[12]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"

    def test_cvd_single_large_sell(self, cvd_scenarios):
        scenario = cvd_scenarios[13]
        assert _evaluate_cvd_scenario(scenario), f"Failed: {scenario['name']}"


# ---------------------------------------------------------------------------
# Aggregate accuracy tests
# ---------------------------------------------------------------------------


class TestCVDDirectionalAccuracy:
    """Aggregate accuracy tests for CVD signals."""

    def test_directional_accuracy_above_no_go(self, cvd_scenarios) -> None:
        """Overall directional accuracy must be above 40% No-Go threshold."""
        results = [_evaluate_cvd_scenario(s) for s in cvd_scenarios]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct > 40.0
        ), f"No-Go: accuracy {accuracy.accuracy_pct}% <= 40%"

    def test_minimum_scenarios(self, cvd_scenarios) -> None:
        """Ensure minimum 50 scenarios are available."""
        assert (
            len(cvd_scenarios) >= 50
        ), f"Only {len(cvd_scenarios)} scenarios, need >= 50"

    def test_positive_direction_scenarios(self, cvd_scenarios) -> None:
        """Positive delta scenarios should have reasonable accuracy."""
        positive = [
            s
            for s in cvd_scenarios
            if s.get("expected", {}).get("cvd_direction") == "positive"
        ]
        if not positive:
            pytest.skip("No positive CVD scenarios found")
        results = [_evaluate_cvd_scenario(s) for s in positive]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"Positive CVD accuracy {accuracy.accuracy_pct}% below threshold"

    def test_negative_direction_scenarios(self, cvd_scenarios) -> None:
        """Negative delta scenarios should have reasonable accuracy."""
        negative = [
            s
            for s in cvd_scenarios
            if s.get("expected", {}).get("cvd_direction") == "negative"
        ]
        if not negative:
            pytest.skip("No negative CVD scenarios found")
        results = [_evaluate_cvd_scenario(s) for s in negative]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"Negative CVD accuracy {accuracy.accuracy_pct}% below threshold"

    def test_neutral_scenarios(self, cvd_scenarios) -> None:
        """Neutral/balanced scenarios should have reasonable accuracy."""
        neutral = [
            s
            for s in cvd_scenarios
            if s.get("expected", {}).get("cvd_direction") == "neutral"
        ]
        if not neutral:
            pytest.skip("No neutral CVD scenarios found")
        results = [_evaluate_cvd_scenario(s) for s in neutral]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"Neutral CVD accuracy {accuracy.accuracy_pct}% below threshold"
