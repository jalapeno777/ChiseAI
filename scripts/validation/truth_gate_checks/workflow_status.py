"""Workflow Status Check - Validates workflow status file entries."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def find_story_in_workflow(story_id: str, workflow_data: dict) -> dict | None:
    """Find a story in the workflow status data."""
    # Check in_progress (handle None values)
    in_progress = workflow_data.get("in_progress") or []
    for story in in_progress:
        if story.get("id") == story_id:
            return story

    # Check completed (handle None values)
    completed = workflow_data.get("completed") or []
    for story in completed:
        if story.get("id") == story_id:
            return story

    # Check recent_changes in metadata
    metadata = workflow_data.get("metadata") or {}
    recent_changes = metadata.get("recent_changes") or []
    for change in recent_changes:
        if change.get("story_id") == story_id:
            return change

    return None


def verify_file_exists(file_path: str, repo_root: Path | None = None) -> dict[str, Any]:
    """Verify a file exists in the git repository."""
    if repo_root is None:
        repo_root = Path.cwd()

    full_path = repo_root / file_path

    # Check if file exists
    if full_path.exists():
        return {
            "passed": True,
            "message": f"File exists: {file_path}",
            "path": file_path,
        }

    # Check if file exists in git (might be tracked but not on disk)
    try:
        result = subprocess.run(
            ["git", "ls-files", file_path],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {
                "passed": True,
                "message": f"File tracked in git: {file_path}",
                "path": file_path,
            }
    except Exception:
        pass

    return {
        "passed": False,
        "message": f"File not found: {file_path}",
        "path": file_path,
    }


def check_workflow_status(
    story_id: str | None = None,
    workflow_file: str = "docs/bmm-workflow-status.yaml",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Check workflow status file entries.

    Validates:
    - Story exists in workflow status
    - Files changed exist in the repository
    - Test results are properly recorded

    Args:
        story_id: Optional story ID to filter (if None, checks all stories)
        workflow_file: Path to workflow status YAML file
        repo_root: Root of the git repository

    Returns:
        Dictionary with check results
    """
    if repo_root is None:
        repo_root = Path.cwd()

    result: dict[str, Any] = {
        "check_type": "workflow-status",
        "timestamp": datetime.now(UTC).isoformat() + "Z",
        "story_id": story_id,
        "passed": True,
        "checks": [],
        "total_checks": 0,
        "passed_checks": 0,
        "failed_checks": 0,
        "errors": [],
    }

    # Load workflow status file
    workflow_path = repo_root / workflow_file
    if not workflow_path.exists():
        result["passed"] = False
        result["errors"].append(f"Workflow file not found: {workflow_file}")
        return result

    try:
        with open(workflow_path) as f:
            workflow_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result["passed"] = False
        result["errors"].append(f"Failed to parse workflow file: {e}")
        return result
    except Exception as e:
        result["passed"] = False
        result["errors"].append(f"Error reading workflow file: {e}")
        return result

    # Determine which stories to check
    stories_to_check: list[tuple[str, dict]] = []

    if story_id:
        story = find_story_in_workflow(story_id, workflow_data)
        if story:
            stories_to_check.append((story_id, story))
        else:
            result["passed"] = False
            result["errors"].append(f"Story not found: {story_id}")
            return result
    else:
        # Check all completed and in-progress stories (handle None values)
        in_progress = workflow_data.get("in_progress") or []
        for story in in_progress:
            if "id" in story:
                stories_to_check.append((story["id"], story))
        completed = workflow_data.get("completed") or []
        for story in completed:
            if "id" in story:
                stories_to_check.append((story["id"], story))

    # Check each story
    for sid, story in stories_to_check:
        story_check: dict[str, Any] = {
            "name": f"Story {sid}",
            "passed": True,
            "message": f"Validating story {sid}",
            "details": [],
        }

        # Check files_changed
        files_changed = story.get("files_changed", [])
        if not files_changed and "files_changed" not in story:
            # Some entries might not have files_changed (e.g., recent_changes)
            story_check["details"].append(
                {
                    "passed": True,
                    "message": "No files_changed field (optional)",
                }
            )
        elif not files_changed:
            story_check["details"].append(
                {
                    "passed": True,
                    "message": "Empty files_changed list",
                }
            )
        else:
            for file_path in files_changed:
                file_result = verify_file_exists(file_path, repo_root)
                story_check["details"].append(file_result)
                if not file_result["passed"]:
                    story_check["passed"] = False
                    result["passed"] = False

        # Check test_results if present
        test_results = story.get("test_results", {})
        if test_results:
            total_tests = test_results.get("total_tests", 0)
            if total_tests > 0:
                story_check["details"].append(
                    {
                        "passed": True,
                        "message": f"Test results recorded: {total_tests} tests",
                    }
                )
            else:
                story_check["details"].append(
                    {
                        "passed": False,
                        "message": "Test results show 0 tests",
                    }
                )
                story_check["passed"] = False
                result["passed"] = False

        result["checks"].append(story_check)

    # Calculate summary
    result["total_checks"] = len(result["checks"])
    result["passed_checks"] = sum(1 for c in result["checks"] if c.get("passed", False))
    result["failed_checks"] = result["total_checks"] - result["passed_checks"]

    return result
