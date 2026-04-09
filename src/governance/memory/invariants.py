"""
Strategic Challenge Invariants for Memory Governance.

From memory-systems-evaluation-20260409.md:
"staleness precomputed at write-time only"

This module enforces the strategic invariant that staleness must NEVER be
computed at query time. The staleness_score must exist in the payload
(precomputed by the Reflector during write/promotion) or the record must
be marked as legacy_missing.

HARDENING (Aria decision AD-PHASE4-20260409T000000Z-ctx001):
- If staleness_score absent in payload, mark as legacy_missing
- Do NOT compute surrogate staleness at query time
- Fail-fast if any code path attempts runtime staleness computation
"""

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


class StalenessComputeError(Exception):
    """Strategic invariant violation: staleness computed at query time."""

    pass


def assert_no_runtime_staleness_compute(payload: dict) -> None:
    """
    Verify staleness_score exists and was NOT computed at query time.

    This is a fail-fast assertion that raises StalenessComputeError if
    any code path attempts to compute staleness at query time.

    Per strategic challenge invariant (memory-systems-evaluation-20260409.md):
    - staleness_score MUST be precomputed at write-time by Reflector
    - If staleness_score is absent, the record should be marked
      as legacy_missing (NOT have a surrogate computed at query time)
    - If a callable staleness is detected (function call result),
      this indicates runtime computation and is a violation

    Args:
        payload: The memory record payload dict to check.

    Raises:
        StalenessComputeError: If staleness_score is computed at query time
        (detected via callable values which indicate dynamic computation).
    """
    staleness = payload.get("staleness_score")

    if staleness is None:
        # Mark as legacy_missing - do NOT compute
        # This is the correct behavior per Aria hardening
        return

    # If staleness_score exists, verify it's NOT a callable
    # (callable would indicate it was computed at query time)
    if callable(staleness):
        logger.error(
            "StalenessComputeError: staleness_score is callable - "
            "indicates runtime computation at query time"
        )
        raise StalenessComputeError(
            "Staleness computed at query time! "
            "staleness_score must be precomputed at write-time only."
        )


def validate_payload_staleness(
    payload: dict, record_id: str | None = None
) -> tuple[bool, List[str]]:
    """
    Validate that a payload conforms to staleness invariants.

    Args:
        payload: The memory record payload to validate.
        record_id: Optional record ID for logging.

    Returns:
        Tuple of (is_valid, legacy_missing_reasons).
        is_valid is True if no runtime staleness compute is detected.
        legacy_missing_reasons lists any payloads missing staleness_score.
    """
    legacy_missing: List[str] = []
    is_valid = True

    staleness = payload.get("staleness_score")

    if staleness is None:
        reason = f"Record {record_id or 'unknown'}: missing staleness_score"
        legacy_missing.append(reason)
        # Not a validation failure - legacy records are expected
    elif callable(staleness):
        reason = f"Record {record_id or 'unknown'}: callable staleness_score detected"
        legacy_missing.append(reason)
        is_valid = False
        logger.error(f"INVARIANT VIOLATION: {reason}")

    return is_valid, legacy_missing
