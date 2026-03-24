#!/usr/bin/env python3
"""
Prevention Rule Parser - Parse and validate prevention_rule fields from incident logs.

This module extracts prevention_rule entries from multiple incident log formats
(YAML frontmatter, Redis JSON, and markdown) and validates they contain
actionable content suitable for durable governance.

Supported formats:
    1. YAML frontmatter in markdown files (iterlog format)
    2. JSON strings from Redis (rpush payloads)
    3. Markdown prose with "Prevention:" headers

Validation rules:
    - Must not be empty or whitespace-only
    - Must not be a placeholder (e.g., "N/A", "TBD", "TODO", "[How to prevent next time]")
    - Must be at least 10 characters long
    - Must contain at least one actionable verb pattern
    - Must not exceed 2000 characters

Exit codes:
    0 - All prevention rules valid
    1 - Validation failures found
    2 - Parse errors

Usage:
    python3 scripts/validation/prevention_rule_parser.py --file docs/tempmemories/iterlog-FOO.md
    python3 scripts/validation/prevention_rule_parser.py --json '{"prevention_rule": "..."}'
    echo 'prevention_rule: add retry' | python3 scripts/validation/prevention_rule_parser.py --stdin-yaml
"""

import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Validation severity levels."""

    ERROR = "error"
    WARNING = "warning"


class IncidentSeverity(str, Enum):
    """Standardized incident severity levels extracted from incident data."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    UNKNOWN = "UNKNOWN"


class RuleCategory(str, Enum):
    """Prevention rule category based on keyword classification."""

    NETWORK = "network"
    CI_CD = "ci_cd"
    SECURITY = "security"
    DATA_VALIDATION = "data_validation"
    CONFIGURATION = "configuration"
    GIT_WORKFLOW = "git_workflow"
    TESTING = "testing"
    MONITORING = "monitoring"
    GENERAL = "general"


# Category keyword mapping for rule classification
_CATEGORY_KEYWORDS: dict[RuleCategory, list[str]] = {
    RuleCategory.NETWORK: [
        "retry",
        "timeout",
        "connection",
        "network",
        "backoff",
        "dns",
        "socket",
        "tcp",
        "http",
        "api call",
        "endpoint",
        "latency",
    ],
    RuleCategory.CI_CD: [
        "ci",
        "pipeline",
        "lint",
        "pre-commit",
        "hook",
        "woodpecker",
        "build",
        "deploy",
        "merge",
        "branch",
        "push",
        "commit",
    ],
    RuleCategory.SECURITY: [
        "security",
        "vulnerability",
        "scan",
        "bandit",
        "sanitize",
        "escape",
        "inject",
        "auth",
        "permission",
        "secret",
        "credential",
    ],
    RuleCategory.DATA_VALIDATION: [
        "validate",
        "validat",
        "input",
        "schema",
        "type check",
        "null check",
        "empty check",
        "format",
        "sanitize data",
    ],
    RuleCategory.CONFIGURATION: [
        "config",
        "environment variable",
        "env var",
        "environment",
        "setting",
        "flag",
        "feature flag",
        "yaml",
        "json config",
    ],
    RuleCategory.GIT_WORKFLOW: [
        "rebase",
        "conflict",
        "worktree",
        "pr ",
        "pull request",
        "main branch",
        "feature branch",
        "squash",
    ],
    RuleCategory.TESTING: [
        "test",
        "tests",
        "testing",
        "unit test",
        "integration test",
        "coverage",
        "regression",
        "mock",
        "fixture",
    ],
    RuleCategory.MONITORING: [
        "monitor",
        "alert",
        "log",
        "metric",
        "dashboard",
        "grafana",
        "observe",
        "health check",
        "heartbeat",
    ],
}


def _build_category_patterns() -> dict[RuleCategory, list[re.Pattern]]:
    """Build regex patterns for each category's keywords.

    Single-word keywords use word boundaries. Multi-word keywords
    are matched as literal substrings (case-insensitive).
    """
    result: dict[RuleCategory, list[re.Pattern]] = {}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        patterns: list[re.Pattern] = []
        for kw in keywords:
            if " " in kw:
                # Multi-word: match as literal substring
                patterns.append(re.compile(re.escape(kw), re.IGNORECASE))
            else:
                # Single word: use word boundaries for exact matching
                patterns.append(
                    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
                )
        result[cat] = patterns
    return result


_CATEGORY_RES = _build_category_patterns()


@dataclass
class ValidationResult:
    """Result of validating a single prevention_rule."""

    is_valid: bool
    rule_text: str
    source: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


