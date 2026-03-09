#!/usr/bin/env python3
"""Generate Phase 4 monthly autonomy scorecard from cadence/evolution artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            continue
    return rows


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def within_window(row: dict[str, Any], since: datetime) -> bool:
    ts = parse_iso(row.get("timestamp_utc"))
    if ts is None:
        return False
    return ts >= since


def generate_scorecard(
    *,
    cadence_runs: list[dict[str, Any]],
    cadence_alerts: list[dict[str, Any]],
    pilot_events: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(str(r.get("status", "unknown")) for r in cadence_runs)
    executable_runs = (
        statuses.get("success", 0)
        + statuses.get("failed", 0)
        + statuses.get("timeout", 0)
    )
    total_runs = max(executable_runs, 1)
    success = statuses.get("success", 0)
    dry = statuses.get("dry_run", 0)
    failures = statuses.get("failed", 0) + statuses.get("timeout", 0)

    alert_types = Counter(str(a.get("alert_type", "unknown")) for a in cadence_alerts)
    event_types = Counter(str(e.get("event_type", "unknown")) for e in pilot_events)

    return {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cadence": {
            "total_runs": total_runs,
            "success_runs": success,
            "dry_runs": dry,
            "failed_runs": failures,
            "success_rate_percent": round((success / total_runs) * 100.0, 2),
            "status_counts": dict(statuses),
        },
        "alerts": {
            "total_alerts": sum(alert_types.values()),
            "by_type": dict(alert_types),
        },
        "events": {
            "total_events": sum(event_types.values()),
            "by_type": dict(event_types),
        },
        "phase4_recommendations": [
            "Increase daemon/cron frequency only after alert rate remains stable for 14 days.",
            "Promote frequently recurring event types into dedicated runbooks/skills.",
            "Prioritize automation for top missed cadence and timeout contributors.",
        ],
    }


def write_markdown(scorecard: dict[str, Any], path: Path) -> None:
    c = scorecard["cadence"]
    a = scorecard["alerts"]
    e = scorecard["events"]
    lines = [
        "# Autonomy Monthly Scorecard",
        "",
        f"- Generated: {scorecard['generated_at_utc']}",
        f"- Cadence success rate: {c['success_rate_percent']}%",
        f"- Total cadence runs: {c['total_runs']}",
        f"- Total alerts: {a['total_alerts']}",
        f"- Total pilot events: {e['total_events']}",
        "",
        "## Cadence Status Counts",
    ]
    for k, v in sorted(c["status_counts"].items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Alert Type Counts")
    for k, v in sorted(a["by_type"].items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Event Type Counts")
    for k, v in sorted(e["by_type"].items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Recommendations")
    for item in scorecard["phase4_recommendations"]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate autonomy scorecard")
    ap.add_argument("--lookback-days", type=int, default=30)
    ap.add_argument("--output-dir", default="_bmad-output/full-pilot")
    args = ap.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    since = datetime.now(UTC) - timedelta(days=max(args.lookback_days, 1))

    cadence_runs = [
        r
        for r in parse_jsonl(Path("_bmad-output/autonomy-cadence/runs.jsonl"))
        if within_window(r, since)
    ]
    cadence_alerts = [
        r
        for r in parse_jsonl(Path("_bmad-output/autonomy-cadence/alerts.jsonl"))
        if within_window(r, since)
    ]
    pilot_events = [
        r for r in parse_jsonl(output_dir / "events.jsonl") if within_window(r, since)
    ]

    scorecard = generate_scorecard(
        cadence_runs=cadence_runs,
        cadence_alerts=cadence_alerts,
        pilot_events=pilot_events,
    )
    (output_dir / "scorecard.json").write_text(
        json.dumps(scorecard, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(scorecard, output_dir / "scorecard.md")
    print(f"Scorecard generated: {output_dir / 'scorecard.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
