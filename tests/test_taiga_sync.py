from __future__ import annotations

from pathlib import Path

import pytest

from chiseai.taiga_sync import (
    RepoStory,
    TaigaSyncError,
    canonical_story_checksum,
    format_taiga_description,
    load_repo_sprints,
    load_repo_stories,
    resolve_taiga_status_id,
)


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_canonical_story_checksum_stable() -> None:
    s1 = RepoStory(
        id="ST-OPS-004",
        title="Taiga Sync",
        epic_id="EP-OPS-001",
        sprint_id="p0-5",
        status="planned",
        acceptance_criteria=["AC1", "AC2"],
    )
    s2 = RepoStory(
        id="ST-OPS-004",
        title="Taiga Sync",
        epic_id="EP-OPS-001",
        sprint_id="p0-5",
        status="planned",
        acceptance_criteria=["AC1", "AC2"],
    )
    assert canonical_story_checksum(s1) == canonical_story_checksum(s2)


def test_format_taiga_description_includes_acceptance_criteria() -> None:
    s = RepoStory(
        id="ST-X-001",
        title="Hello",
        epic_id=None,
        sprint_id=None,
        status="planned",
        acceptance_criteria=["A", "B"],
    )
    d = format_taiga_description(story=s)
    assert "Repo Story ID: ST-X-001" in d
    assert "- A" in d
    assert "- B" in d


def test_resolve_taiga_status_id_exact_and_contains() -> None:
    statuses = [
        {"id": 1, "name": "New"},
        {"id": 2, "name": "In progress"},
        {"id": 3, "name": "Blocked"},
        {"id": 4, "name": "Done"},
    ]
    assert resolve_taiga_status_id(statuses, "New") == 1
    assert resolve_taiga_status_id(statuses, "progress") == 2
    assert resolve_taiga_status_id(statuses, "Missing") is None


def test_load_repo_sprints_and_stories_from_yaml(tmp_path: Path) -> None:
    wf = tmp_path / "docs/bmm-workflow-status.yaml"
    vr = tmp_path / "docs/validation/validation-registry.yaml"
    _write(
        wf,
        """
metadata: {}
sprints:
  - id: p0-5
    name: Observability (Grafana-First)
    status: planned
stories:
  - id: ST-OPS-004
    title: Taiga Integration
    epic_id: EP-OPS-001
    sprint_id: p0-5
    status: planned
""".lstrip(),
    )
    _write(
        vr,
        """
metadata: {}
validations:
  - id: V-OPS-001
    story_id: ST-OPS-004
    status: planned
    acceptance_criteria:
      - AC1
      - AC2
""".lstrip(),
    )

    sprints = load_repo_sprints(wf)
    assert [s.id for s in sprints] == ["p0-5"]

    stories = load_repo_stories(workflow_status_path=wf, validation_registry_path=vr)
    assert len(stories) == 1
    assert stories[0].id == "ST-OPS-004"
    assert stories[0].acceptance_criteria == ["AC1", "AC2"]


def test_load_repo_stories_filters_deprecated(tmp_path: Path) -> None:
    wf = tmp_path / "docs/bmm-workflow-status.yaml"
    vr = tmp_path / "docs/validation/validation-registry.yaml"
    _write(
        wf,
        """
metadata: {}
sprints: []
stories:
  - id: ST-OLD-001
    title: Old
    status: deprecated
""".lstrip(),
    )
    _write(vr, "metadata: {}\nvalidations: []\n")

    stories = load_repo_stories(workflow_status_path=wf, validation_registry_path=vr)
    assert stories == []

    stories2 = load_repo_stories(
        workflow_status_path=wf, validation_registry_path=vr, include_deprecated=True
    )
    assert len(stories2) == 1
    assert stories2[0].id == "ST-OLD-001"


def test_load_repo_stories_requires_files(tmp_path: Path) -> None:
    with pytest.raises(TaigaSyncError):
        load_repo_stories(
            workflow_status_path=tmp_path / "missing.yaml",
            validation_registry_path=tmp_path / "missing2.yaml",
        )
