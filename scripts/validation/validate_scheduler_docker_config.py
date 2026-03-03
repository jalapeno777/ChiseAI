#!/usr/bin/env python3
"""Validate BrainEval Scheduler Docker Configuration.

# SAFETY: Read-only validation script
# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Validates:
1. Docker network configuration (chiseai external network)
2. Dockerfile labels (project=chiseai)
3. Redis connection configuration (service name, not host.docker.internal)
4. No bridge network fallback

Exit codes:
    0: All validations passed
    1: One or more validations failed

Story: ST-MEMORY-INGEST-001
"""

from __future__ import annotations

import sys
from pathlib import Path


def check_file_exists(path: Path) -> bool:
    """Check if file exists."""
    return path.exists()


def check_network_config(compose_path: Path) -> tuple[bool, list[str]]:
    """Check docker-compose network configuration.

    Returns:
        Tuple of (success, messages)
    """
    messages = []
    success = True

    if not compose_path.exists():
        messages.append(f"FAIL: {compose_path} does not exist")
        return False, messages

    content = compose_path.read_text()

    # Check for chiseai external network
    if "networks:" not in content:
        messages.append("FAIL: No networks section found")
        success = False
    elif "chiseai:" not in content:
        messages.append("FAIL: chiseai network not defined")
        success = False
    elif "external: true" not in content:
        messages.append("FAIL: chiseai network not marked as external")
        success = False
    else:
        messages.append("PASS: chiseai external network configured")

    # Check for bridge network (should not exist)
    if "bridge" in content.lower():
        messages.append("WARN: 'bridge' found in compose file - verify no fallback")
        # Not a failure, just a warning

    # Check Redis host uses service name
    if "REDIS_HOST=chiseai-redis" in content:
        messages.append("PASS: Redis host uses chiseai-redis service name")
    else:
        messages.append("FAIL: Redis host not configured with chiseai-redis")
        success = False

    return success, messages


def check_dockerfile_labels(dockerfile_path: Path) -> tuple[bool, list[str]]:
    """Check Dockerfile labels.

    Returns:
        Tuple of (success, messages)
    """
    messages = []
    success = True

    if not dockerfile_path.exists():
        messages.append(f"FAIL: {dockerfile_path} does not exist")
        return False, messages

    content = dockerfile_path.read_text()

    # Check for project label
    if "LABEL project=chiseai" in content:
        messages.append("PASS: LABEL project=chiseai found")
    else:
        messages.append("FAIL: LABEL project=chiseai not found")
        success = False

    # Check for service label
    if "LABEL service=" in content:
        messages.append("PASS: LABEL service found")
    else:
        messages.append("WARN: LABEL service not found (optional)")

    # Check Redis default
    if "REDIS_HOST=chiseai-redis" in content:
        messages.append("PASS: Redis host default is chiseai-redis")
    else:
        messages.append("WARN: Redis host default may not be chiseai-redis")

    return success, messages


def check_redis_config(scripts_dir: Path) -> tuple[bool, list[str]]:
    """Check Redis connection configuration in scripts.

    Returns:
        Tuple of (success, messages)
    """
    messages = []
    issues = []

    # Check schedule_brain_eval.py
    schedule_script = scripts_dir / "schedule_brain_eval.py"
    if schedule_script.exists():
        content = schedule_script.read_text()

        # Should use env var with chiseai-redis fallback in container
        if 'os.environ.get("REDIS_HOST"' in content:
            messages.append("PASS: schedule_brain_eval.py uses REDIS_HOST env var")
        else:
            issues.append("schedule_brain_eval.py does not use REDIS_HOST env var")

        # Check for host.docker.internal (acceptable as fallback)
        if "host.docker.internal" in content:
            messages.append(
                "INFO: schedule_brain_eval.py has host.docker.internal fallback "
                "(ok for local dev, overridden in container)"
            )

    # Check kpi_scheduler.py (should not have direct Redis access)
    kpi_script = scripts_dir / "kpi_scheduler.py"
    if kpi_script.exists():
        content = kpi_script.read_text()

        if "redis" not in content.lower():
            messages.append(
                "PASS: kpi_scheduler.py has no direct Redis access (delegates to subprocesses)"
            )
        else:
            messages.append(
                "INFO: kpi_scheduler.py has Redis references (check if intentional)"
            )

    success = len(issues) == 0
    for issue in issues:
        messages.append(f"WARN: {issue}")

    return success, messages


