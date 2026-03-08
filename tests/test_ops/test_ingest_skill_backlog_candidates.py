from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml


class FakeRedis:
    def __init__(self) -> None:
        self.queues: dict[str, list[str]] = {}

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


def _load_module():
    path = Path("scripts/ops/ingest_skill_backlog_candidates.py")
    spec = importlib.util.spec_from_file_location("ingest_skill_backlog_candidates", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ingest_dedup_and_yaml_safety(tmp_path: Path, monkeypatch):
    module = _load_module()

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
""".strip()
        + "\n",
        encoding="utf-8",
    )

    queue_key = "bmad:chiseai:skills:backlog:candidates:test"
    fake = FakeRedis()
    payload = {
        "generated_at_utc": "2026-03-08T22:10:00Z",
        "week_id": "2026-W10",
        "candidate_id": "SKILL-GAP-2026-W10-01",
        "skill_name": "my-new-skill",
        "trigger": "repeated_missing_skill_count",
        "count": 6,
        "threshold": 5,
        "priority": "high",
        "recommended_action": "Create or import skill my-new-skill.",
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
    assert "BL-SKILL-AUTO-SKILL-MY-NEW-SKILL" in text
    assert text.index("BL-SKILL-AUTO-SKILL-MY-NEW-SKILL") < text.index("current_phase:")

    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)

    # Re-add same payload and run again; backlog ID should not duplicate.
    fake.queues[queue_key] = [json.dumps(payload, sort_keys=True)]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0

    text2 = status_file.read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^\s*id:\s*(BL-SKILL-AUTO-SKILL-MY-NEW-SKILL)\s*$", text2)
    assert len(ids) == 1
