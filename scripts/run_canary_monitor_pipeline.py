#!/usr/bin/env python3
"""Paper Canary Monitoring Pipeline - Telemetry Capture Script.

This script runs the canary monitoring pipeline in test/mock mode
to capture and validate telemetry output.

Usage:
    python3 scripts/run_canary_monitor_pipeline.py [options]

Options:
    --canary-id TEXT        Canary deployment ID (default: test-canary-001)
    --strategy-id TEXT      Strategy ID (default: test-strategy-v1)
    --initial-equity FLOAT  Starting equity (default: 10000)
    --mock-scenario TEXT    Mock scenario: passing|failing_drawdown|failing_winrate|pending (default: passing)
    --with-influxdb         Enable InfluxDB persistence (if available)
    --output-dir TEXT       Output directory for telemetry files (default: _bmad-output/evidence)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config.bootstrap import bootstrap  # noqa: E402
from execution.canary import (  # noqa: E402
    CanaryDeployment,
    CanaryStatus,
    create_canary_deployment,
    create_canary_monitor,
    create_canary_storage,
    create_promotion_packet_generator,
)


def setup_mock_scenario(canary: CanaryDeployment, scenario: str) -> None:
    """Configure canary metrics based on mock scenario."""
    if scenario == "passing":
        # All gates pass
        canary.metrics.total_trades = 15
        canary.metrics.winning_trades = 10
        canary.metrics.losing_trades = 5
        canary.metrics.realized_pnl = 250.0
        canary.metrics.current_equity = 10250.0
        canary.metrics.peak_equity = 10300.0
        canary.metrics.start_equity = 10000.0
        # Simulate 7+ days duration by adjusting start time
        canary.start_time = int(datetime.now().timestamp()) - (8 * 24 * 60 * 60)
        canary._calculate_end_time()

    elif scenario == "failing_drawdown":
        # Drawdown exceeds 5%
        canary.metrics.total_trades = 15
        canary.metrics.winning_trades = 5
        canary.metrics.losing_trades = 10
        canary.metrics.realized_pnl = -600.0
        canary.metrics.current_equity = 9400.0
        canary.metrics.peak_equity = 10000.0
        canary.metrics.start_equity = 10000.0
        canary.start_time = int(datetime.now().timestamp()) - (3 * 24 * 60 * 60)
        canary._calculate_end_time()

    elif scenario == "failing_winrate":
        # Win rate below 55%
        canary.metrics.total_trades = 15
        canary.metrics.winning_trades = 6
        canary.metrics.losing_trades = 9
        canary.metrics.realized_pnl = -100.0
        canary.metrics.current_equity = 9900.0
        canary.metrics.peak_equity = 10050.0
        canary.metrics.start_equity = 10000.0
        canary.start_time = int(datetime.now().timestamp()) - (8 * 24 * 60 * 60)
        canary._calculate_end_time()

    elif scenario == "pending":
        # Not enough duration yet
        canary.metrics.total_trades = 5
        canary.metrics.winning_trades = 3
        canary.metrics.losing_trades = 2
        canary.metrics.realized_pnl = 50.0
        canary.metrics.current_equity = 10050.0
        canary.metrics.peak_equity = 10050.0
        canary.metrics.start_equity = 10000.0
        canary.start_time = int(datetime.now().timestamp()) - (2 * 24 * 60 * 60)
        canary._calculate_end_time()

    # Recalculate derived metrics
    canary.metrics._calculate_metrics()


def create_influxdb_client() -> Any | None:
    """Create InfluxDB client if configuration is available."""
    try:
        from influxdb_client import InfluxDBClient

        # Check environment or use defaults
        url = os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087")
        token = os.getenv("INFLUXDB_TOKEN", "chiseai-token")
        org = os.getenv("INFLUXDB_ORG", "chiseai")

        client = InfluxDBClient(url=url, token=token, org=org)
        # Test connection
        client.ping()
        logger.info(f"Connected to InfluxDB at {url}")
        return client
    except ImportError:
        logger.warning("influxdb-client not installed")
        return None
    except Exception as e:
        logger.warning(f"Could not connect to InfluxDB: {e}")
        return None


async def run_canary_pipeline(
    canary_id: str,
    strategy_id: str,
    initial_equity: float,
    mock_scenario: str,
    use_influxdb: bool,
) -> dict[str, Any]:
    """Run the canary monitoring pipeline and capture telemetry."""

    execution_timestamp = datetime.utcnow().isoformat() + "Z"
    logger.info("=== Starting Canary Monitoring Pipeline ===")
    logger.info(f"Canary ID: {canary_id}")
    logger.info(f"Strategy ID: {strategy_id}")
    logger.info(f"Scenario: {mock_scenario}")
    logger.info(f"Initial Equity: {initial_equity}")

    # Create storage
    influxdb_client = None
    if use_influxdb:
        influxdb_client = create_influxdb_client()

    storage = create_canary_storage(influxdb_client)

    # Create canary deployment
    canary = create_canary_deployment(
        canary_id=canary_id,
        strategy_id=strategy_id,
        champion_strategy_id="champion-v1",
        allocation_pct=10.0,
    )

    # Start the canary
    canary.start(initial_equity=initial_equity)
    logger.info(f"Canary started with status: {canary.status.value}")

    # Set up mock scenario
    setup_mock_scenario(canary, mock_scenario)
    logger.info(f"Mock scenario '{mock_scenario}' configured")

    # Save initial deployment
    storage.save_deployment(canary)

    # Create monitor and register canary
    monitor = create_canary_monitor(
        check_interval_minutes=15,
    )
    monitor.register_canary(canary)

    # Run a single monitoring check
    logger.info("Running monitoring check...")
    check_result = await monitor.run_check(canary)

    # Save monitoring check
    storage.save_monitoring_check(check_result)

    # Log results
    logger.info(f"Check completed at {check_result.timestamp}")
    logger.info(f"Action taken: {check_result.action_taken}")
    logger.info(f"Final status: {canary.status.value}")
    logger.info(f"Message: {check_result.message}")

    # Log gate check details
    logger.info("\n=== Gate Evaluation Results ===")
    gate_results = []
    for gate_check in check_result.gate_checks:
        logger.info(f"  {gate_check.gate_name}: {gate_check.result.value}")
        logger.info(
            f"    Actual: {gate_check.actual_value:.4f}, Threshold: {gate_check.threshold_value:.4f}"
        )
        logger.info(f"    Message: {gate_check.message}")
        gate_results.append(
            {
                "gate_name": gate_check.gate_name,
                "result": gate_check.result.value,
                "actual_value": gate_check.actual_value,
                "threshold_value": gate_check.threshold_value,
                "message": gate_check.message,
            }
        )

    # Generate promotion packet if passed
    promotion_packet = None
    packet_markdown = None
    if canary.status == CanaryStatus.PASSED:
        logger.info("\n=== Generating Promotion Packet ===")
        packet_generator = create_promotion_packet_generator()
        packet = packet_generator.generate_packet(canary, f"packet-{canary_id}")
        if packet:
            promotion_packet = packet.to_dict()
            packet_markdown = packet_generator.generate_markdown_packet(packet)
            logger.info(f"Promotion packet generated: {packet.packet_id}")
            logger.info(f"Packet status: {packet.status}")
        else:
            logger.warning("Could not generate promotion packet")

    # Collect telemetry
    telemetry = {
        "execution_timestamp": execution_timestamp,
        "canary_id": canary_id,
        "strategy_id": strategy_id,
        "mock_scenario": mock_scenario,
        "initial_equity": initial_equity,
        "final_status": canary.status.value,
        "action_taken": check_result.action_taken,
        "gate_criteria": {
            "max_drawdown_pct": canary.criteria.max_drawdown_pct,
            "min_win_rate_pct": canary.criteria.min_win_rate_pct,
            "duration_days": canary.criteria.duration_days,
            "min_trades": canary.criteria.min_trades,
        },
        "gate_evaluations": gate_results,
        "metrics": canary.metrics.to_dict(),
        "promotion_packet": promotion_packet,
        "message": check_result.message,
        "influxdb_enabled": influxdb_client is not None,
    }

    return telemetry, packet_markdown


def write_telemetry_summary(
    telemetry: dict[str, Any],
    packet_markdown: str | None,
    output_dir: str,
) -> str:
    """Write telemetry summary to markdown file."""
    os.makedirs(output_dir, exist_ok=True)

    filename = f"CANARY_TELEMETRY_{telemetry['canary_id']}.md"
    filepath = os.path.join(output_dir, filename)

    # Determine overall status
    final_status = telemetry["final_status"]
    if final_status == "passed":
        status_emoji = "✅ PASS"
    elif final_status == "failed":
        status_emoji = "❌ FAIL"
    elif final_status == "rolled_back":
        status_emoji = "🔄 ROLLED BACK"
    else:
        status_emoji = "⏳ PENDING"

    markdown = f"""# Canary Monitoring Pipeline Telemetry

