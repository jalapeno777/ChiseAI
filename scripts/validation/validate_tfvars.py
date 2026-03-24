#!/usr/bin/env python3
"""
Pre-commit hook to validate that no secrets are in Terraform template files.

Checks all *.tfvars.template files in infrastructure/terraform/ for potential secrets
and exits with appropriate status codes.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Placeholder patterns that are considered safe
PLACEHOLDER_PATTERNS = [
    r"^\s*$",  # Empty or whitespace-only values
    r'^[\s]*"?[\s]*"?[\s]*$',  # Empty quotes
    r"(?i)change[_\-]?me",  # CHANGE_ME, change_me, change-me, changeme
    r"(?i)your[_\-]",  # your-api-key, your_token, etc.
    r"(?i)placeholder",
    r"(?i)example",
    r"(?i)dummy",
    r"(?i)fake",
    r"(?i)test[_\-]?only",
    r"(?i)replace[_\-]?me",
    r"(?i)insert[_\-]?",
    r"(?i)todo",
    r"(?i)xxx+",
    r"(?i)admin",  # Common default passwords like "admin"
    r"(?i)password",  # Literal word "password"
    r"(?i)secret",  # Literal word "secret"
    r"(?i)token",  # Literal word "token"
]

# Patterns that indicate potential secrets
SECRET_PATTERNS = [
    # API keys (various formats)
    r"[a-zA-Z0-9]{32,}",  # Long alphanumeric strings (32+ chars)
    r"[a-f0-9]{32,}",  # Hex strings (32+ chars)
    r"sk-[a-zA-Z0-9]{20,}",  # OpenAI-style keys
    r"[A-Za-z0-9]{20,}[_-][A-Za-z0-9]{10,}",  # Key with separators
]

# Base64-like pattern (alphanumeric with +, /, = padding)
BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]{20,}={0,2}$")

# Token pattern (alphanumeric with common separators like _ and -)
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,}$")

# UUID pattern
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def is_placeholder(value: str) -> bool:
    """Check if a value is a known placeholder pattern."""
    value_stripped = value.strip().strip("\"'")

    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, value_stripped, re.IGNORECASE):
            return True

    return False


def looks_like_secret(value: str) -> tuple[bool, str]:
    """
    Check if a value looks like a potential secret.

    Returns:
        Tuple of (is_secret, reason)
    """
    value_stripped = value.strip().strip("\"'")

    # Skip empty values
    if not value_stripped:
        return False, "empty value"

    # Check if it's a known placeholder
    if is_placeholder(value_stripped):
        return False, "placeholder pattern"

    # Check for UUIDs (often used as API keys)
    if UUID_PATTERN.match(value_stripped):
        return True, "UUID-like pattern (potential API key)"

    # Check for base64-like strings (long, with base64 chars)
    if len(value_stripped) >= 20 and BASE64_PATTERN.match(value_stripped):
        return True, "base64-like pattern"

    # Check for long tokens with padding (e.g., API tokens with = padding)
    if len(value_stripped) >= 40 and re.match(
        r"^[A-Za-z0-9_-]+={0,2}$", value_stripped
    ):
        has_upper = bool(re.search(r"[A-Z]", value_stripped))
        has_lower = bool(re.search(r"[a-z]", value_stripped))
        has_digit = bool(re.search(r"[0-9]", value_stripped))

        if sum([has_upper, has_lower, has_digit]) >= 2:
            return True, "high-entropy token (potential secret)"

    # Check for long alphanumeric strings that aren't obviously placeholders
    if len(value_stripped) > 20:
        # Check if it looks like a random key
        if re.match(r"^[A-Za-z0-9_-]+$", value_stripped):
            # Check for high entropy (mix of upper, lower, digits)
            has_upper = bool(re.search(r"[A-Z]", value_stripped))
            has_lower = bool(re.search(r"[a-z]", value_stripped))
            has_digit = bool(re.search(r"[0-9]", value_stripped))

            if sum([has_upper, has_lower, has_digit]) >= 2:
                return True, "high-entropy string (potential secret)"

    # Check for hex strings that are long
    if len(value_stripped) >= 32 and re.match(
        r"^[a-f0-9]+$", value_stripped, re.IGNORECASE
    ):
        return True, "long hex string (potential secret)"

    # Check for common secret patterns
    if re.match(r"^[A-Za-z0-9_-]{20,}$", value_stripped):
        # Check if it has mixed case and numbers (high entropy indicator)
        has_upper = bool(re.search(r"[A-Z]", value_stripped))
        has_lower = bool(re.search(r"[a-z]", value_stripped))
        has_digit = bool(re.search(r"[0-9]", value_stripped))

        if has_upper and has_lower and has_digit:
            return True, "mixed-case alphanumeric (potential secret)"

    return False, "no secret pattern detected"


def parse_tfvars_line(line: str) -> tuple[str, str] | None:
    """
    Parse a tfvars line to extract variable name and value.

    Returns:
        Tuple of (variable_name, value) or None if not a variable assignment
    """
    # Skip comments and empty lines
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Match variable assignment patterns
    # Supports: var_name = "value" or var_name = value
    match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$", line)
    if match:
        var_name = match.group(1)
        value = match.group(2).strip()
        return var_name, value

    return None


def check_file(filepath: Path) -> list[tuple[int, str, str, str]]:
    """
    Check a single tfvars file for potential secrets.

    Returns:
        List of tuples (line_number, variable_name, value, reason)
    """
    findings = []

    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return findings

    for line_num, line in enumerate(lines, start=1):
        parsed = parse_tfvars_line(line)
        if parsed is None:
            continue

        var_name, value = parsed
        is_secret, reason = looks_like_secret(value)

        if is_secret:
            findings.append((line_num, var_name, value, reason))

    return findings


def fix_file(filepath: Path, findings: list[tuple[int, str, str, str]]) -> int:
    """
    Replace detected secrets with CHANGE_ME in the file.

    Returns:
        Number of replacements made
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath} for fix: {e}", file=sys.stderr)
        return 0

    # Split into lines, preserving the original line endings
    lines = content.splitlines()
    # Track if file ends with newline
    ends_with_newline = content.endswith("\n")

    replacements = 0
    # Process in reverse order to maintain line numbers
    for line_num, var_name, value, reason in sorted(
        findings, key=lambda x: x[0], reverse=True
    ):
        line_idx = line_num - 1
        if line_idx < len(lines):
            original_line = lines[line_idx]
            # Replace the value part while preserving structure
            # Match: var_name = "value" or var_name = value
            # Replace only the value part after the equals sign
            new_line = re.sub(
                r'^(\s*[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*)"?[^"]*"?\s*$',
                r'\1"CHANGE_ME"',
                original_line,
            )
            if new_line != original_line:
                lines[line_idx] = new_line
                replacements += 1

    try:
        # Reconstruct file with proper line endings
        new_content = "\n".join(lines)
        if ends_with_newline:
            new_content += "\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        return replacements
    except Exception as e:
        print(f"Error writing {filepath}: {e}", file=sys.stderr)
        return 0


