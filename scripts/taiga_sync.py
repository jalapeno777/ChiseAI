#!/usr/bin/env python3
"""
Taiga <-> Repo sync tooling.

Default behavior is safe: dry-run only. Use --apply to write changes to Taiga.

Repo canonical fields (we push to Taiga):
- Story ID, title, status, acceptance criteria (from validation registry),
  epic/sprint mapping.

Taiga canonical fields (we do not push to repo here):
- Assignees, story points, tags, comments. (See docs/taiga-sync.md.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from chiseai.taiga_sync import (  # noqa: E402
    TaigaConfig,
    TaigaSyncError,
    plan_and_sync_repo_to_taiga,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Sync ChiseAI repo stories to Taiga")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to Taiga (default: dry-run only)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite Taiga repo-canonical fields even if Taiga changed "
            "since last sync"
        ),
    )
    p.add_argument(
        "--include-deprecated",
        action="store_true",
        help="Include deprecated sprints/stories (default: ignore deprecated)",
    )
    p.add_argument(
        "--validate",
        action="store_true",
        help=(
            "Validate Taiga configuration and connectivity "
            "(fails fast on missing env vars)"
        ),
    )
    p.add_argument(
        "--workflow-status",
        default="docs/bmm-workflow-status.yaml",
        help="Path to workflow status yaml",
    )
    p.add_argument(
        "--validation-registry",
        default="docs/validation/validation-registry.yaml",
        help="Path to validation registry yaml",
    )
    p.add_argument(
        "--state",
        default="docs/taiga/sync-state.yaml",
        help="Path to Taiga sync state yaml",
    )
    args = p.parse_args()

    try:
        cfg = TaigaConfig.from_env()
        if args.validate:
            cfg.validate()
            # Connectivity check: resolves project and required userstory statuses.
            actions = plan_and_sync_repo_to_taiga(
                cfg=cfg,
                workflow_status_path=Path(args.workflow_status),
                validation_registry_path=Path(args.validation_registry),
                state_path=Path(args.state),
                apply=False,
                force=False,
                include_deprecated=args.include_deprecated,
            )
            # We don't care about actions here; only that planning didn't error.
            print(f"✅ Taiga sync validate OK ({len(actions)} planned actions)")
            return 0

        actions = plan_and_sync_repo_to_taiga(
            cfg=cfg,
            workflow_status_path=Path(args.workflow_status),
            validation_registry_path=Path(args.validation_registry),
            state_path=Path(args.state),
            apply=bool(args.apply),
            force=bool(args.force),
            include_deprecated=bool(args.include_deprecated),
        )
    except TaigaSyncError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not actions:
        print("No changes needed.")
        return 0

    for a in actions:
        sid = a.story_id or "-"
        print(f"{a.kind}\t{sid}\t{a.detail}")

    if not args.apply:
        print("\n(dry-run) Re-run with --apply to create/update items in Taiga.")
    else:
        print("\nApplied changes to Taiga and updated sync state (if applicable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
