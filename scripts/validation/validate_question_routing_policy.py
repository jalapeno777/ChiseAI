#!/usr/bin/env python3
"""Validate orchestrator question-routing policy guardrails.

This validator enforces two classes of rules:
1) Governance text must explicitly define Aria-only Craig questioning.
2) BMAD wrappers must remain non-interactive in task mode.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read_text(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def check_required_substrings(rel_path: str, required: List[str]) -> List[str]:
    text = read_text(rel_path)
    errors: List[str] = []
    for needle in required:
        if needle not in text:
            errors.append(f"{rel_path}: missing required text: {needle}")
    return errors


def check_bmad_wrappers() -> List[str]:
    errors: List[str] = []
    wrappers = sorted((ROOT / ".opencode/agent").glob("bmad-agent-*.md"))
    menu_rule = "5. PRESENT the numbered menu (unless `BMAD_TASK_MODE=1` or `NO_INTERACTIVE_MENUS=1`)"
    wait_rule = "6. WAIT for user input before proceeding (unless `BMAD_TASK_MODE=1` or `NO_INTERACTIVE_MENUS=1`)"

    for wrapper in wrappers:
        text = wrapper.read_text(encoding="utf-8")
        rel = str(wrapper.relative_to(ROOT))
        if menu_rule not in text:
            errors.append(f"{rel}: missing task-mode menu bypass rule")
        if wait_rule not in text:
            errors.append(f"{rel}: missing task-mode wait bypass rule")
    return errors


def run_checks() -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    required_map = {
        "AGENTS.md": [
            "### Question Routing Authority (REQUIRED)",
            "Only Aria may ask Craig direct questions.",
        ],
        ".opencode/agent/Aria.md": [
            "## Subagent Question Ownership (required)",
            "Aria is responsible for answering any and all Jarvis/worker questions.",
        ],
        ".opencode/agent/Jarvis.md": [
            "## Question routing policy (required)",
            "Do **not** ask Craig/user direct questions; route all unresolved questions to Aria.",
            "BLOCKER_PACKET",
        ],
        ".opencode/agent/JarvisRuntime.md": [
            "## Question routing policy (required)",
            "Never ask Craig/user direct questions; route unresolved questions to Aria.",
        ],
        "_bmad/core/agents/bmad-master.md": [
            "unless `BMAD_TASK_MODE=1` or `NO_INTERACTIVE_MENUS=1`",
        ],
    }

    for rel_path, required in required_map.items():
        target = ROOT / rel_path
        if not target.exists():
            warnings.append(f"{rel_path}: file not found; skipped")
            continue
        errors.extend(check_required_substrings(rel_path, required))

    errors.extend(check_bmad_wrappers())
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate orchestrator question-routing policy")
    _ = parser.parse_args()

    errors, warnings = run_checks()

    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("QUESTION ROUTING POLICY CHECK: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("QUESTION ROUTING POLICY CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
