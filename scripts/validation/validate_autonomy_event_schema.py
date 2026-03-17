#!/usr/bin/env python3
"""Validate full-pilot autonomy event envelope schema."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "event_id",
    "event_type",
    "timestamp_utc",
    "producer",
    "severity",
    "payload_schema_version",
    "payload",
}
VALID_SEVERITY = {"info", "low", "medium", "high", "critical"}


def validate_event(event: dict[str, Any], idx: int) -> list[str]:
    errs: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(event.keys()))
    if missing:
        errs.append(f"event#{idx}: missing fields: {', '.join(missing)}")
    sev = str(event.get("severity", "")).strip().lower()
    if sev and sev not in VALID_SEVERITY:
        errs.append(f"event#{idx}: invalid severity {sev!r}")
    if not re.match(r"^evt-[a-f0-9-]+$", str(event.get("event_id", ""))):
        errs.append(f"event#{idx}: invalid event_id format")
    if not isinstance(event.get("payload"), dict):
        errs.append(f"event#{idx}: payload must be object")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate autonomy event schema")
    ap.add_argument(
        "--events-file",
        default="_bmad-output/full-pilot/events.jsonl",
        help="Path to events jsonl file",
    )
    args = ap.parse_args()

    path = Path(args.events_file)
    if not path.exists():
        print(f"ERROR: events file not found: {path}")
        return 1

    errors: list[str] = []
    total = 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            item = json.loads(line)
        except Exception:
            errors.append(f"event#{i}: invalid JSON")
            continue
        if not isinstance(item, dict):
            errors.append(f"event#{i}: row must be object")
            continue
        errors.extend(validate_event(item, i))

    if total == 0:
        print("ERROR: no events found")
        return 1
    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1
    print(f"OK: validated {total} event(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
