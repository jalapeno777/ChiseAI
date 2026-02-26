#!/usr/bin/env python3
"""Status Write Gate - Validates workflow status changes against git evidence.

This script enforces the EP-AUTO-GIT workflow status gate:
- Validates merge claims against actual git evidence
- Fails closed on unverifiable claims
- Enforces Merlin-only authority for status changes

Exit codes:
    0 = Verification passed
    1 = Unverifiable claim (git evidence mismatch)
    2 = Authority violation (not Merlin)
    3 = Usage error (missing args, invalid input)
    4 = System error (git/Redis unavailable)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

# Redis key for EP-AUTO-GIT authority
EP_AUTO_GIT_KEY = "bmad:chiseai:ep:auto-git"
STATUS_AUTHORITY_FIELD = "status_authority"
MERGE_AUTHORITY_FIELD = "merge_authority"
PR_AUTHORITY_FIELD = "pr_authority"

# Required authority value
MERLIN_ONLY = "merlin-only"
MERGE_AUTHORITY_AGENT = "merlin"


class GateError(Exception):
    """Base exception for gate errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class AuthorityError(GateError):
    """Raised when authority check fails."""

    def __init__(self, message: str):
        super().__init__(message, exit_code=2)


class UsageError(GateError):
    """Raised when arguments are invalid."""

    def __init__(self, message: str):
        super().__init__(message, exit_code=3)


class SystemError(GateError):
    """Raised when system resources are unavailable."""

    def __init__(self, message: str):
        super().__init__(message, exit_code=4)


def run_git(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def verify_sha_exists(sha: str, cwd: Path | None = None) -> bool:
    """Verify that a SHA exists in the git repository.

    Args:
        sha: The commit SHA to verify
        cwd: Optional working directory

    Returns:
        True if SHA exists, False otherwise
    """
    rc, _, _ = run_git("cat-file", "-t", sha, cwd=cwd)
    return rc == 0


def verify_sha_in_history(sha: str, cwd: Path | None = None) -> bool:
    """Verify that a SHA is in the git history.

    Args:
        sha: The commit SHA to verify
        cwd: Optional working directory

    Returns:
        True if SHA is in history, False otherwise
    """
    # Use rev-parse to check if SHA is reachable
    rc, _, _ = run_git("rev-parse", "--verify", sha, cwd=cwd)
    if rc != 0:
        return False

    # Check if it's in any branch's history
    rc, _, _ = run_git("branch", "-a", "--contains", sha, cwd=cwd)
    return rc == 0


def get_commit_message(sha: str, cwd: Path | None = None) -> str:
    """Get the commit message for a SHA.

    Args:
        sha: The commit SHA
        cwd: Optional working directory

    Returns:
        The commit message
    """
    rc, stdout, _ = run_git("log", "-1", "--format=%B", sha, cwd=cwd)
    if rc != 0:
        return ""
    return stdout


def get_commit_stats(sha: str, cwd: Path | None = None) -> dict[str, Any]:
    """Get statistics about files changed in a commit.

    Args:
        sha: The commit SHA
        cwd: Optional working directory

    Returns:
        Dict with files_changed, insertions, deletions
    """
    rc, stdout, _ = run_git("show", "--stat", "--format=", sha, cwd=cwd)
    if rc != 0:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "files": []}

    files = []
    for line in stdout.split("\n"):
        line = line.strip()
        if "|" in line:
            # Extract filename
            filename = line.split("|")[0].strip()
            if filename:
                files.append(filename)

    # Parse the summary line
    summary_match = re.search(
        r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?",
        stdout,
    )

    if summary_match:
        files_changed = int(summary_match.group(1))
        insertions = int(summary_match.group(2)) if summary_match.group(2) else 0
        deletions = int(summary_match.group(3)) if summary_match.group(3) else 0
    else:
        files_changed = len(files)
        insertions = 0
        deletions = 0

    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
        "files": files,
    }


