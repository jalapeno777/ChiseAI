#!/usr/bin/env python3
"""Live Venue Provenance Validation Script (ST-VENUE-001).

This script performs live validation of venue provenance fields in signal outcomes.
It verifies that:
1. Venue fields are present in outcomes
2. Bybit demo mode is correctly detected and recorded
3. Venue provenance information is complete
4. All provenance fields meet validation criteria

Usage:
    python3 scripts/validation/verify_venue_provenance_live.py

Exit codes:
    0 - All validations passed
    1 - One or more validations failed
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class VenueProvenanceReport:
    """Report for venue provenance validation."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    overall_status: str = "unknown"
    venue_field_checks: dict[str, Any] = field(default_factory=dict)
    bybit_demo_checks: dict[str, Any] = field(default_factory=dict)
    provenance_completeness: dict[str, Any] = field(default_factory=dict)
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


def get_postgres_config() -> dict[str, Any]:
    """Get PostgreSQL configuration."""
    return {
        "host": os.getenv("POSTGRES_HOST", "host.docker.internal"),
        "port": int(os.getenv("POSTGRES_PORT", "5434")),
        "database": os.getenv("POSTGRES_DB", "chiseai"),
        "user": os.getenv("POSTGRES_USER", "chiseai"),
        "password": os.getenv("POSTGRES_PASSWORD", "change-me"),
    }


