#!/usr/bin/env python3
"""Generate weekly go/no-go packet from autonomy scorecard."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate go/no-go packet")
    ap.add_argument("--scorecard", default="_bmad-output/full-pilot/scorecard.json")
    ap.add_argument("--output", default="_bmad-output/full-pilot/go-no-go-packet.json")
    args = ap.parse_args()

    score_path = Path(args.scorecard)
    if not score_path.exists():
        print(f"ERROR: scorecard missing: {score_path}")
        return 1

    score = json.loads(score_path.read_text(encoding="utf-8"))
    success_rate = float(score.get("cadence", {}).get("success_rate_percent", 0.0))
    alerts = int(score.get("alerts", {}).get("total_alerts", 0))

    if success_rate >= 95.0 and alerts <= 5:
        decision = "GO"
        rationale = "Cadence reliability and alert profile within target thresholds."
    elif success_rate >= 85.0 and alerts <= 20:
        decision = "CONDITIONAL_GO"
        rationale = "Operationally acceptable, but requires focused alert remediation."
    else:
        decision = "NO_GO"
        rationale = "Reliability/alert profile outside risk tolerance."

    packet = {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "decision": decision,
        "rationale": rationale,
        "inputs": {
            "cadence_success_rate_percent": success_rate,
            "total_alerts": alerts,
        },
        "required_actions": [
            "Review top alert contributors and assign owners.",
            "Confirm strategy autopilot approvals before next weekly cycle.",
            "Re-run full pilot E2E after remediation.",
        ],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    print(f"Go/no-go packet generated: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
