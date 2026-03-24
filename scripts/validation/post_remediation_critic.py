#!/usr/bin/env python3
"""
Post-Remediation Critic Validator.

Validates that critic reviews were performed after remediation rounds and
that critic findings were addressed. This implements the Swarm Policy
Hardening requirement for the Critic and Remediation Loop (Section F).

Checks performed:
    AC1 - Critic reviews exist after each remediation round (timestamp ordering)
    AC2 - All critic findings flagged as severity >= MEDIUM have been addressed
    AC3 - Remediation rounds that exceed the max remediation limit (2) are flagged

Exit codes:
    0 - All validations passed
    1 - One or more validations failed
    2 - Script error (file not found, parse error, etc.)

Usage:
    python3 scripts/validation/post_remediation_critic.py --evidence <file>
    python3 scripts/validation/post_remediation_critic.py --evidence <file> --verbose
    python3 scripts/validation/post_remediation_critic.py --evidence <file> --json

Evidence file format (YAML or JSON):
    remediation_rounds:
      - round: 1
        timestamp: "2026-03-19T10:00:00Z"
        description: "Fixed validation gate failures"
        files_changed: ["scripts/validation/foo.py"]
        evidence_ref: "docs/evidence/fix-round1.md"
      - round: 2
        timestamp: "2026-03-19T11:00:00Z"
        description: "Addressed critic findings from round 1"
        files_changed: ["scripts/validation/foo.py"]
        evidence_ref: "docs/evidence/fix-round2.md"
    critic_reviews:
      - review_id: "critic-001"
        timestamp: "2026-03-19T10:30:00Z"
        round_reviewed: 1
        findings:
          - finding_id: "F-001"
            severity: "HIGH"
            description: "Missing input validation"
            status: "addressed"
            resolution: "Added bounds checking in validate() method"
          - finding_id: "F-002"
            severity: "LOW"
            description: "Minor docstring formatting"
            status: "deferred"
            resolution: "Deferred to tech debt backlog"
    max_remediation_rounds: 2
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Critic finding severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


class FindingStatus(str, Enum):
    """Status of a critic finding."""

    ADDRESSED = "addressed"
    DEFERRED = "deferred"
    OPEN = "open"
    WONT_FIX = "wont_fix"


@dataclass
class CriticFinding:
    """A single finding from a critic review."""

    finding_id: str
    severity: str
    description: str
    status: str = "open"
    resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CriticFinding:
        return cls(
            finding_id=data.get("finding_id", ""),
            severity=data.get("severity", "INFO").upper(),
            description=data.get("description", ""),
            status=data.get("status", "open").lower(),
            resolution=data.get("resolution", ""),
        )


@dataclass
class CriticReview:
    """A critic review performed after a remediation round."""

    review_id: str
    timestamp: str
    round_reviewed: int
    findings: list[CriticFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "timestamp": self.timestamp,
            "round_reviewed": self.round_reviewed,
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CriticReview:
        findings = [CriticFinding.from_dict(f) for f in data.get("findings", [])]
        return cls(
            review_id=data.get("review_id", ""),
            timestamp=data.get("timestamp", ""),
            round_reviewed=data.get("round_reviewed", 0),
            findings=findings,
        )

    def parsed_timestamp(self) -> datetime:
        """Parse ISO timestamp to datetime."""
        # Handle various ISO formats
        ts = self.timestamp.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=UTC)


@dataclass
class RemediationRound:
    """A single remediation round."""

    round: int
    timestamp: str
    description: str = ""
    files_changed: list[str] = field(default_factory=list)
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RemediationRound:
        return cls(
            round=data.get("round", 0),
            timestamp=data.get("timestamp", ""),
            description=data.get("description", ""),
            files_changed=data.get("files_changed", []),
            evidence_ref=data.get("evidence_ref", ""),
        )

    def parsed_timestamp(self) -> datetime:
        """Parse ISO timestamp to datetime."""
        ts = self.timestamp.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=UTC)


@dataclass
class CheckResult:
    """Result of a single validation check."""

    check_id: str
    description: str
    passed: bool
    details: str = ""
    severity: str = "MEDIUM"  # severity of the violation if not passed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CriticValidationResult:
    """Complete validation result for post-remediation critic check."""

    valid: bool = True
    checks: list[CheckResult] = field(default_factory=list)
    total_remediation_rounds: int = 0
    total_critic_reviews: int = 0
    total_findings: int = 0
    findings_addressed: int = 0
    findings_open: int = 0
    findings_deferred: int = 0

    def add_check(self, check: CheckResult) -> None:
        """Add a check result."""
        self.checks.append(check)
        if not check.passed:
            self.valid = False

    def add_error(
        self,
        check_id: str,
        description: str,
        details: str = "",
        severity: str = "MEDIUM",
    ) -> None:
        """Add a failed check."""
        self.add_check(
            CheckResult(
                check_id=check_id,
                description=description,
                passed=False,
                details=details,
                severity=severity,
            )
        )

    def add_pass(self, check_id: str, description: str, details: str = "") -> None:
        """Add a passed check."""
        self.add_check(
            CheckResult(
                check_id=check_id,
                description=description,
                passed=True,
                details=details,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "checks": [c.to_dict() for c in self.checks],
            "summary": {
                "total_remediation_rounds": self.total_remediation_rounds,
                "total_critic_reviews": self.total_critic_reviews,
                "total_findings": self.total_findings,
                "findings_addressed": self.findings_addressed,
                "findings_open": self.findings_open,
                "findings_deferred": self.findings_deferred,
            },
        }

    def print_report(self, verbose: bool = False) -> None:
        """Print human-readable report."""
        status = "PASS" if self.valid else "FAIL"
        print(f"\n{'=' * 60}")
        print(f"Post-Remediation Critic Validation: {status}")
        print(f"{'=' * 60}")

        for check in self.checks:
            icon = "+" if check.passed else "x"
            print(f"  [{icon}] {check.description}")
            if not check.passed or verbose:
                print(f"      {check.details}")

        print("\nSummary:")
        print(f"  Remediation rounds: {self.total_remediation_rounds}")
        print(f"  Critic reviews:    {self.total_critic_reviews}")
        print(f"  Total findings:    {self.total_findings}")
        print(f"  Addressed:         {self.findings_addressed}")
        print(f"  Open:              {self.findings_open}")
        print(f"  Deferred:          {self.findings_deferred}")
        print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Evidence loading
# ---------------------------------------------------------------------------


def load_evidence(file_path: Path) -> dict[str, Any]:
    """Load evidence from a YAML or JSON file.

    Args:
        file_path: Path to the evidence file.

    Returns:
        Parsed dictionary.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file format is unsupported or parsing fails.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Evidence file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8").strip()

    if file_path.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise ValueError("PyYAML is required to parse YAML files")
        data = yaml.safe_load(content)
    elif file_path.suffix == ".json":
        data = json.loads(content)
    else:
        # Try JSON first, then YAML
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            if yaml is not None:
                try:
                    data = yaml.safe_load(content)
                except yaml.YAMLError as e:
                    raise ValueError(f"Failed to parse file as JSON or YAML: {e}")
            else:
                raise ValueError(
                    f"Unsupported file extension: {file_path.suffix}. "
                    "Use .json, .yaml, or .yml"
                )

    if not isinstance(data, dict):
        raise ValueError("Evidence file must contain a top-level object/dict")

    return data


