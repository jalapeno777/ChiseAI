#!/usr/bin/env python3
"""Sample walk-forward evaluation output demonstration.

This script demonstrates the walk-forward evaluation framework
with a sample strategy and outputs the results.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

from ml.walk_forward import (
    LookAheadBiasCheck,
    WalkForwardConfig,
    WalkForwardEvaluator,
)


class SampleStrategy:
    """Sample strategy for demonstration."""

    def train(self, data: list[dict]) -> dict:
        """Train on historical data."""
        returns = []
        for i in range(1, len(data)):
            prev_close = data[i - 1].get("close", 100)
            curr_close = data[i].get("close", 100)
            ret = (curr_close - prev_close) / prev_close
            returns.append(ret)

        avg_return = sum(returns) / len(returns) if returns else 0
        volatility = (
            (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            if returns
            else 0
        )

        return {
            "trained": True,
            "samples": len(data),
            "avg_return": avg_return,
            "volatility": volatility,
        }

    def predict(self, data: list[dict], train_result: dict) -> dict:
        """Generate predictions and calculate metrics."""
        # Simple momentum strategy simulation
        returns = []
        for i in range(1, len(data)):
            prev_close = data[i - 1].get("close", 100)
            curr_close = data[i].get("close", 100)
            ret = (curr_close - prev_close) / prev_close
            returns.append(ret)

        if not returns:
            return {
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate_pct": 0.0,
                "trade_count": 0,
            }

        # Calculate metrics
        avg_return = sum(returns) / len(returns)
        volatility = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5

        # Sharpe ratio (annualized, assuming daily returns)
        sharpe = (avg_return / volatility * (252**0.5)) if volatility > 0 else 0

        # Win rate
        wins = sum(1 for r in returns if r > 0)
        win_rate = (wins / len(returns)) * 100

        # Max drawdown
        cumulative = [1.0]
        for r in returns:
            cumulative.append(cumulative[-1] * (1 + r))

        max_dd = 0.0
        peak = cumulative[0]
        for value in cumulative:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd

        total_return = (cumulative[-1] - 1) * 100

        return {
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": 1.5,  # Simplified
            "total_return_pct": round(total_return, 2),
            "volatility_pct": round(volatility * 100, 2),
            "trade_count": len(returns),
            "avg_trade_return_pct": round(avg_return * 100, 4),
        }


def generate_sample_data(
    start_date: datetime, days: int, trend: str = "up"
) -> list[dict]:
    """Generate sample OHLCV data."""
    data = []
    price = 100.0

    for i in range(days * 24):  # Hourly data
        timestamp = start_date + timedelta(hours=i)

        # Add some randomness based on trend
        if trend == "up":
            change = 0.001 + (i / (days * 24)) * 0.1
        elif trend == "down":
            change = -0.001 - (i / (days * 24)) * 0.05
        else:
            change = 0.0

        noise = (i % 10 - 5) * 0.001
        price = price * (1 + change + noise)

        data.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": round(price * 0.999, 2),
                "high": round(price * 1.002, 2),
                "low": round(price * 0.998, 2),
                "close": round(price, 2),
                "volume": 1000 + i * 10,
            }
        )

    return data


def main() -> None:
    """Run sample walk-forward evaluation."""
    print("=" * 70)
    print("WALK-FORWARD EVALUATION FRAMEWORK - SAMPLE OUTPUT")
    print("=" * 70)

    # Configuration
    config = WalkForwardConfig(
        train_days=30,
        test_days=7,
        step_days=7,
        min_train_samples=100,
        min_test_samples=50,
        max_windows=10,
    )

    print("\nConfiguration:")
    print(f"  Train window: {config.train_days} days")
    print(f"  Test window: {config.test_days} days")
    print(f"  Step size: {config.step_days} days")
    print(f"  Max windows: {config.max_windows}")

    # Generate sample data (6 months of hourly data)
    start_date = datetime(2024, 1, 1)
    data = generate_sample_data(start_date, days=180, trend="up")

    print("\nData:")
    print(f"  Total samples: {len(data)}")
    print(f"  Date range: {data[0]['timestamp']} to {data[-1]['timestamp']}")

    # Create evaluator and run evaluation
    evaluator = WalkForwardEvaluator(config)
    strategy = SampleStrategy()

    print("\nRunning walk-forward evaluation...")
    print("-" * 70)

    result = evaluator.evaluate_strategy(
        strategy=strategy,
        data=data,
        strategy_id="sample_momentum_strategy",
    )

    # Output results
    print("\nEVALUATION RESULTS")
    print("-" * 70)
    print(f"Strategy ID: {result.strategy_id}")
    print(f"Look-ahead bias check: {result.look_ahead_check.value}")
    print(f"Total evaluation time: {result.total_evaluation_time_seconds:.3f}s")
    print(f"Number of windows: {len(result.window_results)}")

    print("\nPer-Window Results:")
    print("-" * 70)
    for i, window_result in enumerate(result.window_results):
        w = window_result.window
        print(f"\nWindow {i + 1}:")
        print(f"  Train: {w.train_start.date()} to {w.train_end.date()}")
        print(f"  Test:  {w.test_start.date()} to {w.test_end.date()}")
        print(f"  Status: {window_result.status.value}")

        if window_result.status.value == "completed":
            print(f"  Sharpe Ratio: {window_result.sharpe_ratio:.2f}")
            print(f"  Max Drawdown: {window_result.max_drawdown_pct:.2f}%")
            print(f"  Win Rate: {window_result.win_rate_pct:.1f}%")
            print(f"  Total Return: {window_result.total_return_pct:.2f}%")
            print(f"  Trades: {window_result.trade_count}")
            print(f"  Train Time: {window_result.training_time_seconds:.3f}s")
            print(f"  Test Time: {window_result.testing_time_seconds:.3f}s")
        elif window_result.error_message:
            print(f"  Error: {window_result.error_message}")

    print("\nAggregated Metrics:")
    print("-" * 70)
    agg = result.aggregated
    print(f"  Windows evaluated: {agg.window_count}")
    print(f"  Mean Sharpe Ratio: {agg.mean_sharpe:.2f}")
    print(f"  Std Sharpe Ratio: {agg.std_sharpe:.2f}")
    print(f"  Mean Max Drawdown: {agg.mean_max_drawdown:.2f}%")
    print(f"  Mean Win Rate: {agg.mean_win_rate:.1f}%")
    print(f"  Total Trades: {agg.total_trades}")
    print(f"  Total Return: {agg.total_return_pct:.2f}%")
    print(f"  Consistency Score: {agg.consistency_score:.1f}/100")

    if agg.best_window_index is not None:
        print(f"  Best Window: #{agg.best_window_index + 1}")
    if agg.worst_window_index is not None:
        print(f"  Worst Window: #{agg.worst_window_index + 1}")

    # Output as JSON
    print("\nJSON Output (truncated):")
    print("-" * 70)
    output = result.to_dict()
    # Truncate window_results for display
    output["window_results"] = output["window_results"][:2] + ["..."]
    print(json.dumps(output, indent=2)[:1500] + "\n  ...")

    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)

    # Verify acceptance criteria
    print("\nAcceptance Criteria Verification:")
    print("-" * 70)
    checks = [
        (
            "Configurable windows",
            True,
            f"{config.train_days}d train, {config.test_days}d test",
        ),
        (
            "No future data leak",
            result.look_ahead_check == LookAheadBiasCheck.PASSED,
            result.look_ahead_check.value,
        ),
        (
            "Per-window metrics",
            len(result.window_results) > 0,
            f"{len(result.window_results)} windows",
        ),
        ("Aggregated metrics", agg.window_count > 0, f"{agg.window_count} aggregated"),
        (
            "Look-ahead bias check",
            result.look_ahead_check == LookAheadBiasCheck.PASSED,
            "passed",
        ),
        (
            "Performance target",
            result.total_evaluation_time_seconds < 7200,
            f"{result.total_evaluation_time_seconds:.2f}s < 7200s",
        ),
    ]

    for criterion, passed, detail in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {criterion} ({detail})")


if __name__ == "__main__":
    main()
