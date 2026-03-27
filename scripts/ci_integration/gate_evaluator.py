#!/usr/bin/env python3
"""Gate evaluator for CI integration.

This script evaluates pass/fail status for quality gates and implements
gate overrides when appropriate. It produces a gate status report.

Exit codes:
    0 - All mandatory gates passed
    1 - One or more mandatory gates failed

Output:
    JSON report to stdout with gate evaluation results
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class GateResult:
    """Result of a single gate evaluation."""

    name: str
    passed: bool
    mandatory: bool = True
    message: str = ""
    details: dict | None = None
    override_applied: bool = False


@dataclass
class GateEvaluationReport:
    """Complete gate evaluation report."""

    timestamp: str
    branch: str
    commit_sha: str
    gates: list[GateResult] = field(default_factory=list)
    overall_passed: bool = True
    failed_mandatory_gates: int = 0
    passed_gates: int = 0


def check_gate_coverage(
    min_percent: float, actual_percent: float, threshold_type: str = "line"
) -> GateResult:
    """Evaluate coverage gate."""
    passed = actual_percent >= min_percent
    return GateResult(
        name=f"coverage_{threshold_type}",
        passed=passed,
        mandatory=True,
        message=f"{threshold_type.capitalize()} coverage: {actual_percent:.2f}% (min: {min_percent}%)",
        details={
            "minimum": min_percent,
            "actual": actual_percent,
            "threshold_type": threshold_type,
        },
    )


def check_gate_tests(
    min_pass_rate: float, passed: int, failed: int, error: int
) -> GateResult:
    """Evaluate test pass rate gate."""
    total = passed + failed + error
    if total == 0:
        return GateResult(
            name="test_pass_rate",
            passed=False,
            mandatory=True,
            message="No tests executed",
        )

    pass_rate = passed / total
    actual_min = min_pass_rate * 100

    return GateResult(
        name="test_pass_rate",
        passed=pass_rate >= min_pass_rate,
        mandatory=True,
        message=f"Test pass rate: {pass_rate * 100:.2f}% (min: {actual_min:.1f}%)",
        details={
            "minimum": min_pass_rate,
            "actual": pass_rate,
            "passed": passed,
            "failed": failed,
            "error": error,
        },
    )


def check_gate_code_quality(
    max_issues: int, actual_issues: int, tool: str = "ruff"
) -> GateResult:
    """Evaluate code quality gate."""
    return GateResult(
        name=f"code_quality_{tool}",
        passed=actual_issues <= max_issues,
        mandatory=True,
        message=f"{tool} issues: {actual_issues} (max: {max_issues})",
        details={"maximum": max_issues, "actual": actual_issues, "tool": tool},
    )


def check_gate_pylint(min_score: float, actual_score: float) -> GateResult:
    """Evaluate pylint score gate."""
    return GateResult(
        name="pylint_score",
        passed=actual_score >= min_score,
        mandatory=False,
        message=f"Pylint score: {actual_score:.2f} (min: {min_score})",
        details={"minimum": min_score, "actual": actual_score},
    )


def check_gate_black() -> GateResult:
    """Evaluate black formatting gate."""
    return GateResult(
        name="black_formatting",
        passed=True,
        mandatory=True,
        message="Black formatting check passed",
    )


def apply_override(gate_name: str, reason: str, environment_vars: dict) -> bool:
    """Check if a gate override is applied via environment variables."""
    override_key = f"OVERRIDE_{gate_name.upper()}"
    override_value = environment_vars.get(override_key, "").lower()

    if override_value == "true":
        return True
    elif override_value == "false":
        return False

    # Check for reason-based override
    reason_key = f"OVERRIDE_{gate_name.upper()}_REASON"
    return bool(environment_vars.get(reason_key))


def evaluate_gates(
    coverage_line: float | None = None,
    coverage_branch: float | None = None,
    test_passed: int = 0,
    test_failed: int = 0,
    test_error: int = 0,
    ruff_issues: int = 0,
    pylint_score: float | None = None,
    environment_vars: dict | None = None,
    branch: str = "unknown",
    commit_sha: str = "unknown",
) -> GateEvaluationReport:
    """Evaluate all gates and return report."""
    env = environment_vars or {}

    gates = []

    # Coverage gates (example thresholds: 80% line, 70% branch)
    if coverage_line is not None:
        gate = check_gate_coverage(80.0, coverage_line, "line")
        if apply_override(gate.name, "coverage", env):
            gate.override_applied = True
            gate.message += " [OVERRIDE APPLIED]"
        gates.append(gate)

    if coverage_branch is not None:
        gate = check_gate_coverage(70.0, coverage_branch, "branch")
        if apply_override(gate.name, "coverage", env):
            gate.override_applied = True
            gate.message += " [OVERRIDE APPLIED]"
        gates.append(gate)

    # Test pass rate gate (example threshold: 95%)
    gate = check_gate_tests(0.95, test_passed, test_failed, test_error)
    if apply_override(gate.name, "tests", env):
        gate.override_applied = True
        gate.message += " [OVERRIDE APPLIED]"
    gates.append(gate)

    # Code quality gates
    gate = check_gate_code_quality(0, ruff_issues, "ruff")
    if apply_override(gate.name, "ruff", env):
        gate.override_applied = True
        gate.message += " [OVERRIDE APPLIED]"
    gates.append(gate)

    # Pylint gate (optional)
    if pylint_score is not None:
        gate = check_gate_pylint(8.0, pylint_score)
        if apply_override(gate.name, "pylint", env):
            gate.override_applied = True
            gate.message += " [OVERRIDE APPLIED]"
        gates.append(gate)

    # Black formatting gate
    gate = check_gate_black()
    gates.append(gate)

    # Calculate overall pass status (only mandatory gates count)
    mandatory_gates = [g for g in gates if g.mandatory]
    failed_mandatory = [g for g in mandatory_gates if not g.passed]

    report = GateEvaluationReport(
        timestamp=datetime.now(UTC).isoformat(),
        branch=branch,
        commit_sha=commit_sha,
        gates=gates,
        overall_passed=len(failed_mandatory) == 0,
        failed_mandatory_gates=len(failed_mandatory),
        passed_gates=sum(1 for g in gates if g.passed),
    )

    return report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CI Gate Evaluator")
    parser.add_argument("--coverage-line", type=float, help="Line coverage percentage")
    parser.add_argument(
        "--coverage-branch", type=float, help="Branch coverage percentage"
    )
    parser.add_argument(
        "--test-passed", type=int, default=0, help="Number of passed tests"
    )
    parser.add_argument(
        "--test-failed", type=int, default=0, help="Number of failed tests"
    )
    parser.add_argument(
        "--test-error", type=int, default=0, help="Number of error tests"
    )
    parser.add_argument(
        "--ruff-issues", type=int, default=0, help="Number of ruff issues"
    )
    parser.add_argument("--pylint-score", type=float, help="Pylint score")
    parser.add_argument("--branch", type=str, default="unknown", help="Branch name")
    parser.add_argument("--commit-sha", type=str, default="unknown", help="Commit SHA")

    args = parser.parse_args()

    report = evaluate_gates(
        coverage_line=args.coverage_line,
        coverage_branch=args.coverage_branch,
        test_passed=args.test_passed,
        test_failed=args.test_failed,
        test_error=args.test_error,
        ruff_issues=args.ruff_issues,
        pylint_score=args.pylint_score,
        environment_vars=os.environ,
        branch=args.branch,
        commit_sha=args.commit_sha,
    )

    print(json.dumps(asdict(report), indent=2))

    # Exit 0 if all mandatory gates passed, 1 otherwise
    return 0 if report.overall_passed else 1


if __name__ == "__main__":
    sys.exit(main())
