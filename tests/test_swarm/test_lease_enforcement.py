#!/usr/bin/env python3
"""
Tests for lease_enforcement.py — session lease TTL and renewal validation.

Story: SWARM-HARDEN-001
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.swarm.lease_enforcement import (
    BRANCH_LEASE_PREFIX,
    WORKTREE_LEASE_PREFIX,
    EnforcementReport,
    LeaseEnforcementError,
    LeaseEnforcer,
    LeaseInfo,
    LeaseRenewalResult,
    LeaseStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(returncode=0, stdout="", stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# LeaseInfo tests
# ---------------------------------------------------------------------------


class TestLeaseInfo(unittest.TestCase):
    """Test LeaseInfo dataclass properties."""

    def test_valid_lease_is_valid(self):
        info = LeaseInfo(
            key="bmad:chiseai:branch-lease:feature/test",
            value="ST-001/agent/2026-03-19T00:00:00Z",
            ttl_seconds=300,
            status=LeaseStatus.VALID,
            checked_at="2026-03-19T00:00:00Z",
        )
        self.assertTrue(info.is_valid)
        self.assertFalse(info.is_expired)
        self.assertFalse(info.is_missing)

    def test_expired_lease(self):
        info = LeaseInfo(
            key="bmad:chiseai:branch-lease:feature/test",
            value="ST-001/agent/2026-03-19T00:00:00Z",
            ttl_seconds=0,
            status=LeaseStatus.EXPIRED,
            checked_at="2026-03-19T00:00:00Z",
        )
        self.assertFalse(info.is_valid)
        self.assertTrue(info.is_expired)

    def test_missing_lease(self):
        info = LeaseInfo(
            key="bmad:chiseai:branch-lease:feature/test",
            value="",
            ttl_seconds=None,
            status=LeaseStatus.MISSING,
            checked_at="2026-03-19T00:00:00Z",
        )
        self.assertFalse(info.is_valid)
        self.assertTrue(info.is_missing)

    def test_conflict_lease(self):
        info = LeaseInfo(
            key="bmad:chiseai:branch-lease:feature/test",
            value="OTHER-STORY/other-agent/2026-03-19T00:00:00Z",
            ttl_seconds=None,
            status=LeaseStatus.CONFLICT,
            checked_at="2026-03-19T00:00:00Z",
        )
        self.assertFalse(info.is_valid)
        self.assertFalse(info.is_expired)
        self.assertFalse(info.is_missing)


# ---------------------------------------------------------------------------
# LeaseRenewalResult tests
# ---------------------------------------------------------------------------


class TestLeaseRenewalResult(unittest.TestCase):
    """Test LeaseRenewalResult dataclass properties."""

    def test_successful_renewal_extended_ttl(self):
        result = LeaseRenewalResult(
            key="bmad:chiseai:branch-lease:feature/test",
            success=True,
            new_ttl_seconds=432000,
            previous_ttl_seconds=100,
            renewed_at="2026-03-19T00:00:00Z",
        )
        self.assertTrue(result.success)
        self.assertTrue(result.ttl_extended)

    def test_successful_renewal_shorter_ttl(self):
        result = LeaseRenewalResult(
            key="bmad:chiseai:branch-lease:feature/test",
            success=True,
            new_ttl_seconds=60,
            previous_ttl_seconds=300,
            renewed_at="2026-03-19T00:00:00Z",
        )
        self.assertTrue(result.success)
        self.assertFalse(result.ttl_extended)

    def test_failed_renewal(self):
        result = LeaseRenewalResult(
            key="bmad:chiseai:branch-lease:feature/test",
            success=False,
            new_ttl_seconds=None,
            previous_ttl_seconds=100,
            renewed_at="2026-03-19T00:00:00Z",
            error="Ownership conflict",
        )
        self.assertFalse(result.success)
        self.assertFalse(result.ttl_extended)
        self.assertIsNotNone(result.error)

    def test_ttl_extended_when_previous_none(self):
        result = LeaseRenewalResult(
            key="bmad:chiseai:branch-lease:feature/test",
            success=True,
            new_ttl_seconds=432000,
            previous_ttl_seconds=None,
            renewed_at="2026-03-19T00:00:00Z",
        )
        self.assertFalse(result.ttl_extended)


# ---------------------------------------------------------------------------
# EnforcementReport tests
# ---------------------------------------------------------------------------


class TestEnforcementReport(unittest.TestCase):
    """Test EnforcementReport dataclass properties."""

    def test_compliant_report(self):
        report = EnforcementReport(
            branch_lease=None,
            worktree_lease=None,
            story_id="ST-001",
            agent="agent",
            checked_at="2026-03-19T00:00:00Z",
            violations=[],
            warnings=[],
        )
        self.assertTrue(report.is_compliant)
        self.assertFalse(report.has_warnings)

    def test_report_with_violations(self):
        report = EnforcementReport(
            branch_lease=None,
            worktree_lease=None,
            story_id="ST-001",
            agent="agent",
            checked_at="2026-03-19T00:00:00Z",
            violations=["branch lease is missing"],
            warnings=[],
        )
        self.assertFalse(report.is_compliant)

    def test_report_with_warnings(self):
        report = EnforcementReport(
            branch_lease=None,
            worktree_lease=None,
            story_id="ST-001",
            agent="agent",
            checked_at="2026-03-19T00:00:00Z",
            violations=[],
            warnings=["branch lease TTL is low (120s remaining)"],
        )
        self.assertTrue(report.is_compliant)
        self.assertTrue(report.has_warnings)


# ---------------------------------------------------------------------------
# LeaseEnforcer — check_lease tests (AC1: TTL expiration check)
# ---------------------------------------------------------------------------


class TestLeaseEnforcerCheckLease(unittest.TestCase):
    """Test LeaseEnforcer.check_lease for TTL expiration and validity."""

    def setUp(self):
        self.enforcer = LeaseEnforcer(
            redis_host="localhost",
            redis_port=6380,
            redis_db=0,
        )

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_valid_lease_with_positive_ttl(self, mock_cli):
        """AC1: Lease with positive TTL is reported as VALID."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),  # GET
            _make_completed_process(stdout="300"),  # TTL
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.VALID)
        self.assertEqual(info.ttl_seconds, 300)
        self.assertTrue(info.is_valid)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_expired_lease_ttl_zero(self, mock_cli):
        """AC1: Lease with TTL=0 is reported as EXPIRED."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),  # GET
            _make_completed_process(stdout="0"),  # TTL
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.EXPIRED)
        self.assertTrue(info.is_expired)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_expired_lease_ttl_negative(self, mock_cli):
        """AC1: Lease with negative TTL is reported as EXPIRED."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),  # GET
            _make_completed_process(stdout="-5"),  # TTL (already expired)
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.EXPIRED)
        self.assertTrue(info.is_expired)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_missing_lease(self, mock_cli):
        """AC1: Missing lease (GET returns empty) is reported as MISSING."""
        mock_cli.side_effect = [
            _make_completed_process(stdout=""),  # GET returns empty
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.MISSING)
        self.assertTrue(info.is_missing)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_conflict_lease_wrong_owner(self, mock_cli):
        """AC1: Lease owned by different story/agent is reported as CONFLICT."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="OTHER-STORY/other-agent/2026-03-19T00:00:00Z"
            ),  # GET
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.CONFLICT)
        self.assertFalse(info.is_valid)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_redis_get_error(self, mock_cli):
        """AC1: Redis GET failure returns ERROR status."""
        mock_cli.side_effect = [
            _make_completed_process(
                returncode=1, stderr="Connection refused"
            ),  # GET fails
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.ERROR)
        self.assertEqual(info.value, "")

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_redis_ttl_error(self, mock_cli):
        """AC1: Redis TTL failure returns ERROR status."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="ST-001/agent/2026-03-19T00:00:00Z"
            ),  # GET ok
            _make_completed_process(returncode=1, stderr="TTL error"),  # TTL fails
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.ERROR)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_ttl_negative_two_means_missing(self, mock_cli):
        """AC1: TTL=-2 means key expired between GET and TTL call."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="ST-001/agent/2026-03-19T00:00:00Z"
            ),  # GET ok
            _make_completed_process(stdout="-2"),  # TTL = key doesn't exist
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.MISSING)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_ttl_negative_one_means_no_expiry(self, mock_cli):
        """AC1: TTL=-1 means key exists but has no expiration; treat as VALID."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="ST-001/agent/2026-03-19T00:00:00Z"
            ),  # GET ok
            _make_completed_process(stdout="-1"),  # TTL = no expiry
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.VALID)
        self.assertIsNone(info.ttl_seconds)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_invalid_ttl_value(self, mock_cli):
        """AC1: Non-numeric TTL response returns ERROR status."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="ST-001/agent/2026-03-19T00:00:00Z"
            ),  # GET ok
            _make_completed_process(stdout="not-a-number"),  # TTL invalid
        ]

        info = self.enforcer.check_lease(
            f"{BRANCH_LEASE_PREFIX}feature/test",
            "ST-001/agent/",
        )

        self.assertEqual(info.status, LeaseStatus.ERROR)


# ---------------------------------------------------------------------------
# LeaseEnforcer — enforce tests
# ---------------------------------------------------------------------------


class TestLeaseEnforcerEnforce(unittest.TestCase):
    """Test LeaseEnforcer.enforce full enforcement check."""

    def setUp(self):
        self.enforcer = LeaseEnforcer(
            redis_host="localhost",
            redis_port=6380,
            redis_db=0,
            warning_threshold_seconds=300,
        )

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_all_leases_valid(self, mock_cli):
        """Enforce returns compliant report when all leases are valid."""
        # Branch lease: GET + TTL
        # Worktree lease: GET + TTL
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertTrue(report.is_compliant)
        self.assertFalse(report.has_warnings)
        self.assertEqual(len(report.violations), 0)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_expired_branch_lease(self, mock_cli):
        """Enforce reports violation when branch lease is expired."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="0"),  # expired
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertFalse(report.is_compliant)
        self.assertTrue(any("expired" in v.lower() for v in report.violations))

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_missing_worktree_lease(self, mock_cli):
        """Enforce reports violation when worktree lease is missing."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
            _make_completed_process(stdout=""),  # missing
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertFalse(report.is_compliant)
        self.assertTrue(any("missing" in v.lower() for v in report.violations))

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_branch_lease_conflict(self, mock_cli):
        """Enforce reports violation when branch lease has wrong owner."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="OTHER-STORY/other-agent/2026-03-19T00:00:00Z"
            ),  # conflict
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertFalse(report.is_compliant)
        self.assertTrue(any("conflict" in v.lower() for v in report.violations))

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_low_ttl_warning(self, mock_cli):
        """Enforce reports warning when lease TTL is below threshold."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="120"),  # below 300s threshold
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertTrue(report.is_compliant)  # warning, not violation
        self.assertTrue(report.has_warnings)
        self.assertTrue(any("low" in w.lower() for w in report.warnings))

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_no_warning_when_ttl_above_threshold(self, mock_cli):
        """Enforce does not warn when lease TTL is above threshold."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="600"),  # above 300s threshold
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="600"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertTrue(report.is_compliant)
        self.assertFalse(report.has_warnings)

    def test_skip_branch_lease_check(self):
        """Enforce skips branch lease when require_branch_lease=False."""
        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
            require_branch_lease=False,
            require_worktree_lease=False,
        )

        self.assertTrue(report.is_compliant)
        self.assertIsNone(report.branch_lease)
        self.assertIsNone(report.worktree_lease)

    def test_enforcer_with_custom_warning_threshold(self):
        """Enforcer uses custom warning threshold."""
        enforcer = LeaseEnforcer(
            redis_host="localhost",
            redis_port=6380,
            redis_db=0,
            warning_threshold_seconds=60,
        )
        self.assertEqual(enforcer._warning_threshold_seconds, 60)


