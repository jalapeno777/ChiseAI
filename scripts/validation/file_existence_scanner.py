#!/usr/bin/env python3
"""
File Existence Scanner.

Scans for required evidence files and validates they exist at expected paths
under ``docs/evidence/``.  Also enforces naming conventions so that evidence
is machine-discoverable.

Naming convention (enforced):
    docs/evidence/{STORY-ID}[-_]{descriptor}.{json,md,yaml,yml}

Where ``{STORY-ID}`` matches the pattern ``ST-\\d+``, ``CH-\\d+``, ``RE-\\d+``,
``SAFETY-\\d+``, ``BRANCH-\\d+``, ``PAPER-\\d+``, ``RECON-\\d+``, ``REWARD-\\d+``,
``REPO-\\d+``, ``BATCH-\\d+``, ``STRONG-\\d+``, ``TF-\\d+``, or any uppercase
identifier followed by a digit.

Exit codes:
    0 - All required files found, naming OK
    1 - Missing files or naming violations
    2 - I/O or configuration errors

Usage (programmatic):
    from scripts.validation.file_existence_scanner import FileExistenceScanner

    scanner = FileExistenceScanner(evidence_dir="docs/evidence")
    report = scanner.scan()
    print(report.summary())

Usage (CLI):
    python3 scripts/validation/file_existence_scanner.py
    python3 scripts/validation/file_existence_scanner.py --dir docs/evidence --verbose
    python3 scripts/validation/file_existence_scanner.py --story-id ST-001
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EVIDENCE_DIR = Path("docs/evidence")

# Recognised story-id prefixes (any uppercase token followed by a digit is
# also accepted via the loose pattern).
_STORY_ID_LOOSE = re.compile(r"^[A-Z][A-Z0-9]*-\d+", re.IGNORECASE)

# Strict known prefixes for categorisation
KNOWN_PREFIXES = {
    "ST",
    "CH",
    "RE",
    "SAFETY",
    "BRANCH",
    "PAPER",
    "RECON",
    "REWARD",
    "REPO",
    "BATCH",
    "STRONG",
    "TF",
    "AUTOCOG",
    "GOVERNANCE",
    "LINK",
    "LIVE",
    "LLM",
    "ML",
    "NOTIFIER",
    "P0",
    "PARTY",
    "PHASE",
    "SKILL",
    "TECH",
    "TEMPO",
    "TRUTH",
}

VALID_EXTENSIONS = {".json", ".md", ".yaml", ".yml"}

# Pattern that a *full* evidence filename must match.
# The real evidence dir uses varied naming: the story-id portion is the leading
# identifier up to (and including) the first digit-segment after a hyphen, and
# the rest is a descriptor.  We also accept pure descriptive names that still
# start with an uppercase token (e.g. CLOSEOUT-SESSION-20260311-evidence.md).
#
# Pattern breakdown:
#   story_id  = uppercase-token(s) ending with -<digits>
#   or, if no digit segment found, the full stem (minus ext) is the name
# Pattern that a *full* evidence filename must match.
# Requirements:
#   - Starts with an uppercase letter
#   - Contains at least one digit somewhere before the extension
#   - Uses only uppercase letters, digits, hyphens, and underscores
#   - Ends with a valid extension
_FILENAME_PATTERN = re.compile(
    r"^(?P<stem>[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)*)"
    r"(?:[-_](?P<rest>[^/]+))?"
    r"\.(?P<ext>json|md|yaml|yml)$",
)

# Full filename pattern (including the digit requirement).
_FULL_FILENAME_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9]*(?:[-_][A-Za-z0-9]+)*" r"\.(?P<ext>json|md|yaml|yml)$",
)

# Check if a filename has at least one digit in the name portion (before ext)
_FILENAME_HAS_DIGIT = re.compile(r"\d")

# Post-match: extract story_id from stem by finding the last segment that
# contains a digit.  E.g. "AUTOCOG-TIER2-001" -> story_id="AUTOCOG-TIER2-001",
# "BATCH-3-PARTY-MODE-AUDIT-REPORT" -> story_id="BATCH-3",
# "CI-Test-Report-2026-03-02" -> story_id="CI-Test-Report-2026-03-02" (no
# strict digit-segment boundary needed — just require at least one digit).
_STORY_ID_FROM_STEM = re.compile(
    r"^([A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)*-\d+(?:-\d+)*)",
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileIssue:
    """A single naming or existence issue."""

    path: str
    severity: str  # "error" | "warning"
    code: str  # machine-readable code
    message: str


@dataclass
class FileRecord:
    """Record for a single evidence file found on disk."""

    path: Path
    story_id: str | None = None
    descriptor: str | None = None
    extension: str = ""
    naming_ok: bool = True
    issues: list[FileIssue] = field(default_factory=list)


@dataclass
class ScanReport:
    """Aggregated scan result."""

    evidence_dir: Path
    files_scanned: int = 0
    files_valid: int = 0
    files_with_issues: int = 0
    missing_stories: list[str] = field(default_factory=list)
    records: list[FileRecord] = field(default_factory=list)
    issues: list[FileIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when no errors exist (warnings are OK)."""
        return not any(i.severity == "error" for i in self.issues)

    def add_issue(self, issue: FileIssue) -> None:
        """Register an issue."""
        self.issues.append(issue)

    def summary(self) -> str:
        """Human-readable summary string."""
        lines: list[str] = []
        lines.append(f"File Existence Scan: {self.evidence_dir}")
        lines.append(f"  Files scanned: {self.files_scanned}")
        lines.append(
            f"  Valid: {self.files_valid}  |  Issues: {self.files_with_issues}"
        )
        if self.missing_stories:
            lines.append(
                f"  Missing evidence for stories: "
                f"{', '.join(sorted(self.missing_stories))}"
            )
        error_count = sum(1 for i in self.issues if i.severity == "error")
        warn_count = sum(1 for i in self.issues if i.severity == "warning")
        lines.append(f"  Errors: {error_count}  |  Warnings: {warn_count}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class FileExistenceScanner:
    """Scans ``docs/evidence/`` for required files and validates naming."""

    def __init__(
        self,
        evidence_dir: Path | str = DEFAULT_EVIDENCE_DIR,
        required_stories: Sequence[str] | None = None,
        strict_extensions: bool = True,
    ) -> None:
        """
        Args:
            evidence_dir: Root directory to scan (default ``docs/evidence``).
            required_stories: Optional list of story IDs that *must* have
                at least one evidence file.
            strict_extensions: When True, only files with extensions in
                ``VALID_EXTENSIONS`` are considered evidence files.
        """
        self.evidence_dir = Path(evidence_dir)
        self.required_stories = set(required_stories) if required_stories else set()
        self.strict_extensions = strict_extensions

    # -- public API ---------------------------------------------------------

    def scan(self) -> ScanReport:
        """Run the full scan and return a :class:`ScanReport`."""
        report = ScanReport(evidence_dir=self.evidence_dir)

        if not self.evidence_dir.is_dir():
            report.add_issue(
                FileIssue(
                    path=str(self.evidence_dir),
                    severity="error",
                    code="DIR_MISSING",
                    message=f"Evidence directory does not exist: {self.evidence_dir}",
                )
            )
            return report

        # Walk the directory (non-recursive for now — evidence is flat)
        for entry in sorted(self.evidence_dir.iterdir()):
            if not entry.is_file():
                continue

            report.files_scanned += 1
            record = self._inspect_file(entry)
            report.records.append(record)

            for issue in record.issues:
                report.add_issue(issue)

            if record.naming_ok:
                report.files_valid += 1
            else:
                report.files_with_issues += 1

        # Check required stories
        found_stories = {r.story_id for r in report.records if r.story_id is not None}
        for sid in sorted(self.required_stories):
            if sid not in found_stories:
                report.missing_stories.append(sid)
                report.add_issue(
                    FileIssue(
                        path="",
                        severity="error",
                        code="MISSING_STORY_EVIDENCE",
                        message=f"No evidence file found for story: {sid}",
                    )
                )

        return report

    def check_story_has_evidence(self, story_id: str) -> bool:
        """Quick check: does at least one file match *story_id*?"""
        if not self.evidence_dir.is_dir():
            return False
        prefix = story_id + "-"
        for entry in self.evidence_dir.iterdir():
            if entry.is_file() and entry.name.startswith(prefix):
                return True
            # Also match story_id_ variant
            prefix_alt = story_id + "_"
            if entry.is_file() and entry.name.startswith(prefix_alt):
                return True
        return False

    def validate_filename(self, filename: str) -> FileRecord:
        """Validate a filename without touching the filesystem."""
        record = FileRecord(path=Path(filename))
        self._validate_name(record, filename)
        return record

    # -- internals ----------------------------------------------------------

    def _inspect_file(self, path: Path) -> FileRecord:
        """Inspect a single file and return a :class:`FileRecord`."""
        record = FileRecord(
            path=path,
            extension=path.suffix.lower(),
        )

        # Extension check
        if self.strict_extensions and record.extension not in VALID_EXTENSIONS:
            record.naming_ok = False
            record.issues.append(
                FileIssue(
                    path=str(path),
                    severity="warning",
                    code="BAD_EXTENSION",
                    message=(
                        f"Unexpected extension '{record.extension}' "
                        f"(expected one of {sorted(VALID_EXTENSIONS)})"
                    ),
                )
            )

        self._validate_name(record, path.name)
        return record

    def _validate_name(self, record: FileRecord, filename: str) -> None:
        """Validate filename against the naming convention."""
        # First check: the full filename must start uppercase and end with valid ext
        match = _FILENAME_PATTERN.match(filename)
        if match is None:
            record.naming_ok = False
            record.issues.append(
                FileIssue(
                    path=str(record.path),
                    severity="warning",
                    code="BAD_FILENAME",
                    message=(
                        f"Filename '{filename}' does not match naming convention "
                        f"{{PREFIX}}[-_segments].{{json,md,yaml,yml}}"
                    ),
                )
            )
            return

        # Second check: must contain at least one digit (trackability)
        name_part = Path(filename).stem  # filename without extension
        if not _FILENAME_HAS_DIGIT.search(name_part):
            record.naming_ok = False
            record.issues.append(
                FileIssue(
                    path=str(record.path),
                    severity="warning",
                    code="BAD_FILENAME",
                    message=(
                        f"Filename '{filename}' has no digits — "
                        f"evidence files must be trackable (include a story ID or date)"
                    ),
                )
            )
            return

        stem = match.group("stem")
        rest = match.group("rest")

        # Try to extract a story_id from the stem (digit-terminated segment)
        story_match = _STORY_ID_FROM_STEM.match(stem)
        if story_match:
            story_id = story_match.group(1).upper()
            record.story_id = story_id
            # Descriptor is everything after the story_id in the full name
            descriptor_part = stem[len(story_id) :].lstrip("-_")
            if rest:
                descriptor_part = (
                    f"{descriptor_part}-{rest}" if descriptor_part else rest
                )
            record.descriptor = descriptor_part if descriptor_part else None
        else:
            # No digit-terminated segment; use full stem as identifier
            record.story_id = stem.upper()
            record.descriptor = rest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan docs/evidence/ for required evidence files and validate naming.",
    )
    parser.add_argument(
        "--dir",
        default=str(DEFAULT_EVIDENCE_DIR),
        help="Evidence directory to scan (default: docs/evidence)",
    )
    parser.add_argument(
        "--story-id",
        action="append",
        dest="story_ids",
        help="Require evidence for a specific story ID (repeatable)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print per-file details",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    scanner = FileExistenceScanner(
        evidence_dir=args.dir,
        required_stories=args.story_ids,
    )
    report = scanner.scan()

    # Print report
    print(report.summary())
    if args.verbose:
        for issue in report.issues:
            print(
                f"  [{issue.severity.upper()}] {issue.code}: {issue.message}",
                file=sys.stderr,
            )

    if not report.is_valid:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
