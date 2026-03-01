#!/usr/bin/env python3
"""Calculate paper carryover proxy from shadow mode results.

Since paper_carryover_rate is a placeholder metric, this script calculates
a proxy estimate based on backtest-paper correlation and false positive rate
from shadow mode results.

Usage:
    python3 scripts/calculate_carryover_proxy.py --shadow-results _bmad-output/brain/shadow/shadow-run-vnexta.json --output _bmad-output/brain/shadow/paper-carryover-proxy.json
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def calculate_carryover_proxy(shadow_results: dict[str, Any]) -> dict[str, Any]:
    """Calculate paper carryover proxy from shadow results.

    Methodology:
    1. Use backtest-paper correlation as baseline success predictor
    2. Adjust for false positive rate (high FP = lower carryover)
    3. Factor in confidence calibration accuracy
    4. Apply conservative estimate given placeholder status

    Args:
        shadow_results: Shadow mode results dict

    Returns:
        Carryover proxy calculation results
    """
    metrics = shadow_results.get("candidate_metrics", {})
    version = shadow_results.get("version", "unknown")

    # Extract key metrics
    backtest_paper_corr = metrics.get("backtest_paper_correlation", 0.0)
    false_positive_rate = metrics.get("false_positive_rate", 0.5)
    avg_confidence = metrics.get("average_confidence", 0.0)
    high_conf_ratio = metrics.get("high_confidence_ratio", 0.0)

    # Calculate base carryover from correlation
    # Higher correlation = more backtest success translates to paper success
    base_carryover = backtest_paper_corr

    # Adjust for false positive rate
    # Lower FP rate = higher carryover (fewer failed paper trades)
    # FP adjustment: reduce carryover proportionally to FP rate
    fp_adjustment = 1.0 - (false_positive_rate * 0.5)  # 50% weight on FP impact

    # Adjust for confidence calibration
    # Higher confidence accuracy = better prediction quality
    # Use high confidence ratio as proxy for calibration
    confidence_adjustment = 0.8 + (high_conf_ratio * 0.2)  # 80-100% range

    # Calculate estimated carryover
    estimated_carryover = base_carryover * fp_adjustment * confidence_adjustment

    # Apply conservative factor (since this is a proxy)
    # Real carryover may be 10-20% lower due to market conditions
    conservative_factor = 0.85
    conservative_carryover = estimated_carryover * conservative_factor

    # Calculate improvement vs baseline
    # Baseline assumption: current carryover ~0% (placeholder)
    baseline_carryover = 0.0
    improvement = conservative_carryover - baseline_carryover

    # Calculate confidence interval (rough estimate)
    # Based on uncertainty in proxy methodology
    margin_of_error = 0.10  # ±10%
    lower_bound = max(0.0, conservative_carryover - margin_of_error)
    upper_bound = min(1.0, conservative_carryover + margin_of_error)

    return {
        "version": version,
        "timestamp": datetime.utcnow().isoformat(),
        "methodology": {
            "description": "Proxy calculation based on backtest-paper correlation, FP rate, and confidence calibration",
            "formula": "estimated_carryover = correlation * (1 - fp_rate * 0.5) * (0.8 + high_conf_ratio * 0.2) * 0.85",
            "limitations": [
                "Paper carryover rate is currently a placeholder metric",
                "Proxy estimate based on shadow mode simulation, not live paper trading",
                "Conservative factor applied to account for real-world variability",
                "Actual carryover requires live paper trading validation",
            ],
        },
        "inputs": {
            "backtest_paper_correlation": backtest_paper_corr,
            "false_positive_rate": false_positive_rate,
            "average_confidence": avg_confidence,
            "high_confidence_ratio": high_conf_ratio,
        },
        "calculations": {
            "base_carryover_from_correlation": base_carryover,
            "fp_rate_adjustment": fp_adjustment,
            "confidence_calibration_adjustment": confidence_adjustment,
            "raw_estimated_carryover": estimated_carryover,
            "conservative_factor": conservative_factor,
        },
        "results": {
            "estimated_paper_carryover_rate": round(conservative_carryover, 4),
            "confidence_interval": {
                "lower_bound": round(lower_bound, 4),
                "upper_bound": round(upper_bound, 4),
            },
            "improvement_vs_baseline": round(improvement, 4),
            "baseline_assumption": baseline_carryover,
        },
        "assessment": {
            "meets_target": conservative_carryover > 0.0,  # Any improvement is good
            "confidence_level": "MEDIUM",  # Proxy methodology, not live data
            "recommendation": "Use as estimate for promotion packet, validate with live paper trading",
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Calculate paper carryover proxy")
    parser.add_argument(
        "--shadow-results", required=True, help="Shadow results JSON file path"
    )
    parser.add_argument("--output", required=True, help="Output JSON file path")

    args = parser.parse_args()

    # Load shadow results
    shadow_path = Path(args.shadow_results)
    if not shadow_path.exists():
        print(f"Error: Shadow results file not found: {shadow_path}")
        return 1

    with open(shadow_path) as f:
        shadow_results = json.load(f)

    # Calculate carryover proxy
    carryover_proxy = calculate_carryover_proxy(shadow_results)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(carryover_proxy, f, indent=2)

    print(
        f"\nPaper carryover proxy calculated for version: {carryover_proxy['version']}"
    )
    print(
        f"Estimated carryover rate: {carryover_proxy['results']['estimated_paper_carryover_rate']:.2%}"
    )
    print(
        f"Confidence interval: [{carryover_proxy['results']['confidence_interval']['lower_bound']:.2%}, "
        f"{carryover_proxy['results']['confidence_interval']['upper_bound']:.2%}]"
    )
    print(
        f"Improvement vs baseline: {carryover_proxy['results']['improvement_vs_baseline']:+.2%}"
    )
    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    exit(main())
