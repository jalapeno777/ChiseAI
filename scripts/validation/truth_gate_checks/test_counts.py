"""Test Counts Check - Validates recorded test counts match pytest output."""

from __future__ import annotations

import os.path
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


def find_story_in_workflow(story_id: str, workflow_data: dict) -> dict | None:
    """Find a story entry in the workflow data."""
    # Check stories list (new format)
    for story in workflow_data.get("stories", []):
        if story.get("id") == story_id:
            return story

    # Check in_progress
    for story in workflow_data.get("in_progress", []) or []:
        if story.get("id") == story_id:
            return story

    # Check completed
    for story in workflow_data.get("completed", []) or []:
        if story.get("id") == story_id:
            return story

    # Check recent_changes
    for change in workflow_data.get("metadata", {}).get("recent_changes", []) or []:
        if change.get("story_id") == story_id:
            return change

    return None


def find_story_test_count(story_id: str, workflow_data: dict) -> int | None:
    """Find the recorded test count for a story."""
    story = find_story_in_workflow(story_id, workflow_data)
    if story:
        test_results = story.get("test_results", {})
        return test_results.get("total_tests")
    return None


def infer_test_path_from_story(
    story: dict | None, story_id: str | None = None
) -> str | None:
    """
    Infer the test path from story data.

    Strategy:
    1. Look for test files in files_changed entries
    2. Derive from story_id pattern (e.g., STRONG-003-A -> tests/test_strong_system/...)
    3. Fall back to None (caller should use default)

    Args:
        story: Story dictionary from workflow status
        story_id: Optional story ID for pattern-based inference

    Returns:
        Test path string or None if no specific path can be determined
    """
    if story is None:
        return None

    # Strategy 1: Extract test directory from files_changed
    files_changed = story.get("files_changed", [])
    if files_changed:
        test_dirs = set()
        for file_path in files_changed:
            if file_path.startswith("tests/"):
                # Extract the directory containing the test file
                path_parts = file_path.split("/")
                if len(path_parts) >= 2:
                    # Get the test module directory (e.g., tests/test_strong_system/)
                    if len(path_parts) >= 3:
                        test_module_dir = "/".join(path_parts[:3])
                        test_dirs.add(test_module_dir)
                    else:
                        test_dirs.add("tests/")

        if test_dirs:
            # If all test files are in the same directory, use that
            if len(test_dirs) == 1:
                return test_dirs.pop()
            # If multiple directories, find the common parent
            common_prefix = "/".join(
                os.path.commonprefix([d.split("/") for d in test_dirs])
            )
            if common_prefix and common_prefix != "tests":
                return common_prefix
            return "tests/"

    # Strategy 2: Derive from story_id pattern
    if story_id:
        # Pattern: STRONG-XXX-Y -> tests/test_strong_system/test_...
        strong_match = re.match(r"STRONG-(\d+)-[A-Z]", story_id)
        if strong_match:
            # Map STRONG story IDs to their test directories
            strong_test_dirs = {
                "001": "tests/test_strong_system/test_neural_beliefs/",
                "002": "tests/test_strong_system/test_belief_embeddings/",
                "003": "tests/test_strong_system/test_hypothesis_generator/",
                "004": "tests/test_strong_system/test_symbolic_rules/",
            }
            story_num = strong_match.group(1)
            if story_num in strong_test_dirs:
                return strong_test_dirs[story_num]
            # Generic fallback for other STRONG stories
            return "tests/test_strong_system/"

    # Strategy 3: No specific path found
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
        # Load workflow status to find expected count and infer test path
        workflow_path = repo_root / workflow_file
        story = None
        if workflow_path.exists():
            try:
                with open(workflow_path) as f:
                    workflow_data = yaml.safe_load(f)
                expected_count = find_story_test_count(story_id, workflow_data)
                story = find_story_in_workflow(story_id, workflow_data)
            except Exception as e:
                result["errors"].append(f"Failed to load workflow file: {e}")

        if expected_count is None:
            result["passed"] = False
            result["errors"].append(f"No test count found for story {story_id}")
            return result

        # Infer test path from story data and story_id
        inferred_path = infer_test_path_from_story(story, story_id)
        path = inferred_path if inferred_path else "tests/"

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
