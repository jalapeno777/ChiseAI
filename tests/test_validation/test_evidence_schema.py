"""Tests for Evidence Schema Validator.

Validates that evidence_schema_validator.py correctly checks:
- All required top-level fields exist and have correct types
- Nested test_summary structure (required + optional fields)
- Semantic consistency (e.g. passed + failed <= total)
- Edge cases: empty dicts, wrong types, missing fields, etc.

Story: SWARM-HARDEN-001-1.1
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest
from scripts.validation.evidence_schema_validator import (
    EvidenceSchemaValidator,
    REQUIRED_TOP_LEVEL_FIELDS,
    TEST_SUMMARY_OPTIONAL_FIELDS,
    TEST_SUMMARY_REQUIRED_FIELDS,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_evidence(**overrides: Any) -> dict[str, Any]:
    """Return a valid evidence dict, with optional field overrides."""
    base: dict[str, Any] = {
        "story_id": "ST-001",
        "branch": "feature/ST-001-something",
        "head_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "test_summary": {
            "total": 10,
            "passed": 8,
            "failed": 2,
            "skipped": 0,
            "pass_rate": 80.0,
        },
        "status_sync_proof": "https://example.com/status/ST-001",
        "blockers": [],
    }
    base.update(overrides)
    return base


def _valid_test_summary(**overrides: Any) -> dict[str, Any]:
    """Return a valid test_summary dict."""
    base: dict[str, Any] = {
        "total": 10,
        "passed": 8,
        "failed": 2,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------


class TestValidationResult:
    """Unit tests for the ValidationResult dataclass."""

    def test_default_is_valid(self) -> None:
        result = ValidationResult()
        assert result.is_valid is True
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_add_error_invalidates(self) -> None:
        result = ValidationResult()
        result.add_error("oops")
        assert result.is_valid is False
        assert result.error_count == 1
        assert "oops" in result.errors

    def test_add_warning_does_not_invalidate(self) -> None:
        result = ValidationResult()
        result.add_warning("meh")
        assert result.is_valid is True
        assert result.warning_count == 1

    def test_to_dict_round_trip(self) -> None:
        result = ValidationResult()
        result.add_error("e1")
        result.add_warning("w1")
        d = result.to_dict()
        assert d["is_valid"] is False
        assert d["error_count"] == 1
        assert d["warning_count"] == 1
        assert "e1" in d["errors"]
        assert "w1" in d["warnings"]


# ---------------------------------------------------------------------------
# AC1: Required top-level fields
# ---------------------------------------------------------------------------


class TestRequiredTopLevelFields:
    """AC1: Validator checks all required fields exist and have correct types."""

    def test_valid_evidence_passes(self) -> None:
        validator = EvidenceSchemaValidator()
        result = validator.validate(_valid_evidence())
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    def test_missing_story_id(self) -> None:
        evidence = _valid_evidence()
        del evidence["story_id"]
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("story_id" in e for e in result.errors)

    def test_missing_branch(self) -> None:
        evidence = _valid_evidence()
        del evidence["branch"]
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("branch" in e for e in result.errors)

    def test_missing_head_sha(self) -> None:
        evidence = _valid_evidence()
        del evidence["head_sha"]
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("head_sha" in e for e in result.errors)

    def test_missing_test_summary(self) -> None:
        evidence = _valid_evidence()
        del evidence["test_summary"]
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary" in e for e in result.errors)

    def test_missing_status_sync_proof(self) -> None:
        evidence = _valid_evidence()
        del evidence["status_sync_proof"]
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("status_sync_proof" in e for e in result.errors)

    def test_missing_blockers(self) -> None:
        evidence = _valid_evidence()
        del evidence["blockers"]
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("blockers" in e for e in result.errors)

    def test_all_required_fields_reported_when_empty(self) -> None:
        """Every required field produces an error when the dict is empty."""
        result = EvidenceSchemaValidator().validate({})
        field_names = set(REQUIRED_TOP_LEVEL_FIELDS.keys())
        missing_in_errors = field_names - {
            e.split(":")[-1].strip().strip("'\"") for e in result.errors
        }
        assert not result.is_valid
        assert missing_in_errors == set(), f"Fields not reported: {missing_in_errors}"

    # -- type checks --------------------------------------------------------

    def test_story_id_wrong_type_int(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(story_id=123))
        assert not result.is_valid
        assert any("story_id" in e and "str" in e for e in result.errors)

    def test_story_id_wrong_type_none(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(story_id=None))
        assert not result.is_valid

    def test_branch_wrong_type_list(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(branch=["bad"]))
        assert not result.is_valid
        assert any("branch" in e and "str" in e for e in result.errors)

    def test_head_sha_wrong_type_int(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(head_sha=999))
        assert not result.is_valid

    def test_test_summary_wrong_type_str(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(test_summary="not a dict")
        )
        assert not result.is_valid

    def test_blockers_wrong_type_str(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(blockers="nope"))
        assert not result.is_valid

    def test_status_sync_proof_accepts_str(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(status_sync_proof="https://example.com")
        )
        assert result.is_valid

    def test_status_sync_proof_accepts_dict(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(status_sync_proof={"source": "redis", "key": "abc"})
        )
        assert result.is_valid

    def test_status_sync_proof_rejects_int(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(status_sync_proof=42)
        )
        assert not result.is_valid

    def test_non_dict_input(self) -> None:
        result = EvidenceSchemaValidator().validate("not a dict")
        assert not result.is_valid
        assert any("dict" in e for e in result.errors)

    def test_none_input(self) -> None:
        result = EvidenceSchemaValidator().validate(None)
        assert not result.is_valid

    def test_extra_fields_allowed(self) -> None:
        """Extra fields should not cause validation failure."""
        evidence = _valid_evidence()
        evidence["extra_field"] = "allowed"
        evidence["another_one"] = 42
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid, f"Unexpected errors: {result.errors}"


# ---------------------------------------------------------------------------
# head_sha format validation
# ---------------------------------------------------------------------------


class TestHeadShaFormat:
    """Tests for head_sha format validation."""

    def test_full_sha_passes(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(head_sha="a" * 40))
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    def test_abbreviated_sha_passes(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(head_sha="abcdef1"))
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    def test_too_short_sha_fails(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(head_sha="abc12"))
        assert not result.is_valid
        assert any("head_sha" in e and "short" in e.lower() for e in result.errors)

    def test_non_hex_sha_fails(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(head_sha="xyzxyzxyzxyzxyzxyzxyzxyzxyzxyzxyzxyzxyz")
        )
        assert not result.is_valid
        assert any(
            "head_sha" in e and ("hex" in e.lower() or "sha" in e.lower())
            for e in result.errors
        )

    def test_strict_sha_mode_rejects_short(self) -> None:
        result = EvidenceSchemaValidator(strict_head_sha=True).validate(
            _valid_evidence(head_sha="abcdef1")
        )
        assert not result.is_valid


# ---------------------------------------------------------------------------
# story_id format validation
# ---------------------------------------------------------------------------


class TestStoryIdFormat:
    """Tests for story_id format warnings."""

    def test_story_id_without_digit_warns(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(story_id="ST-ABC"))
        assert any("story_id" in w and "digit" in w for w in result.warnings)

    def test_story_id_with_digit_no_warning(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(story_id="ST-001"))
        assert not any("story_id" in w for w in result.warnings)

    def test_various_valid_story_ids(self) -> None:
        """Common story ID patterns should not produce warnings."""
        for sid in ("CH-001", "FT-042", "REPO-7", "SAFETY-10", "REWARD-003"):
            result = EvidenceSchemaValidator().validate(_valid_evidence(story_id=sid))
            assert not any("story_id" in w for w in result.warnings), (
                f"Unexpected warning for {sid}: {result.warnings}"
            )


# ---------------------------------------------------------------------------
# AC2: Nested test_summary structure
# ---------------------------------------------------------------------------


class TestTestSummaryStructure:
    """AC2: Validator checks nested test_summary structure."""

    def test_valid_test_summary(self) -> None:
        evidence = _valid_evidence(
            test_summary=_valid_test_summary(skipped=0, pass_rate=80.0)
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    def test_minimal_test_summary(self) -> None:
        """Only required fields (total, passed, failed) are necessary."""
        evidence = _valid_evidence(test_summary={"total": 5, "passed": 5, "failed": 0})
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    def test_missing_total(self) -> None:
        evidence = _valid_evidence(test_summary={"passed": 5, "failed": 0})
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.total" in e for e in result.errors)

    def test_missing_passed(self) -> None:
        evidence = _valid_evidence(test_summary={"total": 5, "failed": 0})
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.passed" in e for e in result.errors)

    def test_missing_failed(self) -> None:
        evidence = _valid_evidence(test_summary={"total": 5, "passed": 5})
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.failed" in e for e in result.errors)

    def test_empty_test_summary(self) -> None:
        evidence = _valid_evidence(test_summary={})
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        # All three required fields should be reported
        assert sum(1 for e in result.errors if "test_summary" in e) >= 3

    def test_wrong_type_total(self) -> None:
        evidence = _valid_evidence(
            test_summary={"total": "ten", "passed": 5, "failed": 0}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.total" in e and "int" in e for e in result.errors)

    def test_wrong_type_passed(self) -> None:
        evidence = _valid_evidence(
            test_summary={"total": 5, "passed": 5.5, "failed": 0}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.passed" in e and "int" in e for e in result.errors)

    def test_wrong_type_failed(self) -> None:
        evidence = _valid_evidence(
            test_summary={"total": 5, "passed": 5, "failed": True}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.failed" in e and "int" in e for e in result.errors)

    def test_optional_skipped_correct_type(self) -> None:
        evidence = _valid_evidence(test_summary=_valid_test_summary(skipped=2))
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid

    def test_optional_skipped_wrong_type(self) -> None:
        evidence = _valid_evidence(test_summary=_valid_test_summary(skipped="two"))
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.skipped" in e for e in result.errors)

    def test_optional_pass_rate_correct_type(self) -> None:
        evidence = _valid_evidence(test_summary=_valid_test_summary(pass_rate=80.0))
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid

    def test_optional_pass_rate_wrong_type(self) -> None:
        evidence = _valid_evidence(test_summary=_valid_test_summary(pass_rate="80%"))
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("test_summary.pass_rate" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Semantic consistency checks
# ---------------------------------------------------------------------------


class TestSemanticConsistency:
    """Tests for cross-field semantic validation."""

    def test_passed_plus_failed_exceeds_total(self) -> None:
        evidence = _valid_evidence(test_summary={"total": 5, "passed": 4, "failed": 3})
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("exceeds" in e.lower() for e in result.errors)

    def test_passed_plus_failed_equals_total(self) -> None:
        evidence = _valid_evidence(test_summary={"total": 10, "passed": 8, "failed": 2})
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    def test_all_zero_counts(self) -> None:
        evidence = _valid_evidence(test_summary={"total": 0, "passed": 0, "failed": 0})
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid

    def test_negative_total(self) -> None:
        evidence = _valid_evidence(test_summary={"total": -1, "passed": 0, "failed": 0})
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        assert any("total" in e and ">=" in e for e in result.errors)

    def test_negative_passed(self) -> None:
        evidence = _valid_evidence(
            test_summary={"total": 10, "passed": -1, "failed": 0}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid

    def test_negative_failed(self) -> None:
        evidence = _valid_evidence(
            test_summary={"total": 10, "passed": 10, "failed": -1}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid

    def test_pass_rate_mismatch_warns(self) -> None:
        evidence = _valid_evidence(
            test_summary={"total": 10, "passed": 8, "failed": 2, "pass_rate": 50.0}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        # pass_rate 50% != computed 80% → warning
        assert any("pass_rate" in w and "does not match" in w for w in result.warnings)

    def test_pass_rate_close_enough_no_warning(self) -> None:
        """Small floating-point differences should not trigger warning."""
        evidence = _valid_evidence(
            test_summary={"total": 3, "passed": 2, "failed": 1, "pass_rate": 66.67}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        # 2/3 = 66.666... → 66.67 is within 0.5 tolerance
        assert not any("pass_rate" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Blockers validation
# ---------------------------------------------------------------------------


class TestBlockersValidation:
    """Tests for the blockers field."""

    def test_empty_blockers_list(self) -> None:
        result = EvidenceSchemaValidator().validate(_valid_evidence(blockers=[]))
        assert result.is_valid

    def test_blockers_with_strings(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(blockers=["Waiting for review", "Dependency on ST-002"])
        )
        assert result.is_valid

    def test_blockers_with_non_string_items(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(blockers=[42, None])
        )
        assert not result.is_valid
        assert any("blockers[0]" in e for e in result.errors)
        assert any("blockers[1]" in e for e in result.errors)

    def test_blockers_empty_string_warns(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(blockers=["", "real blocker"])
        )
        assert any("blockers[0]" in w and "empty" in w for w in result.warnings)

    def test_blockers_mixed_types(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(blockers=["ok", 123, {"nested": "bad"}])
        )
        assert not result.is_valid
        assert sum(1 for e in result.errors if "blockers[" in e) >= 2


# ---------------------------------------------------------------------------
# status_sync_proof validation
# ---------------------------------------------------------------------------


class TestStatusSyncProofValidation:
    """Tests for the status_sync_proof field."""

    def test_string_proof(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(status_sync_proof="redis:key:value")
        )
        assert result.is_valid

    def test_dict_proof(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(
                status_sync_proof={"source": "redis", "key": "bmad:status:ST-001"}
            )
        )
        assert result.is_valid

    def test_empty_string_warns(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(status_sync_proof="")
        )
        assert any("status_sync_proof" in w and "empty" in w for w in result.warnings)

    def test_empty_dict_warns(self) -> None:
        result = EvidenceSchemaValidator().validate(
            _valid_evidence(status_sync_proof={})
        )
        assert any("status_sync_proof" in w and "empty" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# File-based validation
# ---------------------------------------------------------------------------


class TestFileValidation:
    """Tests for validate_file method."""

    def test_valid_json_file(self, tmp_path: Path) -> None:
        evidence = _valid_evidence()
        file_path = tmp_path / "evidence.json"
        file_path.write_text(json.dumps(evidence))

        result = EvidenceSchemaValidator().validate_file(file_path)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    def test_nonexistent_file(self) -> None:
        result = EvidenceSchemaValidator().validate_file(
            "/tmp/nonexistent_file_12345.json"
        )
        assert not result.is_valid
        assert any("does not exist" in e for e in result.errors)

    def test_invalid_json_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "bad.json"
        file_path.write_text("{not valid json}")

        result = EvidenceSchemaValidator().validate_file(file_path)
        assert not result.is_valid
        assert any("JSON" in e for e in result.errors)

    def test_missing_fields_in_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "partial.json"
        file_path.write_text(json.dumps({"story_id": "ST-001"}))

        result = EvidenceSchemaValidator().validate_file(file_path)
        assert not result.is_valid
        # Should report multiple missing fields
        assert result.error_count >= 4


# ---------------------------------------------------------------------------
# Integration / comprehensive tests
# ---------------------------------------------------------------------------


class TestComprehensiveScenarios:
    """End-to-end scenarios combining multiple validations."""

    def test_fully_populated_valid_evidence(self) -> None:
        evidence = {
            "story_id": "FT-042",
            "branch": "feature/FT-042-something",
            "head_sha": "d" * 40,
            "test_summary": {
                "total": 25,
                "passed": 25,
                "failed": 0,
                "skipped": 0,
                "pass_rate": 100.0,
            },
            "status_sync_proof": {
                "source": "redis",
                "key": "bmad:status:FT-042",
                "value": "complete",
            },
            "blockers": [],
            "extra_metadata": "should be allowed",
        }
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid, f"Unexpected errors: {result.errors}"
        assert result.error_count == 0

    def test_multiple_errors_accumulated(self) -> None:
        """All errors should be reported, not just the first."""
        evidence: dict[str, Any] = {
            "story_id": 123,  # wrong type
            # branch: missing
            "head_sha": "xyz",  # invalid format + too short
            "test_summary": {},  # missing required sub-fields
            "status_sync_proof": "",  # empty (warning)
            # blockers: missing
        }
        result = EvidenceSchemaValidator().validate(evidence)
        assert not result.is_valid
        # Should have errors for: story_id type, missing branch, head_sha format,
        # missing test_summary fields, missing blockers
        assert result.error_count >= 5

    def test_evidence_with_blockers(self) -> None:
        evidence = _valid_evidence(
            story_id="CH-100",
            blockers=["Waiting for upstream PR merge", "Needs design review"],
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid

    def test_abbreviated_sha_with_digit_story_id(self) -> None:
        evidence = _valid_evidence(
            story_id="REPO-7",
            head_sha="abcdef1",
        )
        result = EvidenceSchemaValidator().validate(evidence)
        assert result.is_valid

    def test_pass_rate_tolerance_with_rounding(self) -> None:
        """pass_rate within 0.5% tolerance should not warn."""
        evidence = _valid_evidence(
            test_summary={"total": 7, "passed": 5, "failed": 2, "pass_rate": 71.43}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        # 5/7 = 71.428... → 71.43 is within tolerance
        assert not any("pass_rate" in w for w in result.warnings)

    def test_bool_not_accepted_as_int_in_test_summary(self) -> None:
        """Python booleans are ints subclass; the validator explicitly rejects them."""
        evidence = _valid_evidence(
            test_summary={"total": True, "passed": 1, "failed": 0}
        )
        result = EvidenceSchemaValidator().validate(evidence)
        # bool IS int in Python, but our validator explicitly rejects bool for int fields
        assert not result.is_valid
        assert any("test_summary.total" in e for e in result.errors)
