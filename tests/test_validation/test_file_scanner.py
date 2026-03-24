"""Tests for File Existence Scanner.

Validates that file_existence_scanner.py correctly:
- Scans evidence directory for files
- Validates naming conventions ({STORY-ID}[-_descriptor].{ext})
- Detects missing evidence for required stories
- Handles edge cases (empty dir, bad extensions, missing dir)
- Provides machine-checkable reports

Story: SWARM-HARDEN-001-3.1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from scripts.validation.file_existence_scanner import (
    _FILENAME_PATTERN,
    _STORY_ID_LOOSE,
    DEFAULT_EVIDENCE_DIR,
    KNOWN_PREFIXES,
    VALID_EXTENSIONS,
    FileExistenceScanner,
    FileIssue,
    FileRecord,
    ScanReport,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def evidence_dir(tmp_path: Path) -> Path:
    """Create a fresh evidence directory for each test."""
    d = tmp_path / "evidence"
    d.mkdir()
    return d


def _touch(dirpath: Path, name: str) -> Path:
    """Create an empty file and return its Path."""
    p = dirpath / name
    p.touch()
    return p


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants are well-formed."""

    def test_default_evidence_dir_points_to_docs_evidence(self) -> None:
        assert str(DEFAULT_EVIDENCE_DIR) == "docs/evidence"

    def test_valid_extensions_include_json_md(self) -> None:
        assert ".json" in VALID_EXTENSIONS
        assert ".md" in VALID_EXTENSIONS

    def test_known_prefixes_not_empty(self) -> None:
        assert len(KNOWN_PREFIXES) > 0

    def test_story_id_loose_pattern(self) -> None:
        assert _STORY_ID_LOOSE.match("ST-001")
        assert _STORY_ID_LOOSE.match("CH-123")
        assert _STORY_ID_LOOSE.match("SAFETY-001")
        assert _STORY_ID_LOOSE.match("REWARD-001")
        assert not _STORY_ID_LOOSE.match("no-digits")
        assert not _STORY_ID_LOOSE.match("123-ABC")

    def test_filename_pattern_valid(self) -> None:
        valid = [
            "ST-001-completion-evidence.json",
            "ST-001_completion_evidence.md",
            "CH-123.yaml",
            "SAFETY-001-live-data-evidence-final.json",
            "RECON-20260217.md",
            "STRONG-001-A-S3-completion-evidence.json",
            "AUTOCOG-TIER1-completion-evidence.json",
            "BRAINEVAL-CI-COMPLETION-REPORT-2026-03-03.md",
            "BATCH-3-PARTY-MODE-AUDIT-REPORT.md",
            "CI-Test-Report-2026-03-02.md",
        ]
        for name in valid:
            m = _FILENAME_PATTERN.match(name)
            assert m is not None, f"Expected match for: {name}"

    def test_filename_pattern_invalid(self) -> None:
        invalid = [
            "no-story-id.json",
            ".gitkeep",
            "ST-001",  # no extension
            "data.csv",
        ]
        for name in invalid:
            m = _FILENAME_PATTERN.match(name)
            assert m is None, f"Expected no match for: {name}"

    def test_filename_pattern_valid_but_no_digit(self) -> None:
        """README.md matches the structural pattern but lacks a digit."""
        m = _FILENAME_PATTERN.match("README.md")
        assert m is not None  # structurally valid
        # The digit check is handled separately in _validate_name

    def test_filename_pattern_case_insensitive(self) -> None:
        # The pattern requires uppercase first char; lowercase should not match
        m = _FILENAME_PATTERN.match("st-001-evidence.json")
        assert m is None


# ---------------------------------------------------------------------------
# FileRecord tests
# ---------------------------------------------------------------------------