def check_commit_references_story(
    sha: str, story_id: str, cwd: Path | None = None
) -> bool:
    """Check if a commit message references a story ID.

    Args:
        sha: The commit SHA
        story_id: The story ID to look for (e.g., "ST-AUTO-004")
        cwd: Optional working directory

    Returns:
        True if commit references story, False otherwise
    """
    message = get_commit_message(sha, cwd=cwd)
    # Look for story ID in various formats
    patterns = [
        rf"\({story_id}\)",  # (ST-AUTO-004)
        rf"{story_id}:",  # ST-AUTO-004:
        rf"{story_id}\b",  # ST-AUTO-004 (word boundary)
    ]
    return any(re.search(pattern, message, re.IGNORECASE) for pattern in patterns)


def check_pr_exists(
    pr_number: int, cwd: Path | None = None
) -> tuple[bool, dict[str, Any] | None]:
    """Check if a PR exists via Gitea API.

    Args:
        pr_number: The PR number to check
        cwd: Optional working directory

    Returns:
        Tuple of (exists, pr_data)
    """
    token = (os.getenv("GITEA_TOKEN") or "").strip()
    owner = (
        os.getenv("GITEA_OWNER")
        or os.getenv("CI_REPO_OWNER")
        or os.getenv("WOODPECKER_REPO_OWNER")
        or ""
    ).strip()
    repo = (
        os.getenv("GITEA_REPO")
        or os.getenv("CI_REPO_NAME")
        or os.getenv("WOODPECKER_REPO_NAME")
        or ""
    ).strip()
    base_url = (
        os.getenv("GITEA_BASE_URL") or "http://host.docker.internal:3000"
    ).rstrip("/")

    if not token or not owner or not repo:
        # Cannot check PR without credentials
        return False, None

    url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}"

    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"token {token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return True, data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, None
        return False, None
    except Exception:
        return False, None


def redis_hget(name: str, key: str) -> str | None:
    """Get a value from a Redis hash.

    Args:
        name: The hash key name
        key: The field name

    Returns:
        The value or None if not found/error
    """
    host = (
        os.getenv("CHISE_REDIS_HOST")
        or os.getenv("REDIS_HOST")
        or "host.docker.internal"
    )
    port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
    db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")

    proc = subprocess.run(
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), "HGET", name, key],
        text=True,
        capture_output=True,
        check=False,
    )

    if proc.returncode != 0:
        return None

    result = proc.stdout.strip()
    return result if result else None


def check_merlin_authority() -> tuple[bool, str]:
    """Check if current process/user has Merlin authority.

    Returns:
        Tuple of (has_authority, reason)
    """
    # Check Redis for authority setting
    authority = redis_hget(EP_AUTO_GIT_KEY, STATUS_AUTHORITY_FIELD)

    if authority is None:
        # No authority set, check if we're in a context where we can determine agent
        agent = os.getenv("CHISE_AGENT", "").strip()
        if agent == MERGE_AUTHORITY_AGENT:
            return True, "Agent is Merlin"
        return (
            False,
            f"No authority configured in Redis and agent is '{agent}' (expected '{MERGE_AUTHORITY_AGENT}')",
        )

    if authority != MERLIN_ONLY:
        return False, f"Authority is '{authority}' (expected '{MERLIN_ONLY}')"

    # Authority is merlin-only, check if current agent is Merlin
    agent = os.getenv("CHISE_AGENT", "").strip()
    if agent != MERGE_AUTHORITY_AGENT:
        return False, f"Authority is '{MERLIN_ONLY}' but agent is '{agent}'"

    return True, "Agent is Merlin with merlin-only authority"