def check_venue_fields_exist() -> tuple[bool, dict[str, Any]]:
    """Check if venue-related fields exist in signal_outcomes table.

    Returns:
        Tuple of (success, details)
    """
    config = get_postgres_config()
    details = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "fields_found": [],
        "fields_missing": [],
        "errors": [],
    }

    # Expected venue-related fields
    expected_fields = [
        "venue",  # Primary venue identifier (e.g., "bybit_demo")
        "executor_type",  # Type of executor used (e.g., "BybitDemoConnector")
        "provenance_endpoint",  # API endpoint used
        "provenance_timestamp",  # When provenance was recorded
        "is_demo",  # Boolean flag for demo mode
    ]

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

            # Get column information
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'signal_outcomes'
                ORDER BY ordinal_position;
            """)
            columns = {row[0]: row[1] for row in cur.fetchall()}
            details["all_columns"] = columns

            # Check for venue-related fields
            for field_name in expected_fields:
                if field_name in columns:
                    details["fields_found"].append(
                        {
                            "name": field_name,
                            "type": columns[field_name],
                        }
                    )
                else:
                    details["fields_missing"].append(field_name)

            # Also check for any columns containing 'venue' or 'provenance'
            venue_related = {
                k: v
                for k, v in columns.items()
                if "venue" in k.lower() or "provenance" in k.lower()
            }
            details["venue_related_columns"] = venue_related

        conn.close()

        # Success if we can query the table
        return True, details

    except ImportError as e:
        details["errors"].append(f"psycopg2 not installed: {e}")
        return False, details
    except Exception as e:
        details["errors"].append(str(e))
        return False, details


def check_bybit_demo_mode() -> tuple[bool, dict[str, Any]]:
    """Check that Bybit demo mode is correctly detected and configured.

    Returns:
        Tuple of (success, details)
    """
    details = {
        "checks_performed": [],
        "errors": [],
        "warnings": [],
    }

    try:
        # Add src to path for imports
        src_path = Path(__file__).parent.parent.parent / "src"
        sys.path.insert(0, str(src_path))

        # Check 1: BybitDemoConnector exists and is importable
        try:
            from execution.connectors.bybit_demo_connector import (
                BybitDemoConnector,
                BybitDemoConnectorFactory,
                DemoProvenance,
            )

            details["checks_performed"].append(
                "BybitDemoConnector module is importable"
            )
        except ImportError as e:
            details["errors"].append(f"BybitDemoConnector not importable: {e}")
            return False, details

        # Check 2: DemoProvenance structure is correct
        try:
            prov = DemoProvenance(
                is_demo=True,
                endpoint="https://api-demo.bybit.com",
                api_key_prefix="test",
                timestamp=datetime.now(UTC).isoformat(),
            )
            if prov.is_demo and "api-demo" in prov.endpoint:
                details["checks_performed"].append("DemoProvenance structure is valid")
            else:
                details["errors"].append("DemoProvenance validation failed")
        except Exception as e:
            details["errors"].append(f"DemoProvenance error: {e}")

        # Check 3: BybitDemoConnectorFactory can detect credentials
        try:
            has_creds = BybitDemoConnectorFactory.has_demo_credentials()
            details["demo_credentials_available"] = has_creds
            details["checks_performed"].append(f"Demo credentials check: {has_creds}")
        except Exception as e:
            details["warnings"].append(f"Could not check demo credentials: {e}")

        # Check 4: BybitConfig enforces demo mode
        try:
            from data.exchange.bybit_connector import BybitConfig
            from data.exchange.bybit_safety import SecurityException

            # Test demo mode configuration
            config = BybitConfig(
                api_key="test_key",
                api_secret="test_secret",
                demo=True,
            )

            if config.demo and "api-demo" in config.base_url:
                details["checks_performed"].append(
                    f"BybitConfig demo mode enforced (endpoint: {config.base_url})"
                )
            else:
                details["errors"].append(
                    f"BybitConfig demo mode not enforced (endpoint: {config.base_url})"
                )

            # Test production mode is blocked
            try:
                prod_config = BybitConfig(
                    api_key="test_key",
                    api_secret="test_secret",
                    demo=False,
                    testnet=False,
                )
                details["errors"].append(
                    "Production mode not blocked - SecurityException should have been raised"
                )
            except SecurityException:
                details["checks_performed"].append(
                    "Production mode correctly blocked by SecurityException"
                )

        except Exception as e:
            details["warnings"].append(f"Could not verify BybitConfig demo mode: {e}")

        # Check 5: Endpoint validation is in place
        try:
            from data.exchange.bybit_safety import (
                DEMO_PATTERNS,
                PRODUCTION_PATTERNS,
                validate_endpoint_url,
            )

            if DEMO_PATTERNS and PRODUCTION_PATTERNS:
                details["checks_performed"].append(
                    "Endpoint validation patterns are configured"
                )
            else:
                details["warnings"].append("Endpoint validation patterns missing")

            # Test validation
            try:
                validate_endpoint_url("https://api-demo.bybit.com")
                details["checks_performed"].append("Demo endpoint validation passed")
            except Exception as e:
                details["errors"].append(f"Demo endpoint validation failed: {e}")

        except Exception as e:
            details["warnings"].append(f"Could not verify endpoint validation: {e}")

        return len(details["errors"]) == 0, details

    except Exception as e:
        details["errors"].append(f"Unexpected error: {e}")
        return False, details


def check_provenance_completeness() -> tuple[bool, dict[str, Any]]:
    """Check that venue provenance information is complete.

    Returns:
        Tuple of (success, details)
    """
    config = get_postgres_config()
    details = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "completeness_checks": [],
        "errors": [],
        "warnings": [],
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
            if not cur.fetchone()[0]:
                details["errors"].append("signal_outcomes table does not exist")
                conn.close()
                return False, details

            # Count total outcomes
            cur.execute("SELECT COUNT(*) FROM signal_outcomes;")
            total_count = cur.fetchone()[0]
            details["total_outcomes"] = total_count

            if total_count == 0:
                details["warnings"].append(
                    "No outcomes found in database - cannot verify provenance completeness"
                )
                conn.close()
                return True, details  # Not a failure, just no data yet

            # Check for outcomes with venue information
            # First, check what columns exist
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'signal_outcomes';
            """)
            columns = [row[0] for row in cur.fetchall()]

            # Check for venue field presence
            if "venue" in columns:
                cur.execute("""
                    SELECT COUNT(*) FROM signal_outcomes
                    WHERE venue IS NOT NULL AND venue != '';
                """)
                with_venue = cur.fetchone()[0]
                details["completeness_checks"].append(
                    {
                        "check": "outcomes_with_venue",
                        "count": with_venue,
                        "total": total_count,
                        "percentage": round(with_venue / total_count * 100, 2)
                        if total_count > 0
                        else 0,
                    }
                )

            # Check for executor_type field
            if "executor_type" in columns:
                cur.execute("""
                    SELECT COUNT(*) FROM signal_outcomes
                    WHERE executor_type IS NOT NULL AND executor_type != '';
                """)
                with_executor = cur.fetchone()[0]
                details["completeness_checks"].append(
                    {
                        "check": "outcomes_with_executor_type",
                        "count": with_executor,
                        "total": total_count,
                        "percentage": round(with_executor / total_count * 100, 2)
                        if total_count > 0
                        else 0,
                    }
                )

                # Check distribution of executor types
                cur.execute("""
                    SELECT executor_type, COUNT(*)
                    FROM signal_outcomes
                    WHERE executor_type IS NOT NULL
                    GROUP BY executor_type;
                """)
                executor_distribution = {row[0]: row[1] for row in cur.fetchall()}
                details["executor_type_distribution"] = executor_distribution

            # Check for is_demo field
            if "is_demo" in columns:
                cur.execute("""
                    SELECT COUNT(*) FROM signal_outcomes
                    WHERE is_demo = TRUE;
                """)
                demo_count = cur.fetchone()[0]
                details["completeness_checks"].append(
                    {
                        "check": "outcomes_with_demo_flag",
                        "count": demo_count,
                        "total": total_count,
                        "percentage": round(demo_count / total_count * 100, 2)
                        if total_count > 0
                        else 0,
                    }
                )

            # Get sample of recent outcomes with provenance info
            cur.execute("""
                SELECT id, signal_id, created_at
                FROM signal_outcomes
                ORDER BY created_at DESC
                LIMIT 5;
            """)
            recent_samples = cur.fetchall()
            details["recent_outcome_samples"] = [
                {
                    "id": row[0],
                    "signal_id": str(row[1]),
                    "created_at": row[2].isoformat() if row[2] else None,
                }
                for row in recent_samples
            ]

        conn.close()
        return True, details

    except ImportError as e:
        details["errors"].append(f"psycopg2 not installed: {e}")
        return False, details
    except Exception as e:
        details["errors"].append(str(e))
        return False, details