def parse_remediation_rounds(data: dict[str, Any]) -> list[RemediationRound]:
    """Parse remediation rounds from evidence data."""
    rounds_data = data.get("remediation_rounds", [])
    rounds = []
    for rd in rounds_data:
        rounds.append(RemediationRound.from_dict(rd))
    # Sort by round number
    rounds.sort(key=lambda r: r.round)
    return rounds


def parse_critic_reviews(data: dict[str, Any]) -> list[CriticReview]:
    """Parse critic reviews from evidence data."""
    reviews_data = data.get("critic_reviews", [])
    reviews = []
    for rd in reviews_data:
        reviews.append(CriticReview.from_dict(rd))
    # Sort by timestamp
    reviews.sort(key=lambda r: r.parsed_timestamp())
    return reviews


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------


def check_critic_reviews_after_remediation(
    rounds: list[RemediationRound],
    reviews: list[CriticReview],
    result: CriticValidationResult,
) -> None:
    """AC1: Verify critic reviews exist after each remediation round.

    For each remediation round, there must be at least one critic review
    with a timestamp >= the remediation round's timestamp.
    """
    if not rounds:
        result.add_pass(
            "AC1-no-rounds",
            "No remediation rounds to validate",
            "No remediation rounds present; nothing to check.",
        )
        return

    # Build a lookup: round_number -> list of reviews for that round
    review_by_round: dict[int, list[CriticReview]] = {}
    for review in reviews:
        review_by_round.setdefault(review.round_reviewed, []).append(review)

    for rem_round in rounds:
        matching_reviews = review_by_round.get(rem_round.round, [])

        if not matching_reviews:
            result.add_error(
                "AC1-missing-review",
                f"No critic review found for remediation round {rem_round.round}",
                f"Remediation round {rem_round.round} "
                f"(timestamp: {rem_round.timestamp}) has no corresponding "
                f"critic review. At least one critic review with "
                f"round_reviewed={rem_round.round} is required.",
                severity="HIGH",
            )
            continue

        # Check that at least one review timestamp is after the remediation
        rem_ts = rem_round.parsed_timestamp()
        review_after = False
        for review in matching_reviews:
            if review.parsed_timestamp() >= rem_ts:
                review_after = True
                break

        if review_after:
            result.add_pass(
                f"AC1-round-{rem_round.round}",
                f"Critic review exists after remediation round {rem_round.round}",
                f"Found {len(matching_reviews)} review(s) for round {rem_round.round}.",
            )
        else:
            result.add_error(
                f"AC1-timing-{rem_round.round}",
                f"Critic review timestamp precedes remediation round {rem_round.round}",
                f"Remediation round {rem_round.round} timestamp "
                f"({rem_round.timestamp}) is after all critic review timestamps. "
                f"The critic review must happen AFTER the remediation.",
                severity="HIGH",
            )


