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
