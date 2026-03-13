#!/usr/bin/env python3
"""Run daily autonomous cognition self-assessment cycle."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from autonomous_cognition.controller import AutonomousCognitionController
from governance.notifications.discord_notifier import DiscordNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run autonomous cognition daily self-assessment."
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default=AutonomousCognitionController.DEFAULT_ARTIFACTS_DIR,
        help="Directory for self-assessment artifacts",
    )
    parser.add_argument(
        "--notify-discord",
        action="store_true",
        help="Send completion event to Discord",
    )
    return parser.parse_args()


def main() -> int:
    """Main entrypoint."""
    args = parse_args()
    controller = AutonomousCognitionController(artifacts_dir=args.artifacts_dir)

    try:
        artifact, artifact_path = controller.run_daily_self_assessment()
        logger.info(
            "Self-assessment completed: id=%s status=%s score=%.2f path=%s",
            artifact.assessment_id,
            artifact.status,
            artifact.overall_score,
            artifact_path,
        )

        if args.notify_discord:
            notifier = DiscordNotifier()
            asyncio.run(
                notifier.notify_self_assessment(
                    artifact=artifact,
                    artifact_path=str(Path(artifact_path)),
                )
            )

        print(
            json.dumps(
                {
                    "ok": True,
                    "assessment_id": artifact.assessment_id,
                    "status": artifact.status,
                    "overall_score": artifact.overall_score,
                    "artifact_path": str(artifact_path),
                }
            )
        )
        return 0
    except Exception as e:
        logger.exception("Self-assessment run failed: %s", e)
        if args.notify_discord:
            try:
                notifier = DiscordNotifier()

                class _FailureArtifact:
                    assessment_id = "self-assessment-failed"
                    assessment_date = "unknown"
                    created_at = "unknown"
                    status = "failed"
                    overall_score = 0.0
                    findings = [f"Self-assessment failed: {e}"]
                    recommendations = [
                        "Inspect scripts/ops/run_autonomous_self_assessment.py logs"
                    ]

                asyncio.run(
                    notifier.notify_self_assessment(
                        artifact=_FailureArtifact(),
                        artifact_path=None,
                    )
                )
            except Exception as notify_error:
                logger.error(
                    "Failed to send Discord failure notification: %s", notify_error
                )
        return 1


if __name__ == "__main__":
    sys.exit(main())

