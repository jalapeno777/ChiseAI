from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ci"
    / "check_woodpecker_stuck_pipelines.py"
)
SPEC = importlib.util.spec_from_file_location("check_woodpecker_stuck_pipelines", MODULE_PATH)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


def test_pipeline_stuck_when_no_active_steps_past_threshold() -> None:
    pipeline = {
        "status": "running",
        "started": 100,
        "steps": [
            {"status": "success"},
            {"status": "failure"},
        ],
    }
    assert watchdog._pipeline_stuck(pipeline, now=2200, max_running_seconds=1800)


def test_pipeline_not_stuck_with_active_running_step() -> None:
    pipeline = {
        "status": "running",
        "started": 100,
        "steps": [
            {"status": "success"},
            {"status": "running"},
        ],
    }
    assert not watchdog._pipeline_stuck(pipeline, now=2200, max_running_seconds=1800)
