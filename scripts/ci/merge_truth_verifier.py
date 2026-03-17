#!/usr/bin/env python3
"""
Merge Truth Verifier - CI Blocking Gates Integration
Story: BATCH-3 CI-003-A

Verifies that commits claimed to be "merged to main" are actually
present in the main branch. This prevents false merge claims.

Exit codes:
    0: All merge truth verifications passed
    1: One or more commits not found in main
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class MergeClaim:
    """Represents a claimed merge to main."""

    commit_sha: str
    story_id: Optional[str]
    source: str  # PR title, commit message, etc.
    verified: bool = False
    error_message: Optional[str] = None


@dataclass
class VerificationReport:
    """Complete report of merge truth verification."""

    overall_passed: bool = False
    claims: List[MergeClaim] = field(default_factory=list)
    total_checked: int = 0
    total_verified: int = 0
    total_failed: int = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "overall_passed": self.overall_passed,
            "total_checked": self.total_checked,
            "total_verified": self.total_verified,
            "total_failed": self.total_failed,
            "metadata": self.metadata,
            "claims": [
                {
                    "commit_sha": c.commit_sha,
                    "story_id": c.story_id,
                    "source": c.source,
                    "verified": c.verified,
                    "error_message": c.error_message,
                }
                for c in self.claims
            ],
        }


class MergeTruthVerifier:
    """Verifies that claimed merges are actually in main branch."""

    # Patterns to detect merge claims
    MERGE_CLAIM_PATTERNS = [
        r"(?:merged?|merge)[\s#-]*(ST-[A-Z0-9-]+)",
        r"(?:merged?|merge)[\s#-]*(CH-[A-Z0-9-]+)",
        r"(?:merged?|merge)[\s#-]*(FT-[A-Z0-9-]+)",
        r"(?:merged?|merge)[\s#-]*(STRONG-[A-Z0-9-]+)",
        r"(?:merged?|merge)[\s#-]*(TG-[A-Z0-9-]+)",
        r"(?:merged?|merge)[\s#-]*(BATCH-[A-Z0-9-]+)",
        r"(?:merged?|merge)[\s#-]*(CI-[A-Z0-9-]+)",
        r"(?:closes?|fixes?|resolves?)[\s#-]*(ST-[A-Z0-9-]+)",
        r"(?:closes?|fixes?|resolves?)[\s#-]*(CH-[A-Z0-9-]+)",
        r"(?:closes?|fixes?|resolves?)[\s#-]*(FT-[A-Z0-9-]+)",
    ]

    # Story ID patterns
    STORY_ID_PATTERN = re.compile(r"\b(ST|CH|FT|STRONG|TG|BATCH|CI)-[A-Z0-9-]+\b")

    def __init__(self, verbose: bool = False, main_branch: str = "main"):
        self.verbose = verbose
        self.main_branch = main_branch
        self.report = VerificationReport()

    def log(self, message: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[merge-truth] {message}")

    def run_git_command(self, cmd: List[str]) -> Tuple[int, str, str]:
        """Run a git command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                ["git"] + cmd, capture_output=True, text=True, timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Timeout"
        except Exception as e:
            return 1, "", str(e)

    def is_commit_in_main(self, commit_sha: str) -> bool:
        """Check if a commit is in the main branch."""
        # Use git branch --contains to verify
        exit_code, stdout, stderr = self.run_git_command(
            ["branch", "--contains", commit_sha]
        )

        if exit_code != 0:
            self.log(f"Commit {commit_sha[:8]} not found in any branch")
            return False

        branches = stdout.strip().split("\n")
        branches = [b.strip().strip("* ") for b in branches]

        return self.main_branch in branches

    def get_commit_sha_from_ref(self, ref: str) -> Optional[str]:
        """Resolve a ref (branch, tag, etc.) to a commit SHA."""
        exit_code, stdout, stderr = self.run_git_command(["rev-parse", "--verify", ref])

        if exit_code == 0:
            return stdout.strip()
        return None

    def extract_story_ids(self, text: str) -> List[str]:
        """Extract story IDs from text."""
        matches = self.STORY_ID_PATTERN.findall(text)
        # findall returns tuples for groups, extract full match
        return list(set(matches))

    def find_merge_claims_in_pr(self, pr_title: str, pr_body: str) -> List[MergeClaim]:
        """Find merge claims in PR title and body."""
        claims = []
        text = f"{pr_title}\n{pr_body}"

        for pattern in self.MERGE_CLAIM_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                story_id = match.group(1)
                claims.append(
                    MergeClaim(
                        commit_sha="",  # Will be resolved later
                        story_id=story_id,
                        source=f"PR: {pr_title[:50]}...",
                    )
                )

        return claims

    def find_merge_claims_in_commits(self, commit_range: str) -> List[MergeClaim]:
        """Find merge claims in commit messages."""
        claims = []

        exit_code, stdout, stderr = self.run_git_command(
            ["log", commit_range, "--format=%H %s"]
        )

        if exit_code != 0:
            self.log(f"Failed to get commits: {stderr}")
            return claims

        for line in stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue

            commit_sha, message = parts

            # Check for merge claims in message
            for pattern in self.MERGE_CLAIM_PATTERNS:
                matches = re.finditer(pattern, message, re.IGNORECASE)
                for match in matches:
                    story_id = match.group(1)
                    claims.append(
                        MergeClaim(
                            commit_sha=commit_sha,
                            story_id=story_id,
                            source=f"Commit: {message[:50]}...",
                        )
                    )

        return claims

    def verify_claim(self, claim: MergeClaim) -> MergeClaim:
        """Verify a single merge claim."""
        if not claim.commit_sha:
            claim.error_message = "No commit SHA provided"
            claim.verified = False
            return claim

        if self.is_commit_in_main(claim.commit_sha):
            claim.verified = True
            claim.error_message = None
        else:
            claim.verified = False
            claim.error_message = (
                f"Commit {claim.commit_sha[:8]} not found in {self.main_branch}"
            )

        return claim

    def verify_all_claims(self, claims: List[MergeClaim]) -> VerificationReport:
        """Verify all merge claims."""
        self.report.claims = []
        self.report.total_checked = len(claims)
        self.report.total_verified = 0
        self.report.total_failed = 0

        for claim in claims:
            verified_claim = self.verify_claim(claim)
            self.report.claims.append(verified_claim)

            if verified_claim.verified:
                self.report.total_verified += 1
            else:
                self.report.total_failed += 1

        self.report.overall_passed = self.report.total_failed == 0
        return self.report

    def verify_latest_commit(self) -> VerificationReport:
        """Verify the latest commit claims to be in main."""
        print("=" * 60)
        print("Merge Truth Verifier")
        print("=" * 60)
        print("")

        # Get the current HEAD
        exit_code, stdout, stderr = self.run_git_command(["rev-parse", "HEAD"])
        if exit_code != 0:
            print(f"Error: Could not get HEAD: {stderr}")
            self.report.overall_passed = False
            return self.report

        head_sha = stdout.strip()
        print(f"Checking HEAD commit: {head_sha[:8]}")

        # Get commit message
        exit_code, stdout, stderr = self.run_git_command(
            ["log", "-1", "--format=%s", head_sha]
        )
        if exit_code != 0:
            print(f"Error: Could not get commit message: {stderr}")
            self.report.overall_passed = False
            return self.report

        commit_message = stdout.strip()
        print(f"Commit message: {commit_message[:60]}...")
        print("")

        # Check if this commit is in main
        if self.is_commit_in_main(head_sha):
            print(f"✓ Commit {head_sha[:8]} is in {self.main_branch}")
            self.report.overall_passed = True
        else:
            print(f"✗ Commit {head_sha[:8]} is NOT in {self.main_branch}")
            print("")
            print("WARNING: This commit claims to be merged but is not in main!")
            print("This may indicate:")
            print("  - A false merge claim")
            print("  - A force-push that removed the commit")
            print("  - A merge to a different branch")
            self.report.overall_passed = False

        # Extract story IDs from commit message
        story_ids = self.extract_story_ids(commit_message)
        if story_ids:
            print(f"\nStory IDs found: {', '.join(story_ids)}")

        return self.report

    def verify_pr_merge(
        self, pr_title: str = "", pr_body: str = ""
    ) -> VerificationReport:
        """Verify merge claims in a PR."""
        print("=" * 60)
        print("Merge Truth Verifier - PR Mode")
        print("=" * 60)
        print("")

        # Find claims in PR
        claims = self.find_merge_claims_in_pr(pr_title, pr_body)

        if not claims:
            print("No merge claims found in PR")
            self.report.overall_passed = True
            return self.report

        print(f"Found {len(claims)} merge claim(s)")
        print("")

        # Verify each claim
        self.verify_all_claims(claims)

        # Print results
        for claim in self.report.claims:
            if claim.verified:
                print(f"✓ {claim.story_id}: Verified in {self.main_branch}")
            else:
                print(f"✗ {claim.story_id}: {claim.error_message}")

        return self.report

    def print_summary(self) -> None:
        """Print verification summary."""
        print("\n" + "=" * 60)
        print("Verification Summary")
        print("=" * 60)
        print(f"\nTotal checked: {self.report.total_checked}")
        print(f"Verified: {self.report.total_verified}")
        print(f"Failed: {self.report.total_failed}")

        if self.report.overall_passed:
            print("\n✓ ALL MERGE CLAIMS VERIFIED")
        else:
            print("\n✗ MERGE VERIFICATION FAILED")

    def write_report(self, output_path: str) -> None:
        """Write the report to a JSON file."""
        try:
            with open(output_path, "w") as f:
                json.dump(self.report.to_dict(), f, indent=2)
            self.log(f"Report written to: {output_path}")
        except IOError as e:
            print(f"Warning: Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Verify merge truth - ensure commits are actually in main"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--main-branch", default="main", help="Name of main branch (default: main)"
    )
    parser.add_argument("--pr-title", help="PR title to check for merge claims")
    parser.add_argument("--pr-body", help="PR body to check for merge claims")
    parser.add_argument("--output", "-o", help="Output path for JSON report")
    parser.add_argument(
        "--check-head", action="store_true", help="Check if HEAD commit is in main"
    )

    args = parser.parse_args()

    verifier = MergeTruthVerifier(verbose=args.verbose, main_branch=args.main_branch)

    if args.check_head:
        report = verifier.verify_latest_commit()
    elif args.pr_title or args.pr_body:
        report = verifier.verify_pr_merge(
            pr_title=args.pr_title or "", pr_body=args.pr_body or ""
        )
    else:
        # Default: check HEAD
        report = verifier.verify_latest_commit()

    verifier.print_summary()

    if args.output:
        verifier.write_report(args.output)

    sys.exit(0 if report.overall_passed else 1)


if __name__ == "__main__":
    main()
