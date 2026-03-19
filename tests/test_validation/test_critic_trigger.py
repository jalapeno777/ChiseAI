"""
Tests for post_remediation_critic.py validation script.

Covers:
    AC1 - Critic reviews exist after remediation rounds
    AC2 - Critic findings are addressed (actionable severities)
    AC3 - Max remediation rounds not exceeded
    Edge cases - Empty inputs, invalid data, boundary conditions
"""

import importlib.util
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loading (bypass __init__.py to avoid broken imports)
# ---------------------------------------------------------------------------

_MODULE_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "validation"
    / "post_remediation_critic.py"
)
_MODULE_NAME = "post_remediation_critic"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
assert _spec is not None, f"Could not create spec for {_MODULE_PATH}"
_mod = importlib.util.module_from_spec(_spec)
# Register in sys.modules BEFORE exec_module so that dataclass/Enum
# __module__ lookups work correctly on Python 3.13+
import sys as _sys

_sys.modules[_MODULE_NAME] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

# Export symbols under test
Severity = _mod.Severity
FindingStatus = _mod.FindingStatus
CriticFinding = _mod.CriticFinding
CriticReview = _mod.CriticReview
RemediationRound = _mod.RemediationRound
CheckResult = _mod.CheckResult
CriticValidationResult = _mod.CriticValidationResult
load_evidence = _mod.load_evidence
parse_remediation_rounds = _mod.parse_remediation_rounds
parse_critic_reviews = _mod.parse_critic_reviews
check_critic_reviews_after_remediation = _mod.check_critic_reviews_after_remediation
check_critic_findings_addressed = _mod.check_critic_findings_addressed
check_max_remediation_rounds = _mod.check_max_remediation_rounds
validate = _mod.validate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence(
    remediation_rounds: list[dict] | None = None,
    critic_reviews: list[dict] | None = None,
    max_remediation_rounds: int = 2,
) -> dict:
    """Build a minimal evidence dict for testing."""
    return {
        "remediation_rounds": remediation_rounds or [],
        "critic_reviews": critic_reviews or [],
        "max_remediation_rounds": max_remediation_rounds,
    }


def _make_round(
    round_num: int = 1,
    timestamp: str = "2026-03-19T10:00:00Z",
    description: str = "Fixed something",
) -> dict:
    return {
        "round": round_num,
        "timestamp": timestamp,
        "description": description,
        "files_changed": ["foo.py"],
        "evidence_ref": "docs/evidence/r1.md",
    }


def _make_review(
    review_id: str = "critic-001",
    timestamp: str = "2026-03-19T10:30:00Z",
    round_reviewed: int = 1,
    findings: list[dict] | None = None,
) -> dict:
    return {
        "review_id": review_id,
        "timestamp": timestamp,
        "round_reviewed": round_reviewed,
        "findings": findings or [],
    }


def _make_finding(
    finding_id: str = "F-001",
    severity: str = "MEDIUM",
    description: str = "Some issue",
    status: str = "addressed",
    resolution: str = "Fixed it",
) -> dict:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "description": description,
        "status": status,
        "resolution": resolution,
    }


# ===========================================================================
# Unit tests: Data classes
# ===========================================================================


class TestCriticFinding:
    """Tests for CriticFinding dataclass."""

    def test_from_dict_defaults(self):
        f = CriticFinding.from_dict({"finding_id": "F-1"})
        assert f.finding_id == "F-1"
        assert f.severity == "INFO"
        assert f.description == ""
        assert f.status == "open"
        assert f.resolution == ""

    def test_from_dict_full(self):
        f = CriticFinding.from_dict(
            {
                "finding_id": "F-2",
                "severity": "high",
                "description": "Broken thing",
                "status": "ADDRESSED",
                "resolution": "Fixed",
            }
        )
        assert f.finding_id == "F-2"
        assert f.severity == "HIGH"  # normalised to upper
        assert f.status == "addressed"  # normalised to lower

    def test_to_dict_roundtrip(self):
        data = _make_finding("F-3", "CRITICAL", "Bad", "open", "")
        f = CriticFinding.from_dict(data)
        assert f.to_dict() == data


