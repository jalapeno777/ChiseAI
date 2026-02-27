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


def test_ci_gate_fails_when_status_write_gate_fails(tmp_path: Path) -> None:
    """Verify that ci_gate fails when status-write-gate.status is non-zero."""
    ci_dir = tmp_path / "ci"
    ci_dir.mkdir(parents=True)

    # Create all required status files with exit code 0
    (ci_dir / "swarm-context.status").write_text("0", encoding="utf-8")
    (ci_dir / "lint.status").write_text("0", encoding="utf-8")
    (ci_dir / "security-scan.status").write_text("0", encoding="utf-8")
    (ci_dir / "status-write-gate.status").write_text("1", encoding="utf-8")

    # Mock the CI_DIR
    original_ci_dir = ci_gate.CI_DIR
    try:
        ci_gate.CI_DIR = ci_dir
        result = ci_gate.main()
        assert result == 1, (
            f"Expected ci_gate to fail (return 1) when status-write-gate fails, got {result}"
        )
    finally:
        ci_gate.CI_DIR = original_ci_dir
