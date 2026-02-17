from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "ci_change_scope.py"
SPEC = importlib.util.spec_from_file_location("ci_change_scope", MODULE_PATH)
assert SPEC and SPEC.loader
ci_change_scope = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ci_change_scope
SPEC.loader.exec_module(ci_change_scope)


def test_is_docs_only_true_for_docs_and_opencode_files() -> None:
    paths = [
        "docs/tempmemories/iterlog-test.md",
        ".opencode/agent/Jarvis.md",
        "_bmad-output/implementation-artifacts/reports/test.md",
    ]
    assert ci_change_scope.is_docs_only(paths)


def test_is_docs_only_false_for_code_files() -> None:
    paths = ["scripts/ci/ci_gate.py", "docs/notes.md"]
    assert not ci_change_scope.is_docs_only(paths)


def test_changed_python_filters_existing_py_files() -> None:
    paths = ["scripts/ci/ci_gate.py", "README.md", "docs/notes.md"]
    selected = ci_change_scope.changed_python(paths)
    assert "scripts/ci/ci_gate.py" in selected
    assert "README.md" not in selected


def test_changed_files_fallback_to_show_when_no_base_ref(monkeypatch) -> None:
    def fake_run_git(*args: str) -> tuple[int, str]:
        cmd = " ".join(args)
        if cmd.startswith("rev-parse --verify"):
            return 1, ""
        if cmd == "diff --name-only HEAD~1..HEAD":
            return 1, ""
        if cmd == "show --pretty= --name-only HEAD":
            return 0, "scripts/ci/ci_change_scope.py\nREADME.md\n"
        return 1, ""

    monkeypatch.setattr(ci_change_scope, "_run_git", fake_run_git)
    monkeypatch.setattr(ci_change_scope, "_pr_changed_files_from_gitea", lambda: None)
    files = ci_change_scope.changed_files(None)
    assert files == ["scripts/ci/ci_change_scope.py", "README.md"]


def test_changed_files_prefers_pr_api_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        ci_change_scope,
        "_pr_changed_files_from_gitea",
        lambda: ["src/api/cache/__init__.py", "tests/test_api/test_cache/test_cache_manager.py"],
    )
    monkeypatch.setattr(
        ci_change_scope,
        "_run_git",
        lambda *args: (_ for _ in ()).throw(AssertionError("git fallback should not run")),
    )
    files = ci_change_scope.changed_files(None)
    assert files == [
        "src/api/cache/__init__.py",
        "tests/test_api/test_cache/test_cache_manager.py",
    ]


def test_changed_files_prefers_pipeline_env_files(monkeypatch) -> None:
    monkeypatch.setenv(
        "CI_PIPELINE_FILES",
        '["scripts/ci/ci_change_scope.py","tests/test_ci/test_ci_change_scope.py"]',
    )
    monkeypatch.setattr(
        ci_change_scope,
        "_pr_changed_files_from_gitea",
        lambda: ["should/not/be_used.py"],
    )
    monkeypatch.setattr(
        ci_change_scope,
        "_run_git",
        lambda *args: (_ for _ in ()).throw(AssertionError("git fallback should not run")),
    )
    files = ci_change_scope.changed_files(None)
    assert files == [
        "scripts/ci/ci_change_scope.py",
        "tests/test_ci/test_ci_change_scope.py",
    ]