class TestCriticReview:
    """Tests for CriticReview dataclass."""

    def test_from_dict_defaults(self):
        r = CriticReview.from_dict({"review_id": "cr-1"})
        assert r.review_id == "cr-1"
        assert r.round_reviewed == 0
        assert r.findings == []

    def test_from_dict_with_findings(self):
        r = CriticReview.from_dict(
            {
                "review_id": "cr-2",
                "timestamp": "2026-03-19T12:00:00Z",
                "round_reviewed": 1,
                "findings": [_make_finding()],
            }
        )
        assert len(r.findings) == 1
        assert r.findings[0].finding_id == "F-001"

    def test_parsed_timestamp_iso(self):
        r = CriticReview.from_dict(
            {
                "review_id": "cr-3",
                "timestamp": "2026-03-19T10:30:00Z",
                "round_reviewed": 1,
            }
        )
        ts = r.parsed_timestamp()
        assert ts.year == 2026
        assert ts.month == 3
        assert ts.day == 19

    def test_parsed_timestamp_invalid(self):
        r = CriticReview.from_dict(
            {
                "review_id": "cr-4",
                "timestamp": "not-a-date",
                "round_reviewed": 1,
            }
        )
        ts = r.parsed_timestamp()
        assert ts.year == 1  # datetime.min fallback


class TestRemediationRound:
    """Tests for RemediationRound dataclass."""

    def test_from_dict_defaults(self):
        r = RemediationRound.from_dict({"round": 1})
        assert r.round == 1
        assert r.description == ""
        assert r.files_changed == []

    def test_from_dict_full(self):
        r = RemediationRound.from_dict(_make_round(2, "2026-03-19T11:00:00Z"))
        assert r.round == 2
        assert r.files_changed == ["foo.py"]

    def test_to_dict_roundtrip(self):
        data = _make_round(3)
        r = RemediationRound.from_dict(data)
        assert r.to_dict() == data


# ===========================================================================
# Unit tests: Evidence loading
# ===========================================================================


class TestLoadEvidence:
    """Tests for load_evidence function."""

    def test_load_json_file(self, tmp_path):
        evidence = _make_evidence(
            [_make_round()],
            [_make_review()],
        )
        f = tmp_path / "evidence.json"
        f.write_text(json.dumps(evidence))

        result = load_evidence(f)
        assert "remediation_rounds" in result
        assert len(result["remediation_rounds"]) == 1

    def test_load_yaml_file(self, tmp_path):
        import yaml

        evidence = _make_evidence(
            [_make_round()],
            [_make_review()],
        )
        f = tmp_path / "evidence.yaml"
        f.write_text(yaml.dump(evidence))

        result = load_evidence(f)
        assert len(result["remediation_rounds"]) == 1

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_evidence(Path("/nonexistent/file.json"))

    def test_invalid_json_not_yaml(self, tmp_path):
        f = tmp_path / "evidence.txt"
        # Use content that fails both JSON and YAML parsing
        # Unbalanced brackets + tabs trigger YAML scanner errors
        f.write_text("\tunbalanced: [")

        with pytest.raises(ValueError, match="Failed to parse"):
            load_evidence(f)

    def test_non_dict_content(self, tmp_path):
        f = tmp_path / "evidence.json"
        f.write_text("[1, 2, 3]")

        with pytest.raises(ValueError, match="top-level object"):
            load_evidence(f)


# ===========================================================================
# Unit tests: AC1 - Critic reviews after remediation
# ===========================================================================


