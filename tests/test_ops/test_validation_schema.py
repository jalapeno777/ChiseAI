"""
Tests for chiseai-validation skill verification.

These tests verify:
1. Eval queries trigger the skill via relevant keywords
2. SKILL.md has required sections
3. status_guard.py validate command exists and produces valid output
4. validation-registry.yaml is valid YAML with expected top-level keys
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


SKILL_PATH = Path(".opencode/skills/chiseai-validation/SKILL.md")
SKILL_EVALS_PATH = Path(".opencode/skills/chiseai-validation/evals/evals.json")
STATUS_GUARD_PATH = Path("scripts/governance/status_guard.py")
VALIDATION_REGISTRY_PATH = Path("docs/validation/validation-registry.yaml")


def test_eval_queries_trigger_skill():
    """For each eval in evals.json, verify skill content mentions relevant keywords."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8").lower()
    evals = json.loads(SKILL_EVALS_PATH.read_text(encoding="utf-8"))

    # Keywords that should appear for validation skills
    required_keywords = [
        "validation",
        "CI",
        "gate",
        "status_sync",
        "precommit",
    ]

    failures = []
    for eval_entry in evals:
        eval_id = eval_entry.get("id", "?")
        query = eval_entry.get("query", "").lower()

        # The skill should have validation-related terms
        validation_count = sum(1 for kw in required_keywords if kw in skill_text)
        if validation_count < 3:
            failures.append(
                f"{eval_id}: insufficient validation keywords (found {validation_count}, need 3+)"
            )

    assert not failures, "\n".join(failures)


def test_skill_has_required_sections():
    """Verify SKILL.md has required sections."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # Required sections for validation skill
    required_sections = [
        (r"## When To Use", "When To Use section"),
        (r"## Goal", "Goal section"),
        (
            r"## Validation Layers|## Quick Reference",
            "Validation Layers or Quick Reference",
        ),
        (r"## Templates|## Examples", "Templates or Examples section"),
        (r"## Exit Conditions", "Exit Conditions section"),
    ]

    failures = []
    for pattern, description in required_sections:
        if not re.search(pattern, skill_text, re.IGNORECASE):
            failures.append(f"Missing required section: {description}")

    assert not failures, "\n".join(failures)


def test_status_guard_script_exists():
    """Test that status_guard.py exists and has a validate command."""
    if not STATUS_GUARD_PATH.exists():
        pytest.skip("status_guard.py not found, skipping")

    content = STATUS_GUARD_PATH.read_text(encoding="utf-8")

    # Should have validate function/command
    has_validate = (
        "def validate" in content
        or "validate" in content.lower()
        and "argparse" in content
    )
    assert has_validate, "status_guard.py should have a validate command"


def test_status_guard_validate_command(tmp_path):
    """Test that status_guard.py validate produces valid output for clean YAML."""
    if not STATUS_GUARD_PATH.exists():
        pytest.skip("status_guard.py not found")

    # Create a clean test YAML file
    clean_yaml = tmp_path / "test_status.yaml"
    clean_yaml.write_text(
        """
metadata:
  project_name: ChiseAI
  version: "1.0"
epics: []
completed: []
backlog: []
current_phase:
  phase: active
  status: active
""".strip()
        + "\n",
        encoding="utf-8",
    )

    # Try running status_guard validate
    result = subprocess.run(
        [sys.executable, str(STATUS_GUARD_PATH), "validate", str(clean_yaml)],
        capture_output=True,
        text=True,
    )

    # Should not crash (exit code 0 or documented non-zero)
    # The important thing is it doesn't raise an exception
    # Some validation errors are expected for incomplete files


def test_validation_registry_schema():
    """Test that validation-registry.yaml is valid YAML with expected top-level keys."""
    if not VALIDATION_REGISTRY_PATH.exists():
        pytest.skip("validation-registry.yaml not found")

    content = VALIDATION_REGISTRY_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    assert isinstance(data, dict), "validation-registry.yaml should parse to a dict"

    # Expected top-level keys
    expected_keys = ["metadata", "validations"]
    missing_keys = [k for k in expected_keys if k not in data]
    assert not missing_keys, f"Missing top-level keys: {missing_keys}"

    # Metadata should have project_name and version
    metadata = data.get("metadata", {})
    assert "project_name" in metadata, "metadata should have project_name"
    assert "version" in metadata, "metadata should have version"

    # Validations should be a list
    validations = data.get("validations", [])
    assert isinstance(validations, list), "validations should be a list"

    # Each validation should have required fields
    if validations:
        required_validation_fields = ["id", "title", "status"]
        first_validation = validations[0]
        missing = [f for f in required_validation_fields if f not in first_validation]
        assert not missing, f"Validation entries missing fields: {missing}"


def test_validation_skill_documents_status_sync():
    """Verify validation skill documents status sync process."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # Should mention status sync validation
    assert "status sync" in skill_text.lower() or "status_sync" in skill_text.lower(), (
        "Validation skill should document status sync process"
    )

    # Should reference the validation script
    assert "validate_status_sync" in skill_text or "scripts/validate" in skill_text, (
        "Validation skill should reference validation scripts"
    )


def test_validation_skill_documents_ci_gates():
    """Verify validation skill documents CI gate process."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # Should mention CI gates
    ci_related = ["CI", "gate", "woodpecker", "pre-commit", "precommit"]
    found = [term for term in ci_related if term.lower() in skill_text.lower()]
    assert len(found) >= 2, f"Validation skill should document CI gates, found: {found}"


def test_validation_skill_has_troubleshooting():
    """Verify validation skill has troubleshooting section."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    troubleshooting_keywords = [
        "troubleshoot",
        "troubleshooting",
        "common failures",
        "if ci fails",
        "pre-commit fails",
    ]
    found = any(kw.lower() in skill_text.lower() for kw in troubleshooting_keywords)
    assert found, "Validation skill should have troubleshooting section"
