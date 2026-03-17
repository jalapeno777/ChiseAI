#!/usr/bin/env python3
"""
Evidence Schema Validator

Validates evidence files against their corresponding JSON schemas.
Supports the base evidence schema and type-specific schemas.

Usage:
    python3 validate_evidence_schema.py --file docs/evidence/ST-XXX-evidence.json
    python3 validate_evidence_schema.py --story-id ST-XXX
    python3 validate_evidence_schema.py --all
    python3 validate_evidence_schema.py --all --verbose
    python3 validate_evidence_schema.py --ci-mode  # CI integration mode (warning only)

Exit Codes:
    0 - All validations passed
    1 - One or more validations failed
    2 - Configuration or system errors
"""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Schema paths
BASE_SCHEMA_PATH = Path("docs/validation/evidence-schema.json")
EVIDENCE_TYPES_DIR = Path("docs/validation/evidence-types")
EVIDENCE_DIR = Path("docs/evidence")
VALIDATION_EVIDENCE_DIR = Path("docs/validation/evidence")

# Evidence type to schema mapping
EVIDENCE_TYPE_SCHEMAS = {
    "test_results": "test-evidence.json",
    "merge_verification": None,  # Uses base schema
    "performance_benchmark": None,
    "architecture_design": "architecture-evidence.json",
    "security_audit": None,
    "code_review": None,
    "validation_report": None,
    "incident_response": None,
    "manual_verification": None,
}


