#!/usr/bin/env python3
"""CI Diagnostics - System information and misconfiguration detection.

Collects:
- Python version and environment info
- Installed dependencies and versions
- Git state
- Docker/container status
- Common misconfiguration detection
- Diagnostic reports for troubleshooting

Usage:
    python scripts/ci/diagnostics.py
    python scripts/ci/diagnostics.py --format json
    python scripts/ci/diagnostics.py --check <check_name>
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class DiagnosticCheck:
    """Result of a single diagnostic check."""

    name: str
    passed: bool
    message: str
    details: dict | None = None
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DiagnosticReport:
    """Complete diagnostic report."""

    timestamp: str
    python_version: str
    platform: str
    working_directory: str
    git_branch: str
    git_dirty: bool
    checks: list[DiagnosticCheck] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


def get_python_version() -> str:
    """Get Python version info."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_platform_info() -> str:
    """Get platform information."""
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


def get_git_info() -> tuple[str, bool]:
    """Get current git branch and dirty state."""
    try:
        # Get branch name
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = result.stdout.strip() if result.returncode == 0 else "unknown"

        # Check if dirty
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        dirty = bool(result.stdout.strip())

        return branch, dirty
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown", False


def check_python_path() -> DiagnosticCheck:
    """Check if Python is in PATH and virtual environment is active."""
    python_path = sys.executable
    in_venv = sys.prefix != sys.base_prefix

    passed = True
    message = "Python environment OK"
    recommendations = []

    if not in_venv:
        passed = False
        message = "Not running in a virtual environment"
        recommendations.append(
            "Consider using a virtual environment: python -m venv .venv && source .venv/bin/activate"
        )

    if "venv" in python_path.lower() or ".venv" in python_path:
        message = f"Virtual environment: {python_path}"
    else:
        message = f"System Python: {python_path}"

    return DiagnosticCheck(
        name="python_path",
        passed=passed,
        message=message,
        details={"python_path": python_path, "in_venv": in_venv},
        recommendations=recommendations,
    )


def check_git_state() -> DiagnosticCheck:
    """Check git repository state."""
    branch, dirty = get_git_info()

    passed = not dirty
    message = f"On branch '{branch}'"
    recommendations = []

    if dirty:
        passed = False
        message += " (has uncommitted changes)"
        recommendations.append("Commit or stash changes before running CI")

    return DiagnosticCheck(
        name="git_state",
        passed=passed,
        message=message,
        details={"branch": branch, "dirty": dirty},
        recommendations=recommendations,
    )


