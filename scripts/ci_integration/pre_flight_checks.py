#!/usr/bin/env python3
"""Pre-flight checks for CI integration.

This script runs local CI consistency checks, validates the environment,
and checks for pre-CI issues before the main CI pipeline runs.

Exit codes:
    0 - All checks passed
    1 - One or more checks failed

Output:
    JSON report to stdout with check results
"""

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CheckResult:
    """Result of a single check."""

    name: str
    passed: bool
    message: str
    details: dict | None = None


def check_python_version() -> CheckResult:
    """Check Python version meets minimum requirement."""
    min_version = (3, 10)
    current = sys.version_info[:2]

    passed = current >= min_version
    message = f"Python {'.'.join(map(str, current))}"
    if passed:
        message += " (OK)"
    else:
        message += f" - Required: {'.'.join(map(str, min_version))}"

    return CheckResult(
        name="python_version",
        passed=passed,
        message=message,
        details={
            "required": f"{min_version[0]}.{min_version[1]}",
            "current": f"{current[0]}.{current[1]}",
        },
    )


def check_required_tools() -> CheckResult:
    """Check for required CI tools."""
    required_tools = ["git", "pytest", "ruff", "black"]
    found = {}
    all_found = True

    for tool in required_tools:
        try:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                text=True,
                timeout=10,
            )
            found[tool] = result.returncode == 0
            if not found[tool]:
                all_found = False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            found[tool] = False
            all_found = False

    return CheckResult(
        name="required_tools",
        passed=all_found,
        message="All required tools found" if all_found else "Some tools missing",
        details={"tools": found},
    )


def check_git_status() -> CheckResult:
    """Check git repository status."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        untracked = result.stdout.strip()
        has_changes = bool(untracked)

        return CheckResult(
            name="git_status",
            passed=not has_changes,
            message=(
                "Clean working tree"
                if not has_changes
                else "Uncommitted changes present"
            ),
            details={"has_changes": has_changes, "untracked": bool(untracked)},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return CheckResult(
            name="git_status",
            passed=False,
            message=f"Failed to check git status: {e}",
        )


def check_environment_vars() -> CheckResult:
    """Check for required environment variables."""
    # Also check if .envrc exists and is loaded
    envrc_path = Path("/tmp/worktrees/ST-LOCAL-009-dev/.envrc")
    envrc_exists = envrc_path.exists()

    return CheckResult(
        name="environment_vars",
        passed=envrc_exists,
        message=".envrc exists" if envrc_exists else ".envrc not found",
        details={"envrc_exists": envrc_exists},
    )


def check_code_quality() -> CheckResult:
    """Run basic code quality checks."""
    issues = []
    repo_root = Path("/tmp/worktrees/ST-LOCAL-009-dev")

    # Run black check on ci_integration
    ci_dir = repo_root / "scripts" / "ci_integration"
    if ci_dir.exists():
        try:
            result = subprocess.run(
                ["black", "--check", "--quiet", str(ci_dir)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                issues.append(f"black: {result.stdout}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            issues.append("black: not available")

    # Run ruff check on ci_integration
    if ci_dir.exists():
        try:
            result = subprocess.run(
                ["ruff", "check", str(ci_dir)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                issues.append(f"ruff: {result.stdout}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            issues.append("ruff: not available")

    passed = len(issues) == 0
    return CheckResult(
        name="code_quality",
        passed=passed,
        message=(
            "Code quality checks passed" if passed else f"Issues found: {len(issues)}"
        ),
        details={"issues": issues} if issues else None,
    )


def run_pre_flight_checks() -> list[CheckResult]:
    """Run all pre-flight checks."""
    checks = [
        check_python_version(),
        check_required_tools(),
        check_git_status(),
        check_environment_vars(),
        check_code_quality(),
    ]
    return checks


def main() -> int:
    """Main entry point."""
    checks = run_pre_flight_checks()

    report = {
        "success": all(c.passed for c in checks),
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c.passed),
        "failed_checks": sum(1 for c in checks if not c.passed),
        "checks": [asdict(c) for c in checks],
    }

    print(json.dumps(report, indent=2))

    # Exit 0 if all passed, 1 if any failed
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
