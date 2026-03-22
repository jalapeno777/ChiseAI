from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from subprocess import CompletedProcess

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "ci_gate.py"
SPEC = importlib.util.spec_from_file_location("ci_gate", MODULE_PATH)
assert SPEC and SPEC.loader
ci_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ci_gate
SPEC.loader.exec_module(ci_gate)


def test_print_exact_root_causes_includes_required_fields(
    tmp_path: Path, capsys
) -> None:
    root_json = tmp_path / "root-cause.json"
    root_json.write_text(
        (
            '[{"tool":"ruff","message":"undefined name","file":"src/x.py",'
            '"line":10,"rule":"F821","test":"tests/test_x.py::test_y"}]'
        ),
        encoding="utf-8",
    )

    ci_gate._print_exact_root_causes(root_json)

    err = capsys.readouterr().err
    assert "tool=ruff" in err
    assert "file=src/x.py:10" in err
    assert "rule=F821" in err
    assert "test=tests/test_x.py::test_y" in err


def test_run_root_cause_bundle_uses_pipeline_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    ci_dir = tmp_path / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "7").mkdir(parents=True)
    (ci_dir / "7" / "root-cause.json").write_text("[]", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, check):  # noqa: ANN001, ANN201
        calls.append(cmd)
        return CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(ci_gate.subprocess, "run", fake_run)
    path = ci_gate._run_root_cause_bundle(ci_dir, {"CI_PIPELINE_NUMBER": "7"})

    assert path == ci_dir / "7" / "root-cause.json"
    assert calls


def test_fast_required_includes_status_write_gate() -> None:
    """Verify that FAST_REQUIRED list contains status-write-gate.status."""
    assert "status-write-gate.status" in ci_gate.FAST_REQUIRED


def test_ci_gate_fails_when_status_write_gate_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """Test that ci_gate fails (returns non-zero) when status-write-gate.status contains '1'."""
    ci_dir = tmp_path / "ci"
    ci_dir.mkdir(parents=True)

    # Create all required status files with success (0) except status-write-gate
    for status_file in ci_gate.FAST_REQUIRED:
        if status_file == "status-write-gate.status":
            (ci_dir / status_file).write_text("1", encoding="utf-8")  # Failed
        else:
            (ci_dir / status_file).write_text("0", encoding="utf-8")  # Success

    # Monkeypatch CI_DIR to use our temp directory
    monkeypatch.setattr(ci_gate, "CI_DIR", ci_dir)

    # Mock subprocess.run to avoid actual execution
    monkeypatch.setattr(
        ci_gate.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args, 0, stdout="", stderr=""),
    )

    # Run ci_gate
    result = ci_gate.main()

    # Should return non-zero (failure) because status-write-gate.status is 1
    assert result != 0, "ci_gate should fail when status-write-gate.status is 1"


def test_ci_gate_passes_when_all_statuses_zero(tmp_path: Path, monkeypatch) -> None:
    """Test that ci_gate passes (returns zero) when all fast required statuses are '0'."""
    ci_dir = tmp_path / "ci"
    ci_dir.mkdir(parents=True)

    # Create all required status files with success (0)
    for status_file in ci_gate.FAST_REQUIRED:
        (ci_dir / status_file).write_text("0", encoding="utf-8")

    # Monkeypatch CI_DIR to use our temp directory
    monkeypatch.setattr(ci_gate, "CI_DIR", ci_dir)

    # Run ci_gate
    result = ci_gate.main()

    # Should return zero (success) because all statuses are 0
    assert result == 0, "ci_gate should pass when all statuses are 0"


# --- CI context hardening tests ---


class TestIsCiContext:
    """Unit tests for _is_ci_context()."""

    def test_detects_ci_pipeline_number(self) -> None:
        assert ci_gate._is_ci_context({"CI_PIPELINE_NUMBER": "42"})

    def test_detects_woodpecker_build_event(self) -> None:
        assert ci_gate._is_ci_context({"WOODPECKER_BUILD_EVENT": "push"})

    def test_detects_ci_commit_branch(self) -> None:
        assert ci_gate._is_ci_context({"CI_COMMIT_BRANCH": "main"})

    def test_false_when_no_ci_vars(self) -> None:
        assert not ci_gate._is_ci_context({})

    def test_false_when_ci_vars_empty(self) -> None:
        assert not ci_gate._is_ci_context(
            {"CI_PIPELINE_NUMBER": "  ", "CI_COMMIT_BRANCH": ""}
        )


class TestIsRepoLocalPath:
    """Unit tests for _is_repo_local_path()."""

    def test_detects_subdirectory_under_repo(self) -> None:
        repo_root = Path("/repo")
        assert ci_gate._is_repo_local_path(Path("/repo/_bmad-output/ci"), repo_root)

    def test_false_for_absolute_path_outside_repo(self, tmp_path: Path) -> None:
        assert not ci_gate._is_repo_local_path(
            Path("/woodpecker/ci-status/123"), tmp_path
        )

    def test_detects_relative_path_under_repo_cwd(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert ci_gate._is_repo_local_path(Path("subdir"), tmp_path)


def test_ac1_ci_gate_fails_fast_when_ci_status_dir_unset_in_ci(
    tmp_path: Path, monkeypatch
) -> None:
    """AC1: In CI context, if CI_STATUS_DIR is missing or empty, fail fast."""
    monkeypatch.setattr(ci_gate, "bootstrap", lambda load_env=True: None)
    monkeypatch.setenv("CI_PIPELINE_NUMBER", "123")
    monkeypatch.delenv("CI_STATUS_DIR", raising=False)

    result = ci_gate.main()

    assert result == 1


def test_ac2_ci_gate_fails_fast_when_ci_status_dir_is_repo_local_in_ci(
    tmp_path: Path, monkeypatch
) -> None:
    """AC2: In CI context, if CI_STATUS_DIR resolves to repo-local fallback, fail fast."""
    monkeypatch.setattr(ci_gate, "bootstrap", lambda load_env=True: None)
    monkeypatch.setenv("CI_PIPELINE_NUMBER", "123")
    monkeypatch.setenv("CI_STATUS_DIR", "_bmad-output/ci")

    result = ci_gate.main()

    assert result == 1


def test_ac3_ci_gate_allows_fallback_when_not_in_ci(
    tmp_path: Path, monkeypatch
) -> None:
    """AC3: In non-CI local usage, fallback behavior remains allowed."""
    monkeypatch.setattr(ci_gate, "bootstrap", lambda load_env=True: None)
    for var in [
        "CI_PIPELINE_NUMBER",
        "CI_COMMIT_BRANCH",
        "WOODPECKER_BUILD_EVENT",
        "CI_BUILD_EVENT",
        "WOODPECKER_EVENT",
        "CI_PIPELINE_EVENT",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CI_STATUS_DIR", raising=False)

    ci_dir = tmp_path / "ci"
    ci_dir.mkdir(parents=True)
    for status_file in ci_gate.FAST_REQUIRED:
        (ci_dir / status_file).write_text("0", encoding="utf-8")
    monkeypatch.setattr(ci_gate, "CI_DIR", ci_dir)

    result = ci_gate.main()

    assert result == 0
