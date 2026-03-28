#!/usr/bin/env python3
"""
Validate risk_level field on INSIGHT_PACKET entries in YAML/JSON/Markdown files.

Purpose:
- Ensure every INSIGHT_PACKET contains a risk_level field.
- Validate risk_level values are one of: low, medium, high, critical.
- Support YAML, JSON, and markdown fenced-code-block sources.
- Return exit code 0 if all valid, non-zero on violations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}

REQUIRED_FIELDS = {
    "insight_packet_id",
    "story_id",
    "detected_at_utc",
    "context",
    "risk_level",
}

REQUIRED_ISSUE_FIELDS = {
    "issue",
    "impact_if_ignored",
    "suggested_improvement",
    "reason",
    "urgency",
    "confidence",
    "evidence",
}


class ValidationResult:
    """Accumulates validation errors and warnings."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.files_checked: int = 0
        self.packets_checked: int = 0

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def _is_insight_packet(data: dict[str, Any]) -> bool:
    """Heuristic: identify an INSIGHT_PACKET by required identifier fields."""
    return "insight_packet_id" in data or "story_id" in data


def _extract_packets_from_yaml_or_json(
    path: Path,
) -> list[tuple[dict[str, Any], int | None]]:
    """Extract INSIGHT_PACKET dicts from a YAML or JSON file.

    Returns list of (packet_dict, line_number_or_None).
    """
    packets: list[tuple[dict[str, Any], int | None]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return packets

    if path.suffix in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return packets
    elif path.suffix == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return packets
    else:
        return packets

    if data is None:
        return packets

    # Top-level list of packets
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and _is_insight_packet(item):
                packets.append((item, None))
        return packets

    # Top-level dict with nested structures
    if isinstance(data, dict):
        # Check if the dict itself is an INSIGHT_PACKET
        if _is_insight_packet(data):
            packets.append((data, None))
            return packets

        # Recurse into known keys
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in ("insight_packets", "insights", "issues", "packets"):
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and _is_insight_packet(item):
                            packets.append((item, None))
                elif isinstance(value, dict) and _is_insight_packet(value):
                    packets.append((value, None))

    return packets


def _extract_packets_from_markdown(path: Path) -> list[tuple[dict[str, Any], int]]:
    """Extract INSIGHT_PACKET dicts from markdown fenced code blocks.

    Returns list of (packet_dict, approximate_line_number).
    """
    packets: list[tuple[dict[str, Any], int]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return packets

    lines = raw.splitlines()
    block_pattern = re.compile(r"^```(?:yaml|yml|json)\s*$", re.IGNORECASE)
    end_pattern = re.compile(r"^```\s*$")
    tag_pattern = re.compile(r"(?im)^\s*(?:INSIGHT_PACKET|insight_packet_id)\b")

    i = 0
    while i < len(lines):
        m = block_pattern.match(lines[i])
        if m:
            block_start = i + 1
            block_lines: list[str] = []
            j = block_start
            while j < len(lines) and not end_pattern.match(lines[j]):
                block_lines.append(lines[j])
                j += 1
            block_text = "\n".join(block_lines)

            # Check if this block looks like an INSIGHT_PACKET
            if tag_pattern.search(block_text):
                try:
                    parsed = yaml.safe_load(block_text)
                except yaml.YAMLError:
                    i = j + 1
                    continue
                if isinstance(parsed, dict) and _is_insight_packet(parsed):
                    packets.append((parsed, block_start))

            i = j + 1
        else:
            i += 1

    return packets


def _validate_packet(
    packet: dict[str, Any],
    path: Path,
    index: int,
    line: int | None,
    result: ValidationResult,
) -> None:
    """Validate a single INSIGHT_PACKET dict."""
    loc = f"{path}"
    if line is not None:
        loc += f":{line}"
    if index > 0:
        loc += f" [packet#{index}]"

    # Check for insight_packet_id for identification
    packet_id = packet.get("insight_packet_id", "<unknown>")
    loc_with_id = f"{loc} (id={packet_id})"

    # Check required top-level fields
    for field in REQUIRED_FIELDS:
        if field not in packet:
            result.err(f"{loc_with_id}: missing required field '{field}'")

    # Validate risk_level value
    risk = packet.get("risk_level")
    if risk is not None:
        if not isinstance(risk, str):
            result.err(
                f"{loc_with_id}: risk_level must be a string, got {type(risk).__name__}"
            )
        elif risk.lower() not in VALID_RISK_LEVELS:
            result.err(
                f"{loc_with_id}: invalid risk_level={risk!r}, "
                f"expected one of {sorted(VALID_RISK_LEVELS)}"
            )

    # Check issues list for risk_level in each issue
    issues = packet.get("issues", [])
    if isinstance(issues, list):
        for idx, issue in enumerate(issues):
            if not isinstance(issue, dict):
                continue
            issue_loc = f"{loc_with_id}.issues[{idx}]"
            for field in REQUIRED_ISSUE_FIELDS:
                if field not in issue:
                    result.warn(f"{issue_loc}: missing issue field '{field}'")
            # Each issue can also have risk_level
            issue_risk = issue.get("risk_level")
            if issue_risk is not None:
                if not isinstance(issue_risk, str):
                    result.err(
                        f"{issue_loc}: risk_level must be a string, "
                        f"got {type(issue_risk).__name__}"
                    )
                elif issue_risk.lower() not in VALID_RISK_LEVELS:
                    result.err(
                        f"{issue_loc}: invalid risk_level={issue_risk!r}, "
                        f"expected one of {sorted(VALID_RISK_LEVELS)}"
                    )


def _validate_file(path: Path, result: ValidationResult) -> None:
    """Validate all INSIGHT_PACKETs in a single file."""
    suffix = path.suffix.lower()

    if suffix in (".yaml", ".yml", ".json"):
        packets = _extract_packets_from_yaml_or_json(path)
    elif suffix == ".md":
        packets = _extract_packets_from_markdown(path)
    else:
        result.warn(f"{path}: unsupported file format '{suffix}', skipping")
        return

    if not packets:
        return

    result.files_checked += 1
    for idx, (packet, line) in enumerate(packets):
        result.packets_checked += 1
        _validate_packet(packet, path, idx, line, result)


def _resolve_paths(targets: list[str]) -> list[Path]:
    """Resolve glob patterns and individual file paths."""
    paths: list[Path] = []
    for target in targets:
        p = Path(target)
        if p.is_dir():
            paths.extend(
                f
                for f in sorted(p.rglob("*"))
                if f.is_file() and f.suffix.lower() in (".yaml", ".yml", ".json", ".md")
            )
        elif "*" in target or "?" in target:
            parent = Path(target).parent if Path(target).parent.exists() else Path(".")
            pattern = Path(target).name
            for f in sorted(parent.glob(pattern)):
                if f.is_file():
                    paths.append(f)
        elif p.exists():
            paths.append(p)
        else:
            print(f"WARNING: path not found: {target}", file=sys.stderr)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate risk_level on INSIGHT_PACKET entries.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=["docs/"],
        help="Files or directories to validate (default: docs/)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show per-file details even when valid",
    )
    args = parser.parse_args()

    paths = _resolve_paths(args.targets)
    if not paths:
        print("No files to validate.", file=sys.stderr)
        return 1

    result = ValidationResult()
    for path in paths:
        _validate_file(path, result)

    # Print summary
    print(f"Checked {result.files_checked} file(s), {result.packets_checked} packet(s)")

    for w in result.warnings:
        print(w, file=sys.stderr)
    for e in result.errors:
        print(e, file=sys.stderr)

    if args.verbose and result.ok:
        print("All INSIGHT_PACKETs have valid risk_level fields.")

    if not result.ok:
        print(
            f"\nFAIL: {len(result.errors)} error(s), {len(result.warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
