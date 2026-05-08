#!/usr/bin/env python3
"""Smoke checker for experiment telemetry.

Validates that the experiment data collection is healthy before
running analysis or checkpoint evaluations.

Checks:
- Redis connectivity
- Signal counts meet minimum thresholds
- BOS/CHoCH signals are properly excluded
- Data freshness (recent signals collected)

Exit Codes:
    0: PASS - All checks passed
    1: FAIL - Some checks failed (below threshold)
    2: CRITICAL - Critical issues found (BOS/CHoCH detected)

Usage:
    python smoke_checker.py              # Human-readable output
    python smoke_checker.py --json       # JSON output for automation
    python smoke_checker.py --prometheus # Prometheus metrics format
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

# Import Redis state functions
from tools.redis_state import redis_state_hgetall, redis_state_llen, redis_state_lrange

# Redis key patterns (same as checkpoint_updater.py)
REDIS_KEYS = {
    "control_signals": "experiment:signals:control",
    "treatment_signals": "experiment:signals:treatment",
    "signal_prefix": "experiment:signal:",
    "outcome_prefix": "experiment:outcome:",
    "meta": "experiment:meta",
}

# Signal types no longer excluded (BL-BOS-CHOCH-001 lifted)
EXCLUDED_SIGNAL_TYPES: set[str] = set()

# Thresholds
MIN_SIGNALS = 10  # Minimum signals for basic smoke check
FRESHNESS_HOURS = 24  # Data should be refreshed within this time


class CheckResult(Enum):
    """Smoke check result categories."""

    PASS = "PASS"
    FAIL = "FAIL"
    CRITICAL = "CRITICAL"


# Exit codes mapping
EXIT_CODES = {
    CheckResult.PASS: 0,
    CheckResult.FAIL: 1,
    CheckResult.CRITICAL: 2,
}


def check_redis_connectivity() -> tuple[bool, str]:
    """Check if Redis is accessible.

    Returns:
        Tuple of (is_connected, message)
    """
    try:
        # Use llen on a known key as a lightweight connectivity check
        # This will return 0 if Redis is available but key doesn't exist
        # and will raise exception if Redis is unreachable
        redis_state_llen("experiment:signals:control")
        return True, "Redis connection successful"
    except Exception as e:
        return False, f"Redis connection error: {e}"


def get_signal_ids(group: str) -> list[str]:
    """Get list of signal IDs for a group from Redis.

    Args:
        group: 'control' or 'treatment'

    Returns:
        List of signal ID strings
    """
    key = (
        REDIS_KEYS["control_signals"]
        if group == "control"
        else REDIS_KEYS["treatment_signals"]
    )
    return redis_state_lrange(key, 0, -1)


def get_signal_data(signal_id: str) -> dict[str, Any]:
    """Get signal data from Redis.

    Args:
        signal_id: The signal ID

    Returns:
        Dictionary with signal data or empty dict if not found
    """
    key = f"{REDIS_KEYS['signal_prefix']}{signal_id}"
    return redis_state_hgetall(key)


def check_bos_choch_inclusion() -> tuple[bool, list[str]]:
    """Check if BOS/CHoCH signals are present in the data (now expected).

    Returns:
        Tuple of (has_bos_choch, found_types) where has_bos_choch is True
        if BOS/CHoCH signals were found in the data
    """
    found = set()

    for group in ["control", "treatment"]:
        signal_ids = get_signal_ids(group)
        for sig_id in signal_ids:
            signal = get_signal_data(sig_id)
            if signal:
                signal_type = signal.get("signal_type", "").lower()
                if signal_type in {"bos", "choch", "bos_choch"}:
                    found.add(f"{sig_id}:{signal_type}")

    return len(found) > 0, list(found)


def get_signal_counts() -> dict[str, int]:
    """Get total and group-specific signal counts.

    Returns:
        Dictionary with control_count, treatment_count, total_count
    """
    control_ids = get_signal_ids("control")
    treatment_ids = get_signal_ids("treatment")

    # Count non-excluded signals
    control_valid = 0
    for sig_id in control_ids:
        signal = get_signal_data(sig_id)
        if signal:
            signal_type = signal.get("signal_type", "").lower()
            if signal_type not in EXCLUDED_SIGNAL_TYPES:
                control_valid += 1

    treatment_valid = 0
    for sig_id in treatment_ids:
        signal = get_signal_data(sig_id)
        if signal:
            signal_type = signal.get("signal_type", "").lower()
            if signal_type not in EXCLUDED_SIGNAL_TYPES:
                treatment_valid += 1

    return {
        "control_count": control_valid,
        "treatment_count": treatment_valid,
        "total_count": control_valid + treatment_valid,
    }


def check_data_freshness() -> tuple[bool, str]:
    """Check if data has been collected recently.

    Returns:
        Tuple of (is_fresh, message)
    """
    try:
        meta = redis_state_hgetall(REDIS_KEYS["meta"])
        last_update = meta.get("last_update", "")

        if not last_update:
            # Try alternative field names
            last_update = meta.get("updated_at", "")
            if not last_update:
                last_update = meta.get("timestamp", "")

        if not last_update:
            return False, "No timestamp found in experiment metadata"

        # Parse timestamp
        try:
            update_time = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
        except ValueError:
            # Try unix timestamp
            try:
                update_time = datetime.fromtimestamp(float(last_update), tz=UTC)
            except (ValueError, TypeError):
                return False, f"Could not parse timestamp: {last_update}"

        now = datetime.now(UTC)
        age = now - update_time

        if age > timedelta(hours=FRESHNESS_HOURS):
            return (
                False,
                f"Data is {age.total_seconds() / 3600:.1f} hours old (threshold: {FRESHNESS_HOURS}h)",
            )

        return True, f"Data is {age.total_seconds() / 3600:.1f} hours old"

    except Exception as e:
        return False, f"Error checking data freshness: {e}"


def run_smoke_checks() -> dict[str, Any]:
    """Run all smoke checks.

    Returns:
        Dictionary with check results and overall status
    """
    results = {
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {},
        "overall_result": CheckResult.PASS.value,
        "messages": [],
    }

    # Check 1: Redis connectivity
    redis_ok, redis_msg = check_redis_connectivity()
    results["checks"]["redis_connectivity"] = {
        "status": "OK" if redis_ok else "FAIL",
        "message": redis_msg,
    }
    if not redis_ok:
        results["messages"].append(f"FAIL: {redis_msg}")
        results["overall_result"] = CheckResult.FAIL.value
        # Redis failure is not critical - could be transient
        return results

    # Check 2: BOS/CHoCH inclusion (now expected in pipeline)
    bos_choch_found, found_types = check_bos_choch_inclusion()
    results["checks"]["bos_choch_inclusion"] = {
        "status": "OK" if bos_choch_found else "WARN",
        "message": (
            f"BOS/CHoCH signals found: {found_types}"
            if bos_choch_found
            else "No BOS/CHoCH signals found yet (may appear later)"
        ),
        "found_types": found_types,
    }
    # BOS/CHoCH not found is a warning, not critical - they may not have triggered yet

    # Check 3: Signal counts
    counts = get_signal_counts()
    results["checks"]["signal_counts"] = {
        "status": "OK" if counts["total_count"] >= MIN_SIGNALS else "FAIL",
        "control_count": counts["control_count"],
        "treatment_count": counts["treatment_count"],
        "total_count": counts["total_count"],
        "minimum_required": MIN_SIGNALS,
        "message": f"Total: {counts['total_count']}, Control: {counts['control_count']}, Treatment: {counts['treatment_count']}",
    }
    if counts["total_count"] < MIN_SIGNALS:
        results["messages"].append(
            f"FAIL: Insufficient signals ({counts['total_count']} < {MIN_SIGNALS})"
        )
        if results["overall_result"] != CheckResult.CRITICAL:
            results["overall_result"] = CheckResult.FAIL.value

    # Check 4: Data freshness
    fresh_ok, fresh_msg = check_data_freshness()
    results["checks"]["data_freshness"] = {
        "status": "OK" if fresh_ok else "FAIL",
        "message": fresh_msg,
    }
    if not fresh_ok:
        results["messages"].append(f"FAIL: {fresh_msg}")
        if results["overall_result"] == CheckResult.PASS:
            results["overall_result"] = CheckResult.FAIL.value

    # Summary message
    if results["overall_result"] == CheckResult.PASS.value:
        results["summary"] = "All smoke checks passed"
    elif results["overall_result"] == CheckResult.FAIL.value:
        results["summary"] = "Some checks failed - review required"
    else:
        results["summary"] = (
            "Critical issues found - data collection may be compromised"
        )

    return results


def format_human_output(results: dict[str, Any]) -> str:
    """Format results as human-readable output.

    Args:
        results: Dictionary from run_smoke_checks()

    Returns:
        Formatted string
    """
    lines = [
        "=" * 60,
        "EXPERIMENT TELEMETRY SMOKE CHECK",
        "=" * 60,
        f"Timestamp: {results['timestamp']}",
        f"Overall Result: {results['overall_result']}",
        "",
        "-" * 60,
        "CHECK RESULTS",
        "-" * 60,
    ]

    for check_name, check_data in results["checks"].items():
        status_icon = {"OK": "✅", "FAIL": "⚠️", "CRITICAL": "❌"}.get(
            check_data["status"], "?"
        )
        lines.append(f"{status_icon} {check_name.replace('_', ' ').title()}")
        lines.append(f"   Status: {check_data['status']}")
        lines.append(f"   {check_data['message']}")
        if "found_excluded" in check_data and check_data["found_excluded"]:
            lines.append(f"   Found: {check_data['found_excluded']}")
        lines.append("")

    lines.extend(["-" * 60, "SUMMARY", "-" * 60])
    lines.append(results["summary"])
    lines.append("=" * 60)

    return "\n".join(lines)


def format_json_output(results: dict[str, Any]) -> str:
    """Format results as JSON.

    Args:
        results: Dictionary from run_smoke_checks()

    Returns:
        JSON string
    """

    def sanitize(val: Any) -> Any:
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val

    output = {
        "timestamp": results["timestamp"],
        "overall_result": results["overall_result"],
        "exit_code": EXIT_CODES.get(CheckResult(results["overall_result"]), 1),
        "summary": results["summary"],
        "checks": {},
        "messages": results["messages"],
    }

    for check_name, check_data in results["checks"].items():
        output["checks"][check_name] = {
            "status": check_data["status"],
            "message": check_data["message"],
        }
        if "control_count" in check_data:
            output["checks"][check_name]["control_count"] = check_data["control_count"]
            output["checks"][check_name]["treatment_count"] = check_data[
                "treatment_count"
            ]
            output["checks"][check_name]["total_count"] = check_data["total_count"]
        if "found_excluded" in check_data:
            output["checks"][check_name]["found_excluded"] = check_data[
                "found_excluded"
            ]

    return json.dumps(output, indent=2)


def format_prometheus_output(results: dict[str, Any]) -> str:
    """Format results as Prometheus metrics.

    Args:
        results: Dictionary from run_smoke_checks()

    Returns:
        Prometheus metrics format string
    """
    lines = [
        "# HELP experiment_smoke_check_result Smoke check result (0=PASS, 1=FAIL, 2=CRITICAL)",
        "# TYPE experiment_smoke_check_result gauge",
    ]

    result_value = EXIT_CODES.get(CheckResult(results["overall_result"]), 1)
    lines.append(
        f'experiment_smoke_check_result{{status="{results["overall_result"]}"}} {result_value}'
    )

    # Add individual check metrics
    for check_name, check_data in results["checks"].items():
        check_value = {"OK": 0, "FAIL": 1, "CRITICAL": 2}.get(check_data["status"], 0)
        sanitized_name = check_name.replace(" ", "_")
        lines.append(
            f'experiment_smoke_check_{{check="{sanitized_name}"}} {check_value}'
        )

        # Add count metrics if available
        if "total_count" in check_data:
            lines.append(
                f'experiment_signals_total{{group="all"}} {check_data["total_count"]}'
            )
            lines.append(
                f'experiment_signals_total{{group="control"}} {check_data["control_count"]}'
            )
            lines.append(
                f'experiment_signals_total{{group="treatment"}} {check_data["treatment_count"]}'
            )

    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Experiment telemetry smoke checker")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--prometheus", action="store_true", help="Output results in Prometheus format"
    )

    args = parser.parse_args()

    # Run smoke checks
    results = run_smoke_checks()

    # Output based on format
    if args.prometheus:
        print(format_prometheus_output(results))
    elif args.json:
        print(format_json_output(results))
    else:
        print(format_human_output(results))

    # Exit with appropriate code
    result = CheckResult(results["overall_result"])
    sys.exit(EXIT_CODES[result])


if __name__ == "__main__":
    main()
