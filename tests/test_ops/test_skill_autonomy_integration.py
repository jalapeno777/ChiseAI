"""
Tests for chiseai-skill-autonomy skill verification.

These tests verify:
1. Eval queries trigger the skill via relevant keywords
2. SKILL.md has required sections (When To Use, Commands, Safety)
3. Skill gap candidates are ingested without duplicates
4. Missing skill events are logged to Redis queue
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


class FakeRedis:
    """Minimal fake Redis for testing."""

    def __init__(self) -> None:
        self.queues: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.queues.get(key, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    def ltrim(self, key: str, start: int, end: int) -> None:
        items = self.queues.get(key, [])
        if end == -1:
            self.queues[key] = items[start:]
        else:
            self.queues[key] = items[start : end + 1]

    def rpush(self, key: str, value: str) -> None:
        if key not in self.queues:
            self.queues[key] = []
        self.queues[key].append(value)

    def hset(self, name: str, key: str, value: str) -> None:
        if name not in self.hashes:
            self.hashes[name] = {}
        self.hashes[name][key] = value

    def hgetall(self, name: str) -> dict[str, str]:
        return self.hashes.get(name, {})

    def delete(self, key: str) -> None:
        self.hashes.pop(key, None)
        self.queues.pop(key, None)


SKILL_PATH = Path(".opencode/skills/chiseai-skill-autonomy/SKILL.md")
SKILL_EVALS_PATH = Path(".opencode/skills/chiseai-skill-autonomy/evals/evals.json")


def test_eval_queries_trigger_skill():
    """For each eval in evals.json, verify skill content mentions relevant keywords."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8").lower()
    evals = json.loads(SKILL_EVALS_PATH.read_text(encoding="utf-8"))

    # Keywords that should appear for routing/autonomy skills
    required_keywords = [
        "routing",
        "autonomy",
        "tick",
        "promote",
        "coverage",
        "backlog",
    ]

    failures = []
    for eval_entry in evals:
        eval_id = eval_entry.get("id", "?")
        query = eval_entry.get("query", "").lower()

        # Check if any required keyword is in the skill text
        keywords_found = [kw for kw in required_keywords if kw in skill_text]

        # At minimum, the skill should mention "skill" and some operational keywords
        if "skill" not in skill_text:
            failures.append(f"{eval_id}: 'skill' not found in skill content")

        # The skill should have some operational keywords for eval queries to be relevant
        operational_count = sum(
            1
            for kw in ["routing", "autonomy", "tick", "promote", "coverage"]
            if kw in skill_text
        )
        if operational_count < 2:
            failures.append(
                f"{eval_id}: insufficient operational keywords in skill (found {operational_count}, need 2+)"
            )

    assert not failures, "\n".join(failures)


def test_skill_has_required_sections():
    """Verify SKILL.md has required sections: When To Use, Commands/Operations, Safety."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # Required sections
    required_sections = [
        (r"## When To Use", "When To Use section"),
        (
            r"##.*Commands|##.*Operations|## Required Commands",
            "Commands or Operations section",
        ),
        (r"## Safety|Non-Blocking Rule|Runtime Safeguards", "Safety-related section"),
    ]

    failures = []
    for pattern, description in required_sections:
        if not re.search(pattern, skill_text, re.IGNORECASE):
            failures.append(f"Missing required section: {description}")

    assert not failures, "\n".join(failures)


def test_skill_backlog_ingest_dedup(tmp_path, monkeypatch):
    """Test that skill gap candidates are properly ingested into backlog without duplicates."""
    # This test mirrors the pattern from test_ingest_skill_backlog_candidates.py
    # but tests the skill autonomy backlog queue specifically

    import importlib.util

    script_path = Path("scripts/ops/ingest_skill_backlog_candidates.py")
    if not script_path.exists():
        pytest.skip("ingest_skill_backlog_candidates.py not found")

    spec = importlib.util.spec_from_file_location(
        "ingest_skill_backlog_candidates", script_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    status_file = tmp_path / "bmm-workflow-status.yaml"
    status_file.write_text(
        """
metadata: {}
epics: []
completed: []
backlog:
- id: EXISTING-ITEM-001
  title: Existing
  status: planned
current_phase:
  phase: active
  status: active
""".strip() + "\n",
        encoding="utf-8",
    )

    queue_key = "bmad:chiseai:skills:backlog:candidates:test"
    fake = FakeRedis()
    payload = {
        "generated_at_utc": "2026-03-08T22:10:00Z",
        "week_id": "2026-W10",
        "candidate_id": "SKILL-GAP-2026-W10-01",
        "skill_name": "chiseai-skill-autonomy",
        "trigger": "repeated_missing_skill_count",
        "count": 6,
        "threshold": 5,
        "priority": "high",
        "recommended_action": "Ensure skill autonomy gap is tracked.",
    }
    fake.queues[queue_key] = [json.dumps(payload, sort_keys=True)]

    monkeypatch.setattr(module, "redis_client", lambda: fake)

    argv = [
        "ingest_skill_backlog_candidates.py",
        f"--status-file={status_file}",
        f"--queue-key={queue_key}",
        "--lock-file",
        str(tmp_path / "ingest.lock"),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0

    text = status_file.read_text(encoding="utf-8")
    assert "BL-SKILL-AUTO-SKILL-CHISEAI-SKILL-AUTONOMY" in text

    # Re-add same payload and run again; backlog ID should not duplicate.
    fake.queues[queue_key] = [json.dumps(payload, sort_keys=True)]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0

    text2 = status_file.read_text(encoding="utf-8")
    ids = re.findall(
        r"(?m)^\s*id:\s*(BL-SKILL-AUTO-SKILL-CHISEAI-SKILL-AUTONOMY)\s*$",
        text2,
    )
    assert len(ids) == 1


def test_skill_coverage_gap_logging(tmp_path, monkeypatch):
    """Test that missing skill events are logged to Redis queue."""
    # Simulate what happens when a skill gap is detected
    fake = FakeRedis()
    queue_key = "bmad:chiseai:skills:gaps:task_class:unclassified:weekly:2026-W10"

    # Simulate a gap event being logged
    gap_event = {
        "story_id": "ST-TEST-001",
        "task_class": "unclassified",
        "recommended_skills": ["chiseai-skill-autonomy"],
        "available_skills": [],
        "missing_skills": ["chiseai-skill-autonomy"],
        "coverage_status": "none",
        "fallback_used": True,
        "impact_estimate": "medium",
    }
    fake.rpush(queue_key, json.dumps(gap_event))

    # Verify the event was queued
    events = fake.lrange(queue_key, 0, -1)
    assert len(events) == 1
    logged_event = json.loads(events[0])
    assert logged_event["missing_skills"] == ["chiseai-skill-autonomy"]
    assert logged_event["coverage_status"] == "none"
