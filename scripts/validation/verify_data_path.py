#!/usr/bin/env python3
"""
Data Path Verification Script

Tests PostgreSQL connectivity with actual query execution and verifies
the signal_outcomes table exists and is writable.

Usage:
    python3 scripts/validation/verify_data_path.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
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
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class DataPathHealthReport:
    """Health report for data path verification."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    checks: list[dict[str, Any]] = field(default_factory=list)
    overall_status: str = "unknown"
    postgresql: dict[str, Any] = field(default_factory=dict)
    signal_outcomes_table: dict[str, Any] = field(default_factory=dict)
    test_flow: dict[str, Any] = field(default_factory=dict)

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
    """Get PostgreSQL configuration with fallbacks."""
    return {
        "host": os.getenv("POSTGRES_HOST", "host.docker.internal"),
        "port": int(os.getenv("POSTGRES_PORT", "5434")),
        "database": os.getenv("POSTGRES_DB", "chiseai"),
        "user": os.getenv("POSTGRES_USER", "chiseai"),
        "password": os.getenv("POSTGRES_PASSWORD", "change-me"),
    }


def test_postgresql_connectivity() -> tuple[bool, dict[str, Any]]:
    """Test PostgreSQL connectivity with actual query execution.

    Returns:
        Tuple of (success, details)
    """
    config = get_postgres_config()
    details = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "user": config["user"],
        "connection_attempts": [],
    }

    try:
        import psycopg2

        # Attempt connection
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
            connect_timeout=10,
        )
        details["connection_attempts"].append("Connection established")

        # Test with actual query
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            details["version"] = version
            details["connection_attempts"].append("Query execution successful")

            # Test basic operations
            cur.execute("SELECT NOW();")
            server_time = cur.fetchone()[0]
            details["server_time"] = server_time.isoformat()

        conn.close()
        details["connection_attempts"].append("Connection closed cleanly")
        return True, details

    except ImportError as e:
        details["error"] = f"psycopg2 not installed: {e}"
        details["connection_attempts"].append(f"Import error: {e}")
        return False, details
    except Exception as e:
        details["error"] = str(e)
        details["connection_attempts"].append(f"Connection failed: {e}")
        return False, details


def test_signal_outcomes_table() -> tuple[bool, dict[str, Any]]:
    """Test signal_outcomes table exists and is writable.

    Returns:
        Tuple of (success, details)
    """
    config = get_postgres_config()
    details = {
        "table_name": "signal_outcomes",
        "operations": [],
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
            # Check if table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'signal_outcomes'
                );
            """)
            table_exists = cur.fetchone()[0]
            details["table_exists"] = table_exists
            details["operations"].append(f"Table exists check: {table_exists}")

            if not table_exists:
                details["error"] = "signal_outcomes table does not exist"
                conn.close()
                return False, details

            # Get table schema
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'signal_outcomes'
                ORDER BY ordinal_position;
            """)
            columns = cur.fetchall()
            details["columns"] = [
                {"name": col[0], "type": col[1], "nullable": col[2]} for col in columns
            ]
            details["operations"].append(f"Retrieved {len(columns)} columns")

            # Check for required columns
            required_columns = ["id", "signal_id", "outcome", "created_at"]
            found_columns = [col[0] for col in columns]
            missing_columns = [
                col for col in required_columns if col not in found_columns
            ]
            details["missing_columns"] = missing_columns

            if missing_columns:
                details["error"] = f"Missing required columns: {missing_columns}"
                conn.close()
                return False, details

            # Test write permission with a test record
            test_signal_id = f"test_{uuid.uuid4().hex[:8]}"
            try:
                cur.execute(
                    """
                    INSERT INTO signal_outcomes (signal_id, outcome, metadata)
                    VALUES (%s, %s, %s)
                    RETURNING id;
                """,
                    (test_signal_id, "test", json.dumps({"test": True})),
                )
                inserted_id = cur.fetchone()[0]
                conn.commit()
                details["test_insert_id"] = inserted_id
                details["operations"].append(
                    f"Test insert successful: id={inserted_id}"
                )

                # Verify the insert
                cur.execute(
                    "SELECT * FROM signal_outcomes WHERE id = %s;", (inserted_id,)
                )
                record = cur.fetchone()
                if record:
                    details["operations"].append("Test record verified in database")

                # Clean up test record
                cur.execute(
                    "DELETE FROM signal_outcomes WHERE id = %s;", (inserted_id,)
                )
                conn.commit()
                details["operations"].append("Test record cleaned up")

            except Exception as e:
                details["error"] = f"Write test failed: {e}"
                details["operations"].append(f"Write test failed: {e}")
                conn.rollback()
                conn.close()
                return False, details

        conn.close()
        return True, details

    except Exception as e:
        details["error"] = str(e)
        details["operations"].append(f"Error: {e}")
        return False, details


