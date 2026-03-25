#!/usr/bin/env python3
"""Resolve AI cognition roadmap stories to ticket artifacts and memory keys."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TICKETS_ROOT = REPO_ROOT / "docs/roadmaps/ai-cognition-evolution/tickets"
EPIC_ID = "EP-AI-COG-001"
PRIMARY_REDIS_KEY = "roadmap:ai_cognition_evolution:2026-03-25"
FIRST_SPRINT = ["ST-AI-COG-001", "ST-AI-COG-010", "ST-AI-COG-005"]
STORY_TO_TICKET = {
    "ST-AI-COG-001": "ST-AI-COG-001-Strategy-Substrate.md",
    "ST-AI-COG-002": "ST-AI-COG-002-NeuroSymbolic-Shadow-Integration.md",
    "ST-AI-COG-003": "ST-AI-COG-003-NeuroSymbolic-Canary-Full-Activation.md",
    "ST-AI-COG-004": "ST-AI-COG-004-Belief-Graph-Revision-Pipeline.md",
    "ST-AI-COG-005": "ST-AI-COG-005-Memory-Retrieval-Hardening.md",
    "ST-AI-COG-006": "ST-AI-COG-006-Verifier-Driven-Reasoning.md",
    "ST-AI-COG-007": "ST-AI-COG-007-World-Regime-Model.md",
    "ST-AI-COG-008": "ST-AI-COG-008-Autonomous-Experimentation-Promotion.md",
    "ST-AI-COG-009": "ST-AI-COG-009-Soul-Objective-Governance-Hardening.md",
    "ST-AI-COG-010": "ST-AI-COG-010-Telemetry-Evals-Decision-Scorecards.md",
    "ST-AI-COG-011": "ST-AI-COG-011-Testing-Chaos-Regression-Harness.md",
    "ST-AI-COG-012": "ST-AI-COG-012-Research-Acceleration-Program.md",
}


def _payload(story_id: str) -> dict[str, object]:
    ticket = TICKETS_ROOT / STORY_TO_TICKET[story_id]
    return {
        "story_id": story_id,
        "epic_id": EPIC_ID,
        "ticket_path": str(ticket.relative_to(REPO_ROOT)),
        "ticket_exists": ticket.exists(),
        "redis_alias_key": f"roadmap:story:{story_id}",
        "redis_primary_key": PRIMARY_REDIS_KEY,
        "first_sprint": story_id in FIRST_SPRINT,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story-id", default="")
    parser.add_argument("--first-sprint", action="store_true")
    args = parser.parse_args()

    if args.first_sprint:
        print(
            json.dumps(
                {
                    "epic_id": EPIC_ID,
                    "stories": [_payload(story_id) for story_id in FIRST_SPRINT],
                },
                indent=2,
            )
        )
        return 0

    story_id = args.story_id.strip().upper()
    if story_id not in STORY_TO_TICKET:
        valid = ", ".join(sorted(STORY_TO_TICKET))
        raise SystemExit(f"Unknown story id '{story_id}'. Valid values: {valid}")
    print(json.dumps(_payload(story_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
