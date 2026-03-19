#!/usr/bin/env python3
"""Lease enforcement for swarm session management.

Validates lease TTL expiration and renewal for branch and worktree leases
stored in Redis. Provides a deterministic enforcement contract that workers
can call before performing git operations.

Story: SWARM-HARDEN-001
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis key patterns matching session.py
BRANCH_LEASE_PREFIX = "bmad:chiseai:branch-lease:"
WORKTREE_LEASE_PREFIX = "bmad:chiseai:worktree-lease:"


class LeaseStatus(str, Enum):
    """Enumeration of possible lease states."""

    VALID = "valid"
    EXPIRED = "expired"
    MISSING = "missing"
    CONFLICT = "conflict"
    ERROR = "error"


class LeaseEnforcementError(RuntimeError):
    """Raised when lease enforcement detects a policy violation."""

    pass


class LeaseRenewalError(LeaseEnforcementError):
    """Raised when lease renewal fails."""

    pass


@dataclass
class LeaseInfo:
    """Snapshot of a lease's current state from Redis."""

    key: str
    value: str
    ttl_seconds: int | None
    status: LeaseStatus
    checked_at: str

    @property
    def is_valid(self) -> bool:
        return self.status == LeaseStatus.VALID

    @property
    def is_expired(self) -> bool:
        return self.status == LeaseStatus.EXPIRED

    @property
    def is_missing(self) -> bool:
        return self.status == LeaseStatus.MISSING


@dataclass
class LeaseRenewalResult:
    """Result of a lease renewal attempt."""

    key: str
    success: bool
    new_ttl_seconds: int | None
    previous_ttl_seconds: int | None
    renewed_at: str
    error: str | None = None

    @property
    def ttl_extended(self) -> bool:
        """True when renewal succeeded and TTL is longer than before."""
        if not self.success or self.previous_ttl_seconds is None:
            return False
        if self.new_ttl_seconds is None:
            return False
        return self.new_ttl_seconds > self.previous_ttl_seconds


@dataclass
class EnforcementReport:
    """Full enforcement check result for a session."""

    branch_lease: LeaseInfo | None
    worktree_lease: LeaseInfo | None
    story_id: str
    agent: str
    checked_at: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_compliant(self) -> bool:
        return len(self.violations) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _redis_candidates() -> list[tuple[str, int, int]]:
    host = (
        os.getenv("CHISE_REDIS_HOST")
        or os.getenv("REDIS_HOST")
        or "host.docker.internal"
    )
    port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
    db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")
    candidates = [(host, port, db)]
    if host != "localhost":
        candidates.append(("localhost", port, db))
    return candidates


