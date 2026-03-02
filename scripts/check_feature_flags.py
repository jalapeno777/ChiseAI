#!/usr/bin/env python3
"""Feature Flags Active Check for PAPER-ACTIVATE-003.

This script verifies that all required feature flags are properly configured
in Redis for the Day-0 activation checklist.
"""

import sys
import tempfile
from pathlib import Path

WORKTREE_PATH = (
    Path(tempfile.gettempdir()) / "worktrees" / "PAPER-ACTIVATE-003-quickdev"
)

# Required feature flags from MEMORY_CONTEXT
LAUNCH_SAFETY_FLAGS = [
    "launch:safety:enabled",
    "launch:safety:circuit_breaker:enabled",
    "launch:safety:order_idempotency:enabled",
    "launch:safety:assertions:enabled",
]

LAUNCH_FEEDBACK_FLAGS = [
    "launch:feedback:enabled",
    "launch:feedback:signal_capture:enabled",
    "launch:feedback:ece_updates:enabled",
    "launch:feedback:auto_threshold:enabled",
]

LAUNCH_TRAINING_FLAGS = [
    "launch:training:enabled",
    "launch:training:pipeline:enabled",
    "launch:training:auto_trigger:enabled",
    "launch:training:auto_rollback:enabled",
]

NEURO_SYMBOLIC_FLAGS = [
    "neuro_symbolic:enabled",
    "neuro_symbolic:hybrid_reasoning:enabled",
    "neuro_symbolic:explainability:enabled",
    "neuro_symbolic:adaptive_learning:enabled",
    "neuro_symbolic:knowledge_graph:enabled",
    "neuro_symbolic:pattern_recognition:enabled",
    "neuro_symbolic:multimodal_fusion:enabled",
]

SELF_EVOLUTION_FLAGS = [
    "self_evolution:enabled",
    "self_evolution:auto_calibration:enabled",
    "self_evolution:model_retraining:enabled",
]


def check_redis_hash_flag(key: str, field: str = "enabled") -> tuple[str, str]:
    """Check a feature flag stored as a Redis hash field."""
    try:
        import subprocess

        result = subprocess.run(  # nosec B607
            [
                "python3",
                "-c",
                f"""
import sys
sys.path.insert(0, '.')
from tools.redis_state import redis_state_hget
value = redis_state_hget("{key}", "{field}")
print(value if value else "NOT_FOUND")
""",
            ],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_PATH),
        )
        value = result.stdout.strip()
        if value == "NOT_FOUND" or not value:
            return ("NOT_FOUND", "Flag not found in Redis")
        elif value in ("1", "true", "True", "yes", "on"):
            return ("ENABLED", f"Value: {value}")
        elif value in ("0", "false", "False", "no", "off"):
            return ("DISABLED", f"Value: {value}")
        else:
            return ("UNKNOWN", f"Value: {value}")
    except Exception as e:
        return ("ERROR", str(e))


def check_redis_string_flag(key: str) -> tuple[str, str]:
    """Check a feature flag stored as a Redis string."""
    try:
        import subprocess

        result = subprocess.run(  # nosec B607
            [
                "python3",
                "-c",
                f"""
import sys
sys.path.insert(0, '.')
from tools.redis_state import redis_state_get
value = redis_state_get("{key}")
print(value if value else "NOT_FOUND")
""",
            ],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_PATH),
        )
        value = result.stdout.strip()
        if value == "NOT_FOUND" or not value:
            return ("NOT_FOUND", "Flag not found in Redis")
        elif value in ("1", "true", "True", "yes", "on"):
            return ("ENABLED", f"Value: {value}")
        elif value in ("0", "false", "False", "no", "off"):
            return ("DISABLED", f"Value: {value}")
        else:
            return ("UNKNOWN", f"Value: {value}")
    except Exception as e:
        return ("ERROR", str(e))


def check_flag(flag: str) -> tuple[str, str]:
    """Check a feature flag, trying both hash and string formats."""
    # Try hash format first (e.g., launch:safety with field "enabled")
    if ":" in flag:
        parts = flag.rsplit(":", 1)
        if len(parts) == 2 and parts[1] == "enabled":
            key = parts[0]
            status, info = check_redis_hash_flag(key, "enabled")
            if status != "NOT_FOUND":
                return status, info

    # Try as string key
    return check_redis_string_flag(flag)


def print_section(title: str, flags: list[str]) -> dict[str, tuple[str, str]]:
    """Print a section of feature flags."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")

    results = {}
    for flag in flags:
        status, info = check_flag(flag)
        results[flag] = (status, info)
        symbol = "✅" if status == "ENABLED" else "⚠️" if status == "DISABLED" else "❌"
        print(f"  {symbol} {flag:50s} [{status}]")
        if info and info != f"Value: {status}":
            print(f"      └─ {info}")

    return results


def main():
    print("=" * 60)
    print("  FEATURE FLAGS ACTIVE CHECK - PAPER-ACTIVATE-003")
    print("  Day-0 Activation Checklist Item 1.3")
    print("=" * 60)

    all_results = {}

    # Check Launch Safety Flags (EP-LAUNCH-001)
    all_results.update(
        print_section("EP-LAUNCH-001: Safety Features", LAUNCH_SAFETY_FLAGS)
    )

    # Check Launch Feedback Flags (EP-LAUNCH-002)
    all_results.update(
        print_section("EP-LAUNCH-002: Feedback Loop", LAUNCH_FEEDBACK_FLAGS)
    )

    # Check Launch Training Flags (EP-LAUNCH-003)
    all_results.update(
        print_section("EP-LAUNCH-003: Training Integration", LAUNCH_TRAINING_FLAGS)
    )

    # Check Neuro-Symbolic Flags
    all_results.update(print_section("Neuro-Symbolic Components", NEURO_SYMBOLIC_FLAGS))

    # Check Self-Evolution Flags
    all_results.update(print_section("Self-Evolution Features", SELF_EVOLUTION_FLAGS))

    # Summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")

    enabled_count = sum(1 for status, _ in all_results.values() if status == "ENABLED")
    disabled_count = sum(
        1 for status, _ in all_results.values() if status == "DISABLED"
    )
    not_found_count = sum(
        1 for status, _ in all_results.values() if status == "NOT_FOUND"
    )
    error_count = sum(1 for status, _ in all_results.values() if status == "ERROR")

    print(f"  Total Flags Checked: {len(all_results)}")
    print(f"  ✅ ENABLED: {enabled_count}")
    print(f"  ⚠️  DISABLED: {disabled_count}")
    print(f"  ❌ NOT FOUND: {not_found_count}")
    print(f"  💥 ERRORS: {error_count}")

    # Critical missing flags
    critical_missing = []
    for flag in LAUNCH_SAFETY_FLAGS + LAUNCH_FEEDBACK_FLAGS + LAUNCH_TRAINING_FLAGS:
        if flag in all_results and all_results[flag][0] != "ENABLED":
            critical_missing.append(flag)

    if critical_missing:
        print("\n  ⚠️  CRITICAL FLAGS NOT ENABLED:")
        for flag in critical_missing:
            print(f"      - {flag} [{all_results[flag][0]}]")
    else:
        print("\n  ✅ All critical launch flags are ENABLED")

    print(f"\n{'=' * 60}")

    # Return exit code
    if error_count > 0 or not_found_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