def test_full_signal_flow() -> tuple[bool, dict[str, Any]]:
    """Test the full flow: insert test signal → verify in DB → cleanup.

    Returns:
        Tuple of (success, details)
    """
    config = get_postgres_config()
    details = {
        "flow_steps": [],
        "test_signal_id": None,
        "test_record_id": None,
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

        test_signal_id = f"flow_test_{uuid.uuid4().hex[:8]}"
        details["test_signal_id"] = test_signal_id

        with conn.cursor() as cur:
            # Step 1: Insert test signal outcome
            cur.execute(
                """
                INSERT INTO signal_outcomes (
                    signal_id, outcome, pnl, metadata, created_at
                ) VALUES (%s, %s, %s, %s, NOW())
                RETURNING id, signal_id, outcome, created_at;
            """,
                (
                    test_signal_id,
                    "win",
                    100.50,
                    json.dumps(
                        {
                            "test": True,
                            "flow_verification": True,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ),
                ),
            )
            record = cur.fetchone()
            conn.commit()

            inserted_id = record[0]
            details["test_record_id"] = inserted_id
            details["flow_steps"].append(f"1. Inserted test signal: id={inserted_id}")

            # Step 2: Verify record exists
            cur.execute(
                """
                SELECT id, signal_id, outcome, pnl, metadata, created_at
                FROM signal_outcomes
                WHERE signal_id = %s;
            """,
                (test_signal_id,),
            )
            verified_record = cur.fetchone()

            if not verified_record:
                details["error"] = "Verification failed: record not found"
                details["flow_steps"].append("2. VERIFICATION FAILED: Record not found")
                conn.close()
                return False, details

            details["flow_steps"].append("2. Verified record exists in database")
            details["verified_record"] = {
                "id": verified_record[0],
                "signal_id": verified_record[1],
                "outcome": verified_record[2],
                "pnl": float(verified_record[3]) if verified_record[3] else None,
                "created_at": verified_record[5].isoformat()
                if verified_record[5]
                else None,
            }

            # Step 3: Query by outcome type
            cur.execute(
                """
                SELECT COUNT(*) FROM signal_outcomes
                WHERE signal_id = %s AND outcome = 'win';
            """,
                (test_signal_id,),
            )
            count = cur.fetchone()[0]
            details["flow_steps"].append(
                f"3. Query by outcome returned {count} records"
            )

            # Step 4: Clean up
            cur.execute("DELETE FROM signal_outcomes WHERE id = %s;", (inserted_id,))
            conn.commit()
            details["flow_steps"].append("4. Cleaned up test record")

            # Step 5: Verify cleanup
            cur.execute(
                "SELECT COUNT(*) FROM signal_outcomes WHERE id = %s;", (inserted_id,)
            )
            remaining = cur.fetchone()[0]
            if remaining == 0:
                details["flow_steps"].append("5. Verified cleanup: record removed")
            else:
                details["flow_steps"].append(f"5. WARNING: {remaining} records remain")

        conn.close()
        return True, details

    except Exception as e:
        details["error"] = str(e)
        details["flow_steps"].append(f"Error: {e}")
        return False, details


def generate_report(report: DataPathHealthReport) -> dict[str, Any]:
    """Generate JSON report from health report object."""
    return {
        "timestamp": report.timestamp,
        "execution_id": report.execution_id,
        "overall_status": report.overall_status,
        "checks": report.checks,
        "postgresql": report.postgresql,
        "signal_outcomes_table": report.signal_outcomes_table,
        "test_flow": report.test_flow,
    }


def save_report(report: dict[str, Any]) -> Path:
    """Save report to file."""
    output_dir = Path("_bmad-output")
    output_dir.mkdir(exist_ok=True)

    report_file = output_dir / f"data-path-report-{report['execution_id']}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"\nReport saved to: {report_file}")
    return report_file


def main() -> int:
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("DATA PATH VERIFICATION")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now(UTC).isoformat()}")
    logger.info(f"PostgreSQL Host: host.docker.internal (container context)")
    logger.info("")

    report = DataPathHealthReport()
    all_passed = True

    # Test 1: PostgreSQL Connectivity
    logger.info("[Test 1/3] Testing PostgreSQL connectivity...")
    success, details = test_postgresql_connectivity()
    report.postgresql = details
    report.add_check("postgresql_connectivity", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        logger.error(
            f"PostgreSQL connectivity failed: {details.get('error', 'Unknown error')}"
        )

    # Test 2: Signal Outcomes Table
    logger.info("\n[Test 2/3] Testing signal_outcomes table...")
    success, details = test_signal_outcomes_table()
    report.signal_outcomes_table = details
    report.add_check("signal_outcomes_table", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        logger.error(
            f"Signal outcomes table test failed: {details.get('error', 'Unknown error')}"
        )

    # Test 3: Full Signal Flow
    logger.info("\n[Test 3/3] Testing full signal flow...")
    success, details = test_full_signal_flow()
    report.test_flow = details
    report.add_check("full_signal_flow", "pass" if success else "fail", details)
    if not success:
        all_passed = False
        logger.error(
            f"Full signal flow test failed: {details.get('error', 'Unknown error')}"
        )

    # Determine overall status
    report.overall_status = "healthy" if all_passed else "degraded"

    # Generate and save report
    report_dict = generate_report(report)
    report_file = save_report(report_dict)

    # Print summary
    print("\n" + "=" * 60)
    print("DATA PATH VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Execution ID: {report.execution_id}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Overall Status: {report.overall_status.upper()}")
    print(f"\nChecks Performed:")
    for check in report.checks:
        icon = "✓" if check["status"] == "pass" else "✗"
        print(f"  {icon} {check['name']}: {check['status']}")

    print(f"\nPostgreSQL Details:")
    if "version" in report.postgresql:
        print(f"  Version: {report.postgresql['version'][:50]}...")
    if "server_time" in report.postgresql:
        print(f"  Server Time: {report.postgresql['server_time']}")

    print(f"\nSignal Outcomes Table:")
    print(f"  Exists: {report.signal_outcomes_table.get('table_exists', False)}")
    if "columns" in report.signal_outcomes_table:
        print(f"  Columns: {len(report.signal_outcomes_table['columns'])}")
    if "missing_columns" in report.signal_outcomes_table:
        missing = report.signal_outcomes_table["missing_columns"]
        if missing:
            print(f"  Missing: {', '.join(missing)}")

    print(f"\nTest Flow:")
    if "flow_steps" in report.test_flow:
        for step in report.test_flow["flow_steps"]:
            print(f"  {step}")

    print(f"\nReport saved to: {report_file}")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
