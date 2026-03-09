#!/usr/bin/env python3
"""
Branch hygiene checker for ChiseAI repository.
Analyzes branches and recommends cleanup actions.
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime

from config.bootstrap import bootstrap, check_environment

# Try to import Redis, but don't fail if unavailable
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Warning: redis not available, using local tracking only")


def get_all_branches():
    """Get list of all local branches."""
    result = subprocess.run(  # nosec B607
        ["git", "branch", "--format=%(refname:short)"],
        capture_output=True,
        text=True,
    )

    branches = []
    for line in result.stdout.strip().split("\n"):
        if line:
            branches.append(line.strip())

    return branches


def get_branch_info(branch_name):
    """Get detailed info about a branch."""
    info = {}

    # Last commit date
    result = subprocess.run(  # nosec B607
        ["git", "log", "-1", "--format=%ci", branch_name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        info["last_commit"] = result.stdout.strip()

    # Check if merged to main
    result = subprocess.run(  # nosec B607
        ["git", "branch", "--merged", "main", "--list", branch_name],
        capture_output=True,
        text=True,
    )
    info["merged_to_main"] = branch_name in result.stdout

    # Check commits behind main
    result = subprocess.run(  # nosec B607
        ["git", "rev-list", "--count", f"{branch_name}..main"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        info["commits_behind"] = int(result.stdout.strip())
    else:
        info["commits_behind"] = 0

    # Check if has remote tracking
    result = subprocess.run(  # nosec B607
        ["git", "rev-parse", "--abbrev-ref", f"{branch_name}@{{upstream}}"],
        capture_output=True,
        text=True,
    )
    info["has_remote"] = result.returncode == 0

    return info


def check_branch_naming(branch_name):
    """Check if branch follows naming conventions."""
    valid_patterns = [
        "feature/ST-",
        "feature/CH-",
        "feature/FT-",
        "safety/",
        "hotfix/",
        "chore/",
    ]

    for pattern in valid_patterns:
        if branch_name.startswith(pattern):
            return True, None

    return False, f"Invalid naming: {branch_name}"


def check_pr_exists(branch_name, base_ref="main"):
    """Check if a PR exists for the branch in Gitea."""
    import os
    import urllib.error
    import urllib.parse
    import urllib.request

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
        return False, "Gitea token/owner/repo env vars missing"

    page = 1
    while page <= 10:
        qs = urllib.parse.urlencode({"state": "all", "limit": 50, "page": page})
        url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls?{qs}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"token {token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                rows = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return False, f"Gitea PR check failed: {exc}"

        if not isinstance(rows, list) or not rows:
            break

        for pr in rows:
            if not isinstance(pr, dict):
                continue
            head_ref = str((pr.get("head") or {}).get("ref", "")).strip()
            base_pr_ref = str((pr.get("base") or {}).get("ref", "")).strip()
            if head_ref != branch_name or base_pr_ref != base_ref:
                continue
            if bool(pr.get("merged")):
                return True, f"merged PR #{pr.get('number')}"
            if str(pr.get("state", "")).lower() == "open":
                return True, f"open PR #{pr.get('number')}"

        if len(rows) < 50:
            break
        page += 1

    return False, "No open/merged PR found for branch"


def check_branch_deletion_eligibility(branch_name, base_ref="main"):
    """
    Check if a branch is eligible for deletion.

    Returns:
        dict: {
            'eligible': bool,
            'reason': str,
            'has_pr': bool,
            'pr_detail': str,
            'is_merged': bool,
            'has_merge_evidence': bool,
        }
    """
    result = {
        "eligible": False,
        "reason": "",
        "has_pr": False,
        "pr_detail": "",
        "is_merged": False,
        "has_merge_evidence": False,
    }

    # Check if merged to main
    merged_result = subprocess.run(  # nosec B607
        ["git", "branch", "--merged", base_ref, "--list", branch_name],
        capture_output=True,
        text=True,
    )
    result["is_merged"] = branch_name in merged_result.stdout

    if result["is_merged"]:
        result["eligible"] = True
        result["reason"] = "Branch is merged to main"
        result["has_merge_evidence"] = True
        return result

    # Check for merge commit evidence
    commit_result = subprocess.run(  # nosec B607
        ["git", "rev-parse", branch_name],
        capture_output=True,
        text=True,
    )
    if commit_result.returncode == 0:
        branch_commit = commit_result.stdout.strip()
        ancestor_result = subprocess.run(  # nosec B607
            ["git", "merge-base", "--is-ancestor", branch_commit, base_ref],
            capture_output=True,
            text=True,
        )
        if ancestor_result.returncode == 0:
            result["eligible"] = True
            result["reason"] = (
                f"Branch commit {branch_commit[:8]} is ancestor of {base_ref}"
            )
            result["has_merge_evidence"] = True
            return result

    # Check for PR
    has_pr, pr_detail = check_pr_exists(branch_name, base_ref)
    result["has_pr"] = has_pr
    result["pr_detail"] = pr_detail

    if has_pr:
        result["eligible"] = True
        result["reason"] = pr_detail
        return result

    # Not eligible
    result["reason"] = "No PR or merge evidence found"
    return result


def log_deletion_attempt_to_redis(branch_name, result, force_used=False):
    """Log deletion check to Redis."""
    if not REDIS_AVAILABLE:
        return

    try:
        r = redis.Redis(host="host.docker.internal", port=6380, db=0)

        log_entry = {
            "branch": branch_name,
            "eligible": result["eligible"],
            "reason": result["reason"],
            "has_pr": result["has_pr"],
            "is_merged": result["is_merged"],
            "force_used": force_used,
            "checked_at": datetime.now().isoformat(),
        }

        # Add to list of deletion checks
        r.lpush(
            "bmad:chiseai:branch_hygiene:deletion_checks",
            json.dumps(log_entry),
        )

        # Keep only last 1000 checks
        r.ltrim("bmad:chiseai:branch_hygiene:deletion_checks", 0, 999)

    except Exception as e:
        print(f"Warning: Could not log to Redis: {e}")


def analyze_branches():
    """Analyze all branches and categorize."""
    branches = get_all_branches()

    categories = {"critical": [], "warning": [], "healthy": [], "invalid_name": []}

    for branch in branches:
        if branch == "main":
            continue

        info = get_branch_info(branch)
        issues = []

        # Check naming
        is_valid, naming_issue = check_branch_naming(branch)
        if not is_valid:
            categories["invalid_name"].append(
                {"name": branch, "issue": naming_issue, "info": info}
            )
            continue

        # Check if merged
        if info.get("merged_to_main"):
            categories["critical"].append(
                {"name": branch, "issue": "Already merged to main", "info": info}
            )
            continue

        # Check commits behind
        if info.get("commits_behind", 0) > 7:
            issues.append(f"Behind main by {info['commits_behind']} commits")

        # Check last activity (simplified - assumes commit date)
        if info.get("last_commit"):
            last_date = datetime.fromisoformat(
                info["last_commit"].replace("Z", "+00:00")
            )
            days_inactive = (datetime.now(UTC) - last_date).days
            if days_inactive > 30:
                issues.append(f"No activity for {days_inactive} days")

        if issues:
            categories["warning"].append(
                {"name": branch, "issues": issues, "info": info}
            )
        else:
            categories["healthy"].append({"name": branch, "info": info})

    return categories


def log_to_redis(categories):
    """Log hygiene status to Redis."""
    if not REDIS_AVAILABLE:
        return

    try:
        r = redis.Redis(host="host.docker.internal", port=6380, db=0)

        # Log warnings
        for branch in categories["warning"]:
            r.hset(
                "bmad:chiseai:branch_hygiene:warned:behind",
                branch["name"],
                json.dumps(
                    {
                        "issues": branch["issues"],
                        "checked_at": datetime.now().isoformat(),
                    }
                ),
            )

        # Log summary
        r.hset(
            f"bmad:chiseai:branch_hygiene:summary:{datetime.now().strftime('%Y-%m-%d')}",
            "report",
            json.dumps(
                {
                    "total": sum(len(v) for v in categories.values()),
                    "critical": len(categories["critical"]),
                    "warning": len(categories["warning"]),
                    "healthy": len(categories["healthy"]),
                    "invalid": len(categories["invalid_name"]),
                    "checked_at": datetime.now().isoformat(),
                }
            ),
        )
    except Exception as e:
        print(f"Warning: Could not log to Redis: {e}")


def print_report(categories):
    """Print formatted report."""
    print(f"Branch Hygiene Report - {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 50)

    if categories["critical"]:
        print(f"\n🔴 CRITICAL ({len(categories['critical'])} branches):")
        for branch in categories["critical"]:
            print(f"  {branch['name']}")
            print(f"    → {branch['issue']}")
            print("    → Action: Delete (already merged)")

    if categories["warning"]:
        print(f"\n🟡 WARNING ({len(categories['warning'])} branches):")
        for branch in categories["warning"]:
            print(f"  {branch['name']}")
            for issue in branch["issues"]:
                print(f"    ⚠️  {issue}")
            print("    → Action: Update or delete")

    if categories["invalid_name"]:
        print(f"\n🟠 INVALID NAME ({len(categories['invalid_name'])} branches):")
        for branch in categories["invalid_name"]:
            print(f"  {branch['name']}")
            print(f"    → {branch['issue']}")

    if categories["healthy"]:
        print(f"\n✅ HEALTHY ({len(categories['healthy'])} branches):")
        for branch in categories["healthy"][:5]:  # Show first 5
            print(f"  {branch['name']}")
        if len(categories["healthy"]) > 5:
            print(f"    ... and {len(categories['healthy']) - 5} more")


def check_critical_environment():
    """Verify critical environment variables are set."""
    result = check_environment(
        [
            "REDIS_HOST",
            "CHISE_REDIS_HOST",
        ]
    )

    if not result["ok"]:
        # Not a hard failure - Redis may use defaults
        if not result["present"]:
            print(
                "WARN: No Redis host configured. Using default: host.docker.internal:6380",
            )

    for warning in result.get("warnings", []):
        print(f"WARN: {warning}")


def main():
    # Bootstrap environment first
    bootstrap(load_env=True)

    # Check critical environment variables
    check_critical_environment()

    parser = argparse.ArgumentParser(description="Check branch hygiene")
    parser.add_argument("--report", action="store_true", help="Print report")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done"
    )
    parser.add_argument(
        "--auto-clean", action="store_true", help="Auto-clean safe branches"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force cleanup (dangerous)"
    )
    parser.add_argument(
        "--check-deletion",
        metavar="BRANCH",
        help="Check if a branch is eligible for deletion",
    )

    args = parser.parse_args()

    # Handle deletion eligibility check
    if args.check_deletion:
        result = check_branch_deletion_eligibility(args.check_deletion)
        log_deletion_attempt_to_redis(args.check_deletion, result, args.force)

        status = "✅ ELIGIBLE" if result["eligible"] else "❌ BLOCKED"
        print(f"{status} for deletion: {args.check_deletion}")
        print(f"  Reason: {result['reason']}")
        print(f"  Has PR: {result['has_pr']}")
        if result["pr_detail"]:
            print(f"  PR Detail: {result['pr_detail']}")
        print(f"  Is Merged: {result['is_merged']}")
        print(f"  Has Merge Evidence: {result['has_merge_evidence']}")

        if not result["eligible"]:
            print("\n⚠️  This branch cannot be safely deleted.")
            print("   Either create a PR and merge it, or use --force to override.")
            sys.exit(1)
        sys.exit(0)

    categories = analyze_branches()

    if args.report or not any([args.dry_run, args.auto_clean]):
        print_report(categories)

    log_to_redis(categories)

    if args.dry_run:
        print("\n🧪 DRY RUN - No changes made")
        print("Would delete:", [b["name"] for b in categories["critical"]])

    if args.auto_clean:
        print("\n🧹 AUTO-CLEAN: Deleting merged branches...")
        deleted = []
        errors = []

        for branch in categories["critical"]:
            branch_name = branch["name"]
            try:
                # Safety check: only delete if merged to main
                result = subprocess.run(  # nosec B607
                    ["git", "branch", "--merged", "main", "--list", branch_name],
                    capture_output=True,
                    text=True,
                )
                if branch_name not in result.stdout:
                    errors.append(f"{branch_name}: Not confirmed as merged to main")
                    continue

                # Delete the local branch
                result = subprocess.run(  # nosec B607
                    ["git", "branch", "-d", branch_name],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    deleted.append(branch_name)
                    print(f"  ✅ Deleted: {branch_name}")

                    # Log to Redis
                    if REDIS_AVAILABLE:
                        try:
                            r = redis.Redis(
                                host="host.docker.internal", port=6380, db=0
                            )
                            r.hset(
                                "bmad:chiseai:branch_hygiene:deleted:merged",
                                branch_name,
                                json.dumps(
                                    {
                                        "deleted_at": datetime.now().isoformat(),
                                        "reason": "auto_clean_merged",
                                        "method": "safe_delete",
                                    }
                                ),
                            )
                        except Exception as e:
                            print(f"    Warning: Could not log to Redis: {e}")
                else:
                    errors.append(f"{branch_name}: {result.stderr}")
                    print(f"  ❌ Failed: {branch_name} - {result.stderr}")

            except Exception as e:
                errors.append(f"{branch_name}: {str(e)}")
                print(f"  ❌ Error: {branch_name} - {str(e)}")

        print("\n📊 Summary:")
        print(f"  Deleted: {len(deleted)} branches")
        print(f"  Errors: {len(errors)} branches")

        if deleted:
            print("\n  Deleted branches:")
            for b in deleted:
                print(f"    - {b}")

        if errors:
            print("\n  Errors encountered:")
            for err in errors:
                print(f"    - {err}")

        # Policy confirmation
        print("\n🔒 Policy Compliance:")
        print(f"  --force flag used: {'YES' if args.force else 'NO (safe mode)'}")
        print("  Only merged branches deleted: YES")
        print("  Safety verification: Double-checked merge status before deletion")


if __name__ == "__main__":
    main()