class SchemaValidator:
    """JSON Schema validator for evidence files."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.base_schema: dict | None = None
        self.type_schemas: dict[str, dict] = {}
        self._load_schemas()

    def _load_schemas(self) -> None:
        """Load base schema and type-specific schemas."""
        try:
            with open(BASE_SCHEMA_PATH) as f:
                self.base_schema = json.load(f)
            if self.verbose:
                print(f"✓ Loaded base schema: {BASE_SCHEMA_PATH}")
        except Exception as e:
            self._add_error(
                "schema", f"Failed to load base schema: {e}", str(BASE_SCHEMA_PATH)
            )
            raise

        # Load type-specific schemas
        if EVIDENCE_TYPES_DIR.exists():
            for schema_file in EVIDENCE_TYPES_DIR.glob("*.json"):
                try:
                    with open(schema_file) as f:
                        schema = json.load(f)
                        self.type_schemas[schema_file.name] = schema
                        if self.verbose:
                            print(f"✓ Loaded type schema: {schema_file.name}")
                except Exception as e:
                    self._add_warning(
                        "schema", f"Failed to load type schema {schema_file}: {e}"
                    )

    def _add_error(
        self, file_path: str, message: str, field: str | None = None
    ) -> None:
        """Add an error record."""
        self.errors.append(
            {"file": file_path, "field": field, "message": message, "severity": "ERROR"}
        )

    def _add_warning(
        self, file_path: str, message: str, field: str | None = None
    ) -> None:
        """Add a warning record."""
        self.warnings.append(
            {
                "file": file_path,
                "field": field,
                "message": message,
                "severity": "WARNING",
            }
        )

    def _validate_type(self, value: Any, expected_type: str, path: str) -> list[str]:
        """Validate a value against an expected JSON schema type."""
        errors = []

        type_checks = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
            "null": lambda v: v is None,
        }

        if expected_type in type_checks:
            if not type_checks[expected_type](value):
                errors.append(
                    f"Expected {expected_type} at {path}, got {type(value).__name__}"
                )

        return errors

    def _validate_format(self, value: Any, format_type: str, path: str) -> list[str]:
        """Validate a value against a JSON schema format."""
        errors = []

        if format_type == "date-time":
            if isinstance(value, str):
                # ISO 8601 datetime validation
                iso_patterns = [
                    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$",
                    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
                ]
                if not any(re.match(p, value) for p in iso_patterns):
                    errors.append(f"Invalid date-time format at {path}: {value}")

        return errors

    def _validate_pattern(self, value: str, pattern: str, path: str) -> list[str]:
        """Validate a string value against a regex pattern."""
        errors = []
        try:
            if not re.match(pattern, value):
                errors.append(f"Value at {path} does not match pattern: {pattern}")
        except re.error as e:
            errors.append(f"Invalid pattern at {path}: {e}")
        return errors

    def _validate_value(
        self, value: Any, schema: dict, path: str, file_path: str
    ) -> bool:
        """
        Validate a value against a schema.
        Returns True if valid, False otherwise.
        """
        is_valid = True

        # Type validation
        if "type" in schema:
            type_errors = self._validate_type(value, schema["type"], path)
            for error in type_errors:
                self._add_error(file_path, error, path)
                is_valid = False

        # Enum validation
        if "enum" in schema and value not in schema["enum"]:
            self._add_error(
                file_path,
                f"Value at {path} must be one of {schema['enum']}, got: {value}",
                path,
            )
            is_valid = False

        # Const validation
        if "const" in schema and value != schema["const"]:
            self._add_error(
                file_path,
                f"Value at {path} must be {schema['const']}, got: {value}",
                path,
            )
            is_valid = False

        # Format validation
        if "format" in schema and isinstance(value, str):
            format_errors = self._validate_format(value, schema["format"], path)
            for error in format_errors:
                self._add_error(file_path, error, path)
                is_valid = False

        # Pattern validation
        if "pattern" in schema and isinstance(value, str):
            pattern_errors = self._validate_pattern(value, schema["pattern"], path)
            for error in pattern_errors:
                self._add_error(file_path, error, path)
                is_valid = False

        # Min/Max length validation
        if "minLength" in schema and isinstance(value, str):
            if len(value) < schema["minLength"]:
                self._add_error(
                    file_path,
                    f"String at {path} is too short (min {schema['minLength']})",
                    path,
                )
                is_valid = False

        if "maxLength" in schema and isinstance(value, str):
            if len(value) > schema["maxLength"]:
                self._add_error(
                    file_path,
                    f"String at {path} is too long (max {schema['maxLength']})",
                    path,
                )
                is_valid = False

        # Min/Max validation for numbers
        if "minimum" in schema and isinstance(value, (int, float)):
            if value < schema["minimum"]:
                self._add_error(
                    file_path,
                    f"Value at {path} is below minimum ({schema['minimum']})",
                    path,
                )
                is_valid = False

        if "maximum" in schema and isinstance(value, (int, float)):
            if value > schema["maximum"]:
                self._add_error(
                    file_path,
                    f"Value at {path} is above maximum ({schema['maximum']})",
                    path,
                )
                is_valid = False

        # Object property validation
        if schema.get("type") == "object" and isinstance(value, dict):
            # Check required properties
            if "required" in schema:
                for required in schema["required"]:
                    if required not in value:
                        self._add_error(
                            file_path,
                            f"Missing required field: {required}",
                            f"{path}.{required}" if path else required,
                        )
                        is_valid = False

            # Validate properties
            if "properties" in schema:
                for prop_name, prop_schema in schema["properties"].items():
                    if prop_name in value:
                        prop_valid = self._validate_value(
                            value[prop_name],
                            prop_schema,
                            f"{path}.{prop_name}" if path else prop_name,
                            file_path,
                        )
                        is_valid = is_valid and prop_valid

            # Validate additional properties
            if "additionalProperties" in schema:
                ap = schema["additionalProperties"]
                if ap is False:
                    # Check for extra properties
                    defined_props = set(schema.get("properties", {}).keys())
                    extra_props = set(value.keys()) - defined_props
                    if extra_props:
                        self._add_warning(
                            file_path,
                            f"Additional properties not allowed but found: {extra_props}",
                            path,
                        )
                elif isinstance(ap, dict):
                    # Validate additional properties against schema
                    defined_props = set(schema.get("properties", {}).keys())
                    for prop_name in value:
                        if prop_name not in defined_props:
                            prop_valid = self._validate_value(
                                value[prop_name],
                                ap,
                                f"{path}.{prop_name}" if path else prop_name,
                                file_path,
                            )
                            is_valid = is_valid and prop_valid

        # Array validation
        if schema.get("type") == "array" and isinstance(value, list):
            if "items" in schema:
                for i, item in enumerate(value):
                    item_valid = self._validate_value(
                        item, schema["items"], f"{path}[{i}]", file_path
                    )
                    is_valid = is_valid and item_valid

            if "minItems" in schema and len(value) < schema["minItems"]:
                self._add_error(
                    file_path,
                    f"Array at {path} has too few items (min {schema['minItems']})",
                    path,
                )
                is_valid = False

            if "maxItems" in schema and len(value) > schema["maxItems"]:
                self._add_error(
                    file_path,
                    f"Array at {path} has too many items (max {schema['maxItems']})",
                    path,
                )
                is_valid = False

        # allOf validation (composition)
        if "allOf" in schema:
            for sub_schema in schema["allOf"]:
                if "$ref" in sub_schema:
                    # Handle $ref to base schema
                    ref_schema = self._resolve_ref(sub_schema["$ref"])
                    if ref_schema:
                        ref_valid = self._validate_value(
                            value, ref_schema, path, file_path
                        )
                        is_valid = is_valid and ref_valid
                else:
                    sub_valid = self._validate_value(value, sub_schema, path, file_path)
                    is_valid = is_valid and sub_valid

        return is_valid

    def _resolve_ref(self, ref: str) -> dict | None:
        """Resolve a JSON schema $ref."""
        if ref == "../evidence-schema.json" or ref.endswith("evidence-schema.json"):
            return self.base_schema

        # Try to resolve relative path
        ref_path = Path(ref)
        if not ref_path.is_absolute():
            possible_path = EVIDENCE_TYPES_DIR.parent / ref_path
            if possible_path.exists():
                try:
                    with open(possible_path) as f:
                        return json.load(f)
                except Exception:
                    pass

        return None

    def _get_schema_for_evidence(self, evidence_data: dict) -> dict | None:
        """Get the appropriate schema for an evidence file."""
        evidence_type = evidence_data.get("evidence_type")

        if evidence_type and evidence_type in EVIDENCE_TYPE_SCHEMAS:
            schema_file = EVIDENCE_TYPE_SCHEMAS[evidence_type]
            if schema_file and schema_file in self.type_schemas:
                return self.type_schemas[schema_file]

        return self.base_schema

    def validate_file(self, file_path: Path) -> tuple[bool, list[dict], list[dict]]:
        """
        Validate a single evidence file.
        Returns (is_valid, errors, warnings).
        """
        file_errors_before = len(self.errors)
        file_warnings_before = len(self.warnings)

        if self.verbose:
            print(f"\nValidating: {file_path}")

        # Check file exists
        if not file_path.exists():
            self._add_error(str(file_path), "File does not exist")
            return (
                False,
                self.errors[file_errors_before:],
                self.warnings[file_warnings_before:],
            )

        # Try to parse JSON
        try:
            with open(file_path) as f:
                evidence_data = json.load(f)
        except json.JSONDecodeError as e:
            self._add_error(str(file_path), f"Invalid JSON: {e}")
            return (
                False,
                self.errors[file_errors_before:],
                self.warnings[file_warnings_before:],
            )
        except Exception as e:
            self._add_error(str(file_path), f"Error reading file: {e}")
            return (
                False,
                self.errors[file_errors_before:],
                self.warnings[file_warnings_before:],
            )

        # Get appropriate schema
        schema = self._get_schema_for_evidence(evidence_data)
        if not schema:
            self._add_warning(str(file_path), "No schema found, using basic validation")
            schema = self.base_schema or {"type": "object"}

        # Validate against schema
        is_valid = self._validate_value(evidence_data, schema, "", str(file_path))

        file_errors = self.errors[file_errors_before:]
        file_warnings = self.warnings[file_warnings_before:]

        if self.verbose:
            if is_valid and not file_warnings:
                print("  ✓ Valid")
            elif is_valid:
                print("  ⚠ Valid with warnings")
            else:
                print("  ✗ Invalid")
            for error in file_errors:
                print(f"    ERROR: {error['message']}")
            for warning in file_warnings:
                print(f"    WARNING: {warning['message']}")

        return is_valid, file_errors, file_warnings

    def validate_story(self, story_id: str) -> tuple[bool, list[dict], list[dict]]:
        """Validate all evidence files for a story."""
        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"Validating story: {story_id}")
            print(f"{'=' * 60}")

        story_errors_before = len(self.errors)
        story_warnings_before = len(self.warnings)
        all_valid = True

        # Find evidence files for this story
        evidence_files = []

        # Check docs/evidence/
        if EVIDENCE_DIR.exists():
            for pattern in [f"{story_id}*.json", f"{story_id}*.md"]:
                evidence_files.extend(EVIDENCE_DIR.glob(pattern))

        # Check docs/validation/evidence/
        if VALIDATION_EVIDENCE_DIR.exists():
            for pattern in [f"{story_id}*.json", f"{story_id}*.md"]:
                evidence_files.extend(VALIDATION_EVIDENCE_DIR.glob(pattern))

        # Check subdirectories
        if EVIDENCE_DIR.exists():
            story_subdir = EVIDENCE_DIR / story_id
            if story_subdir.exists():
                evidence_files.extend(story_subdir.glob("*.json"))
                evidence_files.extend(story_subdir.glob("*.md"))

        if not evidence_files:
            self._add_warning(story_id, f"No evidence files found for story {story_id}")
            if self.verbose:
                print("  ⚠ No evidence files found")

        for file_path in evidence_files:
            if file_path.suffix == ".json":
                is_valid, _, _ = self.validate_file(file_path)
                all_valid = all_valid and is_valid
            elif file_path.suffix == ".md":
                # Markdown files are not JSON-schema validated
                if self.verbose:
                    print(f"\nSkipping (markdown): {file_path}")

        story_errors = self.errors[story_errors_before:]
        story_warnings = self.warnings[story_warnings_before:]

        return all_valid, story_errors, story_warnings

    def validate_all(self) -> tuple[bool, list[dict], list[dict]]:
        """Validate all evidence files."""
        if self.verbose:
            print(f"\n{'=' * 60}")
            print("Validating all evidence files")
            print(f"{'=' * 60}")

        all_errors_before = len(self.errors)
        all_warnings_before = len(self.warnings)
        all_valid = True

        evidence_files = []

        # Collect all JSON evidence files
        if EVIDENCE_DIR.exists():
            evidence_files.extend(EVIDENCE_DIR.glob("*.json"))
            evidence_files.extend(EVIDENCE_DIR.glob("**/*.json"))

        if VALIDATION_EVIDENCE_DIR.exists():
            evidence_files.extend(VALIDATION_EVIDENCE_DIR.glob("*.json"))
            evidence_files.extend(VALIDATION_EVIDENCE_DIR.glob("**/*.json"))

        # Remove duplicates and filter
        evidence_files = list(
            set(
                f
                for f in evidence_files
                if f.suffix == ".json" and "evidence" in f.name.lower()
            )
        )

        if self.verbose:
            print(f"\nFound {len(evidence_files)} evidence files to validate")

        for file_path in sorted(evidence_files):
            is_valid, _, _ = self.validate_file(file_path)
            all_valid = all_valid and is_valid

        all_errors = self.errors[all_errors_before:]
        all_warnings = self.warnings[all_warnings_before:]

        return all_valid, all_errors, all_warnings

    def print_summary(self, ci_mode: bool = False) -> None:
        """Print validation summary."""
        print(f"\n{'=' * 60}")
        print("VALIDATION SUMMARY")
        print(f"{'=' * 60}")

        error_count = len(self.errors)
        warning_count = len(self.warnings)

        print(f"Errors:   {error_count}")
        print(f"Warnings: {warning_count}")

        if error_count > 0:
            print("\nErrors by file:")
            for error in self.errors:
                print(f"  [{error['severity']}] {error['file']}")
                if error["field"]:
                    print(f"    Field: {error['field']}")
                print(f"    {error['message']}")

        if warning_count > 0:
            print("\nWarnings by file:")
            for warning in self.warnings:
                print(f"  [{warning['severity']}] {warning['file']}")
                if warning["field"]:
                    print(f"    Field: {warning['field']}")
                print(f"    {warning['message']}")

        if error_count == 0 and warning_count == 0:
            print("\n✓ All validations passed!")
        elif error_count == 0:
            print("\n⚠ Validations passed with warnings")
        else:
            print(f"\n✗ {error_count} validation(s) failed")
            if ci_mode:
                print("  (CI mode: treating as warning only)")

        print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate evidence files against JSON schemas"
    )
    parser.add_argument(
        "--file", "-f", type=str, help="Validate a specific evidence file"
    )
    parser.add_argument(
        "--story-id", "-s", type=str, help="Validate all evidence files for a story ID"
    )
    parser.add_argument(
        "--all", "-a", action="store_true", help="Validate all evidence files"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="CI mode: warnings only (exit 0 even with errors)",
    )
    parser.add_argument(
        "--json-output", action="store_true", help="Output results as JSON"
    )

    args = parser.parse_args()

    # Validate arguments
    if not any([args.file, args.story_id, args.all]):
        parser.print_help()
        sys.exit(2)

    # Create validator
    try:
        validator = SchemaValidator(verbose=args.verbose)
    except Exception as e:
        print(f"Failed to initialize validator: {e}", file=sys.stderr)
        sys.exit(2)

    # Run validation
    try:
        if args.file:
            file_path = Path(args.file)
            is_valid, errors, warnings = validator.validate_file(file_path)
        elif args.story_id:
            is_valid, errors, warnings = validator.validate_story(args.story_id)
        else:  # args.all
            is_valid, errors, warnings = validator.validate_all()
    except Exception as e:
        print(f"Validation failed with error: {e}", file=sys.stderr)
        sys.exit(2)

    # Output results
    if args.json_output:
        result = {
            "valid": is_valid,
            "errors": validator.errors,
            "warnings": validator.warnings,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        print(json.dumps(result, indent=2))
    else:
        validator.print_summary(ci_mode=args.ci_mode)

    # Exit code
    if args.ci_mode:
        # CI mode: always exit 0, but log warnings
        sys.exit(0)
    elif is_valid and len(validator.errors) == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