# ---------------------------------------------------------------------------
# LeaseEnforcer — renew_lease tests (AC2: renewal validation)
# ---------------------------------------------------------------------------


class TestLeaseEnforcerRenewLease(unittest.TestCase):
    """Test LeaseEnforcer.renew_lease for renewal validation."""

    def setUp(self):
        self.enforcer = LeaseEnforcer(
            redis_host="localhost",
            redis_port=6380,
            redis_db=0,
        )
        self.lease_key = f"{BRANCH_LEASE_PREFIX}feature/test"
        self.expected_prefix = "ST-001/agent/"

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_successful_renewal(self, mock_cli):
        """AC2: Successful renewal extends TTL."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout='1) "100"\n2) "0"'
            ),  # EVAL returns [previous_ttl, status_code]
        ]

        result = self.enforcer.renew_lease(
            self.lease_key,
            self.expected_prefix,
            new_ttl_seconds=432000,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.new_ttl_seconds, 432000)
        self.assertEqual(result.previous_ttl_seconds, 100)
        self.assertIsNone(result.error)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renewal_missing_lease(self, mock_cli):
        """AC2: Renewal fails when lease does not exist."""
        mock_cli.side_effect = [
            _make_completed_process(stdout=""),  # GET returns empty
        ]

        result = self.enforcer.renew_lease(
            self.lease_key,
            self.expected_prefix,
            new_ttl_seconds=432000,
        )

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("invalid lua script", result.error.lower())

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renewal_ownership_conflict(self, mock_cli):
        """AC2: Renewal fails when lease is owned by another agent."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="OTHER-STORY/other-agent/2026-03-19T00:00:00Z"
            ),  # GET
        ]

        result = self.enforcer.renew_lease(
            self.lease_key,
            self.expected_prefix,
            new_ttl_seconds=432000,
        )

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("invalid lua script", result.error.lower())

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renewal_redis_get_error(self, mock_cli):
        """AC2: Renewal fails when Redis GET errors."""
        mock_cli.side_effect = [
            _make_completed_process(
                returncode=1, stderr="Connection refused"
            ),  # GET fails
        ]

        result = self.enforcer.renew_lease(
            self.lease_key,
            self.expected_prefix,
            new_ttl_seconds=432000,
        )

        self.assertFalse(result.success)
        self.assertIn("redis", result.error.lower())

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renewal_redis_ttl_error(self, mock_cli):
        """AC2: Renewal fails when Redis TTL command errors."""
        mock_cli.side_effect = [
            _make_completed_process(
                stdout="ST-001/agent/2026-03-19T00:00:00Z"
            ),  # GET ok
            _make_completed_process(returncode=1, stderr="TTL error"),  # TTL fails
        ]

        result = self.enforcer.renew_lease(
            self.lease_key,
            self.expected_prefix,
            new_ttl_seconds=432000,
        )

        self.assertFalse(result.success)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renewal_expire_failure(self, mock_cli):
        """AC2: Renewal fails when EXPIRE command returns non-1."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),  # GET
            _make_completed_process(stdout="100"),  # TTL
            _make_completed_process(
                stdout="0"
            ),  # EXPIRE returns 0 (key expired between reads)
        ]

        result = self.enforcer.renew_lease(
            self.lease_key,
            self.expected_prefix,
            new_ttl_seconds=432000,
        )

        self.assertFalse(result.success)
        self.assertIn("invalid lua script", result.error.lower())

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renewal_with_invalid_ttl_value(self, mock_cli):
        """AC2: Renewal fails when TTL response is not numeric."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),  # GET
            _make_completed_process(stdout="not-a-number"),  # TTL invalid
        ]

        result = self.enforcer.renew_lease(
            self.lease_key,
            self.expected_prefix,
            new_ttl_seconds=432000,
        )

        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# LeaseEnforcer — renew_session_leases tests
