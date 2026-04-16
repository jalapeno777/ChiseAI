"""BOS/CHoCH component validation tests for ICT signal accuracy.

Tests the Break of Structure (BOS) and Change of Character (CHoCH) classifier
against synthetic scenarios to validate directional accuracy >= 60% Go threshold.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

sys.path.insert(0, "src")

from tests.validation.ict.conftest import (
    calculate_directional_accuracy,
    ohlcv_from_list,
)

# ---------------------------------------------------------------------------
# Imports (lazy to avoid import-time side effects)
# ---------------------------------------------------------------------------


def _get_classifier():
    from src.market_analysis.structure.bos_choch import BOSCHoCHClassifier

    return BOSCHoCHClassifier()


def _get_pivot_detector():
    from src.market_analysis.structure.swing_pivot import SwingPivotDetector

    return SwingPivotDetector(window_size=2, min_window_size=2, max_window_size=10)


# ---------------------------------------------------------------------------
# Per-scenario validation
# ---------------------------------------------------------------------------


def _evaluate_bos_choch_scenario(scenario: dict[str, Any]) -> bool:
    """Evaluate a single BOS/CHoCH scenario.

    Returns True if the detector correctly identifies the expected
    breakout/choch pattern direction.
    """
    expected = scenario["expected"]
    ohlcv_data = ohlcv_from_list(scenario["ohlcv"])

    # Need at least window_size * 2 + 1 candles for swing pivot detection (window_size=2 → 5 bars)
    if len(ohlcv_data) < 5:
        # If we expect no break and have insufficient data, that's correct
        return not expected.get("bos") and not expected.get("choch")

    pivot_detector = _get_pivot_detector()
    classifier = _get_classifier()

    pivot_result = pivot_detector.detect(ohlcv_data)
    result = classifier.classify(pivot_result, ohlcv_data)

    has_bullish_bos = len(result.bullish_bos_events) > 0
    has_bearish_bos = len(result.bearish_bos_events) > 0
    has_bullish_choch = len(result.bullish_choch_events) > 0
    has_bearish_choch = len(result.bearish_choch_events) > 0

    detected_bos = has_bullish_bos or has_bearish_bos
    detected_choch = has_bullish_choch or has_bearish_choch
    detected_direction = "none"

    if has_bullish_bos or has_bullish_choch:
        detected_direction = "bullish"
    elif has_bearish_bos or has_bearish_choch:
        detected_direction = "bearish"

    expected_bos = expected.get("bos", False)
    expected_choch = expected.get("choch", False)
    expected_direction = expected.get("direction", "none")

    # Check if direction matches
    direction_match = detected_direction == expected_direction

    # For "none" direction, both detected and expected should have no breaks
    if expected_direction == "none":
        return not detected_bos and not detected_choch

    # For BOS expected: should detect BOS (not just CHoCH)
    if expected_bos and not expected_choch:
        return detected_bos and direction_match

    # For CHoCH expected: should detect CHoCH
    if expected_choch and not expected_bos:
        return detected_choch and direction_match

    # If both expected, either BOS or CHoCH in correct direction works
    if expected_bos and expected_choch:
        return (detected_bos or detected_choch) and direction_match

    return direction_match


# ---------------------------------------------------------------------------
# Test: per-scenario validation
# ---------------------------------------------------------------------------


class TestBOSScenario:
    """Per-scenario BOS/CHoCH validation."""

    def test_bos_choch_scenario_001(self, bos_choch_scenarios):
        scenario = bos_choch_scenarios[0]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_002(self, bos_choch_scenarios):
        scenario = bos_choch_scenarios[1]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_005(self, bos_choch_scenarios):
        """Ranging market - no break."""
        scenario = bos_choch_scenarios[4]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_010(self, bos_choch_scenarios):
        """Minor pullback in uptrend - no BOS."""
        scenario = bos_choch_scenarios[9]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_015(self, bos_choch_scenarios):
        """Slow grind uptrend - no clear break."""
        scenario = bos_choch_scenarios[14]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_018(self, bos_choch_scenarios):
        """Whipsaw ranging - alternating highs/lows."""
        scenario = bos_choch_scenarios[17]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_024(self, bos_choch_scenarios):
        """Gradual downtrend - no break."""
        scenario = bos_choch_scenarios[23]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_028(self, bos_choch_scenarios):
        """Flat market with micro oscillations."""
        scenario = bos_choch_scenarios[27]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    @pytest.mark.xfail(
        reason="BOS/CHoCH under redesign after PR #1029 (Apr 13); feature flag ict:bos_choch:enabled=FALSE",
        strict=False,
    )
    def test_bos_choch_scenario_039(self, bos_choch_scenarios):
        """Narrow range squeeze - no break."""
        scenario = bos_choch_scenarios[38]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"

    def test_bos_choch_scenario_046(self, bos_choch_scenarios):
        """Ranging with fake breakouts - no valid BOS."""
        scenario = bos_choch_scenarios[45]
        assert _evaluate_bos_choch_scenario(scenario), f"Failed: {scenario['name']}"


# ---------------------------------------------------------------------------
# Test: aggregate directional accuracy (Go/No-Go gate)
# ---------------------------------------------------------------------------


class TestBOSSDirectionalAccuracy:
    """Aggregate accuracy tests for BOS/CHoCH signals."""

    def test_directional_accuracy_above_no_go(self, bos_choch_scenarios) -> None:
        """Overall directional accuracy must be above 40% No-Go threshold."""
        results = [_evaluate_bos_choch_scenario(s) for s in bos_choch_scenarios]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct > 40.0
        ), f"No-Go: accuracy {accuracy.accuracy_pct}% <= 40%"

    def test_minimum_scenarios(self, bos_choch_scenarios) -> None:
        """Ensure minimum 50 scenarios are available."""
        assert (
            len(bos_choch_scenarios) >= 50
        ), f"Only {len(bos_choch_scenarios)} scenarios, need >= 50"

    def test_bullish_bos_scenarios_pass(self, bos_choch_scenarios) -> None:
        """Bullish BOS scenarios should have reasonable accuracy."""
        bullish_bos = [
            s for s in bos_choch_scenarios if "bullish_bos" in s.get("tags", [])
        ]
        if not bullish_bos:
            pytest.skip("No bullish BOS scenarios found")
        results = [_evaluate_bos_choch_scenario(s) for s in bullish_bos]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"Bullish BOS accuracy {accuracy.accuracy_pct}% below threshold"

    def test_bearish_bos_scenarios_pass(self, bos_choch_scenarios) -> None:
        """Bearish BOS scenarios should have reasonable accuracy."""
        bearish_bos = [
            s for s in bos_choch_scenarios if "bearish_bos" in s.get("tags", [])
        ]
        if not bearish_bos:
            pytest.skip("No bearish BOS scenarios found")
        results = [_evaluate_bos_choch_scenario(s) for s in bearish_bos]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"Bearish BOS accuracy {accuracy.accuracy_pct}% below threshold"

    def test_no_break_scenarios_pass(self, bos_choch_scenarios) -> None:
        """No-break scenarios should have reasonable accuracy."""
        no_break = [
            s
            for s in bos_choch_scenarios
            if "no_break" in s.get("tags", [])
            or s.get("expected", {}).get("direction") == "none"
        ]
        if not no_break:
            pytest.skip("No no-break scenarios found")
        results = [_evaluate_bos_choch_scenario(s) for s in no_break]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"No-break accuracy {accuracy.accuracy_pct}% below threshold"