class TestAC1CriticReviewAfterRemediation:
    """AC1: Verify critic reviews exist after each remediation round."""

    def test_no_rounds_passes(self):
        """No remediation rounds should pass (nothing to check)."""
        evidence = _make_evidence()
        result = validate(evidence)
        assert result.valid

    def test_round_with_matching_review_passes(self):
        """Remediation round with critic review after it passes."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[_make_review("cr-1", "2026-03-19T10:30:00Z", 1)],
        )
        result = validate(evidence)
        assert result.valid
        ac1_checks = [c for c in result.checks if c.check_id.startswith("AC1")]
        assert all(c.passed for c in ac1_checks)

    def test_round_without_review_fails(self):
        """Remediation round with no critic review fails."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[],
        )
        result = validate(evidence)
        assert not result.valid
        assert any("missing-review" in c.check_id for c in result.checks)

    def test_review_timestamp_before_remediation_fails(self):
        """Critic review timestamp before remediation fails."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[_make_review("cr-1", "2026-03-19T09:00:00Z", 1)],
        )
        result = validate(evidence)
        assert not result.valid
        assert any("timing" in c.check_id for c in result.checks)

    def test_multiple_rounds_all_reviewed(self):
        """Multiple rounds each with reviews passes."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1, "2026-03-19T10:00:00Z"),
                _make_round(2, "2026-03-19T11:00:00Z"),
            ],
            critic_reviews=[
                _make_review("cr-1", "2026-03-19T10:30:00Z", 1),
                _make_review("cr-2", "2026-03-19T11:30:00Z", 2),
            ],
        )
        result = validate(evidence)
        assert result.valid

    def test_second_round_missing_review(self):
        """Second round without review fails while first passes."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1, "2026-03-19T10:00:00Z"),
                _make_round(2, "2026-03-19T11:00:00Z"),
            ],
            critic_reviews=[
                _make_review("cr-1", "2026-03-19T10:30:00Z", 1),
            ],
        )
        result = validate(evidence)
        assert not result.valid

    def test_review_same_timestamp_as_remediation_passes(self):
        """Review at same timestamp as remediation is acceptable (>=)."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[_make_review("cr-1", "2026-03-19T10:00:00Z", 1)],
        )
        result = validate(evidence)
        assert result.valid

    def test_review_for_wrong_round_ignored(self):
        """Review for round 2 should not satisfy round 1."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[_make_review("cr-1", "2026-03-19T10:30:00Z", 2)],
        )
        result = validate(evidence)
        assert not result.valid


# ===========================================================================
# Unit tests: AC2 - Critic findings addressed
# ===========================================================================


class TestAC2FindingsAddressed:
    """AC2: Verify critic findings are addressed."""

    def test_no_reviews_passes(self):
        """No reviews means nothing to check."""
        evidence = _make_evidence()
        result = validate(evidence)
        assert result.valid

    def test_all_findings_addressed_passes(self):
        """All findings marked as addressed passes."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "HIGH", "Bug", "addressed", "Fixed"),
                        _make_finding("F-002", "MEDIUM", "Issue", "addressed", "Fixed"),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert result.valid

    def test_open_critical_finding_fails(self):
        """Open CRITICAL finding fails."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "CRITICAL", "Security hole", "open", ""),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert not result.valid
        assert any(
            "open" in c.check_id and c.severity == "CRITICAL"
            for c in result.checks
            if not c.passed
        )

    def test_open_high_finding_fails(self):
        """Open HIGH finding fails."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "HIGH", "Bug", "open", ""),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert not result.valid

    def test_open_medium_finding_fails(self):
        """Open MEDIUM finding fails."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "MEDIUM", "Issue", "open", ""),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert not result.valid

    def test_open_low_finding_passes(self):
        """Open LOW finding is acceptable (not actionable)."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "LOW", "Nitpick", "open", ""),
                    ],
                )
            ],
        )
        # Should still pass - LOW is not actionable
        ac2_checks = [
            c for c in validate(evidence).checks if c.check_id.startswith("AC2")
        ]
        assert all(c.passed for c in ac2_checks)

    def test_open_info_finding_passes(self):
        """Open INFO finding is acceptable."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "INFO", "Suggestion", "open", ""),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert result.valid

    def test_deferred_critical_finding_fails(self):
        """Deferred CRITICAL finding fails."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding(
                            "F-001", "CRITICAL", "Must fix", "deferred", "Later"
                        ),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert not result.valid

    def test_deferred_low_finding_passes(self):
        """Deferred LOW finding is acceptable."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "LOW", "Minor", "deferred", "Backlog"),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert result.valid

    def test_wont_fix_medium_finding_fails(self):
        """Won't-fix MEDIUM finding fails."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "MEDIUM", "Issue", "wont_fix", "N/A"),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert not result.valid

    def test_wont_fix_info_finding_passes(self):
        """Won't-fix INFO finding is acceptable."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "INFO", "Suggestion", "wont_fix", "N/A"),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert result.valid

    def test_mixed_severities_partial_fail(self):
        """Mixed findings: some addressed, some not."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "HIGH", "Bug", "addressed", "Fixed"),
                        _make_finding("F-002", "HIGH", "Bug2", "open", ""),
                        _make_finding("F-003", "LOW", "Nit", "open", ""),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert not result.valid
        assert result.total_findings == 3
        assert result.findings_addressed == 1
        assert result.findings_open == 2

    def test_findings_counts_accurate(self):
        """Finding counts are accurately tracked."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "HIGH", "Bug", "addressed", "Fixed"),
                        _make_finding(
                            "F-002", "MEDIUM", "Issue", "deferred", "Backlog"
                        ),
                        _make_finding("F-003", "LOW", "Nit", "deferred", "Later"),
                        _make_finding("F-004", "INFO", "Tip", "addressed", "Done"),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert result.total_findings == 4
        assert result.findings_addressed == 2
        assert result.findings_open == 0
        assert result.findings_deferred == 2
        # Should fail because MEDIUM finding was deferred
        assert not result.valid

    def test_severity_case_insensitive(self):
        """Severity values are case-insensitive."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "critical", "Bug", "open", ""),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert not result.valid


