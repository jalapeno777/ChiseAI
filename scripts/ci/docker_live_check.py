#!/usr/bin/env python3
"""Docker Live Check - Verify Docker containers are running correctly.

Checks:
1. Protected containers are running: tradedev, intelligent_ride, aisetup-mcp-discord-1
2. chiseai Docker network exists
3. Report all container statuses

Exit codes:
- 0: All checks pass
- 1: One or more checks failed (but still exit 0 for non-blocking in CI)
"""

import shutil
import subprocess
import sys
from typing import NamedTuple

PROTECTED_CONTAINERS = ["tradedev", "intelligent_ride", "aisetup-mcp-discord-1"]
CHISEAI_NETWORK = "chiseai"


class CheckResult(NamedTuple):
    name: str
    passed: bool
    detail: str


def run_cmd(*args: str) -> tuple[int, str, str]:
    """Run command and return (returncode, stdout, stderr)."""
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def check_container(name: str) -> CheckResult:
    """Check if container is running."""
    rc, out, err = run_cmd("docker", "inspect", "--format", "{{.State.Running}}", name)
    if rc == 0 and out.strip().lower() == "true":
        return CheckResult(name=name, passed=True, detail="running")
    if rc == 0:
        return CheckResult(
            name=name,
            passed=False,
            detail=f"exists but not running (state={out.strip()!r})",
        )
    return CheckResult(name=name, passed=False, detail="not found or docker error")


def check_network(name: str) -> CheckResult:
    """Check if network exists."""
    rc, _, err = run_cmd("docker", "network", "inspect", name)
    if rc == 0:
        return CheckResult(name=name, passed=True, detail="exists")
    return CheckResult(name=name, passed=False, detail="not found or docker error")


def main() -> int:
    """Run all Docker live checks."""
    # Check if docker binary is available (skip in CI agent containers without docker)
    if shutil.which("docker") is None:
        print(
            "docker-live-check: docker binary not found; skipping (CI agent container)"
        )
        return 0

    all_passed = True

    print("=== Docker Live Check ===\n")

    # Check protected containers
    print("Protected Containers:")
    for container in PROTECTED_CONTAINERS:
        result = check_container(container)
        symbol = "✓" if result.passed else "✗"
        print(f"  {symbol} {result.name}: {result.detail}")
        if not result.passed:
            all_passed = False

    # Check chiseai network
    print("\nDocker Networks:")
    net_result = check_network(CHISEAI_NETWORK)
    symbol = "✓" if net_result.passed else "✗"
    print(f"  {symbol} {net_result.name}: {net_result.detail}")
    if not net_result.passed:
        all_passed = False

    # Summary
    print()
    if all_passed:
        print("All Docker live checks passed.")
        return 0
    else:
        print("Some Docker live checks failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