def _redis_cli(
    host: str, port: int, db: int, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B607
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _redis_ping() -> tuple[bool, tuple[str, int, int] | None]:
    for host, port, db in _redis_candidates():
        proc = _redis_cli(host, port, db, "PING")
        if proc.returncode == 0 and proc.stdout.strip() == "PONG":
            return True, (host, port, db)
    return False, None


def _path_slug(path: str) -> str:
    p = path.strip().lstrip("./").strip("/")
    return p.lower().replace("/", ":")


class LeaseEnforcer:
    """Validates and enforces Redis-based swarm session leases.

    Usage::

        enforcer = LeaseEnforcer()
        report = enforcer.enforce(
            story_id="SWARM-HARDEN-001",
            agent="quickdev",
            branch="feature/SWARM-HARDEN-001-8.2",
            worktree_path="/tmp/worktrees/SWARM-HARDEN-001-8.2",
        )
        if not report.is_compliant:
            raise LeaseEnforcementError("; ".join(report.violations))
    """

    def __init__(
        self,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int | None = None,
        warning_threshold_seconds: int = 300,
    ) -> None:
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._redis_db = redis_db
        self._warning_threshold_seconds = warning_threshold_seconds

    def _get_redis_config(self) -> tuple[str, int, int]:
        if self._redis_host is not None:
            port = self._redis_port or 6380
            db = self._redis_db or 0
            return self._redis_host, port, db

        ok, cfg = _redis_ping()
        if not ok or cfg is None:
            raise LeaseEnforcementError("Redis unavailable for lease enforcement")
        return cfg

    def check_lease(self, lease_key: str, expected_prefix: str) -> LeaseInfo:
        """Check the current state of a single lease key.

        Args:
            lease_key: Full Redis key for the lease.
            expected_prefix: Expected prefix of the lease value (e.g. ``story_id/agent/``).

        Returns:
            LeaseInfo with the current TTL and status.
        """
        host, port, db = self._get_redis_config()
        now = _utc_now()

        # GET the lease value
        get_proc = _redis_cli(host, port, db, "GET", lease_key)
        if get_proc.returncode != 0:
            logger.error("Redis GET failed for %s: %s", lease_key, get_proc.stderr)
            return LeaseInfo(
                key=lease_key,
                value="",
                ttl_seconds=None,
                status=LeaseStatus.ERROR,
                checked_at=now,
            )

        lease_val = get_proc.stdout.strip()
        if not lease_val:
            return LeaseInfo(
                key=lease_key,
                value="",
                ttl_seconds=None,
                status=LeaseStatus.MISSING,
                checked_at=now,
            )

        # Check ownership prefix
        if not lease_val.startswith(expected_prefix):
            return LeaseInfo(
                key=lease_key,
                value=lease_val,
                ttl_seconds=None,
                status=LeaseStatus.CONFLICT,
                checked_at=now,
            )

        # TTL check
        ttl_proc = _redis_cli(host, port, db, "TTL", lease_key)
        if ttl_proc.returncode != 0:
            logger.error("Redis TTL failed for %s: %s", lease_key, ttl_proc.stderr)
            return LeaseInfo(
                key=lease_key,
                value=lease_val,
                ttl_seconds=None,
                status=LeaseStatus.ERROR,
                checked_at=now,
            )

        try:
            ttl = int(ttl_proc.stdout.strip())
        except ValueError:
            logger.error("Invalid TTL value for %s: %s", lease_key, ttl_proc.stdout)
            return LeaseInfo(
                key=lease_key,
                value=lease_val,
                ttl_seconds=None,
                status=LeaseStatus.ERROR,
                checked_at=now,
            )

        # TTL == -2 means key does not exist (shouldn't happen after GET)
        # TTL == -1 means no expiration set
        if ttl == -2:
            return LeaseInfo(
                key=lease_key,
                value=lease_val,
                ttl_seconds=None,
                status=LeaseStatus.MISSING,
                checked_at=now,
            )
        if ttl == -1:
            # Key exists but has no TTL — treat as valid but warn
            return LeaseInfo(
                key=lease_key,
                value=lease_val,
                ttl_seconds=None,
                status=LeaseStatus.VALID,
                checked_at=now,
            )
        if ttl <= 0:
            return LeaseInfo(
                key=lease_key,
                value=lease_val,
                ttl_seconds=ttl,
                status=LeaseStatus.EXPIRED,
                checked_at=now,
            )

        return LeaseInfo(
            key=lease_key,
            value=lease_val,
            ttl_seconds=ttl,
            status=LeaseStatus.VALID,
            checked_at=now,
        )

    def enforce(
        self,
        story_id: str,
        agent: str,
        branch: str,
        worktree_path: str,
        require_branch_lease: bool = True,
        require_worktree_lease: bool = True,
    ) -> EnforcementReport:
        """Run a full enforcement check against branch and worktree leases.

        Args:
            story_id: The story identifier.
            agent: The agent identifier.
            branch: The branch name.
            worktree_path: The worktree filesystem path.
            require_branch_lease: Whether to enforce branch lease presence.
            require_worktree_lease: Whether to enforce worktree lease presence.

        Returns:
            EnforcementReport with all violations and warnings.
        """
        now = _utc_now()
        expected_prefix = f"{story_id}/{agent}/"

        branch_lease_info: LeaseInfo | None = None
        worktree_lease_info: LeaseInfo | None = None
        violations: list[str] = []
        warnings: list[str] = []

        if require_branch_lease:
            branch_key = f"{BRANCH_LEASE_PREFIX}{branch}"
            branch_lease_info = self.check_lease(branch_key, expected_prefix)
            violations.extend(self._evaluate_lease(branch_lease_info, "branch"))
            warnings.extend(self._evaluate_lease_warnings(branch_lease_info, "branch"))

        if require_worktree_lease:
            wt_key = f"{WORKTREE_LEASE_PREFIX}{_path_slug(worktree_path)}"
            worktree_lease_info = self.check_lease(wt_key, expected_prefix)
            violations.extend(self._evaluate_lease(worktree_lease_info, "worktree"))
            warnings.extend(
                self._evaluate_lease_warnings(worktree_lease_info, "worktree")
            )

        return EnforcementReport(
            branch_lease=branch_lease_info,
            worktree_lease=worktree_lease_info,
            story_id=story_id,
            agent=agent,
            checked_at=now,
            violations=violations,
            warnings=warnings,
        )

    def _evaluate_lease(self, info: LeaseInfo | None, label: str) -> list[str]:
        """Evaluate a single lease and return violations."""
        if info is None:
            return []
        if info.status == LeaseStatus.MISSING:
            return [f"{label} lease is missing ({info.key})"]
        if info.status == LeaseStatus.EXPIRED:
            return [f"{label} lease has expired (TTL={info.ttl_seconds}s)"]
        if info.status == LeaseStatus.CONFLICT:
            return [
                f"{label} lease ownership conflict: expected prefix "
                f"{info.key} owned by {info.value!r}"
            ]
        if info.status == LeaseStatus.ERROR:
            return [f"{label} lease check failed with Redis error"]
        return []

    def _evaluate_lease_warnings(self, info: LeaseInfo | None, label: str) -> list[str]:
        """Evaluate a single lease for warnings (non-blocking issues)."""
        if info is None or not info.is_valid or info.ttl_seconds is None:
            return []
        if 0 < info.ttl_seconds <= self._warning_threshold_seconds:
            return [
                f"{label} lease TTL is low ({info.ttl_seconds}s remaining); "
                "consider renewing"
            ]
        return []

    def renew_lease(
        self,
        lease_key: str,
        expected_owner_prefix: str,
        new_ttl_seconds: int,
    ) -> LeaseRenewalResult:
        """Renew a lease by extending its TTL, with ownership validation.

        The renewal is atomic in the sense that it checks ownership before
        extending.  If the lease value has changed (ownership conflict), the
        renewal is rejected.

        Args:
            lease_key: Full Redis key for the lease.
            expected_owner_prefix: Expected prefix of the current lease value.
            new_ttl_seconds: New TTL to set on the lease.

        Returns:
            LeaseRenewalResult with success/failure details.

        Raises:
            LeaseRenewalError: If the renewal cannot proceed due to policy violation.
        """
        now = _utc_now()
        host, port, db = self._get_redis_config()

        # 1. Read current lease value
        get_proc = _redis_cli(host, port, db, "GET", lease_key)
        if get_proc.returncode != 0:
            return LeaseRenewalResult(
                key=lease_key,
                success=False,
                new_ttl_seconds=None,
                previous_ttl_seconds=None,
                renewed_at=now,
                error=f"Redis GET failed: {get_proc.stderr.strip()}",
            )

        current_val = get_proc.stdout.strip()
        if not current_val:
            return LeaseRenewalResult(
                key=lease_key,
                success=False,
                new_ttl_seconds=None,
                previous_ttl_seconds=None,
                renewed_at=now,
                error="Lease does not exist; cannot renew a missing lease",
            )

        # 2. Validate ownership
        if not current_val.startswith(expected_owner_prefix):
            return LeaseRenewalResult(
                key=lease_key,
                success=False,
                new_ttl_seconds=None,
                previous_ttl_seconds=None,
                renewed_at=now,
                error=(
                    f"Ownership conflict: lease value {current_val!r} "
                    f"does not match expected prefix {expected_owner_prefix!r}"
                ),
            )

        # 3. Read current TTL for reporting
        ttl_proc = _redis_cli(host, port, db, "TTL", lease_key)
        if ttl_proc.returncode != 0:
            return LeaseRenewalResult(
                key=lease_key,
                success=False,
                new_ttl_seconds=None,
                previous_ttl_seconds=None,
                renewed_at=now,
                error=f"Redis TTL failed: {ttl_proc.stderr.strip()}",
            )

        try:
            previous_ttl = int(ttl_proc.stdout.strip())
        except ValueError:
            return LeaseRenewalResult(
                key=lease_key,
                success=False,
                new_ttl_seconds=None,
                previous_ttl_seconds=None,
                renewed_at=now,
                error=f"Invalid TTL value: {ttl_proc.stdout.strip()!r}",
            )

        # 4. Extend TTL (EXPIRE command)
        expire_proc = _redis_cli(
            host, port, db, "EXPIRE", lease_key, str(new_ttl_seconds)
        )
        if expire_proc.returncode != 0 or expire_proc.stdout.strip() != "1":
            return LeaseRenewalResult(
                key=lease_key,
                success=False,
                new_ttl_seconds=None,
                previous_ttl_seconds=previous_ttl,
                renewed_at=now,
                error=(
                    f"EXPIRE failed: rc={expire_proc.returncode} "
                    f"stdout={expire_proc.stdout.strip()!r} "
                    f"stderr={expire_proc.stderr.strip()!r}"
                ),
            )

        return LeaseRenewalResult(
            key=lease_key,
            success=True,
            new_ttl_seconds=new_ttl_seconds,
            previous_ttl_seconds=previous_ttl,
            renewed_at=now,
        )

    def renew_session_leases(
        self,
        story_id: str,
        agent: str,
        branch: str,
        worktree_path: str,
        new_ttl_seconds: int = 432000,
    ) -> list[LeaseRenewalResult]:
        """Renew both branch and worktree leases for a session.

        Args:
            story_id: The story identifier.
            agent: The agent identifier.
            branch: The branch name.
            worktree_path: The worktree filesystem path.
            new_ttl_seconds: New TTL to set on both leases.

        Returns:
            List of LeaseRenewalResult, one per lease.
        """
        expected_prefix = f"{story_id}/{agent}/"

        branch_key = f"{BRANCH_LEASE_PREFIX}{branch}"
        wt_key = f"{WORKTREE_LEASE_PREFIX}{_path_slug(worktree_path)}"

        results = [
            self.renew_lease(branch_key, expected_prefix, new_ttl_seconds),
            self.renew_lease(wt_key, expected_prefix, new_ttl_seconds),
        ]
        return results
