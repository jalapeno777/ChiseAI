#!/usr/bin/env python3
"""Trigger GitReviewBot for manual testing."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Bootstrap for config and environment (ST-CI-005 compliance)
from config.bootstrap import bootstrap

bootstrap(load_env=True)

from autonomous_git.gitreviewbot import GiteaClient, GitReviewBot


async def review_pr(
    pr_number: int,
    gitea_url: str,
    gitea_token: str,
    owner: str,
    repo: str,
    skip_cache: bool = False,
    auto_merge: bool = False,
) -> None:
    """Review a single PR."""
    gitea = GiteaClient(
        base_url=gitea_url,
        token=gitea_token,
        owner=owner,
        repo=repo,
    )

    bot = GitReviewBot(
        gitea_client=gitea,
        enable_auto_merge=auto_merge,
    )

    try:
        print(f"🔍 Reviewing PR #{pr_number}...")
        decision = await bot.review_pr(pr_number, skip_cache=skip_cache)

        print(f"\n✅ Review Complete")
        print(f"   Decision: {decision.decision.value}")
        print(f"   Confidence: {decision.confidence:.1f}%")
        print(f"   SeniorDev: {decision.senior_dev_confidence:.1f}%")
        print(f"   Critic: {decision.critic_confidence:.1f}%")

        if decision.blockers:
            print(f"\n🚫 Blockers:")
            for blocker in decision.blockers:
                print(f"   - {blocker}")

        if decision.findings:
            print(f"\n📋 Findings ({len(decision.findings)}):")
            for finding in decision.findings[:5]:
                print(
                    f"   [{finding.severity.value}] {finding.file}: {finding.message}"
                )

        if decision.violations:
            print(f"\n⚖️ Violations ({len(decision.violations)}):")
            for violation in decision.violations[:5]:
                print(
                    f"   [{violation.severity.value}] {violation.rule}: {violation.message}"
                )

        if decision.auto_merge_eligible:
            print(f"\n✨ Auto-merge eligible!")

        print(f"\n📝 Summary:")
        print(f"   {decision.summary}")

    except Exception as e:
        print(f"❌ Error reviewing PR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await gitea.close()


def main():
    parser = argparse.ArgumentParser(
        description="Trigger GitReviewBot for manual PR review"
    )
    parser.add_argument(
        "pr_number",
        type=int,
        help="PR number to review",
    )
    parser.add_argument(
        "--gitea-url",
        default=os.getenv("GITEA_URL", "http://localhost:3000"),
        help="Gitea URL (default: $GITEA_URL or http://localhost:3000)",
    )
    parser.add_argument(
        "--gitea-token",
        default=os.getenv("GITEA_TOKEN"),
        help="Gitea API token (default: $GITEA_TOKEN)",
    )
    parser.add_argument(
        "--owner",
        default=os.getenv("GITEA_OWNER", "chiseai"),
        help="Repository owner (default: $GITEA_OWNER or chiseai)",
    )
    parser.add_argument(
        "--repo",
        default=os.getenv("GITEA_REPO", "chiseai"),
        help="Repository name (default: $GITEA_REPO or chiseai)",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        help="Skip diff cache and force fresh review",
    )
    parser.add_argument(
        "--auto-merge",
        action="store_true",
        help="Enable auto-merge for high-confidence PRs",
    )

    args = parser.parse_args()

    if not args.gitea_token:
        print(
            "Error: Gitea token required. Set GITEA_TOKEN env var or use --gitea-token",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(
        review_pr(
            pr_number=args.pr_number,
            gitea_url=args.gitea_url,
            gitea_token=args.gitea_token,
            owner=args.owner,
            repo=args.repo,
            skip_cache=args.skip_cache,
            auto_merge=args.auto_merge,
        )
    )


if __name__ == "__main__":
    main()
