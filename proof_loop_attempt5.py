#!/usr/bin/env python3
"""Proof Loop Attempt 5 - CONCURRENT EXECUTION"""

import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")


async def main():
    output_dir = Path("_bmad-output/forensic-evidence")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║  PROOF LOOP ATTEMPT 5 - FINAL - CONCURRENT EXECUTION              ║")
    print(f"║  Start: {datetime.now(UTC).isoformat()}                              ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    # Step 1: Start continuous signal generation (60 minutes to ensure overlap)
    print("\n[1/4] Starting 60-minute continuous signal generation...")
    signal_log = open(  # noqa: SIM115
        output_dir / f"signal_gen_attempt5_{timestamp}.log", "w"
    )
    signal_proc = subprocess.Popen(
        [
            "python3",
            "scripts/continuous_signal_generator.py",
            "--duration",
            "60",
            "--interval",
            "30",
        ],
        stdout=signal_log,
        stderr=subprocess.STDOUT,
    )

    print(f"    Signal Generator PID: {signal_proc.pid}")
    print("    Waiting 2 minutes for signal generation to warm up...")

    # Step 2: Wait 2 minutes and verify activity
    await asyncio.sleep(120)

    print("\n[2/4] Verifying signal generation...")
    import redis

    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    baseline_signals = len(r.keys("paper:signal:*"))
    baseline_heartbeat = r.hget("bmad:chiseai:scheduler:heartbeat", "timestamp")

    print(f"    Baseline paper signals: {baseline_signals}")
    print(f"    Scheduler heartbeat: {baseline_heartbeat}")

    # Wait another minute and check for activity
    await asyncio.sleep(60)

    check_signals = len(r.keys("paper:signal:*"))
    check_heartbeat = r.hget("bmad:chiseai:scheduler:heartbeat", "timestamp")

    signal_delta = check_signals - baseline_signals

    print(f"    After 3 min - Paper signals: {check_signals} (+{signal_delta})")
    print(f"    After 3 min - Heartbeat: {check_heartbeat}")

    if signal_delta < 1:
        print("    ❌ ERROR: No signal generation detected!")
        signal_proc.terminate()
        return 1

    print(f"    ✅ Activity confirmed: +{signal_delta} signals in 3 minutes")

    # Step 3: NOW start the 30-minute proof loop
    print(
        "\n[3/4] Starting 30-minute proof loop (signal gen continues in background)..."
    )
    from validation.forensic_harness import IntegratedForensicHarness

    harness = IntegratedForensicHarness(duration_minutes=30)
    result = await harness.run_integrated_proof_loop()

    # Step 4: Stop signal generation and save results
    print("\n[4/4] Stopping signal generation...")
    signal_proc.terminate()
    try:
        signal_proc.wait(timeout=10)
    except Exception:
        signal_proc.kill()
    signal_log.close()

    # Save results
    import json

    result_data = {
        "proof_id": f"ATTEMPT5-FINAL-{timestamp}",
        "gate_results": [
            {
                "gate": gate,
                "passed": result.gate_results[gate].status.value == "PASS",
                "status": result.gate_results[gate].status.value,
                "artifacts_found": result.gate_results[gate].artifacts_found,
                "artifacts_missing": result.gate_results[gate].artifacts_missing,
                "validation_errors": result.gate_results[gate].validation_errors,
            }
            for gate in result.gate_results
        ],
        "all_passed": result.overall_status.value == "PASS",
        "overall_status": result.overall_status.value,
        "timestamp": timestamp,
        "signal_gen_pid": signal_proc.pid,
        "signal_delta_before": signal_delta,
        "concurrent_execution": True,
        "start_time": result.start_time,
        "end_time": result.end_time,
    }

    result_path = output_dir / f"ATTEMPT5_FINAL_result_{timestamp}.json"
    with open(result_path, "w") as f:
        json.dump(result_data, f, indent=2)

    # Also save full bundle
    bundle = harness.generate_bundle()
    bundle_path = output_dir / f"ATTEMPT5_FINAL_bundle_{timestamp}.json"
    with open(bundle_path, "w") as f:
        json.dump(bundle.to_dict(), f, indent=2, default=str)

    # Print results
    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║  ATTEMPT 5 - FINAL RESULTS                                        ║")
    print("╠════════════════════════════════════════════════════════════════════╣")

    pass_count = sum(
        1
        for gate in result.gate_results
        if result.gate_results[gate].status.value == "PASS"
    )
    total_gates = len(result.gate_results)

    for gate in sorted(result.gate_results.keys()):
        r = result.gate_results[gate]
        status = "✅ PASS" if r.status.value == "PASS" else "❌ FAIL"
        print(f"║  {gate}: {status}                                         ║")

    overall = "✅ SUCCESS" if result.overall_status.value == "PASS" else "❌ FAILED"
    print("╠════════════════════════════════════════════════════════════════════╣")
    print(
        f"║  PASSED: {pass_count}/{total_gates} gates                                  ║"
    )
    print(f"║  OVERALL: {overall}                                          ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    print(f"\nResults saved to: {result_path}")
    print(f"Bundle saved to: {bundle_path}")

    return 0 if result.overall_status.value == "PASS" else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