def check_dependencies() -> DiagnosticCheck:
    """Check if key dependencies are installed and at correct versions."""
    critical_deps = [
        "pytest",
        "black",
        "ruff",
        "mypy",
        "pip",
    ]

    missing: list[str] = []
    found: dict[str, str] = {}

    for dep in critical_deps:
        try:
            result = subprocess.run(
                [sys.executable, "-m", dep, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                found[dep] = version_line
            else:
                missing.append(dep)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            missing.append(dep)

    passed = len(missing) == 0
    message = f"Found {len(found)}/{len(critical_deps)} critical dependencies"

    recommendations = []
    if missing:
        recommendations.append(f"Install missing: pip install {' '.join(missing)}")

    return DiagnosticCheck(
        name="dependencies",
        passed=passed,
        message=message,
        details={"found": found, "missing": missing},
        recommendations=recommendations,
    )


def check_file_permissions() -> DiagnosticCheck:
    """Check if scripts are executable."""
    scripts_dir = Path(__file__).parent
    non_executable: list[str] = []

    for script in scripts_dir.glob("*.py"):
        if not os.access(script, os.X_OK):
            non_executable.append(str(script.name))

    passed = len(non_executable) == 0
    message = (
        "All scripts executable"
        if passed
        else f"{len(non_executable)} scripts not executable"
    )

    recommendations = []
    if non_executable:
        recommendations.append(f"Run: chmod +x {' '.join(non_executable)}")

    return DiagnosticCheck(
        name="file_permissions",
        passed=passed,
        message=message,
        details={"non_executable": non_executable},
        recommendations=recommendations,
    )


def check_docker_connectivity() -> DiagnosticCheck:
    """Check Docker daemon connectivity."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        passed = result.returncode == 0
        message = (
            "Docker daemon connected" if passed else "Docker daemon not accessible"
        )
        details = {}

        if passed and "Server Version" in result.stdout:
            for line in result.stdout.split("\n"):
                if "Server Version" in line:
                    details["server_version"] = line.split(":")[1].strip()

        recommendations = []
        if not passed:
            recommendations.append(
                "Ensure Docker daemon is running: sudo systemctl start docker"
            )

        return DiagnosticCheck(
            name="docker_connectivity",
            passed=passed,
            message=message,
            details=details,
            recommendations=recommendations,
        )
    except FileNotFoundError:
        return DiagnosticCheck(
            name="docker_connectivity",
            passed=True,
            message="Docker not installed (skipped)",
            details={},
            recommendations=[],
        )
    except subprocess.TimeoutExpired:
        return DiagnosticCheck(
            name="docker_connectivity",
            passed=False,
            message="Docker daemon not responding",
            recommendations=["Check Docker daemon: sudo systemctl status docker"],
        )


def check_environment_vars() -> DiagnosticCheck:
    """Check for required environment variables."""
    required = ["PATH", "HOME", "USER"]
    optional = ["CI", "GITEA_TOKEN", "REDIS_HOST"]

    missing_required: list[str] = []
    present_optional: dict[str, str] = {}

    for var in required:
        if not os.environ.get(var):
            missing_required.append(var)

    for var in optional:
        value = os.environ.get(var)
        if value:
            # Mask sensitive values
            if "TOKEN" in var or "SECRET" in var or "PASSWORD" in var:
                present_optional[var] = "***"
            else:
                present_optional[var] = value

    passed = len(missing_required) == 0
    message = (
        "Environment OK"
        if passed
        else f"Missing required: {', '.join(missing_required)}"
    )

    recommendations = []
    if missing_required:
        recommendations.append("Set missing environment variables before running CI")

    return DiagnosticCheck(
        name="environment_vars",
        passed=passed,
        message=message,
        details={
            "present_optional": present_optional,
            "missing_required": missing_required,
        },
        recommendations=recommendations,
    )


def check_woodpecker_config() -> DiagnosticCheck:
    """Check Woodpecker CI configuration if present."""
    woodpecker_paths = [
        Path(".woodpecker/ci.yaml"),
        Path(".woodpecker.yml"),
        Path(".woodpecker.yaml"),
    ]

    config_found = None
    for path in woodpecker_paths:
        if path.exists():
            config_found = str(path)
            break

    passed = config_found is not None
    message = (
        f"Woodpecker config: {config_found}"
        if config_found
        else "No Woodpecker config found"
    )

    recommendations = []
    if not config_found:
        recommendations.append("Create .woodpecker/ci.yaml for CI configuration")

    return DiagnosticCheck(
        name="woodpecker_config",
        passed=passed,
        message=message,
        details={"config_path": config_found},
        recommendations=recommendations,
    )


def check_local_ci_files() -> DiagnosticCheck:
    """Check for presence of local CI scripts."""
    ci_scripts = [
        "scripts/ci/ci_gate.py",
        "scripts/ci/pre_push_gate.py",
        "scripts/ci/dependency_audit.py",
    ]

    missing: list[str] = []
    found: list[str] = []

    for script in ci_scripts:
        if Path(script).exists():
            found.append(script)
        else:
            missing.append(script)

    passed = len(missing) == 0
    message = f"Found {len(found)}/{len(ci_scripts)} CI scripts"

    recommendations = []
    if missing:
        recommendations.append(f"Missing CI scripts: {', '.join(missing)}")

    return DiagnosticCheck(
        name="local_ci_files",
        passed=passed,
        message=message,
        details={"found": found, "missing": missing},
        recommendations=recommendations,
    )


def run_all_checks() -> DiagnosticReport:
    """Run all diagnostic checks and compile report."""
    checks = [
        check_python_path,
        check_git_state,
        check_dependencies,
        check_file_permissions,
        check_docker_connectivity,
        check_environment_vars,
        check_woodpecker_config,
        check_local_ci_files,
    ]

    results: list[DiagnosticCheck] = []
    for check_fn in checks:
        try:
            result = check_fn()
        except Exception as e:
            result = DiagnosticCheck(
                name=check_fn.__name__,
                passed=False,
                message=f"Check failed with error: {str(e)}",
            )
        results.append(result)

    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count

    return DiagnosticReport(
        timestamp=datetime.now().isoformat(),
        python_version=get_python_version(),
        platform=get_platform_info(),
        working_directory=str(Path.cwd()),
        git_branch=get_git_info()[0],
        git_dirty=get_git_info()[1],
        checks=results,
        summary={"passed": passed_count, "failed": failed_count, "total": len(results)},
    )


def format_report_text(report: DiagnosticReport) -> str:
    """Format report as human-readable text."""
    lines = [
        "=" * 60,
        "CI DIAGNOSTIC REPORT",
        "=" * 60,
        f"Timestamp: {report.timestamp}",
        f"Python: {report.python_version}",
        f"Platform: {report.platform}",
        f"Directory: {report.working_directory}",
        f"Git: {report.git_branch} (dirty={report.git_dirty})",
        "",
        f"Checks: {report.summary['passed']} passed, {report.summary['failed']} failed",
        "",
        "-" * 60,
        "CHECK RESULTS",
        "-" * 60,
        "",
    ]

    for check in report.checks:
        status = "✓ PASS" if check.passed else "✗ FAIL"
        lines.append(f"{status} - {check.name}")
        lines.append(f"       {check.message}")
        if check.recommendations:
            for rec in check.recommendations[:2]:
                lines.append(f"       → {rec}")
        lines.append("")

    lines.append("-" * 60)
    return "\n".join(lines)


def format_report_json(report: DiagnosticReport) -> str:
    """Format report as JSON."""
    return json.dumps(asdict(report), indent=2)


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="CI Diagnostics Tool")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--check",
        help="Run a specific check only",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Return exit code 1 if any check fails",
    )
    args = parser.parse_args()

    if args.check:
        # Run single check
        check_map = {
            "python_path": check_python_path,
            "git_state": check_git_state,
            "dependencies": check_dependencies,
            "file_permissions": check_file_permissions,
            "docker_connectivity": check_docker_connectivity,
            "environment_vars": check_environment_vars,
            "woodpecker_config": check_woodpecker_config,
            "local_ci_files": check_local_ci_files,
        }
        if args.check not in check_map:
            print(f"Unknown check: {args.check}")
            print(f"Available: {', '.join(check_map.keys())}")
            return 1

        result = check_map[args.check]()
        print(f"{'PASS' if result.passed else 'FAIL'}: {result.name}")
        print(f"  {result.message}")
        for rec in result.recommendations:
            print(f"  → {rec}")
        return 0 if result.passed else 1

    # Run all checks
    report = run_all_checks()

    if args.format == "json":
        print(format_report_json(report))
    else:
        print(format_report_text(report))

    if args.check_only or "--check" in sys.argv:
        return 0 if report.summary["failed"] == 0 else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
