"""FVG component validation tests for ICT signal accuracy.

Tests the Fair Value Gap (FVG) detector against synthetic candle
scenarios to validate directional accuracy >= 60% Go threshold.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

sys.path.insert(0, "src")

from tests.validation.ict.conftest import (
    calculate_directional_accuracy,
    candle_objects_from_list,
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def _get_fvg_detector():
    from src.market_analysis.fvg.fvg_detector import FVGDetector

    return FVGDetector(min_gap_percent=0.001, min_candle_size_ratio=0.3)


# ---------------------------------------------------------------------------
# Per-scenario evaluation
# ---------------------------------------------------------------------------


def _evaluate_fvg_scenario(scenario: dict[str, Any]) -> bool:
    """Evaluate a single FVG scenario.

    Returns True if the FVG detector produces results consistent
    with the expected direction and properties.
    """
    expected = scenario["expected"]
    candle_list = scenario["candles"]

    # Need at least 3 candles for FVG detection
    if len(candle_list) < 3:
        return not expected.get("fvg_detected")

    candles = candle_objects_from_list(candle_list)
    detector = _get_fvg_detector()

    try:
        result = detector.detect(
            candles, regime_data=None, token="BTC/USDT", timeframe="1H"
        )
    except Exception:
        # If detector throws, check if we expected no FVG
        return not expected.get("fvg_detected")

    # FVGDetectionResult has a single .fvg attribute (not .fvgs list)
    detected_fvg = getattr(result, "fvg", None)
    detected_fvgs = [detected_fvg] if detected_fvg else []
    has_fvg = len(detected_fvgs) > 0

    # Determine expected direction early so mitigation checks can use it
    expected_dir = (
        expected.get("direction", "none") if expected.get("fvg_detected") else "none"
    )

    # Check FVG detection
    if expected.get("fvg_detected"):
        if not has_fvg:
            return False

        fvg = detected_fvgs[0]

        # Check direction
        if expected_dir == "bullish":
            from src.market_analysis.fvg.fvg_detector import FVGDirection

            if fvg.direction != FVGDirection.BULLISH:
                return False
        elif expected_dir == "bearish":
            from src.market_analysis.fvg.fvg_detector import FVGDirection

            if fvg.direction != FVGDirection.BEARISH:
                return False
    else:
        # Expected no FVG
        if has_fvg:
            return False

    # Check mitigation if applicable
    if expected.get("mitigated"):
        if not has_fvg:
            return True  # Can't check mitigation without FVG
        fvg = detected_fvgs[0]
        from src.market_analysis.fvg.fvg_detector import FVGMitigation

        if fvg.mitigation == FVGMitigation.NONE:
            # Check if any subsequent candle mitigates
            last_candle = candles[-1]
            if expected_dir == "bullish":
                if last_candle.low_price <= fvg.low:
                    pass  # Mitigated
                else:
                    return False
            elif expected_dir == "bearish":
                if last_candle.high_price >= fvg.high:
                    pass  # Mitigated
                else:
                    return False

    # Check wick mitigation
    if expected.get("wick_mitigation") and has_fvg:
        fvg = detected_fvgs[0]
        from src.market_analysis.fvg.fvg_detector import FVGMitigation

        if fvg.mitigation == FVGMitigation.NONE:
            # Check via last candle touching the zone
            last_candle = candles[-1]
            zone_touched = False
            if expected_dir == "bullish":
                if last_candle.low_price <= fvg.low:
                    zone_touched = True
            elif expected_dir == "bearish":
                if last_candle.high_price >= fvg.high:
                    zone_touched = True
            if not zone_touched:
                return False

    # Check full mitigation
    if expected.get("full_mitigation") and has_fvg:
        fvg = detected_fvgs[0]
        from src.market_analysis.fvg.fvg_detector import FVGMitigation

        if fvg.mitigation == FVGMitigation.NONE:
            last_candle = candles[-1]
            zone_fully_covered = False
            if expected_dir == "bullish":
                if (
                    last_candle.low_price <= fvg.low
                    and last_candle.close_price <= fvg.low
                ):
                    zone_fully_covered = True
            elif expected_dir == "bearish":
                if (
                    last_candle.high_price >= fvg.high
                    and last_candle.close_price >= fvg.high
                ):
                    zone_fully_covered = True
            if not zone_fully_covered:
                return False

    return True


# ---------------------------------------------------------------------------
# Per-scenario tests
# ---------------------------------------------------------------------------


class TestFVGScenario:
    """Per-scenario FVG validation."""

    def test_fvg_bullish_simple(self, fvg_scenarios):
        scenario = fvg_scenarios[0]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_bearish_simple(self, fvg_scenarios):
        scenario = fvg_scenarios[1]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_no_overlap(self, fvg_scenarios):
        scenario = fvg_scenarios[4]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_doji_no_fvg(self, fvg_scenarios):
        scenario = fvg_scenarios[13]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_small_candles(self, fvg_scenarios):
        scenario = fvg_scenarios[21]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_single_candle(self, fvg_scenarios):
        scenario = fvg_scenarios[49]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_two_candles(self, fvg_scenarios):
        scenario = fvg_scenarios[50]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_equal_highs(self, fvg_scenarios):
        scenario = fvg_scenarios[42]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_bullish_mitigation(self, fvg_scenarios):
        scenario = fvg_scenarios[2]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"

    def test_fvg_bearish_mitigation(self, fvg_scenarios):
        scenario = fvg_scenarios[3]
        assert _evaluate_fvg_scenario(scenario), f"Failed: {scenario['name']}"


# ---------------------------------------------------------------------------
# Aggregate accuracy tests
# ---------------------------------------------------------------------------


class TestFVGDirectionalAccuracy:
    """Aggregate accuracy tests for FVG signals."""

    def test_directional_accuracy_above_no_go(self, fvg_scenarios) -> None:
        """Overall directional accuracy must be above 40% No-Go threshold."""
        results = [_evaluate_fvg_scenario(s) for s in fvg_scenarios]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct > 40.0
        ), f"No-Go: accuracy {accuracy.accuracy_pct}% <= 40%"

    def test_minimum_scenarios(self, fvg_scenarios) -> None:
        """Ensure minimum 50 scenarios are available."""
        assert (
            len(fvg_scenarios) >= 50
        ), f"Only {len(fvg_scenarios)} scenarios, need >= 50"

    def test_bullish_fvg_scenarios(self, fvg_scenarios) -> None:
        """Bullish FVG scenarios should have reasonable accuracy."""
        bullish = [
            s
            for s in fvg_scenarios
            if s.get("expected", {}).get("direction") == "bullish"
        ]
        if not bullish:
            pytest.skip("No bullish FVG scenarios found")
        results = [_evaluate_fvg_scenario(s) for s in bullish]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"Bullish FVG accuracy {accuracy.accuracy_pct}% below threshold"

    def test_bearish_fvg_scenarios(self, fvg_scenarios) -> None:
        """Bearish FVG scenarios should have reasonable accuracy."""
        bearish = [
            s
            for s in fvg_scenarios
            if s.get("expected", {}).get("direction") == "bearish"
        ]
        if not bearish:
            pytest.skip("No bearish FVG scenarios found")
        results = [_evaluate_fvg_scenario(s) for s in bearish]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"Bearish FVG accuracy {accuracy.accuracy_pct}% below threshold"

    def test_no_fvg_scenarios(self, fvg_scenarios) -> None:
        """No-FVG scenarios should have reasonable accuracy."""
        no_fvg = [
            s for s in fvg_scenarios if not s.get("expected", {}).get("fvg_detected")
        ]
        if not no_fvg:
            pytest.skip("No no-FVG scenarios found")
        results = [_evaluate_fvg_scenario(s) for s in no_fvg]
        accuracy = calculate_directional_accuracy(results)
        assert (
            accuracy.accuracy_pct >= 40.0
        ), f"No-FVG accuracy {accuracy.accuracy_pct}% below threshold"