## Execution Summary

| Field | Value |
|-------|-------|
| **Execution Timestamp** | {telemetry["execution_timestamp"]} |
| **Canary ID** | {telemetry["canary_id"]} |
| **Strategy ID** | {telemetry["strategy_id"]} |
| **Mock Scenario** | {telemetry["mock_scenario"]} |
| **Initial Equity** | {telemetry["initial_equity"]:.2f} |
| **Final Status** | {status_emoji} |
| **Action Taken** | {telemetry["action_taken"]} |
| **InfluxDB Enabled** | {"Yes" if telemetry["influxdb_enabled"] else "No"} |

## Gate Criteria Configuration

| Gate | Threshold |
|------|-----------|
| Max Drawdown | ≤{telemetry["gate_criteria"]["max_drawdown_pct"]}% |
| Min Win Rate | ≥{telemetry["gate_criteria"]["min_win_rate_pct"]}% |
| Duration | ≥{telemetry["gate_criteria"]["duration_days"]} days |
| Min Trades | ≥{telemetry["gate_criteria"]["min_trades"]} |

## Gate Evaluation Results

"""

    for gate in telemetry["gate_evaluations"]:
        result_emoji = (
            "✅"
            if gate["result"] == "pass"
            else "❌" if gate["result"] == "fail" else "⏳"
        )
        markdown += f"""### {gate["gate_name"]}

