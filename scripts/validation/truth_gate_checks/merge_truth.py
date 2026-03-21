"""Merge Truth Check - Validates commits are on main branches."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def verify_commit_on_branch(
    commit: str,
    branch: str,
    repo_root: Path | None = None,
    remote: bool = False,
) -> dict[str, Any]:
    """
    Verify a commit is on a specific branch.

    Args:
        commit: Commit SHA to verify
        branch: Branch name to check
        repo_root: Root of the git repository
        remote: Check remote branches

    Returns:
        Dictionary with verification result
    """
    if repo_root is None:
        repo_root = Path.cwd()

    cmd = ["git", "branch"]
    if remote:
        cmd.append("-r")
    cmd.extend(["--contains", commit])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_root,
        )

        if result.returncode != 0:
            return {
                "passed": False,
                "message": f"Commit {commit[:8]} not found in repository",
                "commit": commit,
                "branch": branch,
                "remote": remote,
            }

        branches = [
            b.strip().strip("* ")
            for b in result.stdout.strip().split("\n")
            if b.strip()
        ]

        # Check if target branch is in the list
        if remote:
            branch_found = f"origin/{branch}" in branches or branch in branches
        else:
            branch_found = branch in branches

        if branch_found:
            return {
                "passed": True,
                "message": f"Commit {commit[:8]} is on {branch}",
                "commit": commit,
                "branch": branch,
                "remote": remote,
                "branches_found": branches,
            }
        else:
            return {
                "passed": False,
                "message": f"Commit {commit[:8]} is NOT on {branch}",
                "commit": commit,
                "branch": branch,
                "remote": remote,
                "branches_found": branches,
            }

    except Exception as e:
        return {
            "passed": False,
            "message": f"Error verifying commit {commit[:8]}: {e}",
            "commit": commit,
            "branch": branch,
            "remote": remote,
            "error": str(e),
        }


def check_merge_truth(
    commits: list[str],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Check merge truth for commits.

    Validates:
    - Commits exist in the repository
    - Commits are on local main branch
    - Commits are on origin/main branch

    Args:
        commits: List of commit SHAs to verify
        repo_root: Root of the git repository

    Returns:
        Dictionary with check results
    """
    if repo_root is None:
        repo_root = Path.cwd()

    result: dict[str, Any] = {
        "check_type": "merge-truth",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "commits": commits,
        "passed": True,
        "checks": [],
        "total_checks": 0,
        "passed_checks": 0,
        "failed_checks": 0,
        "errors": [],
    }

    if not commits:
        result["passed"] = False
        result["errors"].append("No commits provided")
        return result

    for commit in commits:
        commit_check: dict[str, Any] = {
            "name": f"Commit {commit[:8]}",
            "passed": True,
            "message": f"Validating commit {commit[:8]}",
            "commit": commit,
            "details": [],
        }

        # Check local main
        local_result = verify_commit_on_branch(commit, "main", repo_root, remote=False)
        commit_check["details"].append(local_result)
        if not local_result["passed"]:
            commit_check["passed"] = False
            result["passed"] = False

        # Check origin/main
        remote_result = verify_commit_on_branch(commit, "main", repo_root, remote=True)
        commit_check["details"].append(remote_result)
        if not remote_result["passed"]:
            commit_check["passed"] = False
            result["passed"] = False

        result["checks"].append(commit_check)

    # Calculate summary
    result["total_checks"] = len(result["checks"])
    result["passed_checks"] = sum(1 for c in result["checks"] if c.get("passed", False))
    result["failed_checks"] = result["total_checks"] - result["passed_checks"]

    return result
