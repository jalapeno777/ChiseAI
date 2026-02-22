#!/usr/bin/env python3
"""
Runbook Validation Script

Validates runbooks for correctness, completeness, and scenario-based testing.
Part of ST-LAUNCH-021: Runbook Creation & Validation

Usage:
    python scripts/ops/validate_runbooks.py --scenario all
    python scripts/ops/validate_runbooks.py --scenario safety
    python scripts/ops/validate_runbooks.py --scenario ml
    python scripts/ops/validate_runbooks.py --scenario incident
    python scripts/ops/validate_runbooks.py --checklist all

Exit Codes:
    0 - All validations passed
    1 - One or more validations failed
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class ValidationResult:
    """Result of a validation check."""

    name: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class RunbookValidationReport:
    """Complete validation report."""

    timestamp: str
    scenario: str
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def all_passed(self) -> bool:
        return self.failed_count == 0


class RunbookValidator:
    """Validates runbooks for structure, content, and scenarios."""

    RUNBOOKS_DIR = Path("docs/runbooks")
    REQUIRED_RUNBOOKS = [
        "launch_runbook.md",
        "ml_operations.md",
        "incident_response.md",
    ]

    def __init__(self):
        self.results: list[ValidationResult] = []

    def validate_all(self) -> RunbookValidationReport:
        """Run all validations."""
        self.results = []

        # Structure validations
        self._validate_runbooks_exist()
        self._validate_frontmatter()
        self._validate_required_sections()

        # Content validations
        self._validate_executable_steps()
        self._validate_links()

        return RunbookValidationReport(
            timestamp=datetime.utcnow().isoformat(),
            scenario="all",
            results=self.results,
        )

    def validate_safety(self) -> RunbookValidationReport:
        """Validate safety runbook with scenarios."""
        self.results = []

        runbook_path = self.RUNBOOKS_DIR / "launch_runbook.md"

        if not runbook_path.exists():
            self.results.append(
                ValidationResult(
                    name="safety_runbook_exists",
                    passed=False,
                    message="launch_runbook.md not found",
                )
            )
            return self._make_report("safety")

        content = runbook_path.read_text()

        # Safety-specific validations
        checks = [
            ("kill_switch_section", r"##\s+1\.\s+Kill Switch Procedures"),
            ("circuit_breaker_section", r"##\s+2\.\s+Circuit Breaker Management"),
            ("idempotency_section", r"##\s+3\.\s+Order Idempotency Verification"),
            ("rollback_section", r"##\s+4\.\s+Safety Rollback Procedures"),
            ("checklist_section", r"##\s+5\.\s+Pre-Launch Safety Checklist"),
            ("post_incident_section", r"##\s+6\.\s+Post-Incident Safety Verification"),
            ("kill_switch_trigger_api", r"POST.*/kill-switch/trigger"),
            ("rollback_sla", r"5-Minute SLA|5 minute SLA|5 minutes"),
            ("eleven_checklist_items", r"11\s+(Items|items|checklist)"),
        ]

        for check_name, pattern in checks:
            passed = bool(re.search(pattern, content))
            self.results.append(
                ValidationResult(
                    name=f"safety_{check_name}",
                    passed=passed,
                    message=f"{'Found' if passed else 'Missing'}: {check_name}",
                )
            )

        # Scenario-based validations
        self._validate_safety_scenarios(content)

        return self._make_report("safety")

    def validate_ml(self) -> RunbookValidationReport:
        """Validate ML operations runbook with scenarios."""
        self.results = []

        runbook_path = self.RUNBOOKS_DIR / "ml_operations.md"

        if not runbook_path.exists():
            self.results.append(
                ValidationResult(
                    name="ml_runbook_exists",
                    passed=False,
                    message="ml_operations.md not found",
                )
            )
            return self._make_report("ml")

        content = runbook_path.read_text()

        # ML-specific validations
        checks = [
            ("retraining_triggers", r"##\s+1\.\s+Model Retraining Trigger"),
            ("training_pipeline", r"##\s+2\.\s+Training Pipeline Execution"),
            ("validation_gates", r"##\s+3\.\s+Validation Gates"),
            ("model_rollback", r"##\s+4\.\s+Model Rollback"),
            ("shadow_mode", r"##\s+5\.\s+Shadow Mode"),
            ("ab_testing", r"##\s+6\.\s+A/B Testing"),
            ("ece_procedures", r"##\s+7\.\s+Daily ECE"),
            ("shadow_24h", r"24.hour|24h|24 hours"),
            ("ece_threshold", r"ECE.*0\.15|0\.15.*ECE"),
        ]

        for check_name, pattern in checks:
            passed = bool(re.search(pattern, content, re.IGNORECASE))
            self.results.append(
                ValidationResult(
                    name=f"ml_{check_name}",
                    passed=passed,
                    message=f"{'Found' if passed else 'Missing'}: {check_name}",
                )
            )

        # Scenario-based validations
        self._validate_ml_scenarios(content)

        return self._make_report("ml")

    def validate_incident(self) -> RunbookValidationReport:
        """Validate incident response runbook with scenarios."""
        self.results = []

        runbook_path = self.RUNBOOKS_DIR / "incident_response.md"

        if not runbook_path.exists():
            self.results.append(
                ValidationResult(
                    name="incident_runbook_exists",
                    passed=False,
                    message="incident_response.md not found",
                )
            )
            return self._make_report("incident")

        content = runbook_path.read_text()

        # Incident-specific validations
        checks = [
            ("classification", r"##\s+1\.\s+Incident Classification"),
            ("p0_definition", r"P0.*CRITICAL|CRITICAL.*P0"),
            ("p1_definition", r"P1.*HIGH|HIGH.*P1"),
            ("p2_definition", r"P2.*MEDIUM|MEDIUM.*P2"),
            ("p3_definition", r"P3.*LOW|LOW.*P3"),
            ("escalation_procedures", r"##\s+2\.\s+Escalation Procedures"),
            ("recovery_procedures", r"##\s+3\.\s+Recovery Procedures"),
            ("communication_templates", r"##\s+4\.\s+Communication Templates"),
            ("post_mortem", r"##\s+5\.\s+Post-Mortem|post-mortem"),
            ("on_call_procedures", r"##\s+6\.\s+On-Call"),
            ("acknowledgment_sla", r"15.*minute|15min"),
            ("response_sla", r"Response.*SLA|SLA.*Response"),
        ]

        for check_name, pattern in checks:
            passed = bool(re.search(pattern, content, re.IGNORECASE))
            self.results.append(
                ValidationResult(
                    name=f"incident_{check_name}",
                    passed=passed,
                    message=f"{'Found' if passed else 'Missing'}: {check_name}",
                )
            )

        # Scenario-based validations
        self._validate_incident_scenarios(content)

        return self._make_report("incident")

    def validate_checklist(self, item: Optional[str] = None) -> RunbookValidationReport:
        """Validate pre-launch safety checklist."""
        self.results = []

        runbook_path = self.RUNBOOKS_DIR / "launch_runbook.md"
        if not runbook_path.exists():
            self.results.append(
                ValidationResult(
                    name="checklist_runbook_exists",
                    passed=False,
                    message="launch_runbook.md not found",
                )
            )
            return self._make_report("checklist")

        content = runbook_path.read_text()

        # Extract checklist items
        checklist_section = re.search(
            r"##\s+5\.\s+Pre-Launch Safety Checklist.*?(?=##|$)", content, re.DOTALL
        )

        if not checklist_section:
            self.results.append(
                ValidationResult(
                    name="checklist_section_found",
                    passed=False,
                    message="Pre-launch checklist section not found",
                )
            )
            return self._make_report("checklist")

        # Count checklist items
        checklist_items = re.findall(r"\|\s*\d+\s*\|", checklist_section.group())

        self.results.append(
            ValidationResult(
                name="checklist_item_count",
                passed=len(checklist_items) >= 11,
                message=f"Found {len(checklist_items)} checklist items (expected >= 11)",
            )
        )

        # Validate each item has verification
        items_with_verification = re.findall(
            r"\|\s*\d+\s*\|.*\|.*\|.*\|", checklist_section.group()
        )

        self.results.append(
            ValidationResult(
                name="checklist_items_complete",
                passed=len(items_with_verification) >= 11,
                message=f"{len(items_with_verification)} items have complete verification criteria",
            )
        )

        return self._make_report("checklist")

    def _validate_runbooks_exist(self) -> None:
        """Validate that all required runbooks exist."""
        for runbook in self.REQUIRED_RUNBOOKS:
            path = self.RUNBOOKS_DIR / runbook
            exists = path.exists()
            self.results.append(
                ValidationResult(
                    name=f"exists_{runbook}",
                    passed=exists,
                    message=f"{'Found' if exists else 'Missing'}: {runbook}",
                )
            )

    def _validate_frontmatter(self) -> None:
        """Validate YAML frontmatter in runbooks."""
        required_fields = [
            "title",
            "category",
            "severity",
            "last_updated",
            "story_id",
        ]

        for runbook in self.REQUIRED_RUNBOOKS:
            path = self.RUNBOOKS_DIR / runbook
            if not path.exists():
                continue

            content = path.read_text()

            # Check for frontmatter
            frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)

            if not frontmatter_match:
                self.results.append(
                    ValidationResult(
                        name=f"frontmatter_{runbook}",
                        passed=False,
                        message=f"No YAML frontmatter found in {runbook}",
                    )
                )
                continue

            frontmatter = frontmatter_match.group(1)

            for field in required_fields:
                passed = field in frontmatter
                self.results.append(
                    ValidationResult(
                        name=f"frontmatter_{runbook}_{field}",
                        passed=passed,
                        message=f"{'Found' if passed else 'Missing'} field '{field}' in {runbook}",
                    )
                )

    def _validate_required_sections(self) -> None:
        """Validate that runbooks have required sections."""
        section_requirements = {
            "launch_runbook.md": [
                ("overview", r"##\s+Overview|##\s+overview"),
                ("procedures", r"##\s+\d+\.\s+.*Procedures"),
                ("monitoring", r"##\s+\d+\.\s+Monitoring|alert"),
            ],
            "ml_operations.md": [
                ("overview", r"##\s+Overview"),
                ("retraining", r"retrain|training"),
                ("validation", r"validat|gate"),
            ],
            "incident_response.md": [
                ("overview", r"##\s+Overview"),
                ("classification", r"classificat|P0|P1|P2|P3"),
                ("escalation", r"escalat"),
            ],
        }

        for runbook, sections in section_requirements.items():
            path = self.RUNBOOKS_DIR / runbook
            if not path.exists():
                continue

            content = path.read_text()

            for section_name, pattern in sections:
                passed = bool(re.search(pattern, content, re.IGNORECASE))
                self.results.append(
                    ValidationResult(
                        name=f"section_{runbook}_{section_name}",
                        passed=passed,
                        message=f"{'Found' if passed else 'Missing'} section '{section_name}' in {runbook}",
                    )
                )

    def _validate_executable_steps(self) -> None:
        """Validate that executable steps in frontmatter are valid."""
        for runbook in self.REQUIRED_RUNBOOKS:
            path = self.RUNBOOKS_DIR / runbook
            if not path.exists():
                continue

            content = path.read_text()

            # Check if marked as executable
            if "executable: true" not in content:
                continue

            # Extract steps
            steps_match = re.search(
                r"steps:\s*(\[.*?\]|\n.*?)(?=\n\w|$)", content, re.DOTALL
            )

            if steps_match:
                self.results.append(
                    ValidationResult(
                        name=f"executable_steps_{runbook}",
                        passed=True,
                        message=f"Executable steps found in {runbook}",
                    )
                )

    def _validate_links(self) -> None:
        """Validate that internal links in runbooks are valid."""
        for runbook in self.REQUIRED_RUNBOOKS:
            path = self.RUNBOOKS_DIR / runbook
            if not path.exists():
                continue

            content = path.read_text()

            # Find markdown links to other runbooks
            links = re.findall(r"\[.*?\]\((.*?\.md)\)", content)

            for link in links:
                link_path = self.RUNBOOKS_DIR / link
                exists = link_path.exists()
                self.results.append(
                    ValidationResult(
                        name=f"link_{runbook}_{link}",
                        passed=exists,
                        message=f"{'Valid' if exists else 'Broken'} link to {link} in {runbook}",
                    )
                )

    def _validate_safety_scenarios(self, content: str) -> None:
        """Validate safety runbook scenarios."""
        scenarios = [
            ("kill_switch_trigger_scenario", r"When to Trigger|trigger.*kill"),
            ("circuit_breaker_states", r"CLOSED.*OPEN|OPEN.*HALF"),
            ("rollback_procedure", r"Step.*1.*Immediate|rollback.*step"),
            ("verification_checklist", r"\[.*\].*Verify|\[.*\].*Check"),
        ]

        for scenario_name, pattern in scenarios:
            passed = bool(re.search(pattern, content, re.IGNORECASE))
            self.results.append(
                ValidationResult(
                    name=f"scenario_{scenario_name}",
                    passed=passed,
                    message=f"{'Found' if passed else 'Missing'} scenario: {scenario_name}",
                )
            )

    def _validate_ml_scenarios(self, content: str) -> None:
        """Validate ML runbook scenarios."""
        scenarios = [
            ("retraining_trigger", r"trigger.*retrain|retrain.*trigger"),
            ("validation_gate_failure", r"gate.*fail|fail.*gate"),
            ("shadow_promotion", r"shadow.*promote|promote.*shadow"),
            ("ece_recalibration", r"recalibrat|ECE.*update"),
        ]

        for scenario_name, pattern in scenarios:
            passed = bool(re.search(pattern, content, re.IGNORECASE))
            self.results.append(
                ValidationResult(
                    name=f"scenario_{scenario_name}",
                    passed=passed,
                    message=f"{'Found' if passed else 'Missing'} scenario: {scenario_name}",
                )
            )

    def _validate_incident_scenarios(self, content: str) -> None:
        """Validate incident response runbook scenarios."""
        scenarios = [
            ("p0_response", r"P0.*Response|Response.*P0"),
            ("escalation_matrix", r"escalat.*matrix|matrix.*escalat"),
            ("war_room", r"war.*room|war-room"),
            ("post_mortem_process", r"post-mortem.*process|postmortem"),
        ]

        for scenario_name, pattern in scenarios:
            passed = bool(re.search(pattern, content, re.IGNORECASE))
            self.results.append(
                ValidationResult(
                    name=f"scenario_{scenario_name}",
                    passed=passed,
                    message=f"{'Found' if passed else 'Missing'} scenario: {scenario_name}",
                )
            )

    def _make_report(self, scenario: str) -> RunbookValidationReport:
        """Create a validation report."""
        return RunbookValidationReport(
            timestamp=datetime.utcnow().isoformat(),
            scenario=scenario,
            results=self.results,
        )


def print_report(report: RunbookValidationReport, verbose: bool = False) -> None:
    """Print validation report in a readable format."""
    print("=" * 70)
    print(f"RUNBOOK VALIDATION REPORT")
    print(f"Scenario: {report.scenario}")
    print(f"Timestamp: {report.timestamp}")
    print("=" * 70)

    print(f"\nSummary: {report.passed_count} passed, {report.failed_count} failed")
    print("-" * 70)

    # Group by status
    passed = [r for r in report.results if r.passed]
    failed = [r for r in report.results if not r.passed]

    if failed:
        print("\n❌ FAILED CHECKS:")
        for result in failed:
            print(f"  ✗ {result.name}: {result.message}")

    if verbose and passed:
        print("\n✅ PASSED CHECKS:")
        for result in passed:
            print(f"  ✓ {result.name}: {result.message}")

    print("\n" + "=" * 70)
    print(f"RESULT: {'PASS' if report.all_passed else 'FAIL'}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Validate runbooks for ChiseAI platform"
    )
    parser.add_argument(
        "--scenario",
        choices=["all", "safety", "ml", "incident", "checklist"],
        default="all",
        help="Which scenario to validate (default: all)",
    )
    parser.add_argument(
        "--check", type=str, help="Specific check to run (e.g., idempotency)"
    )
    parser.add_argument(
        "--checklist", type=str, help="Validate specific checklist item (or 'all')"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show passed checks as well"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--detailed", action="store_true", help="Show detailed output for scenarios"
    )

    args = parser.parse_args()

    validator = RunbookValidator()

    # Run validation based on scenario
    if args.checklist:
        report = validator.validate_checklist(args.checklist)
    elif args.scenario == "all":
        report = validator.validate_all()
    elif args.scenario == "safety":
        report = validator.validate_safety()
    elif args.scenario == "ml":
        report = validator.validate_ml()
    elif args.scenario == "incident":
        report = validator.validate_incident()
    elif args.scenario == "checklist":
        report = validator.validate_checklist()
    else:
        report = validator.validate_all()

    # Output results
    if args.json:
        output = {
            "timestamp": report.timestamp,
            "scenario": report.scenario,
            "all_passed": report.all_passed,
            "summary": {
                "passed": report.passed_count,
                "failed": report.failed_count,
                "total": len(report.results),
            },
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                }
                for r in report.results
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print_report(report, verbose=args.verbose)

    # Exit with appropriate code
    sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()