@dataclass
class ParseResult:
    """Aggregated result from parsing one or more sources."""

    rules: list[ValidationResult] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def all_valid(self) -> bool:
        return all(r.is_valid for r in self.rules) and not self.parse_errors

    @property
    def valid_count(self) -> int:
        return sum(1 for r in self.rules if r.is_valid)

    @property
    def invalid_count(self) -> int:
        return sum(1 for r in self.rules if not r.is_valid)

    @property
    def total_count(self) -> int:
        return len(self.rules)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_LENGTH = 10
MAX_LENGTH = 2000

PLACEHOLDER_PATTERNS = [
    r"N/?A\.?",
    r"TBD\.?",
    r"TODO\.?",
    r"\[.*\]",
    r"none",
    r"n/a",
    r"tbd",
    r"todo",
    r"\s*",
    r"how to prevent",
    r"\[How to prevent next time\]",
]

# Actionable verb patterns - at least one must be present
ACTIONABLE_PATTERNS = [
    r"\b(add|create|implement|enforce|validate|check|verify|ensure|require|use|run|configure|set|enable|disable|monitor|log|track|alert|block|prevent|avoid|test|write|document|review|audit|scan|reject|fail|guard|limit|cap|lock|restrict|wrap|include|install|deploy|update|remove|delete|cleanup|sanitize|escape|handle|catch|raise|throw|return|assert|confirm)\b",
    r"\b(always|never|must|shall|before|after|when|whenever|only if|unless|do not|don't|ensure that|make sure)\b",
]


def _build_placeholder_regex() -> re.Pattern:
    """Build a combined regex for placeholder detection (case-insensitive)."""
    return re.compile("|".join(PLACEHOLDER_PATTERNS), re.IGNORECASE)


_PLACEHOLDER_RE = _build_placeholder_regex()
_ACTIONABLE_RES = [re.compile(p, re.IGNORECASE) for p in ACTIONABLE_PATTERNS]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_prevention_rule(
    rule_text: str,
    source: str = "unknown",
    strict: bool = True,
) -> ValidationResult:
    """Validate a single prevention_rule string.

    Args:
        rule_text: The prevention rule text to validate.
        source: Description of where this rule came from (for error messages).
        strict: If True, missing actionable verbs is an error.
                If False, it's a warning.

    Returns:
        ValidationResult with is_valid, errors, and warnings.
    """
    result = ValidationResult(is_valid=True, rule_text=rule_text, source=source)

    if rule_text is None:
        result.add_error(f"[{source}] prevention_rule is None")
        return result

    if not isinstance(rule_text, str):
        result.add_error(
            f"[{source}] prevention_rule must be a string, got {type(rule_text).__name__}"
        )
        return result

    stripped = rule_text.strip()

    # Check empty
    if not stripped:
        result.add_error(f"[{source}] prevention_rule is empty")
        return result

    # Check placeholders
    if _PLACEHOLDER_RE.fullmatch(stripped):
        result.add_error(f"[{source}] prevention_rule is a placeholder: '{stripped}'")
        return result

    # Check minimum length
    if len(stripped) < MIN_LENGTH:
        result.add_error(
            f"[{source}] prevention_rule too short ({len(stripped)} chars, "
            f"minimum {MIN_LENGTH}): '{stripped[:50]}...'"
        )
        return result

    # Check maximum length
    if len(stripped) > MAX_LENGTH:
        result.add_warning(
            f"[{source}] prevention_rule is very long ({len(stripped)} chars, "
            f"consider condensing)"
        )

    # Check actionable content
    has_actionable = any(r.search(stripped) for r in _ACTIONABLE_RES)
    if not has_actionable:
        msg = (
            f"[{source}] prevention_rule lacks actionable verb patterns: "
            f"'{stripped[:80]}...'"
        )
        if strict:
            result.add_error(msg)
        else:
            result.add_warning(msg)

    return result


# ---------------------------------------------------------------------------
# Classification & Metadata Extraction
# ---------------------------------------------------------------------------


def classify_rule(rule_text: str) -> RuleCategory:
    """Classify a prevention rule into a category based on keyword analysis.

    Scans the rule text against category-specific keyword patterns and returns
    the first matching category. If no keywords match, returns GENERAL.

    Args:
        rule_text: The prevention rule text to classify.

    Returns:
        RuleCategory enum value.
    """
    stripped = rule_text.strip().lower()
    for category, patterns in _CATEGORY_RES.items():
        if any(p.search(stripped) for p in patterns):
            return category
    return RuleCategory.GENERAL


