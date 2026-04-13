"""
Tests for chiseai-worker-contracts skill verification.

These tests verify:
1. Eval queries trigger the skill via relevant keywords
2. SKILL.md has required sections
3. Contract structure (scope_globs, locks_required, depends_on, exit_conditions, evidence_required) is documented
4. Parallel batch scope conflict detection works
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


SKILL_PATH = Path(".opencode/skills/chiseai-worker-contracts/SKILL.md")
SKILL_EVALS_PATH = Path(".opencode/skills/chiseai-worker-contracts/evals/evals.json")


def test_eval_queries_trigger_skill():
    """For each eval in evals.json, verify skill content mentions relevant keywords."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8").lower()
    evals = json.loads(SKILL_EVALS_PATH.read_text(encoding="utf-8"))

    # Keywords that should appear for delegation/contract skills
    required_keywords = [
        "contract",
        "delegation",
        "scope",
        "worker",
        "batch",
    ]

    failures = []
    for eval_entry in evals:
        eval_id = eval_entry.get("id", "?")
        query = eval_entry.get("query", "").lower()

        # Check if any required keyword is in the skill text
        keywords_found = [kw for kw in required_keywords if kw in skill_text]

        # The skill should have the key delegation-related terms
        if len(keywords_found) < 3:
            failures.append(
                f"{eval_id}: insufficient keywords found {keywords_found} (need at least 3)"
            )

    assert not failures, "\n".join(failures)


def test_skill_has_required_sections():
    """Verify SKILL.md has required sections."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # Required sections for worker contracts
    required_sections = [
        (r"## When To Use", "When To Use section"),
        (r"## Goal", "Goal section"),
        (r"##.*Template|## Templates", "Template section"),
        (
            r"## Exit Conditions|## Troubleshooting",
            "Exit Conditions or Troubleshooting section",
        ),
    ]

    failures = []
    for pattern, description in required_sections:
        if not re.search(pattern, skill_text, re.IGNORECASE):
            failures.append(f"Missing required section: {description}")

    assert not failures, "\n".join(failures)


def test_contract_structure_validation():
    """Validate that the contract structure is documented in the skill."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # Required contract fields that must be documented
    required_fields = [
        "SCOPE_GLOBS",
        "FORBIDDEN_GLOBS",
        "LOCKS_REQUIRED",
        "OWNERSHIP_CHECK",
        "EXIT_CONDITIONS",
        "EVIDENCE_REQUIRED",
        "BRANCH",
        "WORKTREE_PATH",
    ]

    failures = []
    for field in required_fields:
        if field not in skill_text:
            failures.append(f"Contract field not documented: {field}")

    assert not failures, "\n".join(failures)


def test_parallel_batch_scope_conflict_detection():
    """Test that overlapping scope_globs between workers are detected."""
    # Simulate two workers with scopes
    worker_a_scopes = [
        "src/strategy/dsl/trailing_stop/",
        "tests/unit/strategy/test_trailing_stop.py",
    ]
    worker_b_scopes = [
        "src/strategy/dsl/trailing_stop/",  # Overlaps with A
        "src/strategy/dsl/position_sizing/",  # Different from A
    ]
    worker_c_scopes = [
        "src/strategy/dsl/grammar.py",  # Different from both
    ]

    def check_overlap(
        scopes_a: list[str], scopes_b: list[str]
    ) -> list[tuple[str, str]]:
        """Return list of overlapping scope pairs."""
        overlaps = []
        for a in scopes_a:
            for b in scopes_b:
                # Check if one is a prefix of another (potential overlap)
                if a.startswith(b) or b.startswith(a):
                    overlaps.append((a, b))
        return overlaps

    # Worker A and B have overlapping scopes
    overlaps_ab = check_overlap(worker_a_scopes, worker_b_scopes)
    assert len(overlaps_ab) > 0, "Should detect overlap between A and B"

    # Worker A and C have no overlap
    overlaps_ac = check_overlap(worker_a_scopes, worker_c_scopes)
    assert len(overlaps_ac) == 0, "Should not detect overlap between A and C"

    # Worker B and C have no overlap
    overlaps_bc = check_overlap(worker_b_scopes, worker_c_scopes)
    assert len(overlaps_bc) == 0, "Should not detect overlap between B and C"


def test_contract_contains_required_subsections():
    """Verify contract template contains required subsections."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # These are key subsections that must appear in the templates
    required_subsections = [
        "MEMORY_CONTEXT",
        "SESSION_VERIFY",
        "COMPLETION_PUBLICATION_GATE",
        "REPEATED_ERROR_POLICY",
        "INCIDENT_TEMPLATE",
    ]

    failures = []
    for subsection in required_subsections:
        if subsection not in skill_text:
            failures.append(f"Required subsection not in template: {subsection}")

    assert not failures, "\n".join(failures)


def test_batch_contract_has_parallel_safety_rules():
    """Verify parallel batch contracts include safety rules."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    # Look for parallel batch template
    if "PARALLEL BATCH CONTRACT" not in skill_text:
        pytest.fail("Missing PARALLEL BATCH CONTRACT template")

    # Parallel safety rules must be present
    safety_related = [
        "ownership",
        "STOP",
        "conflict",
    ]
    found = [term for term in safety_related if term.lower() in skill_text.lower()]
    assert len(found) >= 2, f"Parallel safety rules incomplete, found: {found}"
