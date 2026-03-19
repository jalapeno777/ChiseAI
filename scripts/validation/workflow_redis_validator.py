#!/usr/bin/env python3
"""
Workflow Redis Validator for ChiseAI.

Validates workflow status consistency stored in Redis iterlog keys
(bmad:chiseai:iterlog:story:*). Ensures:

1. Story keys exist and contain all required fields
2. Field values conform to allowed enumerations (phase, status)
3. TTL settings are correctly applied to iterlog keys
4. Timestamps are valid ISO-8601 format
5. Cross-field consistency (completed_at with status, timestamp ordering)
6. Phase/status compatibility mapping
7. Story title length limits (warning)
8. Acceptance criteria items non-empty (warning)

Usage:
    python3 scripts/validation/workflow_redis_validator.py
    python3 scripts/validation/workflow_redis_validator.py --story-id ST-001
    python3 scripts/validation/workflow_redis_validator.py --strict
    python3 scripts/validation/workflow_redis_validator.py --json

Exit codes:
    0 - All validations passed (or only warnings in non-strict mode)
    1 - Validation errors found
    2 - System error (Redis connection, etc.)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

ITERLOG_PREFIX = "bmad:chiseai:iterlog"
STORY_PREFIX = f"{ITERLOG_PREFIX}:story"

DEFAULT_TTL_SECONDS = 432000  # 5 days

VALID_PHASES = frozenset(
    {
        "analysis",
        "planning",
        "solutioning",
        "implementation",
        "testing",
    }
)

VALID_STATUSES = frozenset(
    {
        "planned",
        "in_progress",
        "blocked",
        "completed",
        "deprecated",
    }
)

# Fields that must be present in every story hash
REQUIRED_FIELDS = frozenset(
    {
        "story_id",
        "story_title",
        "phase",
        "status",
        "started_at",
    }
)

# Fields that are optional but validated when present
OPTIONAL_FIELDS = frozenset(
    {
        "acceptance_criteria",
        "completed_at",
        "key_decisions",
        "learnings",
    }
)

ALL_KNOWN_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

# ISO-8601 timestamp pattern (simplified but covers standard formats)
ISO_8601_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

# Story ID pattern (matches AGENTS.md recognized tokens)
STORY_ID_PATTERN = re.compile(
    r"^(ST|CH|FT|REWARD|REPO|SAFETY|BRANCH|PAPER|RECON|PROCESS)-[A-Z0-9-]*[0-9][A-Z0-9-]*$"
)

# TTL warning threshold: warn if TTL < this many seconds remaining
TTL_WARNING_THRESHOLD_SECONDS = 86400  # 1 day

# Story title max length (warning if exceeded)
STORY_TITLE_MAX_LENGTH = 200

# Phase/status compatibility map: phase -> set of valid statuses
PHASE_STATUS_COMPAT: dict[str, frozenset[str]] = {
    "analysis": frozenset({"planned", "in_progress", "completed", "deprecated"}),
    "planning": frozenset({"planned", "in_progress", "completed", "deprecated"}),
    "solutioning": frozenset({"planned", "in_progress", "completed", "deprecated"}),
    "implementation": frozenset({"planned", "in_progress", "completed", "deprecated"}),
    "testing": frozenset({"planned", "in_progress", "completed", "deprecated"}),
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class FieldValidation:
    """Result of validating a single field."""

    field_name: str
    is_valid: bool
    message: str = ""
    severity: str = "error"  # "error" or "warning"


@dataclass
class StoryValidation:
    """Result of validating a single story key."""

    story_key: str
    story_id: str = ""
    fields_present: list[str] = field(default_factory=list)
    fields_missing: list[str] = field(default_factory=list)
    field_validations: list[FieldValidation] = field(default_factory=list)
    ttl_seconds: int | None = None
    ttl_valid: bool | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


@dataclass
class WorkflowValidationReport:
    """Aggregated validation report for all stories."""

    stories_checked: int = 0
    stories_valid: int = 0
    stories_with_errors: int = 0
    stories_with_warnings: int = 0
    story_results: list[StoryValidation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation_timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.stories_with_errors == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "is_valid": self.is_valid,
            "stories_checked": self.stories_checked,
            "stories_valid": self.stories_valid,
            "stories_with_errors": self.stories_with_errors,
            "stories_with_warnings": self.stories_with_warnings,
            "errors": self.errors,
            "warnings": self.warnings,
            "story_results": [
                {
                    "story_key": sr.story_key,
                    "story_id": sr.story_id,
                    "is_valid": sr.is_valid,
                    "fields_missing": sr.fields_missing,
                    "ttl_seconds": sr.ttl_seconds,
                    "ttl_valid": sr.ttl_valid,
                    "errors": sr.errors,
                    "warnings": sr.warnings,
                    "field_validations": [
                        {
                            "field_name": fv.field_name,
                            "is_valid": fv.is_valid,
                            "message": fv.message,
                            "severity": fv.severity,
                        }
                        for fv in sr.field_validations
                    ],
                }
                for sr in self.story_results
            ],
            "validation_timestamp": self.validation_timestamp,
        }


# =============================================================================
# Redis Client Protocol
# =============================================================================


@runtime_checkable
class RedisClient(Protocol):
    """Protocol for Redis client operations used by the validator."""

    def scan(self, *, cursor: int, match: str, count: int) -> tuple[int, list[str]]: ...
    def hgetall(self, name: str) -> dict[str, str]: ...
    def type(self, name: str) -> str: ...
    def ttl(self, name: str) -> int: ...
    def ping(self) -> bool: ...


# =============================================================================
# Validator
# =============================================================================


class WorkflowRedisValidator:
    """Validates workflow status consistency in Redis iterlog keys.

    Checks that story iteration logs in Redis:
    - Contain all required fields
    - Have valid phase/status enumerations
    - Have proper TTL settings
    - Use valid ISO-8601 timestamps
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        strict: bool = False,
        ttl_warning_threshold: int = TTL_WARNING_THRESHOLD_SECONDS,
    ):
        """Initialize the validator.

        Args:
            redis_client: Redis client instance. If None, will attempt to
                create one from environment defaults.
            strict: If True, warnings are treated as errors.
            ttl_warning_threshold: Warn if TTL remaining is below this.
        """
        self._client: Any = redis_client
        self.strict = strict
        self.ttl_warning_threshold = ttl_warning_threshold

    def _get_redis_client(self) -> Any:
        """Get or create Redis client."""
        if self._client is not None:
            return self._client

        import redis as redis_lib

        host = (
            os.getenv("CHISE_REDIS_HOST")
            or os.getenv("REDIS_HOST")
            or "host.docker.internal"
        )
        port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
        db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")

        client = redis_lib.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
        )
        client.ping()
        self._client = client
        return self._client

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def validate_all_stories(self) -> WorkflowValidationReport:
        """Validate all story iterlog keys in Redis.

        Scans bmad:chiseai:iterlog:story:* and validates each key.

        Returns:
            WorkflowValidationReport with aggregated results.
        """
        report = WorkflowValidationReport()
        client = self._get_redis_client()

        try:
            cursor = 0
            story_keys: list[str] = []
            while True:
                cursor, keys = client.scan(
                    cursor=cursor, match=f"{STORY_PREFIX}:*", count=100
                )
                # Filter out sub-keys (e.g., :decisions, :learnings, :incidents)
                story_keys.extend(k for k in keys if self._is_story_hash_key(k))
                if cursor == 0:
                    break
        except Exception as e:
            report.errors.append(f"Failed to scan story keys: {e}")
            return report

        for key in story_keys:
            story_result = self.validate_story_key(key, client)
            report.story_results.append(story_result)
            report.stories_checked += 1
            if story_result.is_valid:
                report.stories_valid += 1
            else:
                report.stories_with_errors += 1
            if story_result.warnings:
                report.stories_with_warnings += 1

        return report

    def validate_story_key(
        self,
        key: str,
        client: Any | None = None,
    ) -> StoryValidation:
        """Validate a single story iterlog key.

        Args:
            key: Full Redis key (e.g., bmad:chiseai:iterlog:story:ST-001)
            client: Redis client. Uses default if None.

        Returns:
            StoryValidation with detailed results.
        """
        if client is None:
            client = self._get_redis_client()
        assert client is not None  # _get_redis_client always returns a client or raises

        result = StoryValidation(story_key=key)

        # Extract story_id from key
        story_id = self._extract_story_id(key)
        if story_id:
            result.story_id = story_id

        # Check key type is hash
        try:
            key_type = client.type(key)
            if key_type != "hash":
                result.errors.append(f"Key type is '{key_type}', expected 'hash'")
                return result
        except Exception as e:
            result.errors.append(f"Failed to check key type: {e}")
            return result

        # Get all fields
        try:
            fields = client.hgetall(key)
        except Exception as e:
            result.errors.append(f"Failed to read hash fields: {e}")
            return result

        if not fields:
            result.errors.append("Story hash is empty (no fields)")
            return result

        # Check required fields
        result.fields_present = list(fields.keys())
        missing = REQUIRED_FIELDS - set(fields.keys())
        if missing:
            result.fields_missing = sorted(missing)
            result.errors.append(
                f"Missing required fields: {', '.join(sorted(missing))}"
            )

        # Validate individual fields
        for fname, fvalue in fields.items():
            validation = self._validate_field(fname, fvalue, story_id)
            result.field_validations.append(validation)
            if not validation.is_valid and validation.severity == "error":
                result.errors.append(f"Field '{fname}': {validation.message}")
            elif not validation.is_valid and validation.severity == "warning":
                result.warnings.append(f"Field '{fname}': {validation.message}")

        # Check for unknown fields (warning only)
        unknown = set(fields.keys()) - ALL_KNOWN_FIELDS
        if unknown:
            for uf in sorted(unknown):
                result.warnings.append(f"Unknown field '{uf}'")

        # Cross-field consistency validation
        self.validate_cross_fields(fields, result)

        # Validate TTL
        self._validate_ttl(key, client, result)

        # If strict mode, promote warnings to errors
        if self.strict and result.warnings:
            result.errors.extend(result.warnings)
            result.warnings.clear()

        return result

    def validate_cross_fields(
        self, fields: dict[str, str], result: StoryValidation
    ) -> None:
        """Validate cross-field consistency rules.

        Checks:
        1. completed_at required when status=completed
        2. Timestamp ordering: started_at <= completed_at
        3. Phase/status compatibility
        4. Story title max length
        5. Acceptance criteria items non-empty
        """
        status = fields.get("status", "")
        phase = fields.get("phase", "")
        started_at = fields.get("started_at", "")
        completed_at = fields.get("completed_at", "")
        story_title = fields.get("story_title", "")
        acceptance_criteria_raw = fields.get("acceptance_criteria", "")

        # 1. completed_at required when status is "completed"
        if status == "completed" and not completed_at:
            result.errors.append(
                "Field 'completed_at' is required when status is 'completed'"
            )

        # 2. Timestamp ordering: started_at <= completed_at
        if started_at and completed_at:
            start_ts = self._parse_timestamp_safe(started_at)
            end_ts = self._parse_timestamp_safe(completed_at)
            if start_ts is not None and end_ts is not None:
                if start_ts > end_ts:
                    result.errors.append(
                        f"Timestamp ordering violation: started_at ({started_at}) "
                        f"is after completed_at ({completed_at})"
                    )

        # 3. Phase/status compatibility
        if phase and status:
            valid_statuses = PHASE_STATUS_COMPAT.get(phase)
            if valid_statuses is not None and status not in valid_statuses:
                result.errors.append(
                    f"Phase/status incompatibility: phase '{phase}' with "
                    f"status '{status}' is not a valid combination"
                )

        # 4. Story title max length (warning)
        if story_title and len(story_title) > STORY_TITLE_MAX_LENGTH:
            result.warnings.append(
                f"Story title length is {len(story_title)} characters, "
                f"exceeds recommended max of {STORY_TITLE_MAX_LENGTH}"
            )

        # 5. Acceptance criteria items non-empty
        if acceptance_criteria_raw:
            try:
                ac_items = json.loads(acceptance_criteria_raw)
                if isinstance(ac_items, list):
                    empty_items = [
                        i
                        for i, item in enumerate(ac_items)
                        if isinstance(item, str) and not item.strip()
                    ]
                    if empty_items:
                        result.warnings.append(
                            f"Acceptance criteria contains {len(empty_items)} "
                            f"empty item(s) at index(es): "
                            f"{', '.join(str(i) for i in empty_items)}"
                        )
            except json.JSONDecodeError:
                pass  # Already validated by _validate_json_array_field

    def validate_specific_story(self, story_id: str) -> StoryValidation:
        """Validate a specific story by its ID.

        Args:
            story_id: Story ID (e.g., "ST-001")

        Returns:
            StoryValidation for the specified story.
        """
        key = f"{STORY_PREFIX}:{story_id}"
        return self.validate_story_key(key)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _is_story_hash_key(key: str) -> bool:
        """Check if key is a story hash key (not a sub-key like :decisions)."""
        # Sub-keys have suffixes like :decisions, :learnings, :incidents
        suffixes = (":decisions", ":learnings", ":incidents")
        return not any(key.endswith(s) for s in suffixes)

    @staticmethod
    def _extract_story_id(key: str) -> str:
        """Extract story_id from Redis key."""
        prefix = f"{STORY_PREFIX}:"
        if key.startswith(prefix):
            return key[len(prefix) :]
        return ""

    def _validate_field(
        self, name: str, value: str, story_id: str = ""
    ) -> FieldValidation:
        """Validate a single field value."""
        if not value or not value.strip():
            return FieldValidation(
                field_name=name,
                is_valid=False,
                message="Field is empty",
                severity="error",
            )

        # story_id field
        if name == "story_id":
            return self._validate_story_id_field(value, story_id)

        # phase field
        if name == "phase":
            return self._validate_phase_field(value)

        # status field
        if name == "status":
            return self._validate_status_field(value)

        # started_at / completed_at
        if name in ("started_at", "completed_at"):
            return self._validate_timestamp_field(name, value)

        # acceptance_criteria (JSON array)
        if name == "acceptance_criteria":
            return self._validate_json_array_field(name, value)

        # key_decisions / learnings (JSON array)
        if name in ("key_decisions", "learnings"):
            return self._validate_json_array_field(name, value, required=False)

        # story_title - just check non-empty (already checked above)
        return FieldValidation(field_name=name, is_valid=True, message="OK")

    @staticmethod
    def _validate_story_id_field(value: str, expected_id: str = "") -> FieldValidation:
        """Validate the story_id field value."""
        if not STORY_ID_PATTERN.match(value):
            return FieldValidation(
                field_name="story_id",
                is_valid=False,
                message=f"Story ID '{value}' does not match expected pattern",
                severity="error",
            )
        if expected_id and value != expected_id:
            return FieldValidation(
                field_name="story_id",
                is_valid=False,
                message=f"Story ID '{value}' does not match key-derived ID '{expected_id}'",
                severity="error",
            )
        return FieldValidation(field_name="story_id", is_valid=True, message="OK")

    @staticmethod
    def _validate_phase_field(value: str) -> FieldValidation:
        """Validate the phase field."""
        if value not in VALID_PHASES:
            return FieldValidation(
                field_name="phase",
                is_valid=False,
                message=f"Invalid phase '{value}'. Must be one of: {', '.join(sorted(VALID_PHASES))}",
                severity="error",
            )
        return FieldValidation(field_name="phase", is_valid=True, message="OK")

    @staticmethod
    def _validate_status_field(value: str) -> FieldValidation:
        """Validate the status field."""
        if value not in VALID_STATUSES:
            return FieldValidation(
                field_name="status",
                is_valid=False,
                message=f"Invalid status '{value}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
                severity="error",
            )
        return FieldValidation(field_name="status", is_valid=True, message="OK")

    @staticmethod
    def _validate_timestamp_field(name: str, value: str) -> FieldValidation:
        """Validate ISO-8601 timestamp fields."""
        if not ISO_8601_PATTERN.match(value):
            return FieldValidation(
                field_name=name,
                is_valid=False,
                message=f"Invalid timestamp format '{value}'. Expected ISO-8601 (YYYY-MM-DDTHH:MM:SS)",
                severity="error",
            )
        return FieldValidation(field_name=name, is_valid=True, message="OK")

    @staticmethod
    def _validate_json_array_field(
        name: str, value: str, required: bool = True
    ) -> FieldValidation:
        """Validate JSON array fields."""
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                return FieldValidation(
                    field_name=name,
                    is_valid=False,
                    message=f"Expected JSON array, got {type(parsed).__name__}",
                    severity="error",
                )
            return FieldValidation(field_name=name, is_valid=True, message="OK")
        except json.JSONDecodeError as e:
            severity = "error" if required else "warning"
            return FieldValidation(
                field_name=name,
                is_valid=False,
                message=f"Invalid JSON: {e}",
                severity=severity,
            )

    @staticmethod
    def _parse_timestamp_safe(value: str) -> datetime | None:
        """Parse ISO-8601 timestamp string, returning None on failure."""
        if not value or not ISO_8601_PATTERN.match(value):
            return None
        try:
            # Handle timezone variants: Z, +00:00, +0000, no suffix
            cleaned = value.replace("Z", "+00:00")
            if "+" in cleaned and cleaned.index("+") > 16:
                # Has timezone info after seconds
                pass
            return datetime.fromisoformat(cleaned)
        except (ValueError, IndexError):
            return None

    def _validate_ttl(self, key: str, client: Any, result: StoryValidation) -> None:
        """Validate TTL on a story key."""
        try:
            ttl = client.ttl(key)
            result.ttl_seconds = ttl

            if ttl == -2:
                # Key does not exist (shouldn't happen since we just read it)
                result.errors.append(
                    "Key has no TTL and may have expired between reads"
                )
                result.ttl_valid = False
            elif ttl == -1:
                # Key exists but has no expiration
                result.warnings.append(
                    "Key has no TTL set. Expected ~432000s (5 days). "
                    "Iterlog keys should have a TTL to prevent unbounded growth."
                )
                result.ttl_valid = False
            elif ttl <= 0:
                result.errors.append(f"Key TTL is {ttl}s (expired or invalid)")
                result.ttl_valid = False
            elif ttl < self.ttl_warning_threshold:
                result.warnings.append(
                    f"Key TTL is {ttl}s ({ttl // 3600}h remaining), "
                    f"below warning threshold of {self.ttl_warning_threshold}s"
                )
                result.ttl_valid = True
            else:
                result.ttl_valid = True
        except Exception as e:
            result.warnings.append(f"Could not check TTL: {e}")
            result.ttl_valid = None


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """Run the workflow Redis validator from command line."""
    parser = argparse.ArgumentParser(
        description="Validate workflow status consistency in Redis iterlog keys",
    )
    parser.add_argument(
        "--story-id",
        help="Validate a specific story ID instead of scanning all",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed per-field validation",
    )

    args = parser.parse_args()

    try:
        validator = WorkflowRedisValidator(strict=args.strict)
    except Exception as e:
        logger.error(f"Failed to initialize validator: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        if args.story_id:
            story_result = validator.validate_specific_story(args.story_id)
            if args.json_output:
                print(
                    json.dumps(
                        {
                            "story_key": story_result.story_key,
                            "is_valid": story_result.is_valid,
                            "errors": story_result.errors,
                            "warnings": story_result.warnings,
                            "fields_missing": story_result.fields_missing,
                            "ttl_seconds": story_result.ttl_seconds,
                            "ttl_valid": story_result.ttl_valid,
                            "field_validations": [
                                {
                                    "field_name": fv.field_name,
                                    "is_valid": fv.is_valid,
                                    "message": fv.message,
                                }
                                for fv in story_result.field_validations
                            ],
                        },
                        indent=2,
                    )
                )
            else:
                _print_story_result(story_result, args.verbose)

            return 0 if story_result.is_valid else 1
        else:
            report = validator.validate_all_stories()
            if args.json_output:
                print(json.dumps(report.to_dict(), indent=2))
            else:
                _print_report(report, args.verbose)

            return 0 if report.is_valid else 1

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


def _print_story_result(result: StoryValidation, verbose: bool = False) -> None:
    """Print a single story validation result to stdout."""
    status = "PASS" if result.is_valid else "FAIL"
    print(f"[{status}] {result.story_key}")
    if result.story_id:
        print(f"  story_id: {result.story_id}")

    if result.fields_missing:
        print(f"  missing fields: {', '.join(result.fields_missing)}")

    if result.ttl_seconds is not None:
        ttl_status = "OK" if result.ttl_valid else "ISSUE"
        print(f"  TTL: {result.ttl_seconds}s ({ttl_status})")

    for err in result.errors:
        print(f"  ERROR: {err}")
    for warn in result.warnings:
        print(f"  WARNING: {warn}")

    if verbose and result.field_validations:
        print("  field validations:")
        for fv in result.field_validations:
            fv_status = "OK" if fv.is_valid else fv.severity.upper()
            print(f"    {fv.field_name}: [{fv_status}] {fv.message}")


def _print_report(report: WorkflowValidationReport, verbose: bool = False) -> None:
    """Print the full validation report to stdout."""
    status = "PASS" if report.is_valid else "FAIL"
    print(f"Workflow Redis Validation: [{status}]")
    print(f"  Stories checked: {report.stories_checked}")
    print(f"  Valid: {report.stories_valid}")
    print(f"  With errors: {report.stories_with_errors}")
    print(f"  With warnings: {report.stories_with_warnings}")

    for err in report.errors:
        print(f"  ERROR: {err}")
    for warn in report.warnings:
        print(f"  WARNING: {warn}")

    if verbose:
        print()
        for sr in report.story_results:
            _print_story_result(sr, verbose=True)
            print()


if __name__ == "__main__":
    sys.exit(main())