def find_tfvars_templates(directory: Path) -> list[Path]:
    """Find all .tfvars.template files in the given directory."""
    templates = []
    if directory.exists():
        for filepath in directory.rglob("*.tfvars.template"):
            templates.append(filepath)
    return templates


def main():
    parser = argparse.ArgumentParser(
        description="Validate Terraform template files for potential secrets"
    )
    parser.add_argument(
        "--directory",
        "-d",
        default="infrastructure/terraform",
        help="Directory to search for .tfvars.template files (default: infrastructure/terraform)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically replace detected secrets with CHANGE_ME",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output for all files, not just those with issues",
    )

    args = parser.parse_args()

    # Find all template files
    search_dir = Path(args.directory)
    template_files = find_tfvars_templates(search_dir)

    if not template_files:
        if args.verbose:
            print(f"No .tfvars.template files found in {search_dir}")
        sys.exit(0)

    all_findings = {}
    total_files_checked = 0

    for filepath in sorted(template_files):
        total_files_checked += 1
        findings = check_file(filepath)

        if findings:
            all_findings[filepath] = findings

            if args.fix:
                replacements = fix_file(filepath, findings)
                print(f"Fixed {replacements} secret(s) in {filepath}")
            else:
                print(f"\n⚠️  Potential secrets found in: {filepath}")
                for line_num, var_name, value, reason in findings:
                    # Truncate long values for display
                    display_value = value.strip().strip("\"'")
                    if len(display_value) > 50:
                        display_value = display_value[:47] + "..."
                    print(f"  Line {line_num}: {var_name}")
                    print(f'    Value: "{display_value}"')
                    print(f"    Reason: {reason}")
        elif args.verbose:
            print(f"✓ {filepath} - clean")

    # Summary
    if all_findings:
        total_secrets = sum(len(f) for f in all_findings.values())
        if args.fix:
            print(
                f"\n✓ Fixed {total_secrets} potential secret(s) in {len(all_findings)} file(s)"
            )
            sys.exit(0)
        else:
            print(
                f"\n❌ Found {total_secrets} potential secret(s) in {len(all_findings)} file(s)"
            )
            print("\nRun with --fix to automatically replace with CHANGE_ME")
            sys.exit(1)
    else:
        if args.verbose:
            print(f"\n✓ All {total_files_checked} file(s) checked - no secrets found")
        sys.exit(0)


if __name__ == "__main__":
    main()
