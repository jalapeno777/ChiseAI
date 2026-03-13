"""E2E test for autonomous cognition full cycle (Phases 1-5)."""

from __future__ import annotations

from autonomous_cognition.full_cycle import AutonomousCognitionFullCycle


def test_full_cycle_executes_end_to_end() -> None:
    """Full cycle should complete and produce cycle artifact."""
    runner = AutonomousCognitionFullCycle()
    result = runner.run(notify_discord=False)
    assert result.status == "completed"
    assert result.artifact_paths.get("self_assessment")
    assert result.artifact_paths.get("cycle")
    assert result.experiments_run >= 1