# ---------------------------------------------------------------------------


class TestLeaseEnforcerRenewSessionLeases(unittest.TestCase):
    """Test LeaseEnforcer.renew_session_leases for full session renewal."""

    def setUp(self):
        self.enforcer = LeaseEnforcer(
            redis_host="localhost",
            redis_port=6380,
            redis_db=0,
        )

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renew_both_leases(self, mock_cli):
        """AC2: Session renewal renews both branch and worktree leases."""
        # Each renew_lease call makes one EVAL call returning [previous_ttl, status_code]
        mock_cli.side_effect = [
            _make_completed_process(stdout='1) "100"\n2) "0"'),  # branch success
            _make_completed_process(stdout='1) "100"\n2) "0"'),  # worktree success
        ]

        results = self.enforcer.renew_session_leases(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
            new_ttl_seconds=432000,
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].success)  # branch
        self.assertTrue(results[1].success)  # worktree
        self.assertEqual(results[0].new_ttl_seconds, 432000)
        self.assertEqual(results[1].new_ttl_seconds, 432000)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renew_session_partial_failure(self, mock_cli):
        """AC2: Session renewal reports individual failures."""
        # Branch: success
        # Worktree: ownership conflict
        mock_cli.side_effect = [
            _make_completed_process(stdout='1) "100"\n2) "0"'),  # branch success
            # Worktree lease has different owner - returns conflict status
            _make_completed_process(stdout='1) "-2"\n2) "2"'),
            _make_completed_process(
                stdout="OTHER-STORY/other-agent/2026-03-19T00:00:00Z"
            ),  # GET for error msg
        ]

        results = self.enforcer.renew_session_leases(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
            new_ttl_seconds=432000,
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].success)
        self.assertFalse(results[1].success)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_renew_session_custom_ttl(self, mock_cli):
        """AC2: Session renewal uses custom TTL value."""
        mock_cli.side_effect = [
            _make_completed_process(stdout='1) "100"\n2) "0"'),  # branch success
            _make_completed_process(stdout='1) "100"\n2) "0"'),  # worktree success
        ]

        results = self.enforcer.renew_session_leases(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
            new_ttl_seconds=86400,
        )

        for r in results:
            self.assertTrue(r.success)
            self.assertEqual(r.new_ttl_seconds, 86400)


