#!/usr/bin/env python3
"""Validate Redis key prefix consistency between LearningLoop and validators.

Canonical prefix: bmad:chiseai:metacog:*

This script scans source code to ensure all metacognition-related Redis keys
use the canonical prefix, preventing mismatches between producers (LearningLoop)
and consumers (validators).

Usage:
    python3 scripts/validation/validate_redis_key_prefixes.py
    python3 scripts/validation/validate_redis_key_prefixes.py --fix
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Canonical prefix that all metacog Redis keys must use
CANONICAL_PREFIX = "bmad:chiseai:metacog"

# Known wrong prefixes that should be flagged
KNOWN_WRONG_PREFIXES = [
    "bmad:chiseai:learning:",
    "chise:metacog:",
    "bmad:metacog:",
]

# Files to scan for prefix consistency
SCAN_PATHS = [
    Path("src/autonomous_cognition/metacog/"),
    Path("scripts/validation/"),
]

# File extensions to scan
SCAN_EXTENSIONS = {".py"}

# Lines matching these patterns are not real key usage
EXCLUSION_LINE_PATTERNS = [
    r"qdrant_fallback",  # Qdrant fallback is a separate concern
    r"autocog:learning_stats",  # Stats key has its own namespace
]

# This script itself contains wrong-prefix strings in its exclusion list definition
_SELF_EXCLUDE: set[Path] = {Path("scripts/validation/validate_redis_key_prefixes.py")}


@dataclass
class Finding:
    """A prefix mismatch finding."""

    file: Path
    line: int
    raw_line: str
    wrong_prefix: str
    suggestion: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: uses '{self.wrong_prefix}', should use '{self.suggestion}'"


@dataclass
class ValidationResult:
    """Result of prefix validation."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    files_with_issues: int = 0

    @property
    def ok(self) -> bool:
        return len(self.findings) == 0


def _is_excluded(line: str) -> bool:
    """Check if a line matches any exclusion pattern."""
    return any(re.search(pattern, line) for pattern in EXCLUSION_LINE_PATTERNS)


def _suggest_fix(wrong_prefix: str) -> str:
    """Generate the corrected prefix."""
    for wrong_root in KNOWN_WRONG_PREFIXES:
        if wrong_prefix.startswith(wrong_root):
            suffix = wrong_prefix[len(wrong_root) :]
            return f"{CANONICAL_PREFIX}:{suffix}"
    return CANONICAL_PREFIX


def scan_file(filepath: Path) -> list[Finding]:
    """Scan a single file for wrong Redis key prefixes."""
    findings: list[Finding] = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings

    for i, line in enumerate(content.splitlines(), 1):
        if _is_excluded(line):
            continue
        for wrong_prefix in KNOWN_WRONG_PREFIXES:
            if wrong_prefix in line:
                suggestion = _suggest_fix(
                    wrong_prefix
                    + line.split(wrong_prefix)[1].split('"')[0].split("'")[0]
                )
                findings.append(
                    Finding(
                        file=filepath,
                        line=i,
                        raw_line=line.strip(),
                        wrong_prefix=wrong_prefix,
                        suggestion=suggestion,
                    )
                )
    return findings


def validate(root: Path = Path(".")) -> ValidationResult:
    """Run validation across all scan paths."""
    result = ValidationResult()

    for scan_path in SCAN_PATHS:
        full_path = root / scan_path
        if not full_path.exists():
            print(f"  WARN: {full_path} does not exist, skipping", file=sys.stderr)
            continue

        for filepath in sorted(full_path.rglob("*")):
            if filepath.suffix not in SCAN_EXTENSIONS:
                continue
            if filepath.name.startswith("."):
                continue
            if filepath in _SELF_EXCLUDE:
                continue

            result.files_scanned += 1
            findings = scan_file(filepath)
            if findings:
                result.files_with_issues += 1
                result.findings.extend(findings)

    return result


def main() -> int:
    """Entry point."""
    root = Path(".")
    result = validate(root)

    print(f"Scanned {result.files_scanned} files in {len(SCAN_PATHS)} directories")

    if result.ok:
        print("PASS: All Redis key prefixes match canonical bmad:chiseai:metacog:*")
        return 0

    print(
        f"FAIL: {len(result.findings)} finding(s) in {result.files_with_issues} file(s)"
    )
    print()
    for finding in result.findings:
        print(f"  {finding}")
        print(f"    > {finding.raw_line}")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