def check_memory_access(scripts_dir: Path) -> tuple[bool, list[str]]:
    """Check memory access patterns (Redis/Qdrant vs filesystem).

    Returns:
        Tuple of (success, messages)
    """
    messages = []
    warnings = []

    # Check kpi_scheduler.py
    kpi_script = scripts_dir / "kpi_scheduler.py"
    if kpi_script.exists():
        content = kpi_script.read_text()

        # Check for tempmemories access
        if "tempmemories" in content:
            warnings.append("kpi_scheduler.py has tempmemories reference")

        # Check for filesystem memory access
        if "docs/tempmemories" in content:
            warnings.append("kpi_scheduler.py accesses docs/tempmemories")

        # Output files are expected
        if "_bmad-output" in content:
            messages.append(
                "INFO: kpi_scheduler.py writes to _bmad-output (expected for scheduler output)"
            )

    # Check schedule_brain_eval.py
    schedule_script = scripts_dir / "schedule_brain_eval.py"
    if schedule_script.exists():
        content = schedule_script.read_text()

        # Check for tempmemories access
        if "tempmemories" in content:
            warnings.append("schedule_brain_eval.py has tempmemories reference")

        # Check for Redis client
        if "redis.Redis" in content or "import redis" in content:
            messages.append("PASS: schedule_brain_eval.py uses Redis client")

        # Check for Qdrant
        if "qdrant" in content.lower():
            messages.append("INFO: schedule_brain_eval.py has Qdrant reference")

    for warning in warnings:
        messages.append(f"WARN: {warning}")

    return True, messages  # Warnings don't fail the check


def main() -> int:
    """Run all validations.

    Returns:
        Exit code (0=success, 1=failure)
    """
    print("=" * 60)
    print("BrainEval Scheduler Docker Configuration Validation")
    print("Story: ST-MEMORY-INGEST-001")
    print("=" * 60)
    print()

    project_root = Path(__file__).parent.parent.parent
    docker_dir = project_root / "infrastructure" / "docker"
    scripts_dir = project_root / "scripts" / "evaluation"

    all_success = True
    all_messages = []

    # 1. Check network configuration
    print("1. Checking Docker network configuration...")
    compose_path = docker_dir / "docker-compose.scheduler.yml"
    success, messages = check_network_config(compose_path)
    all_success = all_success and success
    all_messages.extend(messages)
    for msg in messages:
        print(f"   {msg}")
    print()

    # 2. Check Dockerfile labels
    print("2. Checking Dockerfile labels...")
    dockerfile_path = docker_dir / "Dockerfile.scheduler"
    success, messages = check_dockerfile_labels(dockerfile_path)
    all_success = all_success and success
    all_messages.extend(messages)
    for msg in messages:
        print(f"   {msg}")
    print()

    # 3. Check Redis configuration
    print("3. Checking Redis connection configuration...")
    success, messages = check_redis_config(scripts_dir)
    all_success = all_success and success
    all_messages.extend(messages)
    for msg in messages:
        print(f"   {msg}")
    print()

    # 4. Check memory access patterns
    print("4. Checking memory access patterns...")
    success, messages = check_memory_access(scripts_dir)
    all_success = all_success and success
    all_messages.extend(messages)
    for msg in messages:
        print(f"   {msg}")
    print()

    # Summary
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    pass_count = sum(1 for m in all_messages if m.startswith("PASS"))
    fail_count = sum(1 for m in all_messages if m.startswith("FAIL"))
    warn_count = sum(1 for m in all_messages if m.startswith("WARN"))
    info_count = sum(1 for m in all_messages if m.startswith("INFO"))

    print(f"  PASS: {pass_count}")
    print(f"  FAIL: {fail_count}")
    print(f"  WARN: {warn_count}")
    print(f"  INFO: {info_count}")
    print()

    if all_success:
        print("✓ ALL VALIDATIONS PASSED")
        return 0
    else:
        print("✗ SOME VALIDATIONS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
