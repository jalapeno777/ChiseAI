#!/usr/bin/env python3
"""Scan CI outputs and produce a short markdown summary.

Primary sources:
- _bmad-output/ci/pytest-junit.xml (pytest failures)
- _bmad-output/ci/*.log (lint/security/local-ci captured logs)
- _bmad-output/ci/*.status (exit codes captured by Woodpecker steps)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import importlib.util
import sys
from pathlib import Path

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

CI_DIR = Path("_bmad-output/ci")
JUNIT_PATH = CI_DIR / "pytest-junit.xml"
MAX_FAILURES = 10
LOG_TAIL_LINES = 120


def _load_triage_parser():
    triage_path = Path(__file__).with_name("woodpecker_triage.py")
    if not triage_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("woodpecker_triage", triage_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "parse_root_causes", None)


def _parse_junit_xml(path: Path) -> ET.Element | None:
    if not path.exists():
        return None
    try:
        tree = ET.parse(path)
        return tree.getroot()
    except ET.ParseError:
        return None


def _extract_failures(root: ET.Element | None) -> list[dict]:
    failures: list[dict] = []
    if root is None:
        return failures

    for testcase in root.findall(".//testcase"):
        failure = testcase.find("failure")
        error = testcase.find("error")
        if failure is None and error is None:
            continue

        name = testcase.get("name", "unknown")
        classname = testcase.get("classname", "")

        issue = failure if failure is not None else error
        message = issue.get("message", "") if issue is not None else ""
        details = (issue.text or "").strip() if issue is not None else ""

        path_str = f"{classname}.{name}" if classname else name
        failures.append(
            {
                "path": path_str,
                "message": message,
                "details": details[:800],
            }
        )

    return failures


def _read_tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    parts = text.splitlines(True)
    return "".join(parts[-lines:])


def _collect_statuses() -> dict[str, int]:
    statuses: dict[str, int] = {}
    if not CI_DIR.exists():
        return statuses
    for p in sorted(CI_DIR.glob("*.status")):
        try:
            raw = p.read_text(encoding="utf-8").strip()
            statuses[p.stem] = int(raw)
        except Exception:  # noqa: BLE001
            statuses[p.stem] = 99
    return statuses


def _collect_logs() -> list[Path]:
    if not CI_DIR.exists():
        return []
    # Keep stable ordering: lint/security/local-ci first, then others.
    preferred = ["lint.log", "security-scan.log", "local-ci-full.log", "local-ci.log"]
    logs: list[Path] = []
    for name in preferred:
        p = CI_DIR / name
        if p.exists():
            logs.append(p)
    for p in sorted(CI_DIR.glob("*.log")):
        if p.name in preferred:
            continue
        logs.append(p)
    return logs


def build_summary() -> tuple[str, int]:
    lines: list[str] = []
    exit_code = 0

    statuses = _collect_statuses()
    if statuses:
        failing = {k: v for k, v in statuses.items() if v != 0}
        if failing:
            exit_code = 1
        lines.append("## CI Step Status")
        lines.append("")
        for k in sorted(statuses.keys()):
            v = statuses[k]
            status_txt = "OK" if v == 0 else f"FAIL ({v})"
            lines.append(f"- `{k}`: **{status_txt}**")
        lines.append("")

    root = _parse_junit_xml(JUNIT_PATH)
    failures = _extract_failures(root)
    if failures:
        exit_code = 1
    lines.append("## Pytest Failures")
    lines.append("")
    lines.append(f"**Total failures/errors:** {len(failures)}")
    lines.append("")

    if failures:
        display = failures[:MAX_FAILURES]
        lines.append(f"### Top {len(display)}")
        lines.append("")
        for i, f in enumerate(display, 1):
            lines.append(f"**{i}.** `{f['path']}`")
            lines.append("")
            if f["message"]:
                lines.append(f"> {f['message']}")
            if f["details"]:
                lines.append("```")
                lines.append(f["details"])
                lines.append("```")
            lines.append("")
        if len(failures) > MAX_FAILURES:
            lines.append(f"*... and {len(failures) - MAX_FAILURES} more*")
            lines.append("")
    else:
        lines.append("No pytest failures found (or JUnit XML missing).")
        lines.append("")

    logs = _collect_logs()
    parse_root_causes = _load_triage_parser()
    extracted_any = False
    if logs and parse_root_causes is not None:
        lines.append("## Extracted Root Causes")
        lines.append("")
        for p in logs:
            text = _read_tail(p, LOG_TAIL_LINES * 3)
            if not text.strip():
                continue
            causes = parse_root_causes(p.stem, text)
            if not causes:
                continue
            extracted_any = True
            lines.append(f"### `{p.name}`")
            lines.append("")
            for rc in causes[:8]:
                loc = ""
                if rc.file:
                    loc = f" ({rc.file}:{rc.line or 1})"
                rule = f" [{rc.rule}]" if rc.rule else ""
                test = f" test={rc.test}" if rc.test else ""
                lines.append(f"- `{rc.tool}`{rule}{test}: {rc.message}{loc}")
                lines.append(f"  - evidence: `{rc.evidence[:160]}`")
            lines.append("")
    if logs and parse_root_causes is not None and not extracted_any:
        lines.append("## Extracted Root Causes")
        lines.append("")
        lines.append("No structured root causes found from available logs.")
        lines.append("")

    if logs:
        lines.append("## Recent Log Tails")
        lines.append("")
        for p in logs:
            tail = _read_tail(p, LOG_TAIL_LINES).rstrip()
            if not tail:
                continue
            lines.append(f"### `{p.name}` (last {LOG_TAIL_LINES} lines)")
            lines.append("```")
            lines.append(tail)
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n", exit_code


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)
    summary, code = build_summary()
    print(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