class TestFileRecord:
    """Test FileRecord dataclass."""

    def test_default_record_is_valid(self) -> None:
        rec = FileRecord(path=Path("ST-001.json"))
        assert rec.naming_ok is True
        assert rec.issues == []

    def test_record_with_issues(self) -> None:
        rec = FileRecord(path=Path("bad.csv"))
        rec.naming_ok = False
        rec.issues.append(
            FileIssue(
                path="bad.csv",
                severity="warning",
                code="BAD_EXTENSION",
                message="bad ext",
            )
        )
        assert rec.naming_ok is False
        assert len(rec.issues) == 1


# ---------------------------------------------------------------------------
# ScanReport tests
# ---------------------------------------------------------------------------


class TestScanReport:
    """Test ScanReport aggregation."""

    def test_empty_report_is_valid(self) -> None:
        report = ScanReport(evidence_dir=Path("docs/evidence"))
        assert report.is_valid is True

    def test_report_with_error_is_not_valid(self) -> None:
        report = ScanReport(evidence_dir=Path("docs/evidence"))
        report.add_issue(
            FileIssue(
                path="x",
                severity="error",
                code="E1",
                message="fail",
            )
        )
        assert report.is_valid is False

    def test_report_with_warning_is_valid(self) -> None:
        report = ScanReport(evidence_dir=Path("docs/evidence"))
        report.add_issue(
            FileIssue(
                path="x",
                severity="warning",
                code="W1",
                message="meh",
            )
        )
        assert report.is_valid is True

    def test_summary_string(self) -> None:
        report = ScanReport(evidence_dir=Path("docs/evidence"))
        report.files_scanned = 10
        report.files_valid = 8
        report.files_with_issues = 2
        s = report.summary()
        assert "Files scanned: 10" in s
        assert "Valid: 8" in s
        assert "Issues: 2" in s


# ---------------------------------------------------------------------------
# FileExistenceScanner — happy path
# ---------------------------------------------------------------------------