| Field | Value |
|-------|-------|
| **Result** | {result_emoji} {gate["result"].upper()} |
| **Actual Value** | {gate["actual_value"]:.4f} |
| **Threshold** | {gate["threshold_value"]:.4f} |
| **Message** | {gate["message"]} |

"""

    markdown += f"""## Captured Metrics

| Metric | Value |
|--------|-------|
| **Start Equity** | {telemetry["metrics"]["start_equity"]:.8f} |
| **Current Equity** | {telemetry["metrics"]["current_equity"]:.8f} |
| **Peak Equity** | {telemetry["metrics"]["peak_equity"]:.8f} |
| **Total Trades** | {telemetry["metrics"]["total_trades"]} |
| **Winning Trades** | {telemetry["metrics"]["winning_trades"]} |
| **Losing Trades** | {telemetry["metrics"]["losing_trades"]} |
| **Win Rate** | {telemetry["metrics"]["win_rate_pct"]:.2f}% |
| **Max Drawdown** | {telemetry["metrics"]["max_drawdown_pct"]:.2f}% |
| **Realized PnL** | {telemetry["metrics"]["realized_pnl"]:.8f} |

## System Message

```
{telemetry["message"]}
```

"""

    if packet_markdown:
        markdown += f"""---

## Promotion Packet

{packet_markdown}

"""

    markdown += f"""---

## Raw Telemetry (JSON)

<details>
<summary>Click to expand</summary>

```json
{json.dumps(telemetry, indent=2)}
```

</details>

---

