from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "woodpecker_triage.py"
)
SPEC = importlib.util.spec_from_file_location("woodpecker_triage", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
woodpecker_triage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = woodpecker_triage
SPEC.loader.exec_module(woodpecker_triage)


def test_parse_ruff_rule_file_line() -> None:
    log = "src/foo.py:12:7: F401 `os` imported but unused"
    causes = woodpecker_triage.parse_root_causes("lint", log)
    assert causes
    assert causes[0].tool == "ruff"
    assert causes[0].file == "src/foo.py"
    assert causes[0].line == 12
    assert causes[0].rule == "F401"


def test_parse_mypy_error_with_code() -> None:
    log = 'src/bar.py:21: error: Incompatible return value type (got "int", expected "str")  [return-value]'
    causes = woodpecker_triage.parse_root_causes("lint", log)
    assert causes
    assert causes[0].tool == "mypy"
    assert causes[0].file == "src/bar.py"
    assert causes[0].line == 21
    assert causes[0].rule == "return-value"


def test_parse_black_would_reformat() -> None:
    log = "would reformat src/baz.py"
    causes = woodpecker_triage.parse_root_causes("lint", log)
    assert causes
    assert causes[0].tool == "black"
    assert causes[0].file == "src/baz.py"


def test_diagnose_local_artifacts_uses_local_ci_full_log(tmp_path: Path) -> None:
    ci_dir = tmp_path / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "local-ci.status").write_text("1\n", encoding="utf-8")
    (ci_dir / "local-ci-full.log").write_text(
        "src/a.py:10:2: F821 undefined name `x`\n", encoding="utf-8"
    )

    args = woodpecker_triage.build_parser().parse_args(
        [
            "diagnose",
            "--from-local-dir",
            str(ci_dir),
            "--write-artifacts",
            "--out-dir",
            str(tmp_path / "out"),
            "--format",
            "json",
        ]
    )
    result = woodpecker_triage.diagnose(args)

    assert result["failed_steps"]
    assert any(
        rc["tool"] == "ruff" and rc["rule"] == "F821" for rc in result["root_causes"]
    )
    artifact_dir = Path(result["artifact_dir"])
    assert (artifact_dir / "root-cause.json").exists()
    assert (artifact_dir / "root-cause.md").exists()
