#!/usr/bin/env python3
"""
Override audit logging for ChiseAI.

Records when override environment variables are activated, providing an
audit trail for authority bypasses.  Logs to Redis with a 30-day TTL and
falls back to stderr when Redis is unavailable.

Redis key pattern: bmad:chiseai:audit:override:<date>
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# ── helpers ──────────────────────────────────────────────────────────

_TOK_RE = re.compile(r"(token|key|secret|pat|password|credential)", re.IGNORECASE)


def _mask_value(var_name: str, value: str) -> str:
    """Mask a value that looks token/credential-like."""
    if _TOK_RE.search(var_name):
        return "***REDACTED***"
    return value


def _caller_context() -> str:
    """Return a short caller summary (function name + file)."""
    import traceback

    # Walk up past this module and log_override's callers
    frames = traceback.extract_stack()
    # frames[-1] is *this* helper, [-2] is log_override, [-3] is the real caller
    if len(frames) >= 3:
        f = frames[-3]
        return f"{f.name} in {os.path.basename(f.filename)}:{f.lineno}"
    return "unknown"


# ── public API ───────────────────────────────────────────────────────


def log_override(
    var_name: str,
    value: str,
    *,
    reason: str = "",
    script_name: str = "",
) -> None:
    """Log an override activation event.

    Parameters
    ----------
    var_name:
        The environment variable name (e.g. ``CHISE_ALLOW_NON_MERLIN_PR``).
    value:
        The raw value of the variable.
    reason:
        Optional human-readable reason for the override.
    script_name:
        Override for the calling script name (auto-detected when empty).
    """
    now = datetime.now(datetime.UTC).isoformat()
    caller = _caller_context()
    if not script_name:
        script_name = os.path.basename(sys.argv[0]) if sys.argv else "unknown"

    entry = {
        "timestamp": now,
        "script": script_name,
        "var": var_name,
        "value": _mask_value(var_name, value),
        "caller": caller,
        "reason": reason or "not provided",
    }

    logged = False

    # Try Redis
    if REDIS_AVAILABLE:
        try:
            r = redis.Redis(host="host.docker.internal", port=6380, db=0)
            date_key = now[:10]  # YYYY-MM-DD
            redis_key = f"bmad:chiseai:audit:override:{date_key}"
            r.rpush(redis_key, json.dumps(entry))
            r.expire(redis_key, 30 * 86400)  # 30 days TTL
            logged = True
        except Exception:
            pass  # fall through to stderr

    # Fallback: stderr with [AUDIT] prefix
    if not logged:
        print(f"[AUDIT] {json.dumps(entry)}", file=sys.stderr)


def log_override_if_active(
    var_name: str,
    *,
    reason: str = "",
    script_name: str = "",
) -> None:
    """Convenience wrapper: log only when the env var is set to a truthy value."""
    raw = os.environ.get(var_name, "").strip()
    if raw:
        log_override(var_name, raw, reason=reason, script_name=script_name)
