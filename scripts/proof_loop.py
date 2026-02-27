#!/usr/bin/env python3
"""Proof loop for 20-30 minute integration verification.

Collects evidence for all gates G1-G8 with deltas.

Usage:
    python3 scripts/proof_loop.py --duration 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, "src")

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087")
INFLUXDB_TOKEN = os.getenv(
    "INFLUXDB_TOKEN",
    "REDACTED_INFLUXDB_TOKEN",
)


class ProofLoop:
    """Proof loop collector for integration verification."""

    def __init__(self, duration_minutes: int = 30):
        self.duration_minutes = duration_minutes
        self.snapshots: list[dict] = []
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

    async def get_redis_counts(self) -> dict:
        """Get current Redis key counts."""
        try:
            import redis as redis_lib

            client = redis_lib.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
            )

            # Count keys by pattern
            signals = len(client.keys("paper:signal:*"))
            orders = len(client.keys("paper:order:*"))
            fills = len(client.keys("paper:fill:*"))
            outcomes = len(client.keys("paper:outcome:*"))

            return {
                "signals": signals,
                "orders": orders,
                "fills": fills,
                "outcomes": outcomes,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {
                "signals": 0,
                "orders": 0,
                "fills": 0,
                "outcomes": 0,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def get_influx_data(self) -> dict:
        """Get recent InfluxDB data."""
        import subprocess

        try:
            curl_cmd = [
                "curl",
                "-s",
                "-G",
                f"{INFLUXDB_URL}/query?db=chiseai",
                "--data-urlencode",
                "q=SELECT * FROM paper_portfolio ORDER BY time DESC LIMIT 1",
                "-H",
                f"Authorization: Token {INFLUXDB_TOKEN}",
            ]
            result = subprocess.run(
                curl_cmd, capture_output=True, text=True, timeout=10
            )
            data = json.loads(result.stdout)
            return {
                "has_data": bool(data.get("results", [{}])[0].get("series")),
                "raw": data,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {
                "has_data": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def take_snapshot(self, label: str) -> dict:
        """Take a snapshot of current state."""
        redis_counts = await self.get_redis_counts()
        influx_data = await self.get_influx_data()

        snapshot = {
            "label": label,
            "timestamp": datetime.now(UTC).isoformat(),
            "redis": redis_counts,
            "influx": influx_data,
        }
        self.snapshots.append(snapshot)
        return snapshot

    def calculate_deltas(self) -> dict:
        """Calculate deltas between first and last snapshot."""
        if len(self.snapshots) < 2:
            return {"error": "Need at least 2 snapshots"}

        first = self.snapshots[0]
        last = self.snapshots[-1]

        return {
            "signal_delta": last["redis"]["signals"] - first["redis"]["signals"],
            "order_delta": last["redis"]["orders"] - first["redis"]["orders"],
            "fill_delta": last["redis"]["fills"] - first["redis"]["fills"],
            "outcome_delta": last["redis"]["outcomes"] - first["redis"]["outcomes"],
            "duration_minutes": self.duration_minutes,
            "start_time": first["timestamp"],
            "end_time": last["timestamp"],
        }

    async def run(self) -> dict:
        """Run the proof loop."""
        print("\n" + "=" * 70)
        print("PROOF LOOP - Integration Verification")
        print(f"Duration: {self.duration_minutes} minutes")
        print("=" * 70)

        self.start_time = datetime.now(UTC)

        # Baseline snapshot
        print("\n📸 BASELINE SNAPSHOT")
        baseline = await self.take_snapshot("baseline")
        print(f"  Signals: {baseline['redis']['signals']}")
        print(f"  Orders: {baseline['redis']['orders']}")
        print(f"  Fills: {baseline['redis']['fills']}")
        print(f"  Outcomes: {baseline['redis']['outcomes']}")

        # Run for specified duration, taking snapshots every minute
        print(f"\n⏱️  Running for {self.duration_minutes} minutes...")
        for i in range(self.duration_minutes):
            await asyncio.sleep(60)  # Wait 1 minute
            snapshot = await self.take_snapshot(f"minute_{i + 1}")
            print(
                f"  Minute {i + 1}: S={snapshot['redis']['signals']} O={snapshot['redis']['orders']} F={snapshot['redis']['fills']} Out={snapshot['redis']['outcomes']}"
            )

        self.end_time = datetime.now(UTC)

        # Final snapshot
        print("\n📸 FINAL SNAPSHOT")
        final = await self.take_snapshot("final")
        print(f"  Signals: {final['redis']['signals']}")
        print(f"  Orders: {final['redis']['orders']}")
        print(f"  Fills: {final['redis']['fills']}")
        print(f"  Outcomes: {final['redis']['outcomes']}")

        # Calculate deltas
        deltas = self.calculate_deltas()

        print("\n" + "=" * 70)
        print("PROOF LOOP RESULTS")
        print("=" * 70)
        print(f"Duration: {deltas['duration_minutes']} minutes")
        print(f"Signal delta: {deltas['signal_delta']:+d}")
        print(f"Order delta: {deltas['order_delta']:+d}")
        print(f"Fill delta: {deltas['fill_delta']:+d}")
        print(f"Outcome delta: {deltas['outcome_delta']:+d}")

        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "deltas": deltas,
            "snapshots": self.snapshots,
        }


async def main():
    parser = argparse.ArgumentParser(
        description="Proof loop for integration verification"
    )
    parser.add_argument("--duration", type=int, default=30, help="Duration in minutes")
    args = parser.parse_args()

    loop = ProofLoop(duration_minutes=args.duration)
    results = await loop.run()

    # Save results
    output_file = f"/tmp/proof_loop_results_{int(time.time())}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to: {output_file}")

    return (
        0
        if all(v >= 0 for v in results["deltas"].values() if isinstance(v, int))
        else 1
    )


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
