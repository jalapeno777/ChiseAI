#!/usr/bin/env python3
"""
Forensic Proof Loop Runner - PARTY-MODE EXECUTION

This script executes the strict 30-minute proof loop with integrated collectors.
Execution ID will be generated and all evidence will be captured.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
import json

# Add paths for imports
sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")
sys.path.insert(0, "/home/tacopants/projects/ChiseAI/scripts")

# Verify environment variables
required_env = ["DISCORD_BOT_TOKEN", "INFLUXDB_TOKEN", "INFLUXDB_ORG", "INFLUXDB_URL"]

print("=" * 70)
print("PARTY-MODE FORENSIC PROOF LOOP EXECUTION")
print("=" * 70)
print(f"Start Time (UTC): {datetime.now(timezone.utc).isoformat()}")
print(f"Executor: Merlin")
print(f"Story ID: PARTY-FORENSIC-009")
print("")

# Check environment
env_ok = True
for env_var in required_env:
    value = os.getenv(env_var)
    status = "✅ Present" if value else "❌ MISSING"
    print(f"{env_var}: {status}")
    if not value:
        env_ok = False

if not env_ok:
    print("\n❌ CRITICAL: Missing required environment variables!")
    sys.exit(1)

print("\n✅ Environment validated")
print("🔄 Initializing forensic harness...")

# Import the harness
from scripts.validation.forensic_harness import IntegratedForensicHarness


async def main():
    """Execute the 30-minute proof loop."""
    try:
        # Initialize harness
        harness = IntegratedForensicHarness(duration_minutes=30)

        print("✅ Harness initialized")
        print(f"⏱️  Duration: 30 minutes")
        print(f"📸 Snapshots: Every 5 minutes (T0, T5, T10, T15, T20, T25, T30)")
        print(f"🎯 Gates: G1-G8")
        print("")
        print("=" * 70)
        print("BEGINNING PROOF LOOP - DO NOT INTERRUPT")
        print("=" * 70)
        print("")

        # Run the proof loop
        result = await harness.run_integrated_proof_loop()

        print("\n" + "=" * 70)
        print("PROOF LOOP COMPLETE")
        print("=" * 70)

        # Print results
        print(f"\nExecution ID: {result.proof_id}")
        print(f"Start Time: {result.start_time}")
        print(f"End Time: {result.end_time}")
        print(f"Duration: 30 minutes")
        print(f"Snapshots: {len(result.snapshots)}")
        print("")
        print("-" * 70)
        print("GATE RESULTS:")
        print("-" * 70)

        for gate, gate_result in result.gate_results.items():
            status_icon = "✅ PASS" if gate_result.status.value == "PASS" else "❌ FAIL"
            print(f"{gate}: {status_icon}")
            if gate_result.artifacts_missing:
                print(f"  Missing artifacts: {gate_result.artifacts_missing}")
            if gate_result.validation_errors:
                print(f"  Validation errors: {gate_result.validation_errors}")

        overall_status = (
            "✅ SUCCESS" if result.overall_status.value == "PASS" else "❌ FAILED"
        )
        print("")
        print("-" * 70)
        print(f"OVERALL STATUS: {overall_status}")
        print("-" * 70)

        # Generate evidence bundle
        print("\n🔄 Generating evidence bundle...")
        bundle = harness.generate_bundle()

        # Save bundle to file
        output_dir = "/home/tacopants/projects/ChiseAI/_bmad-output/forensic-evidence"
        bundle_path = f"{output_dir}/evidence-bundle-{result.proof_id}.json"

        with open(bundle_path, "w") as f:
            json.dump(bundle.to_dict(), f, indent=2, default=str)

        print(f"✅ Evidence bundle saved: {bundle_path}")
        print(f"Bundle Hash: {bundle.bundle_hash}")

        # Generate markdown report
        report_path = f"{output_dir}/forensic-report-{result.proof_id}.md"

        with open(report_path, "w") as f:
            f.write(f"# PARTY-MODE FORENSIC EVIDENCE BUNDLE\n\n")
            f.write(f"**Execution ID**: {result.proof_id}\n")
            f.write(f"**Start Time**: {result.start_time}\n")
            f.write(f"**End Time**: {result.end_time}\n")
            f.write(f"**Duration**: 30 minutes\n")
            f.write(f"**Executor**: Merlin\n")
            f.write(f"**Story ID**: PARTY-FORENSIC-009\n\n")

            f.write("## G1-G8 PASS/FAIL Summary\n\n")
            f.write("| Gate | Status | Evidence |\n")
            f.write("|------|--------|----------|\n")
            for gate, gate_result in result.gate_results.items():
                status = "PASS" if gate_result.status.value == "PASS" else "FAIL"
                evidence = (
                    "All artifacts present"
                    if not gate_result.artifacts_missing
                    else f"Missing: {', '.join(gate_result.artifacts_missing)}"
                )
                f.write(f"| {gate} | {status} | {evidence} |\n")

            f.write("\n## Detailed Evidence\n\n")
            for gate, gate_result in result.gate_results.items():
                f.write(f"### {gate} - Evidence\n")
                f.write(f"- Status: {gate_result.status.value}\n")
                f.write(f"- Evaluated at: {gate_result.evaluated_at}\n")
                f.write(f"- Artifacts found: {gate_result.artifacts_found}\n")
                if gate_result.artifacts_missing:
                    f.write(f"- Artifacts missing: {gate_result.artifacts_missing}\n")
                if gate_result.validation_errors:
                    f.write(f"- Validation errors: {gate_result.validation_errors}\n")
                f.write("\n")

            f.write("## Snapshots\n\n")
            f.write("| Time | Artifacts Captured |\n")
            f.write("|------|-------------------|\n")
            for snapshot in result.snapshots:
                artifact_count = len(snapshot.artifacts)
                f.write(f"| {snapshot.label} | {artifact_count} |\n")

            f.write("\n## Final Verdict\n\n")
            verdict = (
                "SUCCESS"
                if result.overall_status.value == "PASS"
                else "BLOCKED_AFTER_5"
            )
            f.write(f"**VERDICT**: {verdict}\n\n")

            f.write("**Evidence Paths**:\n")
            f.write(f"- JSON Bundle: {bundle_path}\n")
            f.write(f"- This Report: {report_path}\n")

        print(f"✅ Markdown report saved: {report_path}")

        # Return exit code based on result
        return 0 if result.overall_status.value == "PASS" else 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
