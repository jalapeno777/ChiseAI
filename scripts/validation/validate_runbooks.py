#!/usr/bin/env python3
"""
Runbook Validation Script for ST-VALIDATION-002

Validates runbook structure, content, and tests safe commands against live system.
"""

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RunbookCheck:
    """Result of a single runbook check."""

    criterion: str
    status: str  # "PASS", "FAIL", "SKIP", "N/A"
    details: str = ""


@dataclass
class LiveTestResult:
    """Result of a live command test."""

    command: str
    status: str  # "PASS", "FAIL", "SKIP"
    output: str = ""
    error: str = ""
    timestamp: str = ""


@dataclass
class RunbookValidation:
    """Complete validation results for a runbook."""

    name: str
    priority: str
    file_path: str
    checks: list = field(default_factory=list)
    live_tests: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    overall_status: str = "PENDING"


class RunbookValidator:
    """Validates runbook structure and executes safe live tests."""

    # Critical runbooks to validate
    CRITICAL_RUNBOOKS = {
        "self-healing-procedures.md": "P0",
        "model-registry-operations.md": "P0",
        "paper-trading-operations.md": "P0",
        "autonomous_control_plane.md": "P1",
        "incident_response.md": "P1",
        "redis-failure-response.md": "P1",
    }

    # Safe commands to test live (read-only only)
    SAFE_COMMANDS = [
        {
            "name": "Redis connectivity test",
            "command": [
                "redis-cli",
                "-h",
                "host.docker.internal",
                "-p",
                "6380",
                "ping",
            ],
            "expected": "PONG",
            "timeout": 10,
        },
        {
            "name": "Redis DBSIZE check",
            "command": [
                "redis-cli",
                "-h",
                "host.docker.internal",
                "-p",
                "6380",
                "dbsize",
            ],
            "expected": None,  # Any numeric response is valid
            "timeout": 10,
        },
        {
            "name": "Dashboard health check",
            "command": [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "http://host.docker.internal:8502/_stcore/health",
            ],
            "expected": "200",
            "timeout": 15,
        },
        {
            "name": "Docker containers status",
            "command": [
                "docker",
                "ps",
                "--filter",
                "name=chiseai",
                "--format",
                "{{.Names}}",
            ],
            "expected": None,
            "timeout": 10,
        },
        {
            "name": "Redis INFO server",
            "command": [
                "redis-cli",
                "-h",
                "host.docker.internal",
                "-p",
                "6380",
                "info",
                "server",
            ],
            "expected": "redis_version",
            "timeout": 10,
        },
        {
            "name": "Redis memory info",
            "command": [
                "redis-cli",
                "-h",
                "host.docker.internal",
                "-p",
                "6380",
                "info",
                "memory",
            ],
            "expected": "used_memory",
            "timeout": 10,
        },
    ]

    def __init__(self, runbooks_dir: str = "docs/runbooks"):
        self.runbooks_dir = Path(runbooks_dir)
        self.results = []
        self.timestamp = datetime.now(UTC).isoformat()

    def validate_all(self) -> dict:
        """Validate all critical runbooks."""
        print("=" * 80)
        print("RUNBOOK VALIDATION - ST-VALIDATION-002")
        print("=" * 80)
        print(f"Timestamp: {self.timestamp}")
        print(f"Runbooks Directory: {self.runbooks_dir}")
        print()

        # Validate each critical runbook
        for filename, priority in self.CRITICAL_RUNBOOKS.items():
            result = self.validate_runbook(filename, priority)
            self.results.append(result)

        # Run safe live tests
        print("\n" + "=" * 80)
        print("SAFE LIVE SYSTEM TESTS")
        print("=" * 80)
        live_test_results = self.run_live_tests()

        # Generate summary
        summary = self.generate_summary()

        return {
            "story_id": "ST-VALIDATION-002",
            "timestamp": self.timestamp,
            "validator": "dev",
            "summary": summary,
            "runbooks": [asdict(r) for r in self.results],
            "live_tests": [asdict(t) for t in live_test_results],
        }

    def validate_runbook(self, filename: str, priority: str) -> RunbookValidation:
        """Validate a single runbook file."""
        filepath = self.runbooks_dir / filename
        result = RunbookValidation(
            name=filename,
            priority=priority,
            file_path=str(filepath),
        )

        print(f"\n{'─' * 80}")
        print(f"Validating: {filename} (Priority: {priority})")
        print(f"Path: {filepath}")
        print("─" * 80)

        # Check file exists
        if not filepath.exists():
            result.checks.append(
                RunbookCheck(
                    criterion="File exists",
                    status="FAIL",
                    details=f"File not found: {filepath}",
                )
            )
            result.overall_status = "FAIL"
            return result

        result.checks.append(
            RunbookCheck(
                criterion="File exists",
                status="PASS",
                details="File exists and is readable",
            )
        )

        # Read content
        content = filepath.read_text()

        # Validate structure
        self._check_has_heading(
            result, content, "Overview|Purpose|# ", "Has purpose/scope statement"
        )
        self._check_has_heading(
            result,
            content,
            "Prerequisite|Requirements|Before|Pre-condition",
            "Lists prerequisites",
        )
        self._check_has_steps(result, content)
        self._check_has_validation(result, content)
        self._check_has_rollback(result, content)
        self._check_command_syntax(result, content)
        self._check_has_examples(result, content)

        # Determine overall status
        fail_count = sum(1 for c in result.checks if c.status == "FAIL")
        skip_count = sum(1 for c in result.checks if c.status == "SKIP")

        if fail_count > 0:
            result.overall_status = "FAIL"
        elif skip_count > 0:
            result.overall_status = "PARTIAL"
        else:
            result.overall_status = "PASS"

        print(f"  Result: {result.overall_status}")
        for check in result.checks:
            status_icon = (
                "✓"
                if check.status == "PASS"
                else "✗" if check.status == "FAIL" else "○"
            )
            print(f"    {status_icon} {check.criterion}: {check.status}")
            if check.details:
                print(f"       {check.details}")

        return result

    def _check_has_heading(
        self, result: RunbookValidation, content: str, pattern: str, criterion_name: str
    ):
        """Check if content has a specific heading pattern."""
        regex = re.compile(pattern, re.IGNORECASE)
        if regex.search(content):
            result.checks.append(
                RunbookCheck(
                    criterion=criterion_name,
                    status="PASS",
                    details="Found matching section",
                )
            )
        else:
            result.checks.append(
                RunbookCheck(
                    criterion=criterion_name,
                    status="FAIL",
                    details=f"No section matching '{pattern}' found",
                )
            )

    def _check_has_steps(self, result: RunbookValidation, content: str):
        """Check if runbook has numbered steps."""
        # Look for numbered steps (1., 1), Step 1, etc.)
        step_patterns = [
            r"^\s*\d+[\.\)]\s+\w+",  # 1. Step or 1) Step
            r"^\s*\d+[\.\)]\s+\*\*",  # 1. **Bold Step** format
            r"^\s*Step\s+\d+",  # Step 1
            r"^\s*###?#?\s+\d+",  # Markdown heading with number
            r"^\s*\*\*\d+\.\*\*",  # **1.** format
        ]

        for pattern in step_patterns:
            if re.search(pattern, content, re.MULTILINE):
                result.checks.append(
                    RunbookCheck(
                        criterion="Has numbered steps",
                        status="PASS",
                        details="Found numbered procedure steps",
                    )
                )
                return

        result.checks.append(
            RunbookCheck(
                criterion="Has numbered steps",
                status="FAIL",
                details="No numbered steps found",
            )
        )

    def _check_has_validation(self, result: RunbookValidation, content: str):
        """Check if runbook has validation/verification steps."""
        validation_patterns = [
            r"validat",
            r"verify",
            r"check.*result",
            r"confirm.*working",
            r"test.*command",
            r"expected.*output",
            r"verification",
        ]

        for pattern in validation_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                result.checks.append(
                    RunbookCheck(
                        criterion="Has validation/verification",
                        status="PASS",
                        details="Found validation steps",
                    )
                )
                return

        result.checks.append(
            RunbookCheck(
                criterion="Has validation/verification",
                status="FAIL",
                details="No validation/verification section found",
            )
        )

    def _check_has_rollback(self, result: RunbookValidation, content: str):
        """Check if runbook has rollback procedure for destructive operations."""
        rollback_patterns = [r"rollback", r"revert", r"undo", r"back.*out", r"recovery"]
        has_rollback = any(
            re.search(p, content, re.IGNORECASE) for p in rollback_patterns
        )

        # Check if runbook contains destructive operations
        destructive_patterns = [
            r"delete",
            r"remove",
            r"drop",
            r"restart",
            r"kill",
            r"stop",
        ]
        has_destructive = any(
            re.search(p, content, re.IGNORECASE) for p in destructive_patterns
        )

        if has_destructive:
            if has_rollback:
                result.checks.append(
                    RunbookCheck(
                        criterion="Has rollback procedure",
                        status="PASS",
                        details="Rollback procedure found for destructive operations",
                    )
                )
            else:
                result.checks.append(
                    RunbookCheck(
                        criterion="Has rollback procedure",
                        status="FAIL",
                        details="Contains destructive operations but no rollback procedure",
                    )
                )
        else:
            result.checks.append(
                RunbookCheck(
                    criterion="Has rollback procedure",
                    status="N/A",
                    details="No destructive operations found, rollback not required",
                )
            )

    def _check_command_syntax(self, result: RunbookValidation, content: str):
        """Check if commands in code blocks appear syntactically correct."""
        # Extract bash commands
        bash_blocks = re.findall(r"```bash\n(.*?)```", content, re.DOTALL)

        issues = []
        for block in bash_blocks:
            lines = block.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Skip lines containing jq filters or curl data (complex patterns that are valid)
                if "jq " in line or "-d '" in line or '-d "' in line:
                    continue

                # Skip isolated closing braces (from multiline JSON)
                if (
                    line == "}'"
                    or line == '}"'
                    or line.startswith("}'")
                    or line.startswith('}"')
                ):
                    continue

                # Skip Docker format template strings ({{.Field}} syntax)
                # These use double braces which are valid Go templates
                docker_format_pattern = r"\{\{[\.\w]+\}\}"
                line_for_checking = re.sub(docker_format_pattern, "PLACEHOLDER", line)

                # Skip jq filter syntax (jq '.field' or jq '{...}')
                # jq filters use single braces in quoted strings
                jq_filter_pattern = r"jq\s+['\"].*?['\"]"
                line_for_checking = re.sub(
                    jq_filter_pattern, "JQ_FILTER", line_for_checking
                )

                # Skip curl POST data with JSON (-d '{...}' or --data '{...}')
                # These have balanced braces inside single quotes
                curl_data_pattern = r"-d\s+['\"]\{.*?\}['\"]"
                line_for_checking = re.sub(
                    curl_data_pattern, "CURL_DATA", line_for_checking
                )
                curl_data_long_pattern = r"--data\s+['\"]\{.*?\}['\"]"
                line_for_checking = re.sub(
                    curl_data_long_pattern, "CURL_DATA", line_for_checking
                )

                # Check for common syntax issues
                if line_for_checking.count("(") != line_for_checking.count(")"):
                    issues.append(f"Unbalanced parentheses: {line[:50]}...")
                if line_for_checking.count("{") != line_for_checking.count("}"):
                    issues.append(f"Unbalanced braces: {line[:50]}...")
                if line_for_checking.count('"') % 2 != 0:
                    issues.append(f"Unbalanced quotes: {line[:50]}...")

        if issues:
            result.checks.append(
                RunbookCheck(
                    criterion="Command syntax valid",
                    status="FAIL",
                    details=f"Found {len(issues)} potential syntax issues",
                )
            )
            result.issues.extend(issues[:3])  # Store first 3 issues
        else:
            result.checks.append(
                RunbookCheck(
                    criterion="Command syntax valid",
                    status="PASS",
                    details="No obvious syntax issues found",
                )
            )

    def _check_has_examples(self, result: RunbookValidation, content: str):
        """Check if runbook has example outputs or usage examples."""
        example_patterns = [
            r"expected.*output",
            r"example.*output",
            r"sample.*output",
            r"output:",
            r"result:",
            r"#.*→",
            r">>>",
            r"```\n.*PONG",
        ]

        for pattern in example_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                result.checks.append(
                    RunbookCheck(
                        criterion="Has examples/output samples",
                        status="PASS",
                        details="Found example outputs",
                    )
                )
                return

        result.checks.append(
            RunbookCheck(
                criterion="Has examples/output samples",
                status="SKIP",
                details="No example outputs found (optional but recommended)",
            )
        )

    def run_live_tests(self) -> list:
        """Execute safe read-only commands against live system."""
        results = []

        for test in self.SAFE_COMMANDS:
            print(f"\n  Testing: {test['name']}")
            print(f"    Command: {' '.join(test['command'])}")

            result = LiveTestResult(
                command=" ".join(test["command"]),
                status="PENDING",
                timestamp=datetime.now(UTC).isoformat(),
            )

            try:
                proc = subprocess.run(
                    test["command"],
                    capture_output=True,
                    text=True,
                    timeout=test["timeout"],
                )

                output = proc.stdout.strip()
                result.output = output[:500]  # Limit output length

                # Check result
                if proc.returncode == 0:
                    if test["expected"] is None or test["expected"] in output:
                        result.status = "PASS"
                        print("    Status: ✓ PASS")
                        print(f"    Output: {output[:100]}...")
                    else:
                        result.status = "FAIL"
                        result.error = (
                            f"Expected '{test['expected']}' not found in output"
                        )
                        print("    Status: ✗ FAIL")
                        print(f"    Error: {result.error}")
                else:
                    result.status = "FAIL"
                    result.error = f"Exit code {proc.returncode}: {proc.stderr[:200]}"
                    print("    Status: ✗ FAIL")
                    print(f"    Error: {result.error}")

            except subprocess.TimeoutExpired:
                result.status = "FAIL"
                result.error = f"Timeout after {test['timeout']}s"
                print("    Status: ✗ TIMEOUT")
            except Exception as e:
                result.status = "FAIL"
                result.error = str(e)
                print(f"    Status: ✗ ERROR: {e}")

            results.append(result)

        return results

    def generate_summary(self) -> dict:
        """Generate validation summary statistics."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.overall_status == "PASS")
        failed = sum(1 for r in self.results if r.overall_status == "FAIL")
        partial = sum(1 for r in self.results if r.overall_status == "PARTIAL")

        p0_runbooks = [r for r in self.results if r.priority == "P0"]
        p1_runbooks = [r for r in self.results if r.priority == "P1"]

        return {
            "total_runbooks_checked": total,
            "passed": passed,
            "failed": failed,
            "partial": partial,
            "p0_status": {
                "total": len(p0_runbooks),
                "passed": sum(1 for r in p0_runbooks if r.overall_status == "PASS"),
                "failed": sum(1 for r in p0_runbooks if r.overall_status == "FAIL"),
            },
            "p1_status": {
                "total": len(p1_runbooks),
                "passed": sum(1 for r in p1_runbooks if r.overall_status == "PASS"),
                "failed": sum(1 for r in p1_runbooks if r.overall_status == "FAIL"),
            },
        }


def main():
    """Main entry point."""
    validator = RunbookValidator()
    results = validator.validate_all()

    # Print summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    summary = results["summary"]
    print(f"Total Runbooks: {summary['total_runbooks_checked']}")
    print(f"  Passed:  {summary['passed']}")
    print(f"  Failed:  {summary['failed']}")
    print(f"  Partial: {summary['partial']}")
    print()
    print("P0 Runbooks (Critical):")
    print(
        f"  Total: {summary['p0_status']['total']}, Passed: {summary['p0_status']['passed']}, Failed: {summary['p0_status']['failed']}"
    )
    print("P1 Runbooks (High):")
    print(
        f"  Total: {summary['p1_status']['total']}, Passed: {summary['p1_status']['passed']}, Failed: {summary['p1_status']['failed']}"
    )

    # Save results
    output_file = Path("docs/evidence/ST-VALIDATION-002-runbooks-validation.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Evidence saved to: {output_file}")

    # Exit with appropriate code
    if summary["failed"] > 0:
        print("\n⚠ Some runbooks failed validation - see evidence file for details")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
