#!/usr/bin/env python3
"""Live validation script for 20+ minute signal generator testing."""

import json
import time
from datetime import datetime

import redis


def run_validation(duration_minutes=20):
    """Run live validation for specified duration."""
    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    print("Starting 20-minute live validation...")
    print("=" * 60)

    start_time = time.time()
    check_interval = 60  # Check every minute
    validation_duration = duration_minutes * 60  # 20 minutes

    results = []

    while time.time() - start_time < validation_duration:
        elapsed = int(time.time() - start_time)
        remaining = validation_duration - elapsed

        # Check signal generator heartbeat
        heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")

        # Count signals
        signals = len(list(r.scan_iter(match="paper:signal:20260311*")))

        # Get latest signal timestamp
        latest_signal = None
        latest_keys = list(r.scan_iter(match="paper:signal:2026031118*", count=100))
        for key in latest_keys[:10]:  # Check first 10
            data = r.hgetall(key)
            if data.get("timestamp"):
                latest_signal = data["timestamp"]
                break

        # Check supervisor state if available
        supervisor = r.hgetall("bmad:chiseai:supervisor:state")

        result = {
            "elapsed_min": elapsed // 60,
            "elapsed_sec": elapsed,
            "supervisor_status": supervisor.get("status", "not_running"),
            "heartbeat_status": heartbeat.get("status", "unknown"),
            "pipeline_status": heartbeat.get("pipeline_status", "unknown"),
            "signals_15m": heartbeat.get("signals_15m", "0"),
            "signals_generated": heartbeat.get("signals_generated", "0"),
            "total_signals": signals,
            "latest_signal": latest_signal,
            "timestamp": datetime.now().isoformat(),
        }
        results.append(result)

        status_str = result["heartbeat_status"]
        sig_gen = result["signals_generated"]
        print(
            f"[{elapsed // 60:2d}m {elapsed % 60:2d}s] Status: {status_str}, "
            f"Signals: {signals} (gen: {sig_gen}), "
            f"Latest: {latest_signal.split('T')[1][:8] if latest_signal else 'None'}"
        )

        time.sleep(check_interval)

    # Save results
    output_path = "docs/evidence/PAPER-DIAG-001-live-validation-20min.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print("=" * 60)
    print("Validation complete!")
    print(f"Results saved to: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)

    total_checks = len(results)
    running_checks = sum(1 for r in results if r["heartbeat_status"] == "running")
    total_signals_start = results[0]["total_signals"] if results else 0
    total_signals_end = results[-1]["total_signals"] if results else 0
    signals_increase = total_signals_end - total_signals_start

    print(f"Total checks: {total_checks}")
    print(f"Running status checks: {running_checks}/{total_checks}")
    print(f"Signals at start: {total_signals_start}")
    print(f"Signals at end: {total_signals_end}")
    print(f"Net new signals: {signals_increase}")
    print(f"Average signals/min: {signals_increase / duration_minutes:.1f}")

    return results


if __name__ == "__main__":
    run_validation(20)