def check_critic_findings_addressed(
    reviews: list[CriticReview],
    result: CriticValidationResult,
) -> None:
    """AC2: Verify critic findings are addressed.

    Findings with severity >= MEDIUM must have status 'addressed'.
    Findings with severity LOW/INFO may be 'deferred' or 'wont_fix'.
    Any finding with status 'open' is a failure.
    """
    # Severities that require addressing
    actionable_severities = {
        Severity.CRITICAL.value,
        Severity.HIGH.value,
        Severity.MEDIUM.value,
    }

    if not reviews:
        result.add_pass(
            "AC2-no-reviews",
            "No critic reviews to check findings",
            "No critic reviews present; nothing to check.",
        )
        return

    total_findings = 0
    findings_addressed = 0
    findings_open = 0
    findings_deferred = 0

    for review in reviews:
        for finding in review.findings:
            total_findings += 1
            severity = finding.severity.upper()
            status = finding.status.lower()

            if status == FindingStatus.ADDRESSED.value:
                findings_addressed += 1
            elif status == FindingStatus.DEFERRED.value:
                findings_deferred += 1
                # Deferred is only acceptable for LOW/INFO
                if severity in actionable_severities:
                    result.add_error(
                        f"AC2-deferred-{finding.finding_id}",
                        f"Actionable finding {finding.finding_id} ({severity}) "
                        f"was deferred instead of addressed",
                        f"Finding: {finding.description}\n"
                        f"Resolution: {finding.resolution or '(none provided)'}",
                        severity=(
                            "HIGH" if severity == Severity.CRITICAL.value else "MEDIUM"
                        ),
                    )
            elif status == FindingStatus.WONT_FIX.value:
                findings_deferred += 1
                # WONT_FIX is only acceptable for LOW/INFO
                if severity in actionable_severities:
                    result.add_error(
                        f"AC2-wont-fix-{finding.finding_id}",
                        f"Actionable finding {finding.finding_id} ({severity}) "
                        f"marked as won't fix",
                        f"Finding: {finding.description}\n"
                        f"Resolution: {finding.resolution or '(none provided)'}",
                        severity=(
                            "HIGH" if severity == Severity.CRITICAL.value else "MEDIUM"
                        ),
                    )
            else:
                # status is 'open' or unknown
                findings_open += 1
                if severity in actionable_severities:
                    result.add_error(
                        f"AC2-open-{finding.finding_id}",
                        f"Actionable finding {finding.finding_id} ({severity}) "
                        f"is still open/unresolved",
                        f"Finding: {finding.description}\nStatus: {finding.status}",
                        severity=(
                            "CRITICAL"
                            if severity == Severity.CRITICAL.value
                            else "HIGH"
                        ),
                    )

    result.total_findings = total_findings
    result.findings_addressed = findings_addressed
    result.findings_open = findings_open
    result.findings_deferred = findings_deferred

    if findings_open == 0 and result.valid:
        result.add_pass(
            "AC2-all-addressed",
            "All actionable critic findings are addressed",
            f"{findings_addressed}/{total_findings} findings addressed, "
            f"{findings_deferred} deferred (LOW/INFO only).",
        )


