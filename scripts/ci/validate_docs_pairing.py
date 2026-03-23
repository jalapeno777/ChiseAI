#!/usr/bin/env python3
"""Validate docs governance pairing for workflow status and validation registry.

If either docs/bmm-workflow-status.yaml or docs/validation/validation-registry.yaml
changes in a PR, both must change together.
"""

from __future__ import annotations

import json
import os
import sys

WORKFLOW_FILE = "docs/bmm-workflow-status.yaml"
REGISTRY_FILE = "docs/validation/validation-registry.yaml"


def _changed_files() -> set[str]:
    env_files = os.environ.get("CI_PIPELINE_FILES", "").strip()
    if env_files:
        try:
            parsed = json.loads(env_files)
            if isinstance(parsed, list):
                return {str(x).strip() for x in parsed if str(x).strip()}
        except json.JSONDecodeError:
            pass
    return set()


def main() -> int:
    changed = _changed_files()
    workflow_changed = WORKFLOW_FILE in changed
    registry_changed = REGISTRY_FILE in changed

    if not changed:
        print("docs-pairing: no CI_PIPELINE_FILES metadata; skipping")
        return 0

    if not workflow_changed and not registry_changed:
        print("docs-pairing: no status/registry doc changes; skipping")
        return 0

    if workflow_changed and registry_changed:
        print(
            "docs-pairing: OK (workflow-status and validation-registry changed together)"
        )
        return 0

    print("docs-pairing: FAIL", file=sys.stderr)
    print(
        f"  - {WORKFLOW_FILE} changed: {workflow_changed}\n"
        f"  - {REGISTRY_FILE} changed: {registry_changed}",
        file=sys.stderr,
    )
    print(
        "  Update both files in the same PR when workflow/validation state changes.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