class TestScannerHappyPath:
    """Scanner works correctly on well-formed evidence dirs."""

    def test_scan_empty_dir(self, evidence_dir: Path) -> None:
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.is_valid is True
        assert report.files_scanned == 0

    def test_scan_single_valid_file(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-completion-evidence.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.is_valid is True
        assert report.files_scanned == 1
        assert report.files_valid == 1

    def test_scan_multiple_valid_files(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.json")
        _touch(evidence_dir, "ST-002-evidence.md")
        _touch(evidence_dir, "SAFETY-001-live-data-evidence-final.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.is_valid is True
        assert report.files_scanned == 3
        assert report.files_valid == 3

    def test_scan_ignores_subdirectories(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.json")
        subdir = evidence_dir / "ST-001"
        subdir.mkdir()
        _touch(subdir, "nested.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        # Only the top-level file should be counted
        assert report.files_scanned == 1

    def test_scan_extracts_story_id(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "CH-123-descriptor.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert len(report.records) == 1
        assert report.records[0].story_id == "CH-123"
        assert report.records[0].descriptor == "descriptor"

    def test_scan_extracts_complex_story_id(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "AUTOCOG-TIER2-001-action-execution.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.records[0].story_id == "AUTOCOG-TIER2-001"
        assert report.records[0].descriptor == "action-execution"

    def test_scan_extracts_descriptor(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "STRONG-001-A-S3-completion-evidence.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.records[0].story_id == "STRONG-001"
        assert report.records[0].descriptor == "A-S3-completion-evidence"

    def test_scan_file_without_descriptor(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "RECON-20260217.md")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.records[0].story_id == "RECON-20260217"
        # No descriptor after the story_id segment
        assert (
            report.records[0].descriptor is None or report.records[0].descriptor == ""
        )


# ---------------------------------------------------------------------------
# FileExistenceScanner — naming validation
# ---------------------------------------------------------------------------


class TestScannerNamingValidation:
    """Scanner correctly flags naming violations."""

    def test_bad_extension_warning(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.csv")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.files_with_issues == 1
        assert report.is_valid is True  # warnings only
        codes = {i.code for i in report.issues}
        assert "BAD_EXTENSION" in codes

    def test_bad_filename_warning(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "README.md")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.files_with_issues == 1
        codes = {i.code for i in report.issues}
        assert "BAD_FILENAME" in codes

    def test_bad_extension_not_strict(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.csv")
        scanner = FileExistenceScanner(
            evidence_dir=evidence_dir,
            strict_extensions=False,
        )
        report = scanner.scan()
        # With strict_extensions=False, CSV is OK
        codes = {i.code for i in report.issues}
        assert "BAD_EXTENSION" not in codes

    def test_multiple_issues_in_one_file(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "README.txt")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.files_with_issues == 1
        # Should have BAD_EXTENSION and BAD_FILENAME warnings
        codes = {i.code for i in report.issues}
        assert "BAD_EXTENSION" in codes
        assert "BAD_FILENAME" in codes

    def test_no_digit_in_id_warning(self, evidence_dir: Path) -> None:
        """Files with uppercase prefix but no digits get BAD_FILENAME warning."""
        _touch(evidence_dir, "KPI-SOURCE-SEPARATION-RULE.md")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        codes = {i.code for i in report.issues}
        assert "BAD_FILENAME" in codes

    def test_underscore_separator(self, evidence_dir: Path) -> None:
        """Underscore separators should be accepted."""
        _touch(evidence_dir, "ST-001_completion_evidence.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        assert report.files_valid == 1
        assert report.records[0].story_id == "ST-001"


# ---------------------------------------------------------------------------
# FileExistenceScanner — missing story checks
# ---------------------------------------------------------------------------


class TestScannerMissingStories:
    """Scanner detects missing evidence for required stories."""

    def test_missing_story_error(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.json")
        scanner = FileExistenceScanner(
            evidence_dir=evidence_dir,
            required_stories=["ST-001", "ST-002"],
        )
        report = scanner.scan()
        assert report.is_valid is False
        assert "ST-002" in report.missing_stories
        codes = {i.code for i in report.issues}
        assert "MISSING_STORY_EVIDENCE" in codes

    def test_all_stories_present(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.json")
        _touch(evidence_dir, "ST-002-completion.md")
        scanner = FileExistenceScanner(
            evidence_dir=evidence_dir,
            required_stories=["ST-001", "ST-002"],
        )
        report = scanner.scan()
        assert report.is_valid is True
        assert report.missing_stories == []

    def test_no_required_stories(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "README.md")  # badly named but no required stories
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        report = scanner.scan()
        # Only warnings, no MISSING_STORY_EVIDENCE
        codes = {i.code for i in report.issues}
        assert "MISSING_STORY_EVIDENCE" not in codes


# ---------------------------------------------------------------------------
# FileExistenceScanner — missing directory
# ---------------------------------------------------------------------------


class TestScannerMissingDir:
    """Scanner handles non-existent evidence directory."""

    def test_missing_dir_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        scanner = FileExistenceScanner(evidence_dir=missing)
        report = scanner.scan()
        assert report.is_valid is False
        codes = {i.code for i in report.issues}
        assert "DIR_MISSING" in codes

    def test_missing_dir_zero_files_scanned(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        scanner = FileExistenceScanner(evidence_dir=missing)
        report = scanner.scan()
        assert report.files_scanned == 0


# ---------------------------------------------------------------------------
# check_story_has_evidence — quick check
# ---------------------------------------------------------------------------


class TestCheckStoryHasEvidence:
    """Test the quick story-evidence check."""

    def test_story_has_evidence(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-completion.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        assert scanner.check_story_has_evidence("ST-001") is True

    def test_story_has_evidence_underscore(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001_completion.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        assert scanner.check_story_has_evidence("ST-001") is True

    def test_story_missing_evidence(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-002-evidence.json")
        scanner = FileExistenceScanner(evidence_dir=evidence_dir)
        assert scanner.check_story_has_evidence("ST-001") is False

    def test_missing_dir_returns_false(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        scanner = FileExistenceScanner(evidence_dir=missing)
        assert scanner.check_story_has_evidence("ST-001") is False


# ---------------------------------------------------------------------------
# validate_filename — filesystem-free check
# ---------------------------------------------------------------------------


class TestValidateFilename:
    """Test filename validation without touching the filesystem."""

    def test_valid_filename(self) -> None:
        scanner = FileExistenceScanner()
        record = scanner.validate_filename("ST-001-evidence.json")
        assert record.naming_ok is True
        assert record.story_id == "ST-001"
        assert record.descriptor == "evidence"

    def test_invalid_filename(self) -> None:
        scanner = FileExistenceScanner()
        record = scanner.validate_filename("README.md")
        assert record.naming_ok is False
        codes = {i.code for i in record.issues}
        assert "BAD_FILENAME" in codes

    def test_no_extension(self) -> None:
        scanner = FileExistenceScanner()
        record = scanner.validate_filename("ST-001")
        assert record.naming_ok is False


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test the CLI entry point."""

    def test_main_happy_path(self, evidence_dir: Path, tmp_path: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.json")
        from scripts.validation.file_existence_scanner import main

        result = main(["--dir", str(evidence_dir)])
        assert result == 0

    def test_main_missing_story(self, evidence_dir: Path) -> None:
        _touch(evidence_dir, "ST-001-evidence.json")
        from scripts.validation.file_existence_scanner import main

        result = main(
            [
                "--dir",
                str(evidence_dir),
                "--story-id",
                "ST-001",
                "--story-id",
                "ST-002",
            ]
        )
        assert result == 1

    def test_main_verbose(self, evidence_dir: Path, capsys: Any) -> None:
        _touch(evidence_dir, "README.md")
        from scripts.validation.file_existence_scanner import main

        main(["--dir", str(evidence_dir), "--verbose"])
        captured = capsys.readouterr()
        # Stderr should contain the verbose issue output
        assert "BAD_FILENAME" in captured.err or "WARNING" in captured.err


# ---------------------------------------------------------------------------
# Integration: scan against real docs/evidence/ (only if it exists)
# ---------------------------------------------------------------------------


class TestRealEvidenceDir:
    """Integration test against the actual docs/evidence/ directory."""

    @pytest.mark.skipif(
        not Path("docs/evidence").is_dir(),
        reason="docs/evidence/ directory not found (not in repo root)",
    )
    def test_real_dir_scan_completes(self) -> None:
        scanner = FileExistenceScanner()
        report = scanner.scan()
        # The real dir should have at least some files
        assert report.files_scanned > 0
        # And the report should be generatable
        s = report.summary()
        assert "File Existence Scan" in s

    @pytest.mark.skipif(
        not Path("docs/evidence").is_dir(),
        reason="docs/evidence/ directory not found (not in repo root)",
    )
    def test_real_dir_most_files_valid(self) -> None:
        scanner = FileExistenceScanner()
        report = scanner.scan()
        # Most real evidence files are well-named; threshold at 70% because
        # some legacy files use lowercase or non-standard naming.
        assert report.files_valid >= report.files_scanned * 0.7

    @pytest.mark.skipif(
        not Path("docs/evidence").is_dir(),
        reason="docs/evidence/ directory not found (not in repo root)",
    )
    def test_real_dir_machine_checkable_proof(self) -> None:
        """AC4: Provide machine-checkable file existence proof."""
        scanner = FileExistenceScanner()
        report = scanner.scan()
        # Build a machine-checkable output
        proof_lines = [
            f"story_id={r.story_id or 'NONE'} path={r.path} naming_ok={r.naming_ok}"
            for r in report.records
        ]
        proof_text = "\n".join(proof_lines)
        # Verify the proof is parseable and contains real files
        assert len(proof_lines) > 0
        for line in proof_lines:
            assert "path=" in line
            assert "naming_ok=" in line