def verify_merge_claim(
    story_id: str,
    merge_sha: str,
    pr_number: int | None,
    merge_date: str | None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Verify a merge claim against git evidence.

    Args:
        story_id: The story ID (e.g., "ST-AUTO-004")
        merge_sha: The claimed merge commit SHA
        pr_number: The claimed PR number (optional)
        merge_date: The claimed merge date (optional)
        cwd: Optional working directory

    Returns:
        Dict with verification results
    """
    result = {
        "verified": False,
        "story_id": story_id,
        "merge_sha": merge_sha,
        "pr_number": pr_number,
        "merge_date": merge_date,
        "checks": {},
        "errors": [],
    }

    # Check 1: SHA exists
    if not verify_sha_exists(merge_sha, cwd=cwd):
        result["checks"]["sha_exists"] = False
        result["errors"].append(f"SHA '{merge_sha}' does not exist in repository")
        return result
    result["checks"]["sha_exists"] = True

    # Check 2: SHA is in history
    if not verify_sha_in_history(merge_sha, cwd=cwd):
        result["checks"]["sha_in_history"] = False
        result["errors"].append(f"SHA '{merge_sha}' is not in any branch's history")
        return result
    result["checks"]["sha_in_history"] = True

    # Check 3: Commit references story
    if not check_commit_references_story(merge_sha, story_id, cwd=cwd):
        result["checks"]["references_story"] = False
        result["errors"].append(
            f"Commit '{merge_sha}' does not reference story '{story_id}'"
        )
        return result
    result["checks"]["references_story"] = True

    # Check 4: Get commit stats
    stats = get_commit_stats(merge_sha, cwd=cwd)
    result["checks"]["commit_stats"] = stats

    # Check 5: Verify PR if provided
    if pr_number is not None:
        pr_exists, pr_data = check_pr_exists(pr_number, cwd=cwd)
        result["checks"]["pr_exists"] = pr_exists
        if pr_data:
            result["checks"]["pr_data"] = {
                "number": pr_data.get("number"),
                "state": pr_data.get("state"),
                "merged": pr_data.get("merged"),
                "merge_commit_sha": pr_data.get("merge_commit_sha"),
            }
        if not pr_exists:
            result["errors"].append(f"PR #{pr_number} does not exist")

    # Check 6: Verify merge date if provided
    if merge_date:
        # Get actual commit date
        rc, stdout, _ = run_git("log", "-1", "--format=%ci", merge_sha, cwd=cwd)
        if rc == 0:
            actual_date = stdout.split()[0]  # Get just the date part
            result["checks"]["actual_merge_date"] = actual_date
            if actual_date != merge_date:
                result["errors"].append(
                    f"Merge date mismatch: claimed '{merge_date}', actual '{actual_date}'"
                )

    # Determine overall verification
    result["verified"] = len(result["errors"]) == 0

    return result


def validate_yaml_file(file_path: str, epic_id: str | None = None) -> dict[str, Any]:
    """Validate a workflow status YAML file.

    Args:
        file_path: Path to the YAML file
        epic_id: Optional epic ID to filter by

    Returns:
        Dict with validation results
    """
    import yaml

    result = {
        "valid": False,
        "file": file_path,
        "epic_id": epic_id,
        "entries_checked": 0,
        "entries_failed": 0,
        "errors": [],
    }

    try:
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        result["errors"].append(f"Failed to parse YAML: {e}")
        return result

    if not isinstance(data, dict):
        result["errors"].append("Invalid YAML structure: not a dictionary")
        return result

    # recent_changes is under metadata
    metadata = data.get("metadata", {})
    recent_changes = metadata.get("recent_changes", [])
    if not isinstance(recent_changes, list):
        result["errors"].append(
            "Invalid YAML structure: 'recent_changes' is not a list"
        )
        return result

    for entry in recent_changes:
        result["entries_checked"] += 1

        # Check if entry has merge claim
        merge_sha = entry.get("merge_commit_sha")
        story_id = entry.get("story_id")
        pr_number = entry.get("pr_number")

        if epic_id and entry.get("epic_id") != epic_id:
            continue

        if merge_sha and story_id:
            verification = verify_merge_claim(
                story_id=story_id,
                merge_sha=merge_sha,
                pr_number=pr_number,
                merge_date=None,
            )

            if not verification["verified"]:
                result["entries_failed"] += 1
                result["errors"].append(
                    {
                        "entry": entry.get("action", "unknown"),
                        "story_id": story_id,
                        "merge_sha": merge_sha,
                        "errors": verification["errors"],
                    }
                )

    result["valid"] = result["entries_failed"] == 0
    return result


def cmd_verify(args: argparse.Namespace) -> int:
    """Handle the 'verify' subcommand.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    # Check authority first
    has_authority, reason = check_merlin_authority()
    if not has_authority:
        print(f"ERROR: Authority violation - {reason}", file=sys.stderr)
        return 2

    print(f"OK: Authority check passed - {reason}")

    # Verify the merge claim
    try:
        result = verify_merge_claim(
            story_id=args.story_id,
            merge_sha=args.merge_sha,
            pr_number=args.pr_number,
            merge_date=args.merge_date,
        )
    except Exception as e:
        print(f"ERROR: Verification failed - {e}", file=sys.stderr)
        return 4

    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Story ID: {result['story_id']}")
        print(f"Merge SHA: {result['merge_sha']}")
        print(f"Checks:")
        for check, value in result["checks"].items():
            if isinstance(value, bool):
                status = "✓" if value else "✗"
                print(f"  {status} {check}")
            elif isinstance(value, dict):
                print(f"  {check}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {check}: {value}")

        if result["errors"]:
            print(f"\nErrors:")
            for error in result["errors"]:
                print(f"  ✗ {error}")

    if result["verified"]:
        print("\nRESULT: VERIFIED")
        return 0
    else:
        print("\nRESULT: FAILED - Unverifiable claim")
        return 1


def cmd_validate_yaml(args: argparse.Namespace) -> int:
    """Handle the 'validate-yaml' subcommand.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    # Check authority first
    has_authority, reason = check_merlin_authority()
    if not has_authority:
        print(f"ERROR: Authority violation - {reason}", file=sys.stderr)
        return 2

    print(f"OK: Authority check passed - {reason}")

    # Validate the YAML file
    try:
        result = validate_yaml_file(args.file, args.epic)
    except Exception as e:
        print(f"ERROR: Validation failed - {e}", file=sys.stderr)
        return 4

    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"File: {result['file']}")
        print(f"Epic filter: {result['epic_id'] or 'none'}")
        print(f"Entries checked: {result['entries_checked']}")
        print(f"Entries failed: {result['entries_failed']}")

        if result["errors"]:
            print(f"\nErrors:")
            for error in result["errors"]:
                if isinstance(error, dict):
                    print(f"  Entry: {error['entry']}")
                    print(f"  Story: {error['story_id']}")
                    print(f"  SHA: {error['merge_sha']}")
                    for err in error["errors"]:
                        print(f"    ✗ {err}")
                else:
                    print(f"  ✗ {error}")

    if result["valid"]:
        print("\nRESULT: VALID")
        return 0
    else:
        print("\nRESULT: FAILED - YAML contains unverifiable claims")
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="status_write_gate.py",
        description="Status Write Gate - Validates workflow status changes against git evidence",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify a merge claim against git evidence",
    )
    verify_parser.add_argument(
        "--story-id",
        required=True,
        help="Story ID (e.g., ST-AUTO-004)",
    )
    verify_parser.add_argument(
        "--merge-sha",
        required=True,
        help="Claimed merge commit SHA",
    )
    verify_parser.add_argument(
        "--pr-number",
        type=int,
        help="Claimed PR number",
    )
    verify_parser.add_argument(
        "--merge-date",
        help="Claimed merge date (YYYY-MM-DD)",
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    verify_parser.set_defaults(func=cmd_verify)

    # Validate-yaml command
    yaml_parser = subparsers.add_parser(
        "validate-yaml",
        help="Validate entire workflow status YAML file",
    )
    yaml_parser.add_argument(
        "--file",
        required=True,
        help="Path to YAML file",
    )
    yaml_parser.add_argument(
        "--epic",
        help="Filter by epic ID",
    )
    yaml_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    yaml_parser.set_defaults(func=cmd_validate_yaml)

    return parser


def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except GateError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return e.exit_code
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
