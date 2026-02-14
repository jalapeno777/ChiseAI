#!/usr/bin/env python3
"""Sample ECE calculation demonstration.

This script demonstrates ECE calculation for different scenarios
and shows sample output.
"""

import numpy as np

from confidence.ece import ECECalculator, SignalType, calculate_ece


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def demo_basic_ece():
    """Demonstrate basic ECE calculation."""
    print_section("Basic ECE Calculation")

    calc = ECECalculator(n_bins=10)

    # Well-calibrated predictions (confidence matches accuracy)
    predictions = []
    outcomes = []

    # Generate 100 samples per bin with matching accuracy
    for bin_idx in range(10):
        conf_center = (bin_idx + 0.5) / 10  # 0.05, 0.15, ..., 0.95
        target_accuracy = conf_center

        for _ in range(100):
            predictions.append(conf_center)
            # Outcome matches confidence on average
            outcomes.append(1 if np.random.random() < target_accuracy else 0)

    result = calc.calculate(predictions, outcomes)

    print(f"Total samples: {result.total_samples}")
    print(f"Number of bins: {result.n_bins}")
    print(f"ECE: {result.ece:.4f}")
    print(f"Well calibrated: {result.is_well_calibrated}")

    print("\nPer-bin breakdown:")
    print(
        f"{'Bin':>4} {'Range':>10} {'Conf':>8} {'Acc':>8} {'Samples':>8} {'Error':>8}"
    )
    print("-" * 55)
    for b in result.bins:
        print(
            f"{b.bin_index:>4} [{b.bin_start:.1f}-{b.bin_end:.1f}] {b.confidence:>8.3f} {b.accuracy:>8.3f} {b.sample_count:>8} {b.error:>8.3f}"
        )


def demo_per_signal_type():
    """Demonstrate per-signal-type ECE calculation."""
    print_section("Per-Signal-Type ECE Calculation")

    calc = ECECalculator(n_bins=10)

    np.random.seed(42)

    # Generate data for each signal type with different calibration quality
    predictions_by_type = {
        SignalType.ENTRY: np.random.uniform(0.7, 0.95, 200).tolist(),
        SignalType.EXIT: np.random.uniform(0.5, 0.8, 150).tolist(),
        SignalType.STOP_LOSS: np.random.uniform(0.6, 0.9, 100).tolist(),
        SignalType.TAKE_PROFIT: np.random.uniform(0.65, 0.92, 120).tolist(),
    }

    outcomes_by_type = {
        SignalType.ENTRY: [1 if np.random.random() < 0.82 else 0 for _ in range(200)],
        SignalType.EXIT: [1 if np.random.random() < 0.65 else 0 for _ in range(150)],
        SignalType.STOP_LOSS: [
            1 if np.random.random() < 0.75 else 0 for _ in range(100)
        ],
        SignalType.TAKE_PROFIT: [
            1 if np.random.random() < 0.78 else 0 for _ in range(120)
        ],
    }

    results = calc.calculate_per_signal_type(
        predictions_by_type, outcomes_by_type, strategy_id="grid_btc_1h"
    )

    print(f"Strategy: grid_btc_1h")
    print(f"\n{'Signal Type':>15} {'Samples':>10} {'ECE':>10} {'Well Calibrated':>18}")
    print("-" * 60)
    for signal_type, result in results.items():
        status = "✓" if result.is_well_calibrated else "✗"
        print(
            f"{signal_type.value:>15} {result.total_samples:>10} {result.ece:>10.4f} {status:>18}"
        )


def demo_miscalibration():
    """Demonstrate miscalibrated predictions."""
    print_section("Miscalibrated Predictions (Overconfident)")

    calc = ECECalculator(n_bins=10)

    # Overconfident: always predict 90% confidence, but only 50% accurate
    predictions = [0.9] * 200
    outcomes = [1] * 100 + [0] * 100  # 50% accuracy

    result = calc.calculate(predictions, outcomes, strategy_id="overconfident_strategy")

    print(f"Strategy: {result.strategy_id}")
    print(f"All predictions: 90% confidence")
    print(f"Actual accuracy: 50%")
    print(f"ECE: {result.ece:.4f}")
    print(f"Well calibrated: {result.is_well_calibrated}")

    print("\nNote: High ECE indicates poor calibration. The model is overconfident.")


def demo_convenience_function():
    """Demonstrate the convenience function."""
    print_section("Convenience Function")

    predictions = [0.8] * 10
    outcomes = [1] * 7 + [0] * 3  # 70% accuracy

    ece = calculate_ece(predictions, outcomes, n_bins=10)

    print(f"Predictions: 10 predictions at 80% confidence")
    print(f"Outcomes: 7 correct, 3 incorrect (70% accuracy)")
    print(f"ECE: {ece:.4f}")
    print(f"\nFormula: ECE = Σ(n_i/N) * |accuracy_i - confidence_i|")
    print(f"        = 1.0 * |0.70 - 0.80|")
    print(f"        = {ece:.4f}")


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 60)
    print("  ECE (Expected Calibration Error) Calculation Demo")
    print("=" * 60)

    demo_basic_ece()
    demo_per_signal_type()
    demo_miscalibration()
    demo_convenience_function()

    print_section("Summary")
    print("""
ECE measures how well-calibrated confidence scores are:
- ECE = 0.0: Perfect calibration (confidence = accuracy)
- ECE < 0.1: Well calibrated (default threshold)
- ECE > 0.1: Poor calibration (overconfident or underconfident)

Key features demonstrated:
✓ 10-bin configuration (0-10%, 10-20%, ..., 90-100%)
✓ Per-signal-type breakdown (entry, exit, SL, TP)
✓ Historical tracking with ECEHistoryTracker
✓ Trend analysis (improving/degrading/stable)
""")


if __name__ == "__main__":
    main()