# ===========================================================================
# Unit tests: AC3 - Max remediation rounds
# ===========================================================================


class TestAC3MaxRemediationRounds:
    """AC3: Verify remediation does not exceed max rounds."""

    def test_within_limit_passes(self):
        """2 rounds within default limit of 2 passes."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1),
                _make_round(2),
            ],
            critic_reviews=[
                _make_review("cr-1", "2026-03-19T10:30:00Z", 1),
                _make_review("cr-2", "2026-03-19T11:30:00Z", 2),
            ],
        )
        result = validate(evidence)
        ac3_checks = [c for c in result.checks if c.check_id.startswith("AC3")]
        assert all(c.passed for c in ac3_checks)

    def test_exceeds_default_limit_fails(self):
        """3 rounds exceed default limit of 2."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1),
                _make_round(2),
                _make_round(3),
            ],
        )
        result = validate(evidence)
        assert not result.valid
        assert any("max-rounds-exceeded" in c.check_id for c in result.checks)

    def test_custom_limit_lower(self):
        """Custom max_remediation_rounds=1 enforced."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1), _make_round(2)],
            max_remediation_rounds=1,
        )
        result = validate(evidence)
        assert not result.valid

    def test_custom_limit_higher(self):
        """Custom max_remediation_rounds=5 allows 3 rounds."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1),
                _make_round(2),
                _make_round(3),
            ],
            max_remediation_rounds=5,
        )
        result = validate(evidence)
        ac3_checks = [c for c in result.checks if c.check_id.startswith("AC3")]
        assert all(c.passed for c in ac3_checks)

    def test_exceeded_rounds_severity_critical(self):
        """Exceeded max rounds is flagged as CRITICAL severity."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1), _make_round(2), _make_round(3)],
        )
        result = validate(evidence)
        failed_ac3 = [c for c in result.checks if "max-rounds-exceeded" in c.check_id]
        assert len(failed_ac3) == 1
        assert failed_ac3[0].severity == "CRITICAL"


# ===========================================================================
# Integration tests: Full validation scenarios
# ===========================================================================


class TestFullValidation:
    """End-to-end validation tests combining all checks."""

    def test_happy_path_all_pass(self):
        """Complete valid scenario: reviews after remediation, findings addressed."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1, "2026-03-19T10:00:00Z"),
                _make_round(2, "2026-03-19T11:00:00Z"),
            ],
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    [
                        _make_finding(
                            "F-001", "HIGH", "Bug1", "addressed", "Fixed in round 2"
                        ),
                        _make_finding("F-002", "LOW", "Nit", "deferred", "Backlog"),
                    ],
                ),
                _make_review(
                    "cr-2",
                    "2026-03-19T11:30:00Z",
                    2,
                    [
                        _make_finding("F-003", "MEDIUM", "Bug2", "addressed", "Fixed"),
                    ],
                ),
            ],
        )
        result = validate(evidence)
        assert result.valid
        assert result.total_remediation_rounds == 2
        assert result.total_critic_reviews == 2
        assert result.total_findings == 3
        assert result.findings_addressed == 2

    def test_multiple_failures(self):
        """Multiple failures across AC1, AC2, AC3."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1, "2026-03-19T10:00:00Z"),
                _make_round(2, "2026-03-19T11:00:00Z"),
                _make_round(3, "2026-03-19T12:00:00Z"),
            ],
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    [
                        _make_finding("F-001", "HIGH", "Bug", "open", ""),
                    ],
                ),
                # No review for round 2
                # No review for round 3
            ],
        )
        result = validate(evidence)
        assert not result.valid
        # Should have AC1 failure (round 2, 3 missing reviews)
        ac1_fails = [
            c for c in result.checks if c.check_id.startswith("AC1") and not c.passed
        ]
        assert len(ac1_fails) >= 2
        # Should have AC2 failure (open HIGH finding)
        ac2_fails = [
            c for c in result.checks if c.check_id.startswith("AC2") and not c.passed
        ]
        assert len(ac2_fails) >= 1
        # Should have AC3 failure (3 rounds > 2 max)
        ac3_fails = [
            c for c in result.checks if c.check_id.startswith("AC3") and not c.passed
        ]
        assert len(ac3_fails) >= 1

    def test_result_serialisation(self):
        """CriticValidationResult.to_dict produces valid JSON."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round()],
            critic_reviews=[_make_review(findings=[_make_finding()])],
        )
        result = validate(evidence)
        d = result.to_dict()
        # Must be JSON-serialisable
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert "valid" in parsed
        assert "checks" in parsed
        assert "summary" in parsed

    def test_empty_evidence_passes(self):
        """Empty evidence (no rounds, no reviews) passes trivially."""
        evidence = _make_evidence()
        result = validate(evidence)
        assert result.valid
        assert result.total_remediation_rounds == 0
        assert result.total_critic_reviews == 0

    def test_single_round_single_review_single_finding(self):
        """Minimal valid scenario."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    [
                        _make_finding("F-001", "HIGH", "Issue", "addressed", "Fixed"),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert result.valid
        assert result.findings_addressed == 1
        assert result.findings_open == 0

    def test_no_reviews_with_rounds_fails(self):
        """Remediation rounds without any reviews fails."""
        evidence = _make_evidence(
            remediation_rounds=[
                _make_round(1, "2026-03-19T10:00:00Z"),
                _make_round(2, "2026-03-19T11:00:00Z"),
            ],
            critic_reviews=[],
        )
        result = validate(evidence)
        assert not result.valid

    def test_review_with_no_findings_passes(self):
        """Critic review with zero findings is acceptable."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[_make_review("cr-1", "2026-03-19T10:30:00Z", 1)],
        )
        result = validate(evidence)
        assert result.valid
        assert result.total_findings == 0


