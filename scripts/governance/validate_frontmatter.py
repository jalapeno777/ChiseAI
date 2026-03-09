#!/usr/bin/env python3
"""
CLI tool for validating frontmatter in tempmemory markdown files.

Usage:
    python validate_frontmatter.py --file path/to/file.md
    python validate_frontmatter.py --directory path/to/directory
    python validate_frontmatter.py --directory path/to/directory --strict
    python validate_frontmatter.py --file path/to/file.md --fix
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from governance.tempmemory.frontmatter_validator import (
    FrontmatterValidator,
    ValidationResult,
)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="validate_frontmatter",
        description="Validate YAML frontmatter in tempmemory markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file docs/tempmemories/my-story.md
  %(prog)s --directory docs/tempmemories/
  %(prog)s --directory docs/tempmemories/ --strict
  %(prog)s --file docs/tempmemories/my-story.md --fix
        """,
    )

    parser.add_argument("--file", "-f", type=Path, help="Validate a single file")

    parser.add_argument(
        "--directory", "-d", type=Path, help="Validate all .md files in a directory"
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues where possible (not yet implemented)",
    )

    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )

    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        default=True,
        help="Search recursively in directories (default: True)",
    )

    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="Do not search recursively in directories",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show errors, suppress success messages",
    )

    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    return parser


def print_result(result: ValidationResult, quiet: bool = False) -> None:
    """Print a validation result."""
    if result.is_valid and not quiet:
        print(f"✓ {result.file_path}")
    elif not result.is_valid:
        print(f"✗ {result.file_path}")
        for error in result.errors:
            print(f"  ERROR: {error.message}")
        for warning in result.warnings:
            print(f"  WARNING: {warning.message}")


def print_json_results(results: list[ValidationResult]) -> None:
    """Print results as JSON."""
    import json

    output = []
    for result in results:
        output.append(
            {
                "file": str(result.file_path),
                "is_valid": result.is_valid,
                "errors": [
                    {"field": e.field, "message": e.message, "severity": e.severity}
                    for e in result.errors
                ],
                "warnings": [
                    {"field": w.field, "message": w.message, "severity": w.severity}
                    for w in result.warnings
                ],
            }
        )

    print(json.dumps(output, indent=2))


def validate_files(
    validator: FrontmatterValidator, files: list[Path], quiet: bool = False
) -> list[ValidationResult]:
    """Validate a list of files."""
    results = []

    for file_path in files:
        result = validator.validate_file(file_path)
        results.append(result)
        if not quiet or not result.is_valid:
            print_result(result, quiet)

    return results


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Validate arguments
    if not args.file and not args.directory:
        parser.error("Either --file or --directory must be specified")

    if args.file and args.directory:
        parser.error("Cannot specify both --file and --directory")

    # Initialize validator
    validator = FrontmatterValidator(strict=args.strict)

    results = []

    try:
        if args.file:
            # Validate single file
            if args.fix:
                print("Auto-fix not yet implemented", file=sys.stderr)
                return 1

            result = validator.validate_file(args.file)
            results.append(result)

            if args.json:
                print_json_results(results)
            else:
                print_result(result, args.quiet)

                if not result.is_valid:
                    print(f"\n{result.format_report()}", file=sys.stderr)

        elif args.directory:
            # Validate directory
            if not args.directory.exists():
                print(f"Error: Directory not found: {args.directory}", file=sys.stderr)
                return 1

            if args.fix:
                print("Auto-fix not yet implemented", file=sys.stderr)
                return 1

            results = validator.validate_directory(
                args.directory, recursive=args.recursive
            )

            if args.json:
                print_json_results(results)
            else:
                valid_count = sum(1 for r in results if r.is_valid)
                invalid_count = len(results) - valid_count

                if not args.quiet or invalid_count > 0:
                    print(f"\nValidated {len(results)} files:")
                    print(f"  Valid: {valid_count}")
                    print(f"  Invalid: {invalid_count}")

                for result in results:
                    if not result.is_valid:
                        print(f"\n{result.format_report()}", file=sys.stderr)

    except KeyboardInterrupt:
        print("\nValidation interrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Return exit code based on results
    invalid_results = [r for r in results if not r.is_valid]
    return 1 if invalid_results else 0


if __name__ == "__main__":
    sys.exit(main())