def extract_severity(data: dict) -> IncidentSeverity:
    """Extract and normalize a severity level from an incident data dict.

    Looks for 'severity', 'level', or 'priority' keys and normalizes
    to standard P0-P3 levels. Returns UNKNOWN if no valid severity found.

    Args:
        data: Dict potentially containing severity information.

    Returns:
        IncidentSeverity enum value.
    """
    raw = None
    for key in ("severity", "level", "priority"):
        if key in data:
            raw = str(data[key]).strip().upper()
            break

    if raw is None:
        return IncidentSeverity.UNKNOWN

    # Direct match
    for sev in IncidentSeverity:
        if sev.value == raw:
            return sev

    # Normalize common patterns: "critical" -> P0, "high" -> P1, etc.
    normalization = {
        "CRITICAL": IncidentSeverity.P0,
        "HIGH": IncidentSeverity.P1,
        "MEDIUM": IncidentSeverity.P2,
        "LOW": IncidentSeverity.P3,
        "URGENT": IncidentSeverity.P0,
        "MAJOR": IncidentSeverity.P1,
        "MINOR": IncidentSeverity.P3,
        "TRIVIAL": IncidentSeverity.P3,
    }
    return normalization.get(raw, IncidentSeverity.UNKNOWN)


def extract_story_id(data: dict) -> str | None:
    """Extract story_id from an incident data dict.

    Looks for 'story_id', 'story-id', 'storyId', or 'id' keys.

    Args:
        data: Dict potentially containing a story identifier.

    Returns:
        Story ID string or None if not found.
    """
    for key in ("story_id", "story-id", "storyId", "id"):
        if key in data and data[key] is not None:
            val = str(data[key]).strip()
            if val:
                return val
    return None


def detect_duplicate_rules(
    rules: list[ValidationResult],
    similarity_threshold: float = 0.8,
) -> list[tuple[int, int, float]]:
    """Detect near-duplicate prevention rules based on token overlap similarity.

    Compares each pair of rules and returns pairs that exceed the similarity
    threshold. Uses a simple token-set Jaccard similarity for efficiency.

    Args:
        rules: List of ValidationResult to compare.
        similarity_threshold: Minimum Jaccard similarity (0.0-1.0) to flag
            as duplicate. Defaults to 0.8.

    Returns:
        List of (index_a, index_b, similarity_score) tuples for pairs
        exceeding the threshold. Each pair is reported once (a < b).
    """

    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"\b\w+\b", text.lower()))

    token_sets = [_tokenize(r.rule_text) for r in rules]
    duplicates: list[tuple[int, int, float]] = []

    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            a, b = token_sets[i], token_sets[j]
            if not a or not b:
                continue
            intersection = a & b
            union = a | b
            similarity = len(intersection) / len(union)
            if similarity >= similarity_threshold:
                duplicates.append((i, j, round(similarity, 3)))

    return duplicates


def generate_summary(result: ParseResult) -> dict:
    """Generate a structured summary dict from a ParseResult.

    Produces a JSON-serializable summary with counts, categories,
    severities (when available), and duplicate detection.

    Args:
        result: ParseResult from any parse function.

    Returns:
        Dict with structured summary data.
    """
    categories: dict[str, int] = {}
    for r in result.rules:
        cat = classify_rule(r.rule_text)
        categories[cat.value] = categories.get(cat.value, 0) + 1

    duplicates = detect_duplicate_rules(result.rules) if result.total_count > 1 else []

    return {
        "total_rules": result.total_count,
        "valid_count": result.valid_count,
        "invalid_count": result.invalid_count,
        "parse_errors": len(result.parse_errors),
        "all_valid": result.all_valid,
        "categories": categories,
        "duplicate_pairs": [
            {"rule_a_index": a, "rule_b_index": b, "similarity": sim}
            for a, b, sim in duplicates
        ],
        "invalid_sources": [
            {"source": r.source, "errors": r.errors}
            for r in result.rules
            if not r.is_valid
        ],
    }


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_from_yaml_string(yaml_str: str, source: str = "yaml_string") -> ParseResult:
    """Parse prevention_rule from a YAML string.

    Expects a mapping that may contain 'prevention_rule' or 'prevention' keys,
    or an 'issues' list where each item may have 'prevention_rule'.

    Args:
        yaml_str: Raw YAML content.
        source: Label for error messages.

    Returns:
        ParseResult with extracted and validated rules.
    """
    result = ParseResult()

    if not YAML_AVAILABLE:
        result.parse_errors.append(f"[{source}] PyYAML not available")
        return result

    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        result.parse_errors.append(f"[{source}] YAML parse error: {e}")
        return result

    if not isinstance(data, dict):
        result.parse_errors.append(
            f"[{source}] Expected YAML mapping, got {type(data).__name__}"
        )
        return result

    _extract_rules_from_dict(data, source, result)
    return result


