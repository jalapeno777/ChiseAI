#!/usr/bin/env python3
"""
Branch hygiene checker for ChiseAI repository.
Analyzes branches and recommends cleanup actions.
"""

import subprocess
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Try to import Redis, but don't fail if unavailable
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Warning: redis not available, using local tracking only")


def get_all_branches():
    """Get list of all local branches."""
    result = subprocess.run(
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
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ci", branch_name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        info["last_commit"] = result.stdout.strip()

    # Check if merged to main
    result = subprocess.run(
        ["git", "branch", "--merged", "main", "--list", branch_name],
        capture_output=True,
        text=True,
    )
    info["merged_to_main"] = branch_name in result.stdout

    # Check commits behind main
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{branch_name}..main"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        info["commits_behind"] = int(result.stdout.strip())
    else:
        info["commits_behind"] = 0

    # Check if has remote tracking
    result = subprocess.run(
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
            days_inactive = (datetime.now() - last_date).days
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
                f"bmad:chiseai:branch_hygiene:warned:behind",
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
            print(f"    → Action: Delete (already merged)")

    if categories["warning"]:
        print(f"\n🟡 WARNING ({len(categories['warning'])} branches):")
        for branch in categories["warning"]:
            print(f"  {branch['name']}")
            for issue in branch["issues"]:
                print(f"    ⚠️  {issue}")
            print(f"    → Action: Update or delete")

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


def main():
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

    args = parser.parse_args()

    categories = analyze_branches()

    if args.report or not any([args.dry_run, args.auto_clean]):
        print_report(categories)

    log_to_redis(categories)

    if args.dry_run:
        print("\n🧪 DRY RUN - No changes made")
        print("Would delete:", [b["name"] for b in categories["critical"]])


if __name__ == "__main__":
    main()
