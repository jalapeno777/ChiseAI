#!/usr/bin/env python3
"""20-minute live validation of signal generator supervision."""

import json
import os
import time
from datetime import datetime

import redis

r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

print("=" * 70)
print("PAPER-DIAG-001: 20-Minute Live Validation")
print("=" * 70)

start_time = time.time()
validation_duration = 20 * 60  # 20 minutes
check_interval = 60  # Check every minute

results = []
initial_signals = len(list(r.scan_iter(match="paper:signal:20260311*")))
print(f"Initial signal count: {initial_signals}")
print("Validation will run for 20 minutes...")
print("-" * 70)

try:
    while time.time() - start_time < validation_duration:
        elapsed = int(time.time() - start_time)

        # Gather metrics
        heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")
        current_signals = len(list(r.scan_iter(match="paper:signal:20260311*")))

        # Get signal generator PID
        try:
            with open("/tmp/signal_generator.pid") as f:
                signal_pid = f.read().strip()
        except:
            signal_pid = "N/A"

        result = {
            "elapsed_min": elapsed // 60,
            "timestamp": datetime.now().isoformat(),
            "signal_gen_pid": signal_pid,
            "pipeline_status": heartbeat.get("status", "unknown"),
            "signals_generated": heartbeat.get("signals_generated", "0"),
            "iteration": heartbeat.get("iteration", "0"),
            "total_signals": current_signals,
            "new_signals": current_signals - initial_signals,
        }
        results.append(result)

        print(
            f"[{result['elapsed_min']:2d}m] "
            f"PID: {result['signal_gen_pid']:8s} | "
            f"Pipeline: {result['pipeline_status']:8s} | "
            f"Iter: {result['iteration']:4s} | "
            f"Signals: {result['signals_generated']:4s} | "
            f"Total: {result['total_signals']:4d} | "
            f"New: +{result['new_signals']:3d}"
        )

        # Verify health
        if result["pipeline_status"] == "running":
            print("  ✓ Healthy - signals being generated")
        else:
            print(f"  ⚠ Pipeline status: {result['pipeline_status']}")

        time.sleep(check_interval)

except KeyboardInterrupt:
    print("\nValidation interrupted by user")

# Save results
output_file = "docs/evidence/PAPER-DIAG-001-live-validation-20min.json"
os.makedirs(os.path.dirname(output_file), exist_ok=True)

with open(output_file, "w") as f:
    json.dump(
        {
            "validation_start": datetime.fromtimestamp(start_time).isoformat(),
            "validation_end": datetime.now().isoformat(),
            "duration_minutes": 20,
            "initial_signals": initial_signals,
            "final_signals": (
                results[-1]["total_signals"] if results else initial_signals
            ),
            "checks": results,
        },
        f,
        indent=2,
    )

print("=" * 70)
print(f"Validation complete! Results saved to: {output_file}")
if results:
    print(f"Total new signals generated: {results[-1]['new_signals']}")
    print(f"Final pipeline status: {results[-1]['pipeline_status']}")
else:
    print("No results collected")
print("=" * 70)