# ===========================================================================
# CLI / main() tests
# ===========================================================================


class TestCLI:
    """Tests for the main() CLI entry point."""

    def test_main_valid_evidence_json(self, tmp_path):
        """main() returns 0 for valid evidence."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round()],
            critic_reviews=[_make_review()],
        )
        f = tmp_path / "evidence.json"
        f.write_text(json.dumps(evidence))

        ret = (
            _mod.main.__wrapped__(["--evidence", str(f)])
            if hasattr(_mod.main, "__wrapped__")
            else None
        )
        # Use subprocess approach as fallback
        if ret is None:
            import subprocess

            proc = subprocess.run(
                ["python3", str(_MODULE_PATH), "--evidence", str(f)],
                capture_output=True,
                text=True,
            )
            ret = proc.returncode

        assert ret == 0

    def test_main_invalid_evidence_fails(self, tmp_path):
        """main() returns 1 for validation failure."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round()],
            critic_reviews=[],  # No review for round 1
        )
        f = tmp_path / "evidence.json"
        f.write_text(json.dumps(evidence))

        import subprocess

        proc = subprocess.run(
            ["python3", str(_MODULE_PATH), "--evidence", str(f)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "FAIL" in proc.stdout

    def test_main_missing_file(self, tmp_path):
        """main() returns 2 for missing file."""
        import subprocess

        proc = subprocess.run(
            [
                "python3",
                str(_MODULE_PATH),
                "--evidence",
                str(tmp_path / "missing.json"),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2

    def test_main_json_output(self, tmp_path):
        """--json flag produces valid JSON output."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round()],
            critic_reviews=[_make_review()],
        )
        f = tmp_path / "evidence.json"
        f.write_text(json.dumps(evidence))

        import subprocess

        proc = subprocess.run(
            ["python3", str(_MODULE_PATH), "--evidence", str(f), "--json"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        parsed = json.loads(proc.stdout)
        assert "valid" in parsed
        assert parsed["valid"] is True

    def test_main_verbose_output(self, tmp_path):
        """--verbose flag includes details for passed checks."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round()],
            critic_reviews=[_make_review()],
        )
        f = tmp_path / "evidence.json"
        f.write_text(json.dumps(evidence))

        import subprocess

        proc = subprocess.run(
            ["python3", str(_MODULE_PATH), "--evidence", str(f), "--verbose"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        assert "PASS" in proc.stdout


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_finding_with_unknown_status_treated_as_open(self):
        """Unknown finding status treated as open."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "HIGH", "Bug", "in_progress", "Working"),
                    ],
                )
            ],
        )
        result = validate(evidence)
        # Unknown status treated as open -> HIGH open fails
        assert not result.valid

    def test_finding_with_unknown_severity(self):
        """Unknown severity is treated as-is (non-actionable)."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "UNKNOWN", "Something", "open", ""),
                    ],
                )
            ],
        )
        # UNKNOWN severity is not in actionable set, so open is OK
        result = validate(evidence)
        ac2_checks = [c for c in result.checks if c.check_id.startswith("AC2")]
        assert all(c.passed for c in ac2_checks)

    def test_empty_rounds_list(self):
        """Empty rounds list passes."""
        evidence = _make_evidence(remediation_rounds=[])
        result = validate(evidence)
        assert result.valid

    def test_empty_reviews_list(self):
        """Empty reviews list with rounds fails (AC1)."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round()],
            critic_reviews=[],
        )
        result = validate(evidence)
        assert not result.valid

    def test_multiple_reviews_for_same_round(self):
        """Multiple reviews for the same round passes if one is after."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round(1, "2026-03-19T10:00:00Z")],
            critic_reviews=[
                _make_review("cr-1", "2026-03-19T09:00:00Z", 1),
                _make_review("cr-2", "2026-03-19T10:30:00Z", 1),
            ],
        )
        result = validate(evidence)
        ac1_checks = [c for c in result.checks if c.check_id.startswith("AC1")]
        assert all(c.passed for c in ac1_checks)

    def test_finding_without_resolution_text(self):
        """Finding addressed but with empty resolution still passes."""
        evidence = _make_evidence(
            critic_reviews=[
                _make_review(
                    "cr-1",
                    "2026-03-19T10:30:00Z",
                    1,
                    findings=[
                        _make_finding("F-001", "HIGH", "Bug", "addressed", ""),
                    ],
                )
            ],
        )
        result = validate(evidence)
        assert result.valid

    def test_max_rounds_zero_with_rounds(self):
        """max_remediation_rounds=0 fails with any rounds."""
        evidence = _make_evidence(
            remediation_rounds=[_make_round()],
            max_remediation_rounds=0,
        )
        result = validate(evidence)
        assert not result.valid
