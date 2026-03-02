#!/usr/bin/env python3
"""
Signal Flow Verification Script

Checks Redis for signals and PostgreSQL for outcomes, verifying the
signal-to-outcome matching pipeline integrity.

Usage:
    python3 scripts/validation/verify_signal_flow.py

Exit codes:
    0 - Flow is healthy
    1 - Flow issues detected
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class SignalFlowReport:
    """Report for signal flow verification."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    overall_status: str = "unknown"
    redis_signals: dict[str, Any] = field(default_factory=dict)
    postgresql_outcomes: dict[str, Any] = field(default_factory=dict)
    flow_integrity: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add_check(
        self, name: str, status: str, details: dict[str, Any] | None = None
    ) -> None:
        """Add a check result."""
        check = {
            "name": name,
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": details or {},
        }
        self.checks.append(check)
        icon = "✓" if status == "pass" else "✗" if status == "fail" else "⚠"
        logger.info(f"{icon} {name}: {status}")


def get_redis_config() -> dict[str, Any]:
    """Get Redis configuration.

    Note: In container context, we use host.docker.internal to connect
    to the host's Redis server. The REDIS_HOST env var may be set to
    a different value (e.g., 'redis-server') for other contexts.
    """
    # Force host.docker.internal for container context validation
    # Override any env vars that might point elsewhere
    return {
        "host": "host.docker.internal",
        "port": 6380,
        "db": int(os.getenv("REDIS_DB", "0")),
    }


def get_postgres_config() -> dict[str, Any]:
    """Get PostgreSQL configuration."""
    return {
        "host": os.getenv("POSTGRES_HOST", "host.docker.internal"),
        "port": int(os.getenv("POSTGRES_PORT", "5434")),
        "database": os.getenv("POSTGRES_DB", "chiseai"),
        "user": os.getenv("POSTGRES_USER", "chiseai"),
        "password": os.getenv("POSTGRES_PASSWORD", "change-me"),
    }


def check_redis_signals() -> tuple[bool, dict[str, Any]]:
    """Check Redis for signals.

    Returns:
        Tuple of (success, details)
    """
    config = get_redis_config()
    details: dict[str, Any] = {
        "host": config["host"],
        "port": config["port"],
        "signal_patterns_checked": [],
        "signals_found": {},
        "errors": [],
    }

    try:
        import redis

        r = redis.Redis(
            host=config["host"],
            port=config["port"],
            db=config["db"],
            socket_connect_timeout=5,
            decode_responses=True,
        )

        # Test connection
        if not r.ping():
            details["errors"].append("Redis ping failed")
            return False, details

        details["connection"] = "established"

        # Check for signal patterns
        patterns = [
            "bmad:chiseai:signals:*",
            "bmad:chiseai:signal:*",
            "signals:*",
            "signal:*",
        ]

        total_signals = 0
        for pattern in patterns:
            try:
                keys = list(r.scan_iter(match=pattern, count=100))
                details["signal_patterns_checked"].append(
                    {
                        "pattern": pattern,
                        "keys_found": len(keys),
                    }
                )

                if keys:
                    pattern_signals = []
                    for key in keys[:10]:  # Sample first 10
                        key_type = r.type(key)
                        key_info = {
                            "key": key,
                            "type": key_type,
                        }

                        if key_type == "string":
                            try:
                                value = r.get(key)
                                key_info["value_sample"] = (
                                    str(value)[:100] if value else None
                                )
                            except Exception as e:
                                key_info["error"] = str(e)
                        elif key_type == "hash":
                            try:
                                hash_data = cast(dict[Any, Any], r.hgetall(key))
                                key_info["fields"] = list(hash_data.keys())
                                key_info["sample"] = {
                                    k: str(v)[:50]
                                    for k, v in list(hash_data.items())[:3]
                                }
                            except Exception as e:
                                key_info["error"] = str(e)
                        elif key_type == "list":
                            try:
                                length = cast(int, r.llen(key))
                                key_info["length"] = length
                                if length > 0:
                                    samples = cast(list[Any], r.lrange(key, 0, 2))
                                    key_info["samples"] = [
                                        str(s)[:100] for s in samples
                                    ]
                            except Exception as e:
                                key_info["error"] = str(e)

                        pattern_signals.append(key_info)

                    details["signals_found"][pattern] = pattern_signals
                    total_signals += len(keys)

            except Exception as e:
                details["errors"].append(f"Pattern {pattern}: {e}")

        details["total_signals_found"] = total_signals

        # Check for recent signal activity (last 24 hours)
        # Look for keys with timestamps in their names
        recent_patterns = [
            f"bmad:chiseai:signals:{datetime.now(UTC).strftime('%Y-%m-%d')}:*",
        ]

        recent_signals = 0
        for pattern in recent_patterns:
            try:
                keys = list(r.scan_iter(match=pattern, count=100))
                recent_signals += len(keys)
            except Exception:
                pass

        details["recent_signals_24h"] = recent_signals

        r.close()
        return True, details

    except ImportError as e:
        details["errors"].append(f"redis not installed: {e}")
        return False, details
    except Exception as e:
        details["errors"].append(str(e))
        return False, details