def check_max_remediation_rounds(
    rounds: list[RemediationRound],
    max_rounds: int,
    result: CriticValidationResult,
) -> None:
    """AC3: Verify remediation did not exceed the maximum allowed rounds.

    Per Swarm Policy Hardening Section F, max 2 remediation rounds are
    allowed before escalation.
    """
    if not rounds:
        return

    actual_rounds = len(rounds)
    if actual_rounds > max_rounds:
        result.add_error(
            "AC3-max-rounds-exceeded",
            f"Remediation exceeded maximum {max_rounds} rounds "
            f"({actual_rounds} rounds performed)",
            f"Per Swarm Policy Hardening Section F, after {max_rounds} failed "
            f"remediation rounds, blockers must be returned to Aria with full "
            f"evidence. Escalation is required.",
            severity="CRITICAL",
        )
    else:
        result.add_pass(
            "AC3-max-rounds-ok",
            f"Remediation rounds ({actual_rounds}) within limit ({max_rounds})",
            "",
        )


# ---------------------------------------------------------------------------
# Main validation runner
# ---------------------------------------------------------------------------


def validate(evidence_data: dict[str, Any]) -> CriticValidationResult:
    """Run all post-remediation critic validations.

    Args:
        evidence_data: Parsed evidence dictionary containing
            remediation_rounds, critic_reviews, and optionally
            max_remediation_rounds.

    Returns:
        CriticValidationResult with all check results.
    """
    result = CriticValidationResult()

    # Parse input
    rounds = parse_remediation_rounds(evidence_data)
    reviews = parse_critic_reviews(evidence_data)
    max_rounds = evidence_data.get("max_remediation_rounds", 2)

    result.total_remediation_rounds = len(rounds)
    result.total_critic_reviews = len(reviews)

    # Run checks
    check_critic_reviews_after_remediation(rounds, reviews, result)
    check_critic_findings_addressed(reviews, result)
    check_max_remediation_rounds(rounds, max_rounds, result)

    return result


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Post-Remediation Critic Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        required=True,
        help="Path to evidence file (YAML or JSON)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Show detailed output for passed checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_output",
        help="Output result as JSON to stdout",
    )

    args = parser.parse_args()

    try:
        evidence_data = load_evidence(args.evidence)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        result = validate(evidence_data)
    except Exception as e:
        print(f"ERROR: Validation failed with exception: {e}", file=sys.stderr)
        return 2

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        result.print_report(verbose=args.verbose)

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
