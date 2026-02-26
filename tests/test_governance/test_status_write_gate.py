#!/usr/bin/env python3
"""Tests for status_write_gate.py

Tests cover:
- Valid SHA verification
- Invalid SHA (should fail)
- Authority check
- Missing arguments
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "governance"))

from status_write_gate import (
    verify_sha_exists,
    verify_sha_in_history,
    check_commit_references_story,
    get_commit_stats,
    check_merlin_authority,
    verify_merge_claim,
    AuthorityError,
    GateError,
)


class TestShaVerification(unittest.TestCase):
    """Tests for SHA verification functions."""

    def test_verify_sha_exists_valid(self):
        """Test that a valid SHA exists."""
        # Use a known valid SHA from the repo
        result = verify_sha_exists("02237f6")
        self.assertTrue(result)

    def test_verify_sha_exists_invalid(self):
        """Test that an invalid SHA does not exist."""
        result = verify_sha_exists("0000000")
        self.assertFalse(result)

    def test_verify_sha_in_history_valid(self):
        """Test that a valid SHA is in history."""
        result = verify_sha_in_history("02237f6")
        self.assertTrue(result)

    def test_verify_sha_in_history_invalid(self):
        """Test that an invalid SHA is not in history."""
        result = verify_sha_in_history("0000000")
        self.assertFalse(result)


class TestCommitReferences(unittest.TestCase):
    """Tests for commit reference checking."""

    def test_check_commit_references_story_valid(self):
        """Test that commit references story."""
        # 02237f6 is ST-AUTO-004 merge commit
        result = check_commit_references_story("02237f6", "ST-AUTO-004")
        self.assertTrue(result)

    def test_check_commit_references_story_invalid(self):
        """Test that commit does not reference wrong story."""
        result = check_commit_references_story("02237f6", "ST-OTHER-001")
        self.assertFalse(result)


class TestCommitStats(unittest.TestCase):
    """Tests for commit statistics."""

    def test_get_commit_stats_valid(self):
        """Test getting stats for valid commit."""
        stats = get_commit_stats("02237f6")
        self.assertIn("files_changed", stats)
        self.assertIn("insertions", stats)
        self.assertIn("deletions", stats)
        self.assertIn("files", stats)
        self.assertIsInstance(stats["files_changed"], int)
        self.assertIsInstance(stats["files"], list)

    def test_get_commit_stats_invalid(self):
        """Test getting stats for invalid commit."""
        stats = get_commit_stats("0000000")
        self.assertEqual(stats["files_changed"], 0)
        self.assertEqual(stats["files"], [])


class TestAuthorityCheck(unittest.TestCase):
    """Tests for authority checking."""

    def test_check_merlin_authority_without_env(self):
        """Test authority check without CHISE_AGENT set."""
        # Clear the environment variable
        old_agent = os.environ.pop("CHISE_AGENT", None)
        try:
            has_authority, reason = check_merlin_authority()
            self.assertFalse(has_authority)
            self.assertIn("merlin", reason.lower())
        finally:
            # Restore environment
            if old_agent:
                os.environ["CHISE_AGENT"] = old_agent

    def test_check_merlin_authority_with_merlin(self):
        """Test authority check with CHISE_AGENT=merlin."""
        old_agent = os.environ.get("CHISE_AGENT")
        os.environ["CHISE_AGENT"] = "merlin"
        try:
            has_authority, reason = check_merlin_authority()
            self.assertTrue(has_authority)
            self.assertIn("merlin", reason.lower())
        finally:
            if old_agent:
                os.environ["CHISE_AGENT"] = old_agent
            else:
                os.environ.pop("CHISE_AGENT", None)

    def test_check_merlin_authority_with_wrong_agent(self):
        """Test authority check with wrong agent."""
        old_agent = os.environ.get("CHISE_AGENT")
        os.environ["CHISE_AGENT"] = "senior-dev"
        try:
            has_authority, reason = check_merlin_authority()
            self.assertFalse(has_authority)
            self.assertIn("merlin", reason.lower())
        finally:
            if old_agent:
                os.environ["CHISE_AGENT"] = old_agent
            else:
                os.environ.pop("CHISE_AGENT", None)


class TestMergeClaimVerification(unittest.TestCase):
    """Tests for merge claim verification."""

    def test_verify_merge_claim_valid(self):
        """Test verification of valid merge claim."""
        old_agent = os.environ.get("CHISE_AGENT")
        os.environ["CHISE_AGENT"] = "merlin"
        try:
            result = verify_merge_claim(
                story_id="ST-AUTO-004",
                merge_sha="02237f6",
                pr_number=276,
                merge_date=None,
            )
            self.assertTrue(result["verified"])
            self.assertTrue(result["checks"]["sha_exists"])
            self.assertTrue(result["checks"]["sha_in_history"])
            self.assertTrue(result["checks"]["references_story"])
        finally:
            if old_agent:
                os.environ["CHISE_AGENT"] = old_agent
            else:
                os.environ.pop("CHISE_AGENT", None)

    def test_verify_merge_claim_invalid_sha(self):
        """Test verification with invalid SHA."""
        old_agent = os.environ.get("CHISE_AGENT")
        os.environ["CHISE_AGENT"] = "merlin"
        try:
            result = verify_merge_claim(
                story_id="ST-AUTO-004",
                merge_sha="0000000",
                pr_number=None,
                merge_date=None,
            )
            self.assertFalse(result["verified"])
            self.assertFalse(result["checks"]["sha_exists"])
            self.assertTrue(len(result["errors"]) > 0)
        finally:
            if old_agent:
                os.environ["CHISE_AGENT"] = old_agent
            else:
                os.environ.pop("CHISE_AGENT", None)

    def test_verify_merge_claim_wrong_story(self):
        """Test verification with wrong story ID."""
        old_agent = os.environ.get("CHISE_AGENT")
        os.environ["CHISE_AGENT"] = "merlin"
        try:
            result = verify_merge_claim(
                story_id="ST-OTHER-001",
                merge_sha="02237f6",
                pr_number=None,
                merge_date=None,
            )
            self.assertFalse(result["verified"])
            self.assertFalse(result["checks"]["references_story"])
        finally:
            if old_agent:
                os.environ["CHISE_AGENT"] = old_agent
            else:
                os.environ.pop("CHISE_AGENT", None)


class TestCLI(unittest.TestCase):
    """Tests for command-line interface."""

    SCRIPT_PATH = (
        Path(__file__).parent.parent.parent
        / "scripts"
        / "governance"
        / "status_write_gate.py"
    )

    def run_script(self, *args, env=None):
        """Run the script with given arguments."""
        cmd = [sys.executable, str(self.SCRIPT_PATH), *args]
        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env_vars,
        )
        return result

    def test_cli_help(self):
        """Test CLI help output."""
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Status Write Gate", result.stdout)

    def test_cli_verify_help(self):
        """Test verify subcommand help."""
        result = self.run_script("verify", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--story-id", result.stdout)
        self.assertIn("--merge-sha", result.stdout)

    def test_cli_missing_args(self):
        """Test CLI with missing arguments."""
        result = self.run_script("verify")
        self.assertNotEqual(result.returncode, 0)

    def test_cli_valid_verification(self):
        """Test CLI with valid verification."""
        result = self.run_script(
            "verify",
            "--story-id",
            "ST-AUTO-004",
            "--merge-sha",
            "02237f6",
            env={"CHISE_AGENT": "merlin"},
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("VERIFIED", result.stdout)

    def test_cli_invalid_sha(self):
        """Test CLI with invalid SHA."""
        result = self.run_script(
            "verify",
            "--story-id",
            "ST-AUTO-004",
            "--merge-sha",
            "0000000",
            env={"CHISE_AGENT": "merlin"},
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAILED", result.stdout)

    def test_cli_no_authority(self):
        """Test CLI without authority."""
        env = os.environ.copy()
        env.pop("CHISE_AGENT", None)
        result = self.run_script(
            "verify",
            "--story-id",
            "ST-AUTO-004",
            "--merge-sha",
            "02237f6",
            env=env,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Authority violation", result.stderr)


if __name__ == "__main__":
    unittest.main()