def check_postgresql_outcomes() -> tuple[bool, dict[str, Any]]:
    """Check PostgreSQL for outcomes.

    Returns:
        Tuple of (success, details)
    """
    config = get_postgres_config()
    details: dict[str, Any] = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "outcomes": {},
        "errors": [],
    }

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
            connect_timeout=10,
        )

        with conn.cursor() as cur:
            # Check if signal_outcomes table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'signal_outcomes'
                );
            """)
            table_exists = cur.fetchone()[0]
            details["table_exists"] = table_exists

            if not table_exists:
                details["errors"].append("signal_outcomes table does not exist")
                conn.close()
                return False, details

            # Count total outcomes
            cur.execute("SELECT COUNT(*) FROM signal_outcomes;")
            total_count = cur.fetchone()[0]
            details["outcomes"]["total_count"] = total_count

            # Count outcomes by type
            cur.execute("""
                SELECT outcome, COUNT(*)
                FROM signal_outcomes
                GROUP BY outcome;
            """)
            by_outcome = cur.fetchall()
            details["outcomes"]["by_type"] = {row[0]: row[1] for row in by_outcome}

            # Count recent outcomes (last 24 hours)
            cur.execute("""
                SELECT COUNT(*)
                FROM signal_outcomes
                WHERE created_at > NOW() - INTERVAL '24 hours';
            """)
            recent_count = cur.fetchone()[0]
            details["outcomes"]["recent_24h"] = recent_count

            # Get sample of recent outcomes
            cur.execute("""
                SELECT id, signal_id, outcome, pnl, created_at
                FROM signal_outcomes
                ORDER BY created_at DESC
                LIMIT 5;
            """)
            recent_samples = cur.fetchall()
            details["outcomes"]["recent_samples"] = [
                {
                    "id": row[0],
                    "signal_id": row[1],
                    "outcome": row[2],
                    "pnl": float(row[3]) if row[3] else None,
                    "created_at": row[4].isoformat() if row[4] else None,
                }
                for row in recent_samples
            ]

            # Check for outcomes without matching signals (orphaned)
            # This is a simplified check - assumes signals might be in Redis
            cur.execute("""
                SELECT signal_id, COUNT(*)
                FROM signal_outcomes
                GROUP BY signal_id
                HAVING COUNT(*) > 1;
            """)
            duplicates = cur.fetchall()
            details["outcomes"]["duplicate_signal_ids"] = [
                {"signal_id": row[0], "count": row[1]} for row in duplicates
            ]

        conn.close()
        return True, details

    except ImportError as e:
        details["errors"].append(f"psycopg2 not installed: {e}")
        return False, details
    except Exception as e:
        details["errors"].append(str(e))
        return False, details


def verify_flow_integrity(
    redis_details: dict[str, Any], pg_details: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    """Verify signal-to-outcome flow integrity.

    Args:
        redis_details: Details from Redis check
        pg_details: Details from PostgreSQL check

    Returns:
        Tuple of (success, details)
    """
    details: dict[str, Any] = {
        "checks_performed": [],
        "warnings": [],
        "errors": [],
        "recommendations": [],
    }

    # Check 1: Are there signals in Redis?
    redis_signals = redis_details.get("total_signals_found", 0)
    if redis_signals == 0:
        details["warnings"].append("No signals found in Redis")
        details["recommendations"].append(
            "Verify signal generation is working or check different key patterns"
        )
    else:
        details["checks_performed"].append(f"Found {redis_signals} signals in Redis")

    # Check 2: Are there outcomes in PostgreSQL?
    pg_outcomes = pg_details.get("outcomes", {}).get("total_count", 0)
    if pg_outcomes == 0:
        details["warnings"].append("No outcomes found in PostgreSQL")
        details["recommendations"].append(
            "Verify outcome capture service is running and recording data"
        )
    else:
        details["checks_performed"].append(
            f"Found {pg_outcomes} outcomes in PostgreSQL"
        )

    # Check 3: Recent activity comparison
    redis_recent = redis_details.get("recent_signals_24h", 0)
    pg_recent = pg_details.get("outcomes", {}).get("recent_24h", 0)

    if redis_recent > 0 and pg_recent == 0:
        details["errors"].append(
            f"Signals found in Redis ({redis_recent} recent) but no recent outcomes in PostgreSQL"
        )
        details["recommendations"].append(
            "CRITICAL: Signal-to-outcome pipeline may be broken - check outcome capture service"
        )
    elif redis_recent == 0 and pg_recent > 0:
        details["checks_performed"].append(
            f"Outcomes recorded ({pg_recent} recent) but no recent signals in Redis (may be expected if signals are transient)"
        )
    elif redis_recent > 0 and pg_recent > 0:
        details["checks_performed"].append(
            f"Active flow: {redis_recent} recent signals, {pg_recent} recent outcomes"
        )

    # Check 4: Outcome type distribution
    by_type = pg_details.get("outcomes", {}).get("by_type", {})
    if by_type:
        details["checks_performed"].append(
            f"Outcome types: {', '.join(f'{k}={v}' for k, v in by_type.items())}"
        )

    # Check 5: Duplicate signal IDs
    duplicates = pg_details.get("outcomes", {}).get("duplicate_signal_ids", [])
    if duplicates:
        details["warnings"].append(
            f"Found {len(duplicates)} signal_ids with multiple outcomes"
        )
        details["recommendations"].append(
            "Review duplicate handling logic - may indicate reprocessing or data quality issues"
        )

    # Overall assessment
    if details["errors"]:
        details["integrity_status"] = "broken"
    elif details["warnings"]:
        details["integrity_status"] = "degraded"
    else:
        details["integrity_status"] = "healthy"

    return details["integrity_status"] == "healthy", details


def generate_report(report: SignalFlowReport) -> dict[str, Any]:
    """Generate JSON report from report object."""
    return {
        "timestamp": report.timestamp,
        "execution_id": report.execution_id,
        "overall_status": report.overall_status,
        "checks": report.checks,
        "redis_signals": report.redis_signals,
        "postgresql_outcomes": report.postgresql_outcomes,
        "flow_integrity": report.flow_integrity,
    }


def save_report(report: dict[str, Any]) -> Path:
    """Save report to file."""
    output_dir = Path("_bmad-output")
    output_dir.mkdir(exist_ok=True)

    report_file = output_dir / f"signal-flow-report-{report['execution_id']}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"\nReport saved to: {report_file}")
    return report_file


def main() -> int:
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("SIGNAL FLOW VERIFICATION")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now(UTC).isoformat()}")
    logger.info("Redis Host: host.docker.internal (container context)")
    logger.info("PostgreSQL Host: host.docker.internal (container context)")
    logger.info("")

    report = SignalFlowReport()
    all_passed = True

    # Test 1: Check Redis for signals
    logger.info("[Test 1/3] Checking Redis for signals...")
    success, details = check_redis_signals()
    report.redis_signals = details
    report.add_check("redis_signals", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        if details.get("errors"):
            for error in details["errors"]:
                logger.error(f"Redis error: {error}")

    # Test 2: Check PostgreSQL for outcomes
    logger.info("\n[Test 2/3] Checking PostgreSQL for outcomes...")
    success, details = check_postgresql_outcomes()
    report.postgresql_outcomes = details
    report.add_check("postgresql_outcomes", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        if details.get("errors"):
            for error in details["errors"]:
                logger.error(f"PostgreSQL error: {error}")

    # Test 3: Verify flow integrity
    logger.info("\n[Test 3/3] Verifying signal-to-outcome flow integrity...")
    success, details = verify_flow_integrity(
        report.redis_signals, report.postgresql_outcomes
    )
    report.flow_integrity = details
    report.add_check("flow_integrity", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        if details.get("errors"):
            for error in details["errors"]:
                logger.error(f"Flow integrity error: {error}")

    # Determine overall status
    report.overall_status = "healthy" if all_passed else "degraded"

    # Generate and save report
    report_dict = generate_report(report)
    report_file = save_report(report_dict)

    # Print summary
    print("\n" + "=" * 60)
    print("SIGNAL FLOW VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Execution ID: {report.execution_id}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Overall Status: {report.overall_status.upper()}")
    print("\nChecks Performed:")
    for check in report.checks:
        icon = "✓" if check["status"] == "pass" else "✗"
        print(f"  {icon} {check['name']}: {check['status']}")

    print("\nRedis Signals:")
    print(f"  Total Found: {report.redis_signals.get('total_signals_found', 'N/A')}")
    print(f"  Recent (24h): {report.redis_signals.get('recent_signals_24h', 'N/A')}")
    patterns = report.redis_signals.get("signal_patterns_checked", [])
    if patterns:
        print("  Patterns Checked:")
        for p in patterns:
            print(f"    - {p['pattern']}: {p['keys_found']} keys")

    print("\nPostgreSQL Outcomes:")
    outcomes = report.postgresql_outcomes.get("outcomes", {})
    print(f"  Total: {outcomes.get('total_count', 'N/A')}")
    print(f"  Recent (24h): {outcomes.get('recent_24h', 'N/A')}")
    by_type = outcomes.get("by_type", {})
    if by_type:
        print("  By Type:")
        for outcome_type, count in by_type.items():
            print(f"    - {outcome_type}: {count}")

    print("\nFlow Integrity:")
    print(f"  Status: {report.flow_integrity.get('integrity_status', 'unknown')}")
    checks = report.flow_integrity.get("checks_performed", [])
    for check in checks:
        print(f"  ✓ {check}")
    warnings = report.flow_integrity.get("warnings", [])
    for warning in warnings:
        print(f"  ⚠ {warning}")
    errors = report.flow_integrity.get("errors", [])
    for error in errors:
        print(f"  ✗ {error}")

    recommendations = report.flow_integrity.get("recommendations", [])
    if recommendations:
        print("\nRecommendations:")
        for rec in recommendations:
            print(f"  → {rec}")

    print(f"\nReport saved to: {report_file}")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