def parse_from_yaml_file(
    file_path: Path, source: str | None = None, strict: bool = True
) -> ParseResult:
    """Parse prevention_rule from a YAML or markdown-with-YAML-frontmatter file.

    Args:
        file_path: Path to the file.
        source: Optional label; defaults to the file path.
        strict: If True, missing actionable verbs is an error.

    Returns:
        ParseResult with extracted and validated rules.
    """
    source = source or str(file_path)
    result = ParseResult()

    if not file_path.exists():
        result.parse_errors.append(f"[{source}] File not found: {file_path}")
        return result

    content = file_path.read_text(encoding="utf-8")

    # Check for YAML frontmatter (between --- delimiters, or opening --- only)
    has_frontmatter = False
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            # Standard frontmatter: ---\nyaml\n---
            yaml_content = parts[1].strip()
            has_frontmatter = True
        else:
            # Opening --- only: try to extract YAML up to first markdown heading
            rest = content[3:].lstrip("\n")
            # Find the first markdown heading or blank-line boundary
            fm_end = len(rest)
            for m in re.finditer(r"^(?:#|\n\n)", rest, re.MULTILINE):
                if m.start() > 0:
                    fm_end = m.start()
                    break
            yaml_content = rest[:fm_end].strip()
            if yaml_content:
                has_frontmatter = True

    if has_frontmatter and yaml_content:
        fm_result = parse_from_yaml_string(yaml_content, f"{source}:frontmatter")
        result.rules.extend(fm_result.rules)
        result.parse_errors.extend(fm_result.parse_errors)

    # Also try parsing the full file as YAML (handles pure YAML files).
    # Skip this for markdown files that have frontmatter delimiters,
    # since the full content will fail YAML parsing.
    if not has_frontmatter:
        pure_result = parse_from_yaml_string(content, f"{source}:yaml")
        if not result.rules and pure_result.rules:
            result.rules.extend(pure_result.rules)
        if pure_result.parse_errors and not result.parse_errors:
            result.parse_errors.extend(pure_result.parse_errors)

    # Scan for inline prevention patterns in markdown prose
    _extract_from_markdown_prose(content, source, result, strict=strict)

    return result


def parse_from_json(
    json_str: str, source: str = "json", strict: bool = True
) -> ParseResult:
    """Parse prevention_rule from a JSON string (Redis payload format).

    Expects a JSON object with a 'prevention_rule' key, or an array of such objects.

    Args:
        json_str: Raw JSON content.
        source: Label for error messages.
        strict: If True, missing actionable verbs is an error.

    Returns:
        ParseResult with extracted and validated rules.
    """
    result = ParseResult()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        result.parse_errors.append(f"[{source}] JSON parse error: {e}")
        return result

    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                _extract_rules_from_dict(item, f"{source}[{i}]", result, strict=strict)
    elif isinstance(data, dict):
        _extract_rules_from_dict(data, source, result, strict=strict)
    else:
        result.parse_errors.append(
            f"[{source}] Expected JSON object or array, got {type(data).__name__}"
        )

    return result