# ---------------------------------------------------------------------------
# LeaseEnforcer — Redis unavailability tests
# ---------------------------------------------------------------------------


class TestLeaseEnforcerRedisUnavailable(unittest.TestCase):
    """Test behavior when Redis is unavailable."""

    @patch("scripts.swarm.lease_enforcement._redis_ping")
    def test_check_lease_raises_when_redis_unavailable(self, mock_ping):
        """check_lease raises LeaseEnforcementError when Redis is unavailable."""
        mock_ping.return_value = (False, None)

        enforcer = LeaseEnforcer()  # No explicit host — uses _redis_ping

        with self.assertRaises(LeaseEnforcementError) as ctx:
            enforcer.check_lease("some-key", "prefix/")

        self.assertIn("Redis unavailable", str(ctx.exception))

    @patch("scripts.swarm.lease_enforcement._redis_ping")
    def test_enforce_raises_when_redis_unavailable(self, mock_ping):
        """enforce raises LeaseEnforcementError when Redis is unavailable."""
        mock_ping.return_value = (False, None)

        enforcer = LeaseEnforcer()

        with self.assertRaises(LeaseEnforcementError):
            enforcer.enforce(
                story_id="ST-001",
                agent="agent",
                branch="feature/test",
                worktree_path="/tmp/worktrees/test",
            )

    @patch("scripts.swarm.lease_enforcement._redis_ping")
    def test_renew_lease_raises_when_redis_unavailable(self, mock_ping):
        """renew_lease raises LeaseEnforcementError when Redis is unavailable."""
        mock_ping.return_value = (False, None)

        enforcer = LeaseEnforcer()

        with self.assertRaises(LeaseEnforcementError):
            enforcer.renew_lease("some-key", "prefix/", 300)