def verify_venue_provenance_integrity(
    venue_details: dict[str, Any],
    bybit_details: dict[str, Any],
    completeness_details: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """Verify overall venue provenance integrity.

    Args:
        venue_details: Details from venue field check
        bybit_details: Details from Bybit demo check
        completeness_details: Details from completeness check

    Returns:
        Tuple of (success, details)
    """
    details = {
        "checks_performed": [],
        "warnings": [],
        "errors": [],
        "recommendations": [],
    }

    # Check 1: Venue fields exist or are documented
    fields_found = venue_details.get("fields_found", [])
    fields_missing = venue_details.get("fields_missing", [])

    if fields_found:
        details["checks_performed"].append(
            f"Found {len(fields_found)} venue-related field(s): "
            f"{', '.join(f['name'] for f in fields_found)}"
        )
    else:
        details["warnings"].append(
            "No dedicated venue fields found in signal_outcomes table. "
            "Venue information may be stored in metadata or note fields."
        )
        details["recommendations"].append(
            "Consider adding venue, executor_type, and is_demo columns "
            "to signal_outcomes table for explicit provenance tracking"
        )

    # Check 2: Bybit demo mode is properly configured
    demo_creds_available = bybit_details.get("demo_credentials_available", False)
    if demo_creds_available:
        details["checks_performed"].append("Bybit demo credentials are available")
    else:
        details["warnings"].append(
            "Bybit demo credentials not available in environment"
        )
        details["recommendations"].append(
            "Set BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET environment variables"
        )

    # Check 3: Provenance completeness
    total_outcomes = completeness_details.get("total_outcomes", 0)
    if total_outcomes > 0:
        details["checks_performed"].append(
            f"Found {total_outcomes} outcome(s) in database"
        )

        completeness_checks = completeness_details.get("completeness_checks", [])
        for check in completeness_checks:
            check_name = check.get("check", "unknown")
            count = check.get("count", 0)
            percentage = check.get("percentage", 0)

            if percentage >= 90:
                details["checks_performed"].append(
                    f"{check_name}: {count}/{total_outcomes} ({percentage}%)"
                )
            elif percentage >= 50:
                details["warnings"].append(
                    f"{check_name}: Only {percentage}% complete ({count}/{total_outcomes})"
                )
            else:
                details["errors"].append(
                    f"{check_name}: Low coverage ({percentage}%, {count}/{total_outcomes})"
                )
    else:
        details["warnings"].append(
            "No outcomes in database yet - completeness cannot be verified"
        )

    # Check 4: Executor type distribution
    executor_dist = completeness_details.get("executor_type_distribution", {})
    if executor_dist:
        bybit_demo_count = executor_dist.get("BybitDemoConnector", 0)
        if bybit_demo_count > 0:
            details["checks_performed"].append(
                f"Found {bybit_demo_count} outcome(s) from BybitDemoConnector"
            )
        else:
            details["warnings"].append("No outcomes from BybitDemoConnector found yet")

    # Overall assessment
    if details["errors"]:
        details["integrity_status"] = "broken"
    elif details["warnings"]:
        details["integrity_status"] = "degraded"
    else:
        details["integrity_status"] = "healthy"

    return details["integrity_status"] == "healthy", details


def generate_report(report: VenueProvenanceReport) -> dict[str, Any]:
    """Generate JSON report from report object."""
    return {
        "timestamp": report.timestamp,
        "execution_id": report.execution_id,
        "overall_status": report.overall_status,
        "checks": report.checks,
        "venue_field_checks": report.venue_field_checks,
        "bybit_demo_checks": report.bybit_demo_checks,
        "provenance_completeness": report.provenance_completeness,
    }


def save_report(report: dict[str, Any]) -> Path:
    """Save report to file."""
    output_dir = Path("_bmad-output")
    output_dir.mkdir(exist_ok=True)

    report_file = output_dir / f"venue-provenance-report-{report['execution_id']}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"\nReport saved to: {report_file}")
    return report_file


def main() -> int:
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("VENUE PROVENANCE LIVE VALIDATION")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now(UTC).isoformat()}")
    logger.info(f"PostgreSQL Host: host.docker.internal (container context)")
    logger.info("")

    report = VenueProvenanceReport()
    all_passed = True

    # Test 1: Check venue fields exist
    logger.info("[Test 1/4] Checking venue field presence in signal_outcomes...")
    success, details = check_venue_fields_exist()
    report.venue_field_checks = details
    report.add_check("venue_fields_exist", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        if details.get("errors"):
            for error in details["errors"]:
                logger.error(f"Venue field error: {error}")

    # Test 2: Check Bybit demo mode
    logger.info("\n[Test 2/4] Checking Bybit demo mode configuration...")
    success, details = check_bybit_demo_mode()
    report.bybit_demo_checks = details
    report.add_check("bybit_demo_mode", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        if details.get("errors"):
            for error in details["errors"]:
                logger.error(f"Bybit demo error: {error}")

    # Test 3: Check provenance completeness
    logger.info("\n[Test 3/4] Checking venue provenance completeness...")
    success, details = check_provenance_completeness()
    report.provenance_completeness = details
    report.add_check("provenance_completeness", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        if details.get("errors"):
            for error in details["errors"]:
                logger.error(f"Completeness error: {error}")

    # Test 4: Verify overall integrity
    logger.info("\n[Test 4/4] Verifying venue provenance integrity...")
    success, details = verify_venue_provenance_integrity(
        report.venue_field_checks,
        report.bybit_demo_checks,
        report.provenance_completeness,
    )
    report.add_check(
        "venue_provenance_integrity", "pass" if success else "fail", details
    )
    if not success:
        all_passed = False
        if details.get("errors"):
            for error in details["errors"]:
                logger.error(f"Integrity error: {error}")

    # Determine overall status
    report.overall_status = "healthy" if all_passed else "degraded"

    # Generate and save report
    report_dict = generate_report(report)
    report_file = save_report(report_dict)

    # Print summary
    print("\n" + "=" * 60)
    print("VENUE PROVENANCE VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Execution ID: {report.execution_id}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Overall Status: {report.overall_status.upper()}")
    print(f"\nChecks Performed:")
    for check in report.checks:
        icon = "✓" if check["status"] == "pass" else "✗"
        print(f"  {icon} {check['name']}: {check['status']}")

    print(f"\nVenue Fields:")
    fields_found = report.venue_field_checks.get("fields_found", [])
    if fields_found:
        print(f"  Found {len(fields_found)} venue-related field(s):")
        for field in fields_found:
            print(f"    - {field['name']} ({field['type']})")
    else:
        print("  No dedicated venue fields found")

    fields_missing = report.venue_field_checks.get("fields_missing", [])
    if fields_missing:
        print(f"  Missing fields: {', '.join(fields_missing)}")

    print(f"\nBybit Demo Mode:")
    demo_creds = report.bybit_demo_checks.get("demo_credentials_available", "unknown")
    print(f"  Demo credentials available: {demo_creds}")
    checks = report.bybit_demo_checks.get("checks_performed", [])
    for check in checks:
        print(f"  ✓ {check}")

    print(f"\nProvenance Completeness:")
    total = report.provenance_completeness.get("total_outcomes", 0)
    print(f"  Total outcomes: {total}")
    completeness = report.provenance_completeness.get("completeness_checks", [])
    for check in completeness:
        print(
            f"  - {check['check']}: {check['count']}/{check['total']} ({check['percentage']}%)"
        )

    executor_dist = report.provenance_completeness.get("executor_type_distribution", {})
    if executor_dist:
        print(f"\nExecutor Type Distribution:")
        for executor_type, count in executor_dist.items():
            print(f"  - {executor_type}: {count}")

    print(f"\nIntegrity Status: {details.get('integrity_status', 'unknown')}")
    warnings = details.get("warnings", [])
    if warnings:
        print(f"\nWarnings:")
        for warning in warnings:
            print(f"  ⚠ {warning}")

    recommendations = details.get("recommendations", [])
    if recommendations:
        print(f"\nRecommendations:")
        for rec in recommendations:
            print(f"  → {rec}")

    print(f"\nReport saved to: {report_file}")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
