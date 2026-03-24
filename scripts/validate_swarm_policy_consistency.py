#!/usr/bin/env python3
"""Validate swarm governance policy consistency across AGENTS and agent files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate() -> list[str]:
    errors: list[str] = []

    agents_md = REPO_ROOT / "AGENTS.md"
    jarvis_md = REPO_ROOT / ".opencode/agent/Jarvis.md"
    jarvis_runtime_md = REPO_ROOT / ".opencode/agent/JarvisRuntime.md"
    aria_md = REPO_ROOT / ".opencode/agent/Aria.md"
    aria_runtime_md = REPO_ROOT / ".opencode/agent/AriaRuntime.md"
    quickdev_md = REPO_ROOT / ".opencode/agent/Quickdev.md"
    dev_md = REPO_ROOT / ".opencode/agent/Dev.md"
    senior_md = REPO_ROOT / ".opencode/agent/SeniorDev.md"
    merlin_md = REPO_ROOT / ".opencode/agent/Merlin.md"
    critic_md = REPO_ROOT / ".opencode/agent/Critic.md"
    quickdev_fast_md = REPO_ROOT / ".opencode/agent/QuickdevFast.md"
    juniordev_md = REPO_ROOT / ".opencode/agent/Juniordev.md"
    readme_md = REPO_ROOT / ".opencode/agent/README.md"
    lessons_md = REPO_ROOT / "docs/tempmemories/lessons.md"

    all_policy_files = [
        agents_md,
        jarvis_md,
        jarvis_runtime_md,
        aria_md,
        aria_runtime_md,
        merlin_md,
        readme_md,
    ]

    # 1) Legacy 5-attempt escalation phrases must be removed.
    legacy_patterns = [
        r"\b5-attempt escalation\b",
        r"\breaches 5 attempts\b",
        r"\bfails 5 times\b",
        r"\b5 attempts on same blocker\b",
        r"\bunresolved after 5 attempts\b",
    ]
    for path in all_policy_files:
        text = _read_text(path)
        for pattern in legacy_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                errors.append(f"{path}: legacy escalation phrase matches /{pattern}/")

    # 2) Canonical escalation ladder must be explicitly present.
    agents_text = _read_text(agents_md)
    for required in (
        "`quickdev`: max 2 passes",
        "`dev`: max 2 passes",
        "`senior-dev`: max 2 passes",
        "`merlin`: max 3 passes",
    ):
        _check(
            required in agents_text,
            f"{agents_md}: missing escalation requirement {required}",
            errors,
        )

    # 3) Plan gate requirements.
    aria_text = _read_text(aria_md)
    aria_runtime_text = _read_text(aria_runtime_md)
    jarvis_text = _read_text(jarvis_md)
    jarvis_runtime_text = _read_text(jarvis_runtime_md)
    _check(
        "PLAN_APPROVED=true" in aria_text,
        f"{aria_md}: missing PLAN_APPROVED=true gate",
        errors,
    )
    _check(
        "PLAN_APPROVED=true" in aria_runtime_text,
        f"{aria_runtime_md}: missing PLAN_APPROVED=true gate",
        errors,
    )
    _check(
        "PLAN_APPROVED=true" in jarvis_text,
        f"{jarvis_md}: missing PLAN_APPROVED=true gate",
        errors,
    )
    _check(
        "PLAN_APPROVED=true" in jarvis_runtime_text,
        f"{jarvis_runtime_md}: missing PLAN_APPROVED=true gate",
        errors,
    )

    # 4) Routing defaults: quickdev-fast should not be default route.
    _check(
        "Use the `quickdev-fast` agent for trivial 1SP" not in jarvis_text,
        f"{jarvis_md}: quickdev-fast still present in default routing",
        errors,
    )
    _check(
        "`quickdev-fast`:" not in jarvis_runtime_text,
        f"{jarvis_runtime_md}: quickdev-fast still present in routing defaults",
        errors,
    )

    # 5) Worker pass limits.
    _check(
        "Maximum 2 passes" in _read_text(quickdev_md),
        f"{quickdev_md}: missing max 2 pass rule",
        errors,
    )
    _check(
        "Maximum 2 passes" in _read_text(dev_md),
        f"{dev_md}: missing max 2 pass rule",
        errors,
    )
    _check(
        "Maximum 2 passes" in _read_text(senior_md),
        f"{senior_md}: missing max 2 pass rule",
        errors,
    )
    _check(
        "Maximum 3 passes" in _read_text(merlin_md),
        f"{merlin_md}: missing max 3 pass rule",
        errors,
    )

    # 6) Critic task-level output requirements.
    critic_text = _read_text(critic_md)
    for required in ("task_id", "result`: PASS|FAIL", "evidence_ref"):
        _check(
            required in critic_text,
            f"{critic_md}: missing critic output field {required}",
            errors,
        )

    # 7) Lessons loop presence.
    lessons_text = _read_text(lessons_md)
    _check(lessons_text != "", f"{lessons_md}: missing lessons file", errors)
    _check(
        "Rule Template" in lessons_text,
        f"{lessons_md}: missing Rule Template section",
        errors,
    )

    # 8) Soft deprecation markers.
    _check(
        "DEPRECATED" in _read_text(quickdev_fast_md),
        f"{quickdev_fast_md}: missing DEPRECATED marker",
        errors,
    )
    _check(
        "DEPRECATED" in _read_text(juniordev_md),
        f"{juniordev_md}: missing DEPRECATED marker",
        errors,
    )
    _check(
        "Fast-Agent Deprecation Status" in _read_text(readme_md),
        f"{readme_md}: missing fast-agent deprecation status section",
        errors,
    )

    # 9) Lightweight escalation path simulation check.
    next_owner = {
        "quickdev": "dev",
        "dev": "senior-dev",
        "senior-dev": "merlin",
        "merlin": "aria",
    }
    _check(
        next_owner["quickdev"] == "dev"
        and next_owner["dev"] == "senior-dev"
        and next_owner["senior-dev"] == "merlin"
        and next_owner["merlin"] == "aria",
        "Escalation simulation failed",
        errors,
    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on validation failures (default behavior)",
    )
    _ = parser.parse_args()

    errors = validate()
    if errors:
        print("SWARM POLICY CONSISTENCY: FAIL")
        for err in errors:
            print(f"- {err}")
        return 1

    print("SWARM POLICY CONSISTENCY: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
