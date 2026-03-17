#!/usr/bin/env python3
"""
Blocking Gates Runner - CI Blocking Gates Integration
Story: BATCH-3 CI-002-A

Runs blocking gates in CI pipeline. This is the server-side validation
that determines if a build passes or fails.

Exit codes:
    0: All blocking gates passed
    1: One or more blocking gates failed
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class GateResult:
    """Result of a single gate execution."""

    name: str
    passed: bool
    exit_code: int
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""
    error_message: Optional[str] = None


@dataclass
class GatesReport:
    """Complete report of all gate executions."""

    overall_passed: bool = False
    gates: List[GateResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "overall_passed": self.overall_passed,
            "total_duration_seconds": self.total_duration_seconds,
            "metadata": self.metadata,
            "gates": [
                {
                    "name": g.name,
                    "passed": g.passed,
                    "exit_code": g.exit_code,
                    "duration_seconds": g.duration_seconds,
                    "error_message": g.error_message,
                }
                for g in self.gates
            ],
        }


class BlockingGatesRunner:
    """Runs blocking gates for CI pipeline validation."""

    # Define blocking gates - these MUST pass
    BLOCKING_GATES = [
        "swarm-context",
        "lint",
        "security-scan",
        "dependency-audit",
        "secret-scan",
        "risk-invariants",
        "brain-regression",
        "docs-pairing",
        "docker-governance",
        "changed-lines-coverage",
        "status-write-gate",
        "performance-gate",
        "evidence-gate",
    ]

    # Gates that only block on main/cron or when FORCE_FULL_GATE=1
    FULL_ONLY_GATES = [
        "local-ci",
        "brain-eval",
    ]

    def __init__(
        self,
        verbose: bool = False,
        ci_status_dir: Optional[str] = None,
        force_full: bool = False,
    ):
        self.verbose = verbose
        self.ci_status_dir = ci_status_dir or os.environ.get(
            "CI_STATUS_DIR", "/tmp/ci-status"
        )
        self.force_full = force_full or os.environ.get("CI_FORCE_FULL", "0") == "1"
        self.report = GatesReport()

    def log(self, message: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[blocking-gates] {message}")

    def read_status_file(self, gate_name: str) -> Optional[Tuple[int, str]]:
        """Read the status file for a gate."""
        status_file = Path(self.ci_status_dir) / f"{gate_name}.status"
        log_file = Path(self.ci_status_dir) / f"{gate_name}.log"

        if not status_file.exists():
            self.log(f"Status file not found: {status_file}")
            return None

        try:
            exit_code = int(status_file.read_text().strip())
            log_content = log_file.read_text() if log_file.exists() else ""
            return exit_code, log_content
        except (ValueError, IOError) as e:
            self.log(f"Error reading status file: {e}")
            return None

    def run_gate(self, gate_name: str) -> GateResult:
        """Run a single gate and return the result."""
        print(f"→ Checking gate: {gate_name}")
        start_time = __import__("time").time()

        status = self.read_status_file(gate_name)

        if status is None:
            # Gate hasn't run yet or status file missing
            duration = __import__("time").time() - start_time
            return GateResult(
                name=gate_name,
                passed=False,
                exit_code=-1,
                duration_seconds=duration,
                error_message="Status file not found - gate did not run",
            )

        exit_code, log_content = status
        duration = __import__("time").time() - start_time

        # Determine if this gate should block
        should_block = gate_name in self.BLOCKING_GATES
        if gate_name in self.FULL_ONLY_GATES and not self.force_full:
            should_block = False
            self.log(f"Gate {gate_name} is full-only, skipping block in PR mode")

        passed = exit_code == 0

        if passed:
            print(f"  ✓ {gate_name} passed")
        elif should_block:
            print(f"  ✗ {gate_name} FAILED (blocking)")
        else:
            print(f"  ⚠ {gate_name} failed (non-blocking)")

        return GateResult(
            name=gate_name,
            passed=passed,
            exit_code=exit_code,
            duration_seconds=duration,
            stdout=log_content[:1000] if log_content else "",  # Truncate for report
            error_message=None if passed else f"Exit code: {exit_code}",
        )

    def run_all_gates(self) -> GatesReport:
        """Run all gates and generate report."""
        print("=" * 60)
        print("Blocking Gates Runner")
        print("=" * 60)
        print("")

        # Collect metadata
        self.report.metadata = {
            "ci_status_dir": self.ci_status_dir,
            "force_full": self.force_full,
            "blocking_gates": self.BLOCKING_GATES,
            "full_only_gates": self.FULL_ONLY_GATES,
        }

        # Run all gates
        all_gates = self.BLOCKING_GATES + self.FULL_ONLY_GATES
        start_time = __import__("time").time()

        for gate_name in all_gates:
            result = self.run_gate(gate_name)
            self.report.gates.append(result)

        self.report.total_duration_seconds = __import__("time").time() - start_time

        # Determine overall result
        blocking_results = [
            g for g in self.report.gates if g.name in self.BLOCKING_GATES
        ]
        self.report.overall_passed = all(g.passed for g in blocking_results)

        return self.report

    def print_summary(self) -> None:
        """Print a summary of all gate results."""
        print("\n" + "=" * 60)
        print("Gates Summary")
        print("=" * 60)

        blocking_passed = 0
        blocking_failed = 0
        full_only_passed = 0
        full_only_failed = 0

        for gate in self.report.gates:
            if gate.name in self.BLOCKING_GATES:
                if gate.passed:
                    blocking_passed += 1
                else:
                    blocking_failed += 1
            elif gate.name in self.FULL_ONLY_GATES:
                if gate.passed:
                    full_only_passed += 1
                else:
                    full_only_failed += 1

        print(f"\nBlocking Gates: {blocking_passed} passed, {blocking_failed} failed")
        if self.force_full:
            print(
                f"Full-Only Gates: {full_only_passed} passed, {full_only_failed} failed"
            )
        else:
            print(f"Full-Only Gates: skipped (PR mode)")

        if blocking_failed > 0:
            print("\nFailed blocking gates:")
            for gate in self.report.gates:
                if gate.name in self.BLOCKING_GATES and not gate.passed:
                    print(f"  ✗ {gate.name}")
                    if gate.error_message:
                        print(f"    {gate.error_message}")

        print(f"\nTotal duration: {self.report.total_duration_seconds:.2f}s")

        if self.report.overall_passed:
            print("\n✓ ALL BLOCKING GATES PASSED")
        else:
            print("\n✗ BLOCKING GATES FAILED")

    def write_report(self, output_path: Optional[str] = None) -> None:
        """Write the report to a JSON file."""
        if output_path is None:
            output_path = os.path.join(self.ci_status_dir, "blocking-gates-report.json")

        try:
            with open(output_path, "w") as f:
                json.dump(self.report.to_dict(), f, indent=2)
            self.log(f"Report written to: {output_path}")
        except IOError as e:
            print(f"Warning: Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Run blocking gates for CI pipeline validation"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--ci-status-dir",
        help="Directory containing CI status files (default: CI_STATUS_DIR env var or /tmp/ci-status)",
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Force full gate validation (including full-only gates)",
    )
    parser.add_argument("--output", "-o", help="Output path for JSON report")

    args = parser.parse_args()

    runner = BlockingGatesRunner(
        verbose=args.verbose,
        ci_status_dir=args.ci_status_dir,
        force_full=args.force_full,
    )

    report = runner.run_all_gates()
    runner.print_summary()

    if args.output:
        runner.write_report(args.output)
    else:
        runner.write_report()

    sys.exit(0 if report.overall_passed else 1)


if __name__ == "__main__":
    main()