def parse_prevention_rules(file_path: Path, strict: bool = True) -> ParseResult:
    """Convenience entry point: auto-detect format and parse.

    Supports .yaml, .yml, .json files and .md files with YAML frontmatter.

    Args:
        file_path: Path to the incident log file.
        strict: If True, missing actionable verbs is an error.

    Returns:
        ParseResult with extracted and validated rules.
    """
    source = str(file_path)
    suffix = file_path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        return parse_from_yaml_file(file_path, source, strict=strict)
    elif suffix == ".json":
        content = file_path.read_text(encoding="utf-8")
        return parse_from_json(content, source, strict=strict)
    elif suffix == ".md":
        return parse_from_yaml_file(file_path, source, strict=strict)
    else:
        # Try YAML first, then JSON
        content = file_path.read_text(encoding="utf-8")
        result = parse_from_yaml_string(content, source)
        if not result.rules and not result.parse_errors:
            result = parse_from_json(content, source, strict=strict)
        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_rules_from_dict(
    data: dict, source: str, result: ParseResult, strict: bool = True
) -> None:
    """Extract prevention_rule from a dict and validate it."""
    # Extract metadata if present
    severity = extract_severity(data)
    story_id = extract_story_id(data)
    if severity != IncidentSeverity.UNKNOWN:
        result.metadata[f"{source}:severity"] = severity.value
    if story_id:
        result.metadata[f"{source}:story_id"] = story_id

    # Direct key
    for key in ("prevention_rule", "prevention"):
        if key in data and data[key] is not None:
            rule_str = str(data[key]).strip()
            if rule_str:
                vr = validate_prevention_rule(
                    rule_str, f"{source}:{key}", strict=strict
                )
                result.rules.append(vr)
                return  # Don't double-count

    # Nested under 'issues' list
    issues = data.get("issues", [])
    if isinstance(issues, list):
        for i, issue in enumerate(issues):
            if isinstance(issue, dict):
                # Extract per-issue metadata
                issue_sev = extract_severity(issue)
                issue_story = extract_story_id(issue)
                if issue_sev != IncidentSeverity.UNKNOWN:
                    result.metadata[f"{source}:issues[{i}]:severity"] = issue_sev.value
                if issue_story:
                    result.metadata[f"{source}:issues[{i}]:story_id"] = issue_story

                for key in ("prevention_rule", "prevention"):
                    if key in issue and issue[key] is not None:
                        rule_str = str(issue[key]).strip()
                        if rule_str:
                            vr = validate_prevention_rule(
                                rule_str,
                                f"{source}:issues[{i}].{key}",
                                strict=strict,
                            )
                            result.rules.append(vr)
                            break  # One rule per issue item


def _extract_from_markdown_prose(
    content: str, source: str, result: ParseResult, strict: bool = True
) -> None:
    """Extract prevention rules from markdown prose sections.

    Looks for patterns like:
    **Prevention:**\n<rule text>
    prevention_rule: <rule text>

    Args:
        content: Markdown content to scan.
        source: Label for error messages.
        result: ParseResult to append rules to.
        strict: If True, missing actionable verbs is an error.
    """
    # Pattern 1: Bold header "Prevention:" followed by text
    bold_pattern = re.compile(
        r"\*\*Prevention[\s:]+\*\*\s*\n(.+?)(?:\n\n|\n##|\Z)",
        re.DOTALL,
    )
    for m in bold_pattern.finditer(content):
        rule_text = m.group(1).strip()
        if rule_text and rule_text != "N/A":
            vr = validate_prevention_rule(
                rule_text, f"{source}:markdown_prevention", strict=strict
            )
            # Only add if we don't already have this exact rule
            if not any(r.rule_text == rule_text for r in result.rules):
                result.rules.append(vr)

    # Pattern 2: Inline key-value in prose
    inline_pattern = re.compile(
        r"prevention_rule:\s*(.+?)(?:\n|$)",
        re.IGNORECASE,
    )
    for m in inline_pattern.finditer(content):
        rule_text = m.group(1).strip()
        if rule_text:
            vr = validate_prevention_rule(rule_text, f"{source}:inline", strict=strict)
            if not any(r.rule_text == rule_text for r in result.rules):
                result.rules.append(vr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse and validate prevention_rule fields from incident logs."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to incident log file")
    group.add_argument("--json", dest="json_str", help="JSON string to parse")
    group.add_argument(
        "--stdin-yaml",
        action="store_true",
        help="Read YAML from stdin",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Treat warnings as errors (default: True)",
    )
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="Treat actionable-verb check as warning only",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all validation details",
    )

    args = parser.parse_args()

    strict = not args.lenient

    if args.file:
        result = parse_prevention_rules(args.file, strict=strict)
    elif args.json_str:
        result = parse_from_json(
            args.json_str,
            "cli_json",
            strict=strict,
        )
    elif args.stdin_yaml:
        yaml_content = sys.stdin.read()
        result = parse_from_yaml_string(yaml_content, "stdin_yaml")

    # Print results
    if args.verbose or not result.all_valid:
        for vr in result.rules:
            status = "PASS" if vr.is_valid else "FAIL"
            print(f"[{status}] {vr.source}: {vr.rule_text[:80]}")
            for err in vr.errors:
                print(f"  ERROR: {err}")
            for warn in vr.warnings:
                print(f"  WARN: {warn}")

    for pe in result.parse_errors:
        print(f"PARSE ERROR: {pe}")

    print(f"\nSummary: {result.valid_count}/{result.total_count} valid")
    if result.parse_errors:
        print(f"  Parse errors: {len(result.parse_errors)}")

    if result.all_valid:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
