"""Test Counts Check - Validates recorded test counts match pytest output."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def run_pytest_collect(
    path: str | None = None, repo_root: Path | None = None
) -> dict[str, Any]:
    """
    Run pytest --collect-only and return test count.

    Args:
        path: Path to test directory or file (None for all tests)
        repo_root: Root of the git repository

    Returns:
        Dictionary with collection results
    """
    if repo_root is None:
        repo_root = Path.cwd()

    cmd = ["python3", "-m", "pytest", "--collect-only"]
    if path:
        cmd.append(path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=120,
        )

        # Parse output for test count
        output = result.stdout + result.stderr

        # Look for "collected X items" in output
        match = re.search(r"collected\s+(\d+)\s+items?", output)
        if match:
            return {
                "success": True,
                "test_count": int(match.group(1)),
                "output": output,
                "returncode": result.returncode,
            }

        # Alternative: count test functions
        test_count = len(re.findall(r"<(Function|Class)\s+", output))

        return {
            "success": True,
            "test_count": test_count,
            "output": output,
            "returncode": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "test_count": 0,
            "error": "pytest collection timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "test_count": 0,
            "error": str(e),
        }


def find_story_test_count(story_id: str, workflow_data: dict) -> int | None:
    """Find the recorded test count for a story."""
    # Check in_progress
    for story in workflow_data.get("in_progress", []):
        if story.get("id") == story_id:
            test_results = story.get("test_results", {})
            return test_results.get("total_tests")

    # Check completed
    for story in workflow_data.get("completed", []):
        if story.get("id") == story_id:
            test_results = story.get("test_results", {})
            return test_results.get("total_tests")

    # Check recent_changes
    for change in workflow_data.get("metadata", {}).get("recent_changes", []):
        if change.get("story_id") == story_id:
            test_results = change.get("test_results", {})
            if story_id in test_results:
                return test_results[story_id].get("total_tests")
            return test_results.get("total_tests")

    return None


def check_test_counts(
    story_id: str | None = None,
    path: str | None = None,
    workflow_file: str = "docs/bmm-workflow-status.yaml",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Check that recorded test counts match pytest collection.

    Validates:
    - Recorded test count matches pytest --collect-only output
    - Test files exist and are collectable

    Args:
        story_id: Story ID to check (uses workflow status for expected count)
        path: Path to test directory (overrides story_id lookup)
        workflow_file: Path to workflow status YAML file
        repo_root: Root of the git repository

    Returns:
        Dictionary with check results
    """
    if repo_root is None:
        repo_root = Path.cwd()

    result: dict[str, Any] = {
        "check_type": "test-counts",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "story_id": story_id,
        "path": path,
        "passed": True,
        "checks": [],
        "total_checks": 0,
        "passed_checks": 0,
        "failed_checks": 0,
        "errors": [],
    }

    # Determine expected count and test path
    expected_count: int | None = None

    if story_id and not path:
        # Load workflow status to find expected count
        workflow_path = repo_root / workflow_file
        if workflow_path.exists():
            try:
                with open(workflow_path) as f:
                    workflow_data = yaml.safe_load(f)
                expected_count = find_story_test_count(story_id, workflow_data)
            except Exception as e:
                result["errors"].append(f"Failed to load workflow file: {e}")

        if expected_count is None:
            result["passed"] = False
            result["errors"].append(f"No test count found for story {story_id}")
            return result

        # Infer test path from story_id
        path = f"tests/"

    # Run pytest collection
    collect_result = run_pytest_collect(path, repo_root)

    if not collect_result["success"]:
        result["passed"] = False
        result["errors"].append(
            f"pytest collection failed: {collect_result.get('error', 'Unknown error')}"
        )
        return result

    actual_count = collect_result["test_count"]

    # Compare counts
    if expected_count is not None:
        count_match = actual_count == expected_count
        check_detail: dict[str, Any] = {
            "name": "Test Count Match",
            "passed": count_match,
            "message": (
                f"Expected: {expected_count}, Actual: {actual_count}"
                if not count_match
                else f"Test count matches: {actual_count}"
            ),
            "expected": expected_count,
            "actual": actual_count,
        }
        result["checks"].append(check_detail)

        if not count_match:
            result["passed"] = False
    else:
        # Just report the count without comparison
        result["checks"].append(
            {
                "name": "Test Collection",
                "passed": True,
                "message": f"Collected {actual_count} tests",
                "actual": actual_count,
            }
        )

    # Calculate summary
    result["total_checks"] = len(result["checks"])
    result["passed_checks"] = sum(1 for c in result["checks"] if c.get("passed", False))
    result["failed_checks"] = result["total_checks"] - result["passed_checks"]

    return result
