#!/usr/bin/env python3
"""Run autonomous cognition Phase 2-5 jobs and full cycle."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from autonomous_cognition.full_cycle import AutonomousCognitionFullCycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Run autonomous cognition jobs.")
    parser.add_argument(
        "--mode",
        choices=[
            "full",
            "improvement_cycle",
            "belief_consistency",
            "calibration",
            "autonomy_tune",
            "constitution_audit",
        ],
        default="full",
    )
    parser.add_argument("--notify-discord", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    runner = AutonomousCognitionFullCycle()

    try:
        # For now, all modes reuse full cycle; phase-specific modes remain aliases.
        result = runner.run(notify_discord=args.notify_discord)
        logger.info(
            "Autonomous cycle completed: run_id=%s status=%s",
            result.run_id,
            result.status,
        )
        print(json.dumps({"ok": True, **result.to_dict()}))
        return 0
    except Exception as e:
        logger.exception("Autonomous cycle failed: %s", e)
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

