#!/usr/bin/env python3
"""Execute 30-minute forensic proof loop with full evidence collection."""

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Add paths
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from validation.forensic_harness import IntegratedForensicHarness


class EvidenceBundleSaver:
    """Helper to save evidence bundle with proper formatting."""

    def __init__(self, bundle):
        self.bundle = bundle

    def save(self, path):
        """Save bundle to JSON file."""
        with open(path, "w") as f:
            json.dump(self.bundle.to_dict(), f, indent=2, default=str)


async def main():
    proof_id = (
        f"FORENSIC-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    )
    output_dir = Path("_bmad-output/forensic-evidence")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"FORENSIC PROOF LOOP - Execution ID: {proof_id}")
    print("=" * 70)
    print(f"Start Time: {datetime.now(UTC).isoformat()}")
    print(f"Duration: 30 minutes")
    print(f"Snapshots: T0, T5, T10, T15, T20, T25, T30")
    print("=" * 70)

    harness = IntegratedForensicHarness(duration_minutes=30)

    try:
        result = await harness.run_integrated_proof_loop()

        # Generate evidence bundle
        bundle = harness.generate_bundle()
        bundle_path = output_dir / f"evidence-bundle-{proof_id}.json"

        # Save bundle using helper
        saver = EvidenceBundleSaver(bundle)
        saver.save(bundle_path)

        # Generate markdown report
        report_path = output_dir / f"forensic-report-{proof_id}.md"
        generate_markdown_report(result, bundle, report_path, proof_id)

        # Print summary
        print("\n" + "=" * 70)
        print("FORENSIC VALIDATION COMPLETE")
        print("=" * 70)

        for gate_name, gate_result in result.gate_results.items():
            status = "✅ PASS" if gate_result.status.value == "PASS" else "❌ FAIL"
            print(f"{gate_result.gate}: {status}")
            if gate_result.artifacts_missing:
                print(f"  Missing: {gate_result.artifacts_missing}")
            if gate_result.validation_errors:
                print(f"  Errors: {gate_result.validation_errors}")

        overall = "✅ SUCCESS" if result.overall_status.value == "PASS" else "❌ FAILED"
        print(f"\nOverall: {overall}")
        print(f"\nEvidence Bundle: {bundle_path}")
        print(f"Report: {report_path}")
        print("=" * 70)

        return 0 if result.overall_status.value == "PASS" else 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 2
    finally:
        # Clean up resources
        try:
            await harness.close()
        except Exception:
            pass


def generate_markdown_report(result, bundle, path, proof_id):
    """Generate markdown report."""
    with open(path, "w") as f:
        f.write("# FORENSIC EVIDENCE BUNDLE\n\n")
        f.write(f"**Execution ID**: {proof_id}\n")
        f.write(f"**Start Time**: {result.start_time}\n")
        f.write(f"**End Time**: {result.end_time}\n")
        f.write(f"**Duration**: 30 minutes\n")
        f.write(f"**Executor**: Merlin\n")
        f.write(f"**Bundle Hash**: {bundle.bundle_hash}\n\n")

        f.write("## G1-G8 PASS/FAIL Summary\n\n")
        f.write("| Gate | Status | Artifacts Found | Missing | Errors |\n")
        f.write("|------|--------|-----------------|---------|--------|\n")

        for gate_name, gate_result in result.gate_results.items():
            status = "✅ PASS" if gate_result.status.value == "PASS" else "❌ FAIL"
            found = (
                ", ".join(gate_result.artifacts_found)
                if gate_result.artifacts_found
                else "None"
            )
            missing = (
                ", ".join(gate_result.artifacts_missing)
                if gate_result.artifacts_missing
                else "None"
            )
            errors = (
                "; ".join(gate_result.validation_errors[:2])
                if gate_result.validation_errors
                else "None"
            )
            f.write(
                f"| {gate_result.gate} | {status} | {found} | {missing} | {errors} |\n"
            )

        overall = "✅ SUCCESS" if result.overall_status.value == "PASS" else "❌ FAILED"
        f.write(f"\n**Final Verdict**: {overall}\n\n")

        f.write("## Snapshots Captured\n\n")
        f.write("| Label | Timestamp | Artifacts |\n")
        f.write("|-------|-----------|-----------|\n")
        for snapshot in result.snapshots:
            art_count = len(snapshot.artifacts)
            f.write(f"| {snapshot.label} | {snapshot.timestamp_utc} | {art_count} |\n")

        f.write("\n## Evidence Schema Compliance\n\n")
        f.write("Each gate requires:\n")
        f.write("- **command**: What was executed\n")
        f.write("- **exit_code**: 0 for success, non-zero for failure\n")
        f.write("- **timestamp_utc**: ISO format UTC timestamp\n")
        f.write("- **key_output_snippet**: Relevant output (secrets redacted)\n")
        f.write("- **artifact_or_log_path**: Path to full evidence\n\n")

        f.write("## Immutable Bundle\n\n")
        f.write(f"- **Bundle Path**: `{path.parent}/evidence-bundle-{proof_id}.json`\n")
        f.write(f"- **SHA-256 Hash**: `{bundle.bundle_hash}`\n")
        f.write(f"- **Created At**: {bundle.created_at}\n\n")

        f.write("---\n\n")
        f.write("*This evidence bundle was generated by the Forensic Proof Loop.*\n")
        f.write("*All timestamps are in UTC.*\n")

    return path


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
