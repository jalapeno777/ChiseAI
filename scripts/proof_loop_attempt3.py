#!/usr/bin/env python3
"""Coordinated proof loop with trading activity."""

import asyncio
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from validation.forensic_harness import IntegratedForensicHarness


async def main():
    output_dir = Path("_bmad-output/forensic-evidence")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║  PROOF LOOP ATTEMPT 3 - COORDINATED EXECUTION                     ║")
    print(
        f"║  Start: {datetime.now(timezone.utc).isoformat()}                              ║"
    )
    print("╚════════════════════════════════════════════════════════════════════╝")

    # Start trading activity in background (will run for 35+ minutes)
    print("\n[1/3] Starting trading activity...")
    trading_log = output_dir / f"trading_{timestamp}.log"
    trading_proc = subprocess.Popen(
        [
            "python3",
            "scripts/run_trading_activity.py",
            "--mode",
            "paper",
            "--duration",
            "2100",  # 35 minutes to ensure overlap
            "--confidence-threshold",
            "0.55",
        ],
        stdout=open(trading_log, "w"),
        stderr=subprocess.STDOUT,
    )

    print(f"    Trading PID: {trading_proc.pid}")
    print(f"    Log file: {trading_log}")

    # Wait 30 seconds for trading to warm up
    print("    Waiting 30s for warm-up...")
    await asyncio.sleep(30)

    # Check trading is producing activity
    print("\n[2/3] Checking trading activity...")
    import redis

    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    # Wait for trading to start generating ANY activity (signals, orders, fills, outcomes)
    max_wait = 180
    check_interval = 15
    waited = 0

    # Get initial counts of all activity types
    activity_initial = {
        "signals": len(r.keys("paper:signal:*")),
        "orders": len(r.keys("paper:order:*")),
        "fills": len(r.keys("paper:fill:*")),
        "outcomes": len(r.keys("paper:outcome:*")),
    }
    total_initial = sum(activity_initial.values())
    print(f"    Initial activity: {activity_initial} (total: {total_initial})")

    while waited < max_wait:
        await asyncio.sleep(check_interval)
        waited += check_interval

        activity_current = {
            "signals": len(r.keys("paper:signal:*")),
            "orders": len(r.keys("paper:order:*")),
            "fills": len(r.keys("paper:fill:*")),
            "outcomes": len(r.keys("paper:outcome:*")),
        }
        total_current = sum(activity_current.values())

        # Check if trading log shows signal processing
        trading_active = False
        try:
            with open(trading_log, "r") as f:
                content = f.read()
                if "Processing signal" in content or "Trade executed" in content:
                    trading_active = True
        except:
            pass

        print(
            f"    After {waited}s: signals={activity_current['signals']}, orders={activity_current['orders']}, fills={activity_current['fills']}, outcomes={activity_current['outcomes']} (trading_active={trading_active})"
        )

        if total_current > total_initial or trading_active:
            print(
                f"    ✅ Activity detected! Redis: +{total_current - total_initial} items, Trading log: active"
            )
            signals_current = activity_current["signals"]
            signals_initial = activity_initial["signals"]
            break
    else:
        print("    ❌ ERROR: No trading activity detected after 3 minutes!")
        trading_proc.terminate()
        return 1

    # NOW start the 30-minute proof loop
    print("\n[3/3] Starting 30-minute proof loop...")
    print("    This will run for 30 minutes. Trading will continue in background.")
    harness = IntegratedForensicHarness(duration_minutes=30)
    result = await harness.run_integrated_proof_loop()

    # Stop trading activity
    print("\n[4/3] Stopping trading activity...")
    trading_proc.terminate()
    try:
        trading_proc.wait(timeout=10)
    except:
        trading_proc.kill()

    # Save results
    import json

    result_data = {
        "proof_id": f"ATTEMPT3-{timestamp}",
        "gate_results": [
            {"gate": r.gate, "passed": r.passed, "evidence": r.evidence}
            for r in result.gate_results
        ],
        "all_passed": result.all_passed,
        "timestamp": timestamp,
        "trading_pid": trading_proc.pid,
        "signals_initial": signals_initial,
        "signals_final": signals_current,
        "signal_delta": signals_current - signals_initial,
    }

    result_file = output_dir / f"ATTEMPT3_result_{timestamp}.json"
    with open(result_file, "w") as f:
        json.dump(result_data, f, indent=2)

    # Print results
    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║  ATTEMPT 3 RESULTS                                                ║")
    print("╠════════════════════════════════════════════════════════════════════╣")

    for r in result.gate_results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        gate_name = r.gate[:15].ljust(15)
        print(f"║  {gate_name}: {status}                                          ║")

    overall = "✅ SUCCESS" if result.all_passed else "❌ FAILED"
    print("╠════════════════════════════════════════════════════════════════════╣")
    print(f"║  OVERALL: {overall}                                          ║")
    print(f"║  Result file: {result_file.name}                        ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    return 0 if result.all_passed else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
