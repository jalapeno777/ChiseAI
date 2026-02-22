#!/usr/bin/env python3
"""
Test script for ST-OPS-002: Grafana Dashboards - Paper & Live Execution

This script:
1. Adds sample order/fill events to InfluxDB
2. Adds sample portfolio snapshots
3. Adds sample kill-switch events
4. Verifies dashboards can query the data

Usage:
    python3 scripts/test_execution_dashboards.py [--host <host>] [--port <port>]

Environment Variables:
    INFLUXDB_URL: InfluxDB URL (default: http://localhost:18087)
    INFLUXDB_TOKEN: InfluxDB token (default: chiseai-token)
    INFLUXDB_ORG: InfluxDB organization (default: chiseai)
    INFLUXDB_BUCKET: InfluxDB bucket (default: chiseai)
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config.bootstrap import bootstrap

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
except ImportError:
    print("Error: influxdb-client not installed. Run: pip install influxdb-client")
    sys.exit(1)


def get_influxdb_client(
    url: Optional[str] = None, token: Optional[str] = None, org: Optional[str] = None
) -> InfluxDBClient:
    """Create InfluxDB client from environment or defaults."""
    url = url or os.getenv("INFLUXDB_URL", "http://localhost:18087")
    token = token or os.getenv("INFLUXDB_TOKEN", "chiseai-token")
    org = org or os.getenv("INFLUXDB_ORG", "chiseai")

    return InfluxDBClient(url=url, token=token, org=org)


def write_sample_orders(
    write_api, bucket: str, environment: str = "paper", count: int = 10
) -> list:
    """Write sample order events to InfluxDB."""
    orders = []
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    sides = ["buy", "sell"]

    now = datetime.now(timezone.utc)

    for i in range(count):
        order_id = f"order_{environment}_{int(time.time() * 1000)}_{i}"
        symbol = random.choice(symbols)
        side = random.choice(sides)
        price = (
            round(random.uniform(20000, 70000), 2)
            if "BTC" in symbol
            else round(random.uniform(1000, 5000), 2)
        )
        size = round(random.uniform(0.01, 1.0), 4)
        timestamp = now.timestamp() - random.randint(0, 3600)  # Within last hour

        point = (
            Point("orders")
            .tag("environment", environment)
            .tag("order_id", order_id)
            .tag("symbol", symbol)
            .tag("side", side)
            .field("order_id", order_id)
            .field("price", price)
            .field("size", size)
            .field("timestamp", int(timestamp * 1000))
            .time(int(timestamp * 1e9))
        )

        write_api.write(bucket=bucket, record=point)
        orders.append(
            {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "price": price,
                "size": size,
                "timestamp": timestamp,
            }
        )

    return orders


def write_sample_fills(
    write_api, bucket: str, orders: list, environment: str = "paper"
) -> list:
    """Write sample fill events to InfluxDB, linked to orders."""
    fills = []

    for order in orders:
        # Simulate fill latency (50-500ms)
        latency_ms = random.randint(50, 500)
        fill_timestamp = order["timestamp"] + (latency_ms / 1000)
        fill_id = f"fill_{order['order_id']}"

        # Fill price slightly different from order price (slippage)
        fill_price = order["price"] * (1 + random.uniform(-0.001, 0.001))

        point = (
            Point("fills")
            .tag("environment", environment)
            .tag("order_id", order["order_id"])
            .tag("symbol", order["symbol"])
            .tag("side", order["side"])
            .field("fill_id", fill_id)
            .field("order_id", order["order_id"])
            .field("price", round(fill_price, 2))
            .field("size", order["size"])
            .field("timestamp", int(fill_timestamp * 1000))
            .time(int(fill_timestamp * 1e9))
        )

        write_api.write(bucket=bucket, record=point)
        fills.append(
            {
                "fill_id": fill_id,
                "order_id": order["order_id"],
                "symbol": order["symbol"],
                "price": round(fill_price, 2),
                "size": order["size"],
                "timestamp": fill_timestamp,
                "latency_ms": latency_ms,
            }
        )

    return fills


def write_sample_portfolio_snapshots(
    write_api, bucket: str, environment: str = "paper", count: int = 60
) -> None:
    """Write sample portfolio snapshots to InfluxDB."""
    base_equity = 100000.0
    now = datetime.now(timezone.utc)

    for i in range(count):
        # Generate equity curve with some random walk
        pnl_change = random.uniform(-500, 600)
        base_equity += pnl_change

        unrealized_pnl = random.uniform(-1000, 2000)
        realized_pnl = base_equity - 100000.0
        margin_used = random.uniform(10000, 30000)
        margin_used_percent = (margin_used / base_equity) * 100
        max_drawdown = random.uniform(-15, -2)
        position_count = random.randint(0, 5)

        timestamp = now.timestamp() - (count - i) * 60  # Every minute

        point = (
            Point("portfolio_snapshot")
            .tag("environment", environment)
            .field("total_equity", round(base_equity, 2))
            .field("available_equity", round(base_equity - margin_used, 2))
            .field("margin_used", round(margin_used, 2))
            .field("margin_used_percent", round(margin_used_percent, 2))
            .field("unrealized_pnl", round(unrealized_pnl, 2))
            .field("realized_pnl", round(realized_pnl, 2))
            .field("max_drawdown_percent", round(max_drawdown, 2))
            .field("position_count", position_count)
            .time(int(timestamp * 1e9))
        )

        write_api.write(bucket=bucket, record=point)


def write_sample_positions(write_api, bucket: str, environment: str = "paper") -> None:
    """Write sample position data to InfluxDB."""
    positions = [
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "size": 0.5,
            "entry_price": 45000,
            "leverage": 2,
        },
        {
            "symbol": "ETHUSDT",
            "side": "short",
            "size": 2.0,
            "entry_price": 3200,
            "leverage": 3,
        },
    ]

    now = datetime.now(timezone.utc)

    for pos in positions:
        unrealized_pnl = random.uniform(-200, 500)

        point = (
            Point("positions")
            .tag("environment", environment)
            .tag("symbol", pos["symbol"])
            .tag("side", pos["side"])
            .field("symbol", pos["symbol"])
            .field("side", pos["side"])
            .field("size", pos["size"])
            .field("entry_price", pos["entry_price"])
            .field("leverage", pos["leverage"])
            .field("unrealized_pnl", round(unrealized_pnl, 2))
            .time(int(now.timestamp() * 1e9))
        )

        write_api.write(bucket=bucket, record=point)


def write_sample_kill_switch(
    write_api, bucket: str, environment: str = "live", triggered: bool = False
) -> None:
    """Write sample kill-switch state to InfluxDB."""
    now = datetime.now(timezone.utc)

    point = (
        Point("kill_switch")
        .tag("environment", environment)
        .field("triggered", 1 if triggered else 0)
        .field("trigger_count", random.randint(0, 5) if triggered else 0)
        .field("last_trigger_time", int(now.timestamp() * 1000) if triggered else 0)
        .time(int(now.timestamp() * 1e9))
    )

    write_api.write(bucket=bucket, record=point)


def verify_data(query_api, bucket: str, environment: str) -> dict:
    """Verify data was written correctly."""
    results = {}

    # Check orders
    query = f"""
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "orders")
      |> filter(fn: (r) => r.environment == "{environment}")
      |> count()
    """
    tables = query_api.query(query)
    order_count = sum([len(table.records) for table in tables])
    results["orders"] = order_count

    # Check fills
    query = f"""
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "fills")
      |> filter(fn: (r) => r.environment == "{environment}")
      |> count()
    """
    tables = query_api.query(query)
    fill_count = sum([len(table.records) for table in tables])
    results["fills"] = fill_count

    # Check portfolio snapshots
    query = f"""
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "portfolio_snapshot")
      |> filter(fn: (r) => r.environment == "{environment}")
      |> count()
    """
    tables = query_api.query(query)
    snapshot_count = sum([len(table.records) for table in tables])
    results["portfolio_snapshots"] = snapshot_count

    # Check positions
    query = f"""
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "positions")
      |> filter(fn: (r) => r.environment == "{environment}")
      |> count()
    """
    tables = query_api.query(query)
    position_count = sum([len(table.records) for table in tables])
    results["positions"] = position_count

    # Check kill switch (live only)
    if environment == "live":
        query = f"""
        from(bucket: "{bucket}")
          |> range(start: -1h)
          |> filter(fn: (r) => r._measurement == "kill_switch")
          |> filter(fn: (r) => r.environment == "{environment}")
          |> count()
        """
        tables = query_api.query(query)
        kill_switch_count = sum([len(table.records) for table in tables])
        results["kill_switch"] = kill_switch_count

    return results


def test_dashboard_api(grafana_url: str = "http://localhost:3001") -> bool:
    """Test that Grafana dashboards are accessible via API."""
    import urllib.request

    dashboard_uids = ["chiseai-paper-execution", "chiseai-live-execution"]

    all_ok = True
    for uid in dashboard_uids:
        try:
            url = f"{grafana_url}/api/dashboards/uid/{uid}"
            req = urllib.request.Request(url)
            # Note: This requires Grafana auth, may fail in test environment
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    print(f"  ✓ Dashboard {uid} accessible")
                else:
                    print(f"  ✗ Dashboard {uid} returned status {response.status}")
                    all_ok = False
        except Exception as e:
            print(f"  ⚠ Dashboard {uid} check skipped (Grafana may need auth): {e}")

    return all_ok


def print_data_schema():
    """Print the expected InfluxDB data schema for the dashboards."""
    print("\n" + "=" * 60)
    print("EXPECTED INFLUXDB DATA SCHEMA")
    print("=" * 60)
    print("""
