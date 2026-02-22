#!/usr/bin/env python3
"""
Quick validation burn-in test (15 minutes) to confirm PostgreSQL fix.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap  # noqa: E402


async def run_validation_burn_in(duration_seconds: int = 900) -> dict:
    """Run a validation burn-in test."""
    start_time = time.time()
    execution_id = f"val-{int(start_time)}"

    logger.info("=" * 60)
    logger.info(f"VALIDATION BURN-IN - ID: {execution_id}")
    logger.info(f"Duration: {duration_seconds}s ({duration_seconds / 60:.1f} minutes)")
    logger.info("=" * 60)

    # Bootstrap
    bootstrap(load_env=True)

    # Metrics
    metrics = {
        "postgresql": {"checks": 0, "failures": 0},
        "influxdb": {"checks": 0, "failures": 0},
        "redis": {"checks": 0, "failures": 0},
    }
    health_checks = []
    incidents = []

    # Test database connectivity
    logger.info("\n[Pre-test] Testing database connectivity...")

    # PostgreSQL test
    try:
        import psycopg2

        conn = psycopg2.connect(
            host="host.docker.internal",
            port=5434,
            database="chiseai",
            user="chiseai",
            password="change-me",
            connect_timeout=5,
        )
        conn.close()
        logger.info("✓ PostgreSQL: Connected")
    except Exception as e:
        logger.error(f"✗ PostgreSQL: {e}")
        incidents.append({"component": "postgresql", "message": str(e)})

    # InfluxDB test
    try:
        from influxdb_client import InfluxDBClient

        url = os.getenv("DQ_INFLUX_URL", "http://host.docker.internal:18087")
        token = os.getenv("INFLUXDB_TOKEN", "")
        org = os.getenv("DQ_INFLUX_ORG", "chiseai")
        client = InfluxDBClient(url=url, token=token, org=org)
        health = client.health()
        logger.info(f"✓ InfluxDB: {health.status}")
        client.close()
    except Exception as e:
        logger.error(f"✗ InfluxDB: {e}")
        incidents.append({"component": "influxdb", "message": str(e)})

    # Redis test
    try:
        import redis as redis_lib

        r = redis_lib.Redis(
            host="host.docker.internal",
            port=6380,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        r.ping()
        logger.info("✓ Redis: Connected")
    except Exception as e:
        logger.error(f"✗ Redis: {e}")
        incidents.append({"component": "redis", "message": str(e)})

    # Run burn-in loop
    logger.info(f"\nStarting {duration_seconds}s burn-in test...")
    check_interval = 30  # seconds
    status_interval = 300  # 5 minutes
    last_status = 0

    while time.time() - start_time < duration_seconds:
        elapsed = time.time() - start_time

        # Health check
        check_result = {"timestamp": datetime.now(UTC).isoformat(), "elapsed": elapsed}

        # PostgreSQL
        try:
            import psycopg2

            conn = psycopg2.connect(
                host="host.docker.internal",
                port=5434,
                database="chiseai",
                user="chiseai",
                password="change-me",
                connect_timeout=5,
            )
            conn.close()
            metrics["postgresql"]["checks"] += 1
            check_result["postgresql"] = "ok"
        except Exception as e:
            metrics["postgresql"]["checks"] += 1
            metrics["postgresql"]["failures"] += 1
            check_result["postgresql"] = f"fail: {e}"

        # InfluxDB
        try:
            from influxdb_client import InfluxDBClient

            url = os.getenv("DQ_INFLUX_URL", "http://host.docker.internal:18087")
            token = os.getenv("INFLUXDB_TOKEN", "")
            org = os.getenv("DQ_INFLUX_ORG", "chiseai")
            client = InfluxDBClient(url=url, token=token, org=org)
            health = client.health()
            client.close()
            metrics["influxdb"]["checks"] += 1
            check_result["influxdb"] = "ok"
        except Exception as e:
            metrics["influxdb"]["checks"] += 1
            metrics["influxdb"]["failures"] += 1
            check_result["influxdb"] = f"fail: {e}"

        # Redis
        try:
            import redis as redis_lib

            r = redis_lib.Redis(
                host="host.docker.internal",
                port=6380,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            r.ping()
            metrics["redis"]["checks"] += 1
            check_result["redis"] = "ok"
        except Exception as e:
            metrics["redis"]["checks"] += 1
            metrics["redis"]["failures"] += 1
            check_result["redis"] = f"fail: {e}"

        health_checks.append(check_result)

        # Status update every 5 minutes
        if elapsed - last_status >= status_interval:
            last_status = elapsed
            uptime_pct = (elapsed / duration_seconds) * 100
            logger.info(f"\n{'=' * 60}")
            logger.info(
                f"STATUS UPDATE ({elapsed / 60:.1f}min / {duration_seconds / 60:.0f}min)"
            )
            logger.info(f"Uptime: {uptime_pct:.1f}%")
            logger.info(f"Health checks: {len(health_checks)}")
            for db, stats in metrics.items():
                if stats["checks"] > 0:
                    fail_rate = (stats["failures"] / stats["checks"]) * 100
                    logger.info(
                        f"{db}: {stats['checks']} checks, {stats['failures']} failures ({fail_rate:.1f}%)"
                    )
            logger.info(f"{'=' * 60}")

        await asyncio.sleep(check_interval)

    # Calculate final metrics
    end_time = time.time()
    actual_duration = end_time - start_time
    uptime_pct = min(100.0, (actual_duration / duration_seconds) * 100)

    # Calculate health percentages
    db_health = {}
    for db, stats in metrics.items():
        if stats["checks"] > 0:
            success_rate = (
                (stats["checks"] - stats["failures"]) / stats["checks"]
            ) * 100
            db_health[db] = f"{success_rate:.1f}%"
        else:
            db_health[db] = "N/A"

    # Determine verdict
    total_failures = sum(stats["failures"] for stats in metrics.values())
    total_checks = sum(stats["checks"] for stats in metrics.values())

    if total_checks > 0 and total_failures / total_checks > 0.1:
        verdict = "NO-GO"
        rationale = f"High failure rate: {(total_failures / total_checks) * 100:.1f}%"
    elif metrics["postgresql"]["failures"] > 0:
        verdict = "NO-GO"
        rationale = "PostgreSQL had failures during burn-in"
    else:
        verdict = "GO"
        rationale = "All systems performed within acceptable parameters"

    report = {
        "burn_in_id": execution_id,
        "test_type": "validation_burn_in",
        "start_time": datetime.fromtimestamp(start_time, UTC).isoformat(),
        "end_time": datetime.fromtimestamp(end_time, UTC).isoformat(),
        "duration_configured_seconds": duration_seconds,
        "duration_actual_seconds": actual_duration,
        "uptime_percentage": uptime_pct,
        "database_health": {
            "checks": metrics,
            "summary": db_health,
        },
        "incidents": {
            "total": len(incidents),
            "details": incidents,
        },
        "health_checks": {
            "total": len(health_checks),
        },
        "verdict": verdict,
        "rationale": rationale,
    }

    return report


async def main():
    """Main entry point."""
    report = await run_validation_burn_in(duration_seconds=900)  # 15 minutes

    # Save report
    output_dir = Path("_bmad-output")
    output_dir.mkdir(exist_ok=True)
    report_file = output_dir / "validation-burn-in.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION BURN-IN REPORT (15 minutes)")
    print("=" * 60)
    print(f"Duration: {report['duration_actual_seconds']:.0f} seconds")
    print(f"Uptime: {report['uptime_percentage']:.1f}%")

    print("\nDatabase Health:")
    for db, status in report["database_health"]["summary"].items():
        checks = report["database_health"]["checks"][db]["checks"]
        failures = report["database_health"]["checks"][db]["failures"]
        print(f"  - {db}: {status} ({checks} checks, {failures} failures)")

    print(f"\nIncidents: {report['incidents']['total']}")

    print("\n" + "=" * 60)
    print(f"VERDICT: {report['verdict']}")
    print(f"Rationale: {report['rationale']}")
    print("=" * 60)
    print(f"\nReport saved to: {report_file}")

    return 0 if report["verdict"] == "GO" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