# ---------------------------------------------------------------------------
# Integration-style: _path_slug consistency
# ---------------------------------------------------------------------------


class TestPathSlugConsistency(unittest.TestCase):
    """Verify path slug generation matches session.py patterns."""

    def test_path_slug_normalization(self):
        from scripts.swarm.lease_enforcement import _path_slug

        self.assertEqual(_path_slug("/tmp/worktrees/test"), "tmp:worktrees:test")
        self.assertEqual(_path_slug("scripts/swarm"), "scripts:swarm")
        self.assertEqual(_path_slug("./foo/bar/"), "foo:bar")

    def test_worktree_lease_key_format(self):
        from scripts.swarm.lease_enforcement import _path_slug

        wt_path = "/tmp/worktrees/SWARM-HARDEN-001-8.2"
        expected_key = f"{WORKTREE_LEASE_PREFIX}{_path_slug(wt_path)}"
        self.assertEqual(
            expected_key,
            "bmad:chiseai:worktree-lease:tmp:worktrees:swarm-harden-001-8.2",
        )


# ---------------------------------------------------------------------------
# LeaseEnforcer — TTL boundary edge cases
# ---------------------------------------------------------------------------


class TestLeaseEnforcerTTLBoundaries(unittest.TestCase):
    """Test TTL boundary conditions for lease enforcement."""

    def setUp(self):
        self.enforcer = LeaseEnforcer(
            redis_host="localhost",
            redis_port=6380,
            redis_db=0,
            warning_threshold_seconds=300,
        )

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_ttl_exactly_at_warning_threshold(self, mock_cli):
        """TTL exactly at warning threshold produces a warning."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="300"),  # exactly at threshold
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertTrue(report.is_compliant)
        self.assertTrue(report.has_warnings)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_ttl_just_above_warning_threshold(self, mock_cli):
        """TTL one second above warning threshold produces no warning."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="301"),  # one above threshold
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertTrue(report.is_compliant)
        self.assertFalse(report.has_warnings)

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_very_large_ttl(self, mock_cli):
        """Very large TTL values are handled correctly."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="999999999"),
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="999999999"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        self.assertTrue(report.is_compliant)
        self.assertFalse(report.has_warnings)
        self.assertEqual(report.branch_lease.ttl_seconds, 999999999)


# ---------------------------------------------------------------------------
# LeaseEnforcer — error status does not produce warning
# ---------------------------------------------------------------------------


class TestLeaseEnforcerErrorNoWarning(unittest.TestCase):
    """Ensure ERROR status leases don't produce spurious warnings."""

    def setUp(self):
        self.enforcer = LeaseEnforcer(
            redis_host="localhost",
            redis_port=6380,
            redis_db=0,
            warning_threshold_seconds=300,
        )

    @patch("scripts.swarm.lease_enforcement._redis_cli")
    def test_error_status_no_low_ttl_warning(self, mock_cli):
        """Lease in ERROR state should not produce low-TTL warnings."""
        mock_cli.side_effect = [
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(returncode=1, stderr="error"),  # TTL fails
            _make_completed_process(stdout="ST-001/agent/2026-03-19T00:00:00Z"),
            _make_completed_process(stdout="3000"),
        ]

        report = self.enforcer.enforce(
            story_id="ST-001",
            agent="agent",
            branch="feature/test",
            worktree_path="/tmp/worktrees/test",
        )

        # Branch lease should have ERROR status and produce a violation
        # but NOT a low-TTL warning
        branch_warnings = [w for w in report.warnings if "branch" in w.lower()]
        self.assertEqual(len(branch_warnings), 0)
        self.assertTrue(any("error" in v.lower() for v in report.violations))


if __name__ == "__main__":
    unittest.main()
