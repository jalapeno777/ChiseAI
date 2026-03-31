from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "dependency_audit.py"
)
SPEC = importlib.util.spec_from_file_location("dependency_audit", MODULE_PATH)
assert SPEC and SPEC.loader
dependency_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dependency_audit
SPEC.loader.exec_module(dependency_audit)


def test_changed_files_uses_pipeline_files_when_present(monkeypatch) -> None:
    monkeypatch.setenv("CI_PIPELINE_FILES", '["docs/notes.md","scripts/ci/foo.py"]')
    monkeypatch.setenv("CI_PIPELINE_NUMBER", "3393")
    monkeypatch.setattr(
        dependency_audit,
        "_git_changed_files",
        lambda: (_ for _ in ()).throw(AssertionError("git fallback should not run")),
    )

    assert dependency_audit._changed_files() == ["docs/notes.md", "scripts/ci/foo.py"]


def test_changed_files_skips_git_fallback_in_ci_when_pipeline_files_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CI_PIPELINE_FILES", raising=False)
    monkeypatch.setenv("CI_PIPELINE_NUMBER", "3393")
    monkeypatch.setattr(
        dependency_audit,
        "_git_changed_files",
        lambda: (_ for _ in ()).throw(
            AssertionError("git fallback should not run in CI")
        ),
    )

    assert dependency_audit._changed_files() == []


def test_changed_files_uses_git_fallback_locally(monkeypatch) -> None:
    monkeypatch.delenv("CI_PIPELINE_FILES", raising=False)
    monkeypatch.delenv("CI_PIPELINE_NUMBER", raising=False)
    monkeypatch.setattr(
        dependency_audit,
        "_git_changed_files",
        lambda: ["scripts/ci/dependency_audit.py", "README.md"],
    )

    assert dependency_audit._changed_files() == [
        "scripts/ci/dependency_audit.py",
        "README.md",
    ]