*Generated by ChiseAI Canary Monitoring Pipeline*
"""

    with open(filepath, "w") as f:
        f.write(markdown)

    logger.info(f"Telemetry summary written to: {filepath}")
    return filepath


async def query_influxdb_for_canary_measurements(canary_id: str) -> list[dict]:
    """Query InfluxDB for canary measurements."""
    try:
        from influxdb_client import InfluxDBClient

        url = os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087")
        token = os.getenv("INFLUXDB_TOKEN", "chiseai-token")
        org = os.getenv("INFLUXDB_ORG", "chiseai")
        bucket = "chiseai"

        client = InfluxDBClient(url=url, token=token, org=org)
        query_api = client.query_api()

        query = f"""
        from(bucket: "{bucket}")
            |> range(start: -1h)
            |> filter(fn: (r) => r._measurement == "canary_deployment" or r._measurement == "canary_monitoring_check")
            |> filter(fn: (r) => r.canary_id == "{canary_id}")
        """

        tables = query_api.query(query)
        results = []
        for table in tables:
            for record in table.records:
                results.append(
                    {
                        "measurement": record.get_measurement(),
                        "field": record.get_field(),
                        "value": record.get_value(),
                        "time": record.get_time().isoformat(),
                        "tags": record.values,
                    }
                )

        return results
    except Exception as e:
        logger.warning(f"Could not query InfluxDB: {e}")
        return []


async def main():
    # Bootstrap environment first
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="Run Paper Canary Monitoring Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default passing scenario
    python3 scripts/run_canary_monitor_pipeline.py

    # Run with failing drawdown scenario
    python3 scripts/run_canary_monitor_pipeline.py --mock-scenario failing_drawdown

    # Run with InfluxDB persistence
    python3 scripts/run_canary_monitor_pipeline.py --with-influxdb
        """,
    )
    parser.add_argument(
        "--canary-id",
        default="test-canary-001",
        help="Canary deployment ID (default: test-canary-001)",
    )
    parser.add_argument(
        "--strategy-id",
        default="test-strategy-v1",
        help="Strategy ID (default: test-strategy-v1)",
    )
    parser.add_argument(
        "--initial-equity",
        type=float,
        default=10000.0,
        help="Starting equity (default: 10000)",
    )
    parser.add_argument(
        "--mock-scenario",
        default="passing",
        choices=["passing", "failing_drawdown", "failing_winrate", "pending"],
        help="Mock scenario to simulate (default: passing)",
    )
    parser.add_argument(
        "--with-influxdb",
        action="store_true",
        help="Enable InfluxDB persistence (if available)",
    )
    parser.add_argument(
        "--output-dir",
        default="_bmad-output/evidence",
        help="Output directory for telemetry files (default: _bmad-output/evidence)",
    )

    args = parser.parse_args()

    # Run pipeline
    telemetry, packet_markdown = await run_canary_pipeline(
        canary_id=args.canary_id,
        strategy_id=args.strategy_id,
        initial_equity=args.initial_equity,
        mock_scenario=args.mock_scenario,
        use_influxdb=args.with_influxdb,
    )

    # Write telemetry summary
    filepath = write_telemetry_summary(
        telemetry=telemetry,
        packet_markdown=packet_markdown,
        output_dir=args.output_dir,
    )

    # Query InfluxDB for evidence
    if args.with_influxdb:
        logger.info("\n=== Querying InfluxDB for Canary Measurements ===")
        influxdb_results = await query_influxdb_for_canary_measurements(args.canary_id)
        if influxdb_results:
            logger.info(f"Found {len(influxdb_results)} measurements in InfluxDB")
            for result in influxdb_results[:5]:  # Show first 5
                logger.info(
                    f"  {result['measurement']}.{result['field']}: {result['value']}"
                )
        else:
            logger.info(
                "No measurements found in InfluxDB (may need to wait for flush)"
            )

    logger.info("\n=== Pipeline Complete ===")
    logger.info(f"Telemetry file: {filepath}")
    logger.info(f"Final status: {telemetry['final_status']}")

    return telemetry["final_status"] == "passed"


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