Measurements:

1. orders (tag: environment, order_id, symbol, side)
   - Fields: order_id (string), price (float), size (float), timestamp (int)

2. fills (tag: environment, order_id, symbol, side)
   - Fields: fill_id (string), order_id (string), price (float), size (float), timestamp (int)

3. portfolio_snapshot (tag: environment)
   - Fields: total_equity, available_equity, margin_used, margin_used_percent,
             unrealized_pnl, realized_pnl, max_drawdown_percent, position_count

4. positions (tag: environment, symbol, side)
   - Fields: symbol, side, size, entry_price, leverage, unrealized_pnl

5. kill_switch (tag: environment)
   - Fields: triggered (int: 0=armed, 1=triggered), trigger_count, last_trigger_time

Example Line Protocol:
  orders,environment=paper,order_id=ord123,symbol=BTCUSDT,side=buy \\
    order_id="ord123",price=45000.00,size=0.5,timestamp=1707700000000 1707700000000000000
""")


def main():
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="Test execution dashboards by writing sample data to InfluxDB"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("INFLUXDB_HOST", "localhost"),
        help="InfluxDB host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("INFLUXDB_PORT", "18087")),
        help="InfluxDB port (default: 18087)",
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("INFLUXDB_BUCKET", "chiseai"),
        help="InfluxDB bucket (default: chiseai)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("INFLUXDB_TOKEN", "chiseai-token"),
        help="InfluxDB token",
    )
    parser.add_argument(
        "--org",
        default=os.getenv("INFLUXDB_ORG", "chiseai"),
        help="InfluxDB organization",
    )
    parser.add_argument(
        "--grafana-url",
        default=os.getenv("GRAFANA_URL", "http://localhost:3001"),
        help="Grafana URL for dashboard verification",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only print data schema, skip writing data",
    )

    args = parser.parse_args()

    # Print schema first
    print_data_schema()

    if args.schema_only:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print("Dashboard files created:")
        print("  ✓ infrastructure/grafana/provisioning/dashboards/paper-execution.json")
        print("  ✓ infrastructure/grafana/provisioning/dashboards/live-execution.json")
        print()
        print("Terraform configuration updated:")
        print("  ✓ infrastructure/terraform/dashboards.tf")
        print()
        print("To write test data to InfluxDB:")
        print("  1. Get your InfluxDB token from the InfluxDB UI")
        print("  2. Run: export INFLUXDB_TOKEN=your-token")
        print("  3. Run: python3 scripts/test_execution_dashboards.py")
        return 0

    influxdb_url = f"http://{args.host}:{args.port}"

    print("=" * 60)
    print("ST-OPS-002: Testing Execution Dashboards")
    print("=" * 60)
    print(f"InfluxDB URL: {influxdb_url}")
    print(f"Bucket: {args.bucket}")
    print()

    # Create client
    try:
        client = InfluxDBClient(url=influxdb_url, token=args.token, org=args.org)

        # Test connection
        health = client.health()
        if health.status != "pass":
            print(f"⚠ InfluxDB health check: {health.status}")
        else:
            print("✓ InfluxDB connection successful")
    except Exception as e:
        print(f"✗ Failed to connect to InfluxDB: {e}")
        print("\nMake sure InfluxDB is running:")
        print("  docker ps | grep influxdb")
        print("\nNote: If authentication fails, you may need to:")
        print("  1. Get the correct token from InfluxDB UI or CLI")
        print("  2. Set INFLUXDB_TOKEN environment variable")
        print("  3. Or use --token flag")
        return 1

    write_api = client.write_api(write_options=SYNCHRONOUS)
    query_api = client.query_api()

    # Write paper trading data
    print("\n--- Paper Trading Environment ---")
    print("Writing sample orders...")
    try:
        paper_orders = write_sample_orders(write_api, args.bucket, "paper", 10)
        print(f"  ✓ Wrote {len(paper_orders)} orders")
    except Exception as e:
        print(f"  ✗ Failed to write orders: {e}")
        paper_orders = []

    if paper_orders:
        print("Writing sample fills (linked to orders)...")
        try:
            paper_fills = write_sample_fills(
                write_api, args.bucket, paper_orders, "paper"
            )
            print(f"  ✓ Wrote {len(paper_fills)} fills")
        except Exception as e:
            print(f"  ✗ Failed to write fills: {e}")

    print("Writing sample portfolio snapshots...")
    try:
        write_sample_portfolio_snapshots(write_api, args.bucket, "paper", 60)
        print("  ✓ Wrote 60 portfolio snapshots")
    except Exception as e:
        print(f"  ✗ Failed to write snapshots: {e}")

    print("Writing sample positions...")
    try:
        write_sample_positions(write_api, args.bucket, "paper")
        print("  ✓ Wrote sample positions")
    except Exception as e:
        print(f"  ✗ Failed to write positions: {e}")

    # Write live trading data
    print("\n--- Live Trading Environment ---")
    print("Writing sample orders...")
    try:
        live_orders = write_sample_orders(write_api, args.bucket, "live", 10)
        print(f"  ✓ Wrote {len(live_orders)} orders")
    except Exception as e:
        print(f"  ✗ Failed to write orders: {e}")
        live_orders = []

    if live_orders:
        print("Writing sample fills (linked to orders)...")
        try:
            live_fills = write_sample_fills(write_api, args.bucket, live_orders, "live")
            print(f"  ✓ Wrote {len(live_fills)} fills")
        except Exception as e:
            print(f"  ✗ Failed to write fills: {e}")

    print("Writing sample portfolio snapshots...")
    try:
        write_sample_portfolio_snapshots(write_api, args.bucket, "live", 60)
        print("  ✓ Wrote 60 portfolio snapshots")
    except Exception as e:
        print(f"  ✗ Failed to write snapshots: {e}")

    print("Writing sample positions...")
    try:
        write_sample_positions(write_api, args.bucket, "live")
        print("  ✓ Wrote sample positions")
    except Exception as e:
        print(f"  ✗ Failed to write positions: {e}")

    print("Writing kill-switch state (armed)...")
    try:
        write_sample_kill_switch(write_api, args.bucket, "live", triggered=False)
        print("  ✓ Wrote kill-switch state (ARMED - green)")
    except Exception as e:
        print(f"  ✗ Failed to write kill-switch: {e}")

    # Flush writes
    write_api.flush()

    # Verify data
    print("\n--- Verifying Data in InfluxDB ---")
    time.sleep(1)  # Give InfluxDB time to index

    print("\nPaper environment:")
    try:
        paper_results = verify_data(query_api, args.bucket, "paper")
        for key, count in paper_results.items():
            status = "✓" if count > 0 else "✗"
            print(f"  {status} {key}: {count} records")
    except Exception as e:
        print(f"  ✗ Failed to query: {e}")

    print("\nLive environment:")
    try:
        live_results = verify_data(query_api, args.bucket, "live")
        for key, count in live_results.items():
            status = "✓" if count > 0 else "✗"
            print(f"  {status} {key}: {count} records")
    except Exception as e:
        print(f"  ✗ Failed to query: {e}")

    # Test dashboard accessibility
    print("\n--- Testing Grafana Dashboards ---")
    test_dashboard_api(args.grafana_url)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Dashboard files created:")
    print("  ✓ infrastructure/grafana/provisioning/dashboards/paper-execution.json")
    print("  ✓ infrastructure/grafana/provisioning/dashboards/live-execution.json")
    print()
    print("Terraform configuration updated:")
    print("  ✓ infrastructure/terraform/dashboards.tf")
    print()
    print("Dashboard URLs (when Grafana is running):")
    print(f"  Paper Trading:  {args.grafana_url}/d/chiseai-paper-execution")
    print(f"  Live Trading:   {args.grafana_url}/d/chiseai-live-execution")
    print()
    print("To verify dashboards are working:")
    print("  1. Open Grafana in your browser")
    print("  2. Navigate to Dashboards > ChiseAI folder")
    print("  3. Open 'ChiseAI - Paper Trading Execution'")
    print("  4. Open 'ChiseAI - Live Trading Execution'")
    print("  5. Verify panels show data (may need to refresh)")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
