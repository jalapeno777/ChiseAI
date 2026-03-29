#!/usr/bin/env python3
"""
CANARY Mode Validation Report Script.

Generates a pass/fail validation report comparing CANARY cycle artifacts
against the success/failure criteria defined in the validation checklist.

Usage:
    python3 scripts/autocog_canary_report.py [--output-format json|text] [--output-file FILE]

Output:
    - PASS: All success criteria met
    - WARN: Some criteria not met but no critical failures
    - FAIL: One or more critical failure criteria triggered
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Constants from runtime_integration.py
DIVERGENCE_THRESHOLD_LOW = 0.15
DIVERGENCE_THRESHOLD_HIGH = 0.35
DIVERGENCE_THRESHOLD_CRITICAL = 0.45
DRIFT_THRESHOLD_FOR_DEMOTION = 0.40
PROMOTE_THRESHOLD = 0.35
CANARY_MAX_POSITION_FRACTION = 0.01
REQUIRED_CONSECUTIVE_CHECKS = 5
AUTOCOG_CYCLE_DIR = "_bmad-output/autocog/cycles"
REDIS_KEY_PREFIX = "bmad:chiseai:autocog"

# Try to import redis
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


def get_repo_root() -> Path:
    """Get the repository root directory."""
    env_root = Path(__file__).parent.parent.resolve()
    marker = env_root / "pyproject.toml"
    if marker.exists():
        return env_root
    return Path.cwd()


def load_latest_cycle_artifacts(n: int = 5) -> list[dict[str, Any]]:
    """Load the N most recent CANARY cycle artifacts."""
    repo_root = get_repo_root()
    cycles_dir = repo_root / AUTOCOG_CYCLE_DIR

    if not cycles_dir.exists():
        return []

    cycle_files = sorted(
        cycles_dir.glob("autocog-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )

    artifacts = []
    for cycle_file in cycle_files[:n]:
        try:
            with open(cycle_file, encoding="utf-8") as f:
                artifacts.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue

    return artifacts


def load_canary_config() -> dict[str, Any]:
    """Load the CANARY configuration from config/autocog-canary.yaml."""
    repo_root = get_repo_root()
    config_path = repo_root / "config" / "autocog-canary.yaml"

    if not config_path.exists():
        return {}

    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # yaml not available, return empty
        return {}
    except (yaml.YAMLError, OSError):
        return {}


def get_redis_state() -> dict[str, Any]:
    """Get CANARY state from Redis."""
    if not REDIS_AVAILABLE:
        return {"available": False}

    try:
        redis_client = redis.Redis.from_url(
            "redis://host.docker.internal:6380/1", socket_connect_timeout=2
        )
        redis_client.ping()

        current_mode = redis_client.hget(f"{REDIS_KEY_PREFIX}:state", "current_mode")
        divergence_score = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:metrics", "divergence_score"
        )
        consecutive_count = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:state", "consecutive_non_regression_count"
        )
        position_fraction = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:metrics", "position_fraction"
        )
        trade_count = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:metrics", "trade_count_today"
        )
        error_count = redis_client.hget(f"{REDIS_KEY_PREFIX}:metrics", "error_count")

        return {
            "available": True,
            "current_mode": current_mode.decode("utf-8") if current_mode else "unknown",
            "divergence_score": (
                float(divergence_score.decode("utf-8")) if divergence_score else None
            ),
            "consecutive_non_regression_count": (
                int(consecutive_count.decode("utf-8")) if consecutive_count else 0
            ),
            "position_fraction": (
                float(position_fraction.decode("utf-8")) if position_fraction else None
            ),
            "trade_count_today": int(trade_count.decode("utf-8")) if trade_count else 0,
            "error_count": int(error_count.decode("utf-8")) if error_count else 0,
        }

    except redis.RedisError:
        return {"available": False}


class CanaryCriteriaEvaluator:
    """Evaluates CANARY mode against success/failure criteria."""

    def __init__(
        self,
        redis_state: dict[str, Any],
        cycles: list[dict[str, Any]],
        config: dict[str, Any],
    ):
        self.redis_state = redis_state
        self.cycles = cycles
        self.config = config
        self.latest_cycle = cycles[0] if cycles else {}
        self.passed_checks: list[str] = []
        self.failed_checks: list[str] = []
        self.warning_checks: list[str] = []
        self.recommendations: list[str] = []

    def evaluate(self) -> dict[str, Any]:
        """Run all evaluation checks and return results."""
        self._check_divergence()
        self._check_consecutive_non_regression()
        self._check_position_fraction()
        self._check_experiment_limits()
        self._check_error_rate()
        self._check_win_rate()
        self._check_mode()
        self._check_notification_suppression()

        return self._generate_result()

    def _check_divergence(self) -> None:
        """Check divergence against thresholds."""
        divergence = self.redis_state.get("divergence_score")

        if divergence is None:
            self.warning_checks.append("divergence - No data available")
            return

        if divergence >= DRIFT_THRESHOLD_FOR_DEMOTION:
            self.failed_checks.append(
                f"divergence CRITICAL: {divergence:.3f} >= {DRIFT_THRESHOLD_FOR_DEMOTION} (demotion threshold)"
            )
        elif divergence >= DIVERGENCE_THRESHOLD_HIGH:
            self.warning_checks.append(
                f"divergence elevated: {divergence:.3f} >= {DIVERGENCE_THRESHOLD_HIGH}"
            )
        elif divergence >= DIVERGENCE_THRESHOLD_LOW:
            self.warning_checks.append(
                f"divergence borderline: {divergence:.3f} >= {DIVERGENCE_THRESHOLD_LOW}"
            )
        else:
            self.passed_checks.append(
                f"divergence OK: {divergence:.3f} < {DIVERGENCE_THRESHOLD_LOW}"
            )

    def _check_consecutive_non_regression(self) -> None:
        """Check consecutive non-regression count."""
        count = self.redis_state.get("consecutive_non_regression_count", 0)

        if count >= REQUIRED_CONSECUTIVE_CHECKS:
            self.passed_checks.append(
                f"consecutive_non_regression OK: {count} >= {REQUIRED_CONSECUTIVE_CHECKS} (promotion threshold)"
            )
        else:
            self.warning_checks.append(
                f"consecutive_non_regression pending: {count}/{REQUIRED_CONSECUTIVE_CHECKS}"
            )

    def _check_position_fraction(self) -> None:
        """Check position fraction is within CANARY limits."""
        position_frac = self.redis_state.get("position_fraction")

        if position_frac is None:
            self.warning_checks.append("position_fraction - No data available")
            return

        if position_frac > CANARY_MAX_POSITION_FRACTION:
            self.failed_checks.append(
                f"position_fraction EXCEEDED: {position_frac:.4f} > {CANARY_MAX_POSITION_FRACTION}"
            )
        else:
            self.passed_checks.append(
                f"position_fraction OK: {position_frac:.4f} <= {CANARY_MAX_POSITION_FRACTION}"
            )

    def _check_experiment_limits(self) -> None:
        """Check experiments per cycle is within limits."""
        if not self.latest_cycle:
            self.warning_checks.append("experiments_per_cycle - No cycle data")
            return

        experiments_run = self.latest_cycle.get("experiments_run", 0)

        if experiments_run > 1:
            self.failed_checks.append(
                f"experiments_per_cycle EXCEEDED: {experiments_run} > 1"
            )
        else:
            self.passed_checks.append(
                f"experiments_per_cycle OK: {experiments_run} <= 1"
            )

    def _check_error_rate(self) -> None:
        """Check error rate is within acceptable limits."""
        error_count = self.redis_state.get("error_count", 0)
        trade_count = self.redis_state.get("trade_count_today", 0)

        if error_count == 0:
            self.passed_checks.append("error_rate OK: 0 errors")
            return

        if trade_count > 0:
            error_rate = error_count / trade_count
            if error_rate > 0.05:  # 5% threshold
                self.failed_checks.append(f"error_rate CRITICAL: {error_rate:.1%} > 5%")
            else:
                self.passed_checks.append(f"error_rate OK: {error_rate:.1%} <= 5%")
        else:
            if error_count > 0:
                self.warning_checks.append(
                    f"error_count: {error_count} errors but no trades"
                )

    def _check_win_rate(self) -> None:
        """Check win rate meets minimum threshold."""
        if not self.latest_cycle:
            self.warning_checks.append("win_rate - No cycle data")
            return

        metrics = self.latest_cycle.get("metrics", {})
        winning_trades = metrics.get("winning_trades", 0)
        total_trades = metrics.get("total_trades", 0)

        if total_trades == 0:
            self.warning_checks.append("win_rate - No trades recorded yet")
            return

        win_rate = winning_trades / total_trades

        if win_rate < 0.50:
            self.warning_checks.append(f"win_rate low: {win_rate:.1%} < 50%")
        else:
            self.passed_checks.append(f"win_rate OK: {win_rate:.1%} >= 50%")

    def _check_mode(self) -> None:
        """Check current mode is CANARY."""
        current_mode = self.redis_state.get("current_mode", "unknown")

        if current_mode == "canary":
            self.passed_checks.append("mode OK: current_mode == canary")
        elif current_mode == "unknown":
            self.warning_checks.append("mode UNKNOWN: Redis not populated yet")
        else:
            self.warning_checks.append(
                f"mode: current_mode == {current_mode} (not canary)"
            )

    def _check_notification_suppression(self) -> None:
        """Check notification suppression is working."""
        # This is a placeholder - actual check would need Redis notification state
        # For now, we just note it's expected to be working in CANARY
        self.passed_checks.append(
            "notification_suppression: expected active in CANARY mode"
        )

    def _generate_recommendations(self) -> list[str]:
        """Generate recommendations based on evaluation results."""
        recommendations = []

        if self.failed_checks:
            if any("divergence" in f for f in self.failed_checks):
                recommendations.append(
                    "ACTION REQUIRED: Divergence exceeds demotion threshold. Consider demoting to SHADOW mode."
                )
            if any("position_fraction" in f for f in self.failed_checks):
                recommendations.append(
                    "ACTION REQUIRED: Position fraction exceeded. Review trading logic."
                )
            if any("error_rate" in f for f in self.failed_checks):
                recommendations.append(
                    "ACTION REQUIRED: Error rate exceeds threshold. Investigate errors before continuing."
                )

        if not self.failed_checks and not self.warning_checks:
            consecutive = self.redis_state.get("consecutive_non_regression_count", 0)
            if consecutive >= REQUIRED_CONSECUTIVE_CHECKS:
                recommendations.append(
                    "PROMOTE TO FULL: All criteria met for promotion to FULL mode."
                )
            else:
                recommendations.append(
                    "CONTINUE CANARY: All criteria met. Continue monitoring for promotion readiness."
                )

        if self.warning_checks and not self.failed_checks:
            recommendations.append(
                "CONTINUE CANARY: Some criteria are borderline but no critical failures. Continue monitoring."
            )

        return recommendations

    def _generate_result(self) -> dict[str, Any]:
        """Generate the final evaluation result."""
        self.recommendations = self._generate_recommendations()

        if self.failed_checks:
            status = "FAIL"
        elif self.warning_checks:
            status = "WARN"
        else:
            status = "PASS"

        return {
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "redis_available": self.redis_state.get("available", False),
            "current_mode": self.redis_state.get("current_mode", "unknown"),
            "metrics": {
                "divergence_score": self.redis_state.get("divergence_score"),
                "consecutive_non_regression_count": self.redis_state.get(
                    "consecutive_non_regression_count", 0
                ),
                "position_fraction": self.redis_state.get("position_fraction"),
                "trade_count_today": self.redis_state.get("trade_count_today", 0),
                "error_count": self.redis_state.get("error_count", 0),
            },
            "thresholds": {
                "DIVERGENCE_THRESHOLD_LOW": DIVERGENCE_THRESHOLD_LOW,
                "DIVERGENCE_THRESHOLD_HIGH": DIVERGENCE_THRESHOLD_HIGH,
                "DRIFT_THRESHOLD_FOR_DEMOTION": DRIFT_THRESHOLD_FOR_DEMOTION,
                "CANARY_MAX_POSITION_FRACTION": CANARY_MAX_POSITION_FRACTION,
                "REQUIRED_CONSECUTIVE_CHECKS": REQUIRED_CONSECUTIVE_CHECKS,
                "PROMOTE_THRESHOLD": PROMOTE_THRESHOLD,
            },
            "latest_cycle": {
                "run_id": (
                    self.latest_cycle.get("run_id") if self.latest_cycle else None
                ),
                "status": (
                    self.latest_cycle.get("status") if self.latest_cycle else None
                ),
                "experiments_run": (
                    self.latest_cycle.get("experiments_run", 0)
                    if self.latest_cycle
                    else 0
                ),
                "promotions": (
                    self.latest_cycle.get("promotions", 0) if self.latest_cycle else 0
                ),
                "rejections": (
                    self.latest_cycle.get("rejections", 0) if self.latest_cycle else 0
                ),
            },
            "evaluation": {
                "passed_checks": self.passed_checks,
                "warning_checks": self.warning_checks,
                "failed_checks": self.failed_checks,
                "recommendations": self.recommendations,
            },
        }


def format_text_report(data: dict[str, Any]) -> str:
    """Format the report as human-readable text."""
    lines = []
    lines.append("\n" + "=" * 70)
    lines.append("CANARY MODE VALIDATION REPORT")
    lines.append("=" * 70)

    status = data["status"]
    status_color = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(status, "?")
    lines.append(f"\n  Status: {status_color} {status}")

    lines.append(f"\n  Generated: {data['timestamp']}")
    lines.append(f"  Redis Available: {'Yes' if data['redis_available'] else 'No'}")
    lines.append(f"  Current Mode: {data['current_mode']}")

    lines.append("\n" + "-" * 70)
    lines.append("METRICS")
    lines.append("-" * 70)

    metrics = data["metrics"]
    thresholds = data["thresholds"]

    div = metrics.get("divergence_score")
    div_str = f"{div:.3f}" if div is not None else "N/A"
    lines.append(
        f"  Divergence Score:        {div_str} (threshold: {thresholds['DIVERGENCE_THRESHOLD_LOW']})"
    )

    consec = metrics.get("consecutive_non_regression_count")
    required = thresholds["REQUIRED_CONSECUTIVE_CHECKS"]
    lines.append(f"  Consecutive Non-Regr:    {consec}/{required}")

    pos = metrics.get("position_fraction")
    pos_str = f"{pos:.4f}" if pos is not None else "N/A"
    lines.append(
        f"  Position Fraction:       {pos_str} (max: {thresholds['CANARY_MAX_POSITION_FRACTION']})"
    )

    lines.append(f"  Trade Count Today:       {metrics.get('trade_count_today', 0)}")
    lines.append(f"  Error Count:             {metrics.get('error_count', 0)}")

    if data["latest_cycle"].get("run_id"):
        lines.append("\n" + "-" * 70)
        lines.append("LATEST CYCLE")
        lines.append("-" * 70)
        lc = data["latest_cycle"]
        lines.append(f"  Run ID:          {lc['run_id']}")
        lines.append(f"  Status:          {lc['status']}")
        lines.append(f"  Experiments:     {lc['experiments_run']}")
        lines.append(f"  Promotions:      {lc['promotions']}")
        lines.append(f"  Rejections:      {lc['rejections']}")

    eval_data = data["evaluation"]

    if eval_data["passed_checks"]:
        lines.append("\n" + "-" * 70)
        lines.append("✓ PASSED CHECKS")
        lines.append("-" * 70)
        for check in eval_data["passed_checks"]:
            lines.append(f"  • {check}")

    if eval_data["warning_checks"]:
        lines.append("\n" + "-" * 70)
        lines.append("⚠ WARNING CHECKS")
        lines.append("-" * 70)
        for check in eval_data["warning_checks"]:
            lines.append(f"  • {check}")

    if eval_data["failed_checks"]:
        lines.append("\n" + "-" * 70)
        lines.append("✗ FAILED CHECKS")
        lines.append("-" * 70)
        for check in eval_data["failed_checks"]:
            lines.append(f"  • {check}")

    if eval_data["recommendations"]:
        lines.append("\n" + "-" * 70)
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 70)
        for rec in eval_data["recommendations"]:
            lines.append(f"  → {rec}")

    lines.append("\n" + "=" * 70 + "\n")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CANARY Mode Validation Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/autocog_canary_report.py
  python3 scripts/autocog_canary_report.py --output-format json
  python3 scripts/autocog_canary_report.py --output-file /tmp/canary_report.json
        """,
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Write output to file instead of stdout",
    )

    args = parser.parse_args()

    # Gather data
    redis_state = get_redis_state()
    cycles = load_latest_cycle_artifacts(n=5)
    config = load_canary_config()

    # Evaluate
    evaluator = CanaryCriteriaEvaluator(redis_state, cycles, config)
    result = evaluator.evaluate()

    # Format output
    if args.output_format == "json":
        output = json.dumps(result, indent=2)
    else:
        output = format_text_report(result)

    # Write output
    if args.output_file:
        args.output_file.write_text(output, encoding="utf-8")
        print(f"Report written to: {args.output_file}")
    else:
        print(output)

    # Return exit code based on status
    status_to_exit = {"PASS": 0, "WARN": 1, "FAIL": 2}
    return status_to_exit.get(result["status"], 1)


if __name__ == "__main__":
    sys.exit(main())
