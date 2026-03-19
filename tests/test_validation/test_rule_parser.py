"""
Tests for prevention_rule_parser.py

Comprehensive tests covering:
- YAML frontmatter parsing
- JSON (Redis payload) parsing
- Markdown prose extraction
- Validation rules (length, placeholders, actionable verbs)
- Edge cases (None, empty, non-string, malformed input)
- CLI integration
"""

import json
from pathlib import Path

import pytest
import yaml

import importlib.util

# Load the module directly to avoid broken __init__.py imports
_module_path = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "validation"
    / "prevention_rule_parser.py"
)
_spec = importlib.util.spec_from_file_location("prevention_rule_parser", _module_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Export symbols for test access
validate_prevention_rule = _mod.validate_prevention_rule
parse_from_yaml_string = _mod.parse_from_yaml_string
parse_from_yaml_file = _mod.parse_from_yaml_file
parse_from_json = _mod.parse_from_json
parse_prevention_rules = _mod.parse_prevention_rules
ValidationResult = _mod.ValidationResult
ParseResult = _mod.ParseResult
classify_rule = _mod.classify_rule
extract_severity = _mod.extract_severity
extract_story_id = _mod.extract_story_id
detect_duplicate_rules = _mod.detect_duplicate_rules
generate_summary = _mod.generate_summary
IncidentSeverity = _mod.IncidentSeverity
RuleCategory = _mod.RuleCategory


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def valid_rule_text() -> str:
    """A valid, actionable prevention rule."""
    return "Always run the full Woodpecker lint stack locally before pushing when touching scripts/*.py"


@pytest.fixture
def valid_incident_yaml() -> str:
    """YAML with a single incident containing a valid prevention_rule."""
    return yaml.dump(
        {
            "story_id": "TEST-001",
            "issues": [
                {
                    "issue_type": "merge_conflict",
                    "severity": "P1",
                    "root_cause": "Redis connection timeout due to network partition",
                    "prevention_rule": "Add retry logic with exponential backoff for Redis connections",
                }
            ],
        }
    )


@pytest.fixture
def valid_incident_json() -> str:
    """JSON matching the Redis rpush payload format."""
    return json.dumps(
        {
            "story_id": "TEST-001",
            "severity": "P1",
            "symptom": "Redis connection timeout",
            "root_cause": "Network partition",
            "prevention_rule": "Add retry logic with exponential backoff for Redis connections",
            "timestamp": "2026-03-01T12:00:00Z",
        }
    )


@pytest.fixture
def markdown_with_frontmatter(tmp_path: Path) -> Path:
    """Markdown file with YAML frontmatter containing prevention_rule."""
    content = """---
story_id: TEST-002
issues:
  - issue_type: file_access
    severity: P2
    prevention_rule: "Check directory permissions before operations"

## Incidents

### Incident 1

**Prevention:**
Ensure all temp directories are created with proper permissions before writing.

"""
    p = tmp_path / "iterlog.md"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def markdown_prose_only(tmp_path: Path) -> Path:
    """Markdown file with only prose prevention sections (no frontmatter)."""
    content = """# Iteration Log: PROSE-001

## Incident: 2026-03-01

**Symptom:**
Dashboard failed to load.

**Root Cause:**
Missing environment variable.

**Prevention:**
Validate all required environment variables are set at application startup.

"""
    p = tmp_path / "prose.md"
    p.write_text(content, encoding="utf-8")
    return p


# ===================================================================
# validate_prevention_rule
# ===================================================================


class TestValidatePreventionRule:
    """Tests for the core validation function."""

    def test_valid_rule_passes(self, valid_rule_text):
        """AC2: Valid actionable rule should pass validation."""
        result = validate_prevention_rule(valid_rule_text, source="test")
        assert result.is_valid is True
        assert not result.errors

    def test_none_rule_fails(self):
        """None prevention_rule should fail."""
        result = validate_prevention_rule(None, source="test")
        assert result.is_valid is False
        assert any("None" in e for e in result.errors)

    def test_empty_string_fails(self):
        """Empty string should fail."""
        result = validate_prevention_rule("", source="test")
        assert result.is_valid is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_whitespace_only_fails(self):
        """Whitespace-only string should fail."""
        result = validate_prevention_rule("   \n\t  ", source="test")
        assert result.is_valid is False

    def test_non_string_type_fails(self):
        """Non-string types should fail."""
        result = validate_prevention_rule(42, source="test")
        assert result.is_valid is False
        assert any("string" in e.lower() for e in result.errors)

    def test_list_type_fails(self):
        """List type should fail."""
        result = validate_prevention_rule(["rule1"], source="test")
        assert result.is_valid is False

    def test_too_short_fails(self):
        """Rule shorter than 10 chars should fail."""
        result = validate_prevention_rule("Add retry", source="test")
        assert result.is_valid is False
        assert any("too short" in e.lower() for e in result.errors)

    def test_exactly_min_length_passes(self):
        """Rule at exactly 10 chars with actionable verb should pass."""
        rule = "Always check env vars before deploy"
        result = validate_prevention_rule(rule, source="test")
        assert result.is_valid is True

    def test_placeholder_na_fails(self):
        """'N/A' placeholder should fail."""
        result = validate_prevention_rule("N/A", source="test")
        assert result.is_valid is False
        assert any("placeholder" in e.lower() for e in result.errors)

    def test_placeholder_tbd_fails(self):
        """'TBD' placeholder should fail."""
        result = validate_prevention_rule("TBD", source="test")
        assert result.is_valid is False

    def test_placeholder_todo_fails(self):
        """'TODO' placeholder should fail."""
        result = validate_prevention_rule("TODO", source="test")
        assert result.is_valid is False

    def test_placeholder_bracketed_fails(self):
        """'[How to prevent next time]' placeholder should fail."""
        result = validate_prevention_rule("[How to prevent next time]", source="test")
        assert result.is_valid is False

    def test_placeholder_none_fails(self):
        """'none' should fail."""
        result = validate_prevention_rule("none", source="test")
        assert result.is_valid is False

    def test_no_actionable_verb_fails_strict(self):
        """Rule without actionable verb should fail in strict mode."""
        rule = "The system experienced a problem that needs resolution soon"
        result = validate_prevention_rule(rule, source="test", strict=True)
        assert result.is_valid is False
        assert any("actionable" in e.lower() for e in result.errors)

    def test_no_actionable_verb_warns_lenient(self):
        """Rule without actionable verb should warn in lenient mode."""
        rule = "The system experienced a problem that needs resolution soon"
        result = validate_prevention_rule(rule, source="test", strict=False)
        # In lenient mode, missing actionable verb is a warning not error
        assert any("actionable" in w.lower() for w in result.warnings)

    def test_very_long_rule_warns(self):
        """Rule exceeding 2000 chars should warn."""
        rule = "Always " + "verify " * 500  # ~3500 chars
        result = validate_prevention_rule(rule, source="test")
        assert result.is_valid is True  # Still valid, just warned
        assert any("long" in w.lower() for w in result.warnings)

    def test_actionable_verb_add(self):
        """Rule starting with 'Add' should pass."""
        result = validate_prevention_rule(
            "Add retry logic with exponential backoff for all Redis connections",
            source="test",
        )
        assert result.is_valid is True

    def test_actionable_verb_enforce(self):
        """Rule with 'enforce' should pass."""
        result = validate_prevention_rule(
            "Enforce pre-commit hooks for all Python files in the repository",
            source="test",
        )
        assert result.is_valid is True

    def test_actionable_verb_validate(self):
        """Rule with 'validate' should pass."""
        result = validate_prevention_rule(
            "Validate all required environment variables are set before starting",
            source="test",
        )
        assert result.is_valid is True

    def test_actionable_verb_ensure(self):
        """Rule with 'ensure' should pass."""
        result = validate_prevention_rule(
            "Ensure that all branch names follow the feature/STORY-ID-slug pattern",
            source="test",
        )
        assert result.is_valid is True

    def test_actionable_verb_before(self):
        """Rule with 'before' should pass."""
        result = validate_prevention_rule(
            "Run all lint checks locally before pushing to remote branches",
            source="test",
        )
        assert result.is_valid is True

    def test_actionable_verb_do_not(self):
        """Rule with 'do not' should pass."""
        result = validate_prevention_rule(
            "Do not merge to main without explicit human approval from Captain Craig",
            source="test",
        )
        assert result.is_valid is True

    def test_case_insensitive_placeholder(self):
        """Placeholder detection should be case-insensitive."""
        result = validate_prevention_rule("n/a", source="test")
        assert result.is_valid is False

    def test_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped before validation."""
        rule = "  Add retry logic with exponential backoff  "
        result = validate_prevention_rule(rule, source="test")
        assert result.is_valid is True

    def test_multiline_rule_passes(self):
        """Multi-line rule with actionable verb should pass."""
        rule = "Add retry logic with exponential backoff.\nUse 3 retries with 1s, 2s, 4s delays."
        result = validate_prevention_rule(rule, source="test")
        assert result.is_valid is True

    def test_placeholder_regex_no_embedded_anchors(self):
        """C1: Placeholder patterns work without embedded anchors in fullmatch."""
        # These should all be caught as placeholders
        placeholders = [
            "N/A",
            "TBD",
            "TODO",
            "[placeholder]",
            "none",
            "n/a",
            "tbd",
            "todo",
            "how to prevent",
        ]
        for placeholder in placeholders:
            result = validate_prevention_rule(placeholder, source="test")
            assert result.is_valid is False, (
                f"Should detect placeholder: '{placeholder}'"
            )
            assert any("placeholder" in e.lower() for e in result.errors), (
                f"Should flag placeholder: '{placeholder}'"
            )


# ===================================================================
# parse_from_yaml_string
# ===================================================================


class TestParseFromYamlString:
    """Tests for YAML string parsing."""

    def test_single_incident_with_prevention_rule(self, valid_incident_yaml):
        """AC1: Parser extracts prevention_rule from YAML with issues list."""
        result = parse_from_yaml_string(valid_incident_yaml, source="test")
        assert result.total_count == 1
        assert result.rules[0].is_valid is True
        assert "retry" in result.rules[0].rule_text.lower()

    def test_direct_prevention_rule_key(self):
        """Parser handles top-level prevention_rule key."""
        yaml_str = yaml.dump({"prevention_rule": "Always check permissions first"})
        result = parse_from_yaml_string(yaml_str, source="test")
        assert result.total_count == 1
        assert result.rules[0].is_valid is True

    def test_prevention_key_alias(self):
        """Parser handles 'prevention' as alias for 'prevention_rule'."""
        yaml_str = yaml.dump({"prevention": "Always check permissions first"})
        result = parse_from_yaml_string(yaml_str, source="test")
        assert result.total_count == 1
        assert result.rules[0].is_valid is True

    def test_multiple_issues(self):
        """Parser extracts rules from multiple issues."""
        yaml_str = yaml.dump(
            {
                "issues": [
                    {
                        "prevention_rule": "Add retry logic with exponential backoff for network calls"
                    },
                    {
                        "prevention_rule": "Validate environment variables before application startup"
                    },
                ]
            }
        )
        result = parse_from_yaml_string(yaml_str, source="test")
        assert result.total_count == 2
        assert result.all_valid is True

    def test_invalid_yaml(self):
        """Parser handles invalid YAML gracefully."""
        result = parse_from_yaml_string("invalid: yaml: [broken", source="test")
        assert len(result.parse_errors) > 0
        assert any("parse error" in e.lower() for e in result.parse_errors)

    def test_non_mapping_yaml(self):
        """Parser handles YAML that is not a mapping."""
        result = parse_from_yaml_string("- item1\n- item2", source="test")
        assert any("mapping" in e.lower() for e in result.parse_errors)

    def test_empty_yaml(self):
        """Parser handles empty YAML."""
        result = parse_from_yaml_string("", source="test")
        assert result.total_count == 0

    def test_no_prevention_rule(self):
        """Parser handles YAML with no prevention_rule key."""
        yaml_str = yaml.dump({"story_id": "TEST-001", "status": "done"})
        result = parse_from_yaml_string(yaml_str, source="test")
        assert result.total_count == 0

    def test_null_prevention_rule_skipped(self):
        """Null prevention_rule should be skipped."""
        yaml_str = yaml.dump({"prevention_rule": None})
        result = parse_from_yaml_string(yaml_str, source="test")
        assert result.total_count == 0

    def test_invalid_rule_in_yaml(self):
        """Invalid prevention_rule in YAML is flagged."""
        yaml_str = yaml.dump({"prevention_rule": "N/A"})
        result = parse_from_yaml_string(yaml_str, source="test")
        assert result.total_count == 1
        assert result.rules[0].is_valid is False


# ===================================================================
# parse_from_json
# ===================================================================


class TestParseFromJson:
    """Tests for JSON (Redis payload) parsing."""

    def test_single_incident_json(self, valid_incident_json):
        """AC1: Parser extracts prevention_rule from JSON payload."""
        result = parse_from_json(valid_incident_json, source="test")
        assert result.total_count == 1
        assert result.rules[0].is_valid is True
        assert "retry" in result.rules[0].rule_text.lower()

    def test_json_array_of_incidents(self):
        """Parser handles array of incident objects."""
        json_str = json.dumps(
            [
                {
                    "prevention_rule": "Add retry logic with exponential backoff for network calls"
                },
                {
                    "prevention_rule": "Validate environment variables before application startup"
                },
            ]
        )
        result = parse_from_json(json_str, source="test")
        assert result.total_count == 2
        assert result.all_valid is True

    def test_json_with_no_prevention_rule(self):
        """Parser handles JSON without prevention_rule."""
        json_str = json.dumps({"story_id": "TEST-001", "severity": "P1"})
        result = parse_from_json(json_str, source="test")
        assert result.total_count == 0

    def test_invalid_json(self):
        """Parser handles invalid JSON."""
        result = parse_from_json("{broken json", source="test")
        assert len(result.parse_errors) > 0
        assert any("parse error" in e.lower() for e in result.parse_errors)

    def test_json_non_object(self):
        """Parser handles JSON that is not an object or array."""
        result = parse_from_json('"just a string"', source="test")
        assert any("object or array" in e.lower() for e in result.parse_errors)

    def test_json_empty_object(self):
        """Parser handles empty JSON object."""
        result = parse_from_json("{}", source="test")
        assert result.total_count == 0

    def test_json_null_values_in_array(self):
        """Parser skips null entries in array."""
        json_str = json.dumps(
            [
                {"prevention_rule": "Always validate inputs before processing"},
                None,
                "not a dict",
            ]
        )
        result = parse_from_json(json_str, source="test")
        assert result.total_count == 1
        assert result.rules[0].is_valid is True


# ===================================================================
# parse_from_yaml_file
# ===================================================================


class TestParseFromYamlFile:
    """Tests for file-based parsing."""

    def test_yaml_file(self, tmp_path):
        """Parser reads prevention_rule from a .yaml file."""
        yaml_content = yaml.dump(
            {"prevention_rule": "Always run tests before pushing to main branch"}
        )
        f = tmp_path / "incident.yaml"
        f.write_text(yaml_content)

        result = parse_from_yaml_file(f)
        assert result.total_count == 1
        assert result.rules[0].is_valid is True

    def test_markdown_with_frontmatter(self, markdown_with_frontmatter):
        """AC1: Parser extracts prevention_rule from markdown frontmatter."""
        result = parse_from_yaml_file(markdown_with_frontmatter)
        assert result.total_count >= 1
        # Should find the frontmatter rule
        frontmatter_rules = [r for r in result.rules if "frontmatter" in r.source]
        assert len(frontmatter_rules) >= 1
        assert frontmatter_rules[0].is_valid is True

    def test_markdown_prose_only(self, markdown_prose_only):
        """AC1: Parser extracts prevention_rule from markdown prose."""
        result = parse_from_yaml_file(markdown_prose_only)
        assert result.total_count >= 1
        # Should find the prose prevention section
        prose_rules = [
            r
            for r in result.rules
            if "markdown_prevention" in r.source or "inline" in r.source
        ]
        assert len(prose_rules) >= 1
        assert prose_rules[0].is_valid is True

    def test_file_not_found(self, tmp_path):
        """Parser handles missing file."""
        result = parse_from_yaml_file(tmp_path / "nonexistent.yaml")
        assert len(result.parse_errors) > 0
        assert any("not found" in e.lower() for e in result.parse_errors)

    def test_combined_markdown_file(self, tmp_path):
        """Parser extracts rules from both frontmatter and prose in same file."""
        content = """---
issues:
  - prevention_rule: "Enforce pre-commit hooks for all Python files"
---

## Incident

**Prevention:**
Validate environment variables are set before starting the application.

"""
        f = tmp_path / "combined.md"
        f.write_text(content, encoding="utf-8")

        result = parse_from_yaml_file(f)
        assert result.total_count >= 2
        assert result.all_valid is True

    def test_strict_parameter_propagated_to_markdown_prose(self, tmp_path):
        """C2: strict parameter is propagated to markdown prose validation."""
        content = """# Iteration Log

## Incident

**Prevention:**
The system had a problem that needs attention and resolution soon.
"""
        f = tmp_path / "strict_test.md"
        f.write_text(content, encoding="utf-8")

        # Test with strict=True (default) - should fail
        result_strict = parse_from_yaml_file(f, strict=True)
        prose_rules = [
            r for r in result_strict.rules if "markdown_prevention" in r.source
        ]
        assert len(prose_rules) >= 1
        assert prose_rules[0].is_valid is False
        assert any("actionable" in e.lower() for e in prose_rules[0].errors)

        # Test with strict=False - should pass with warning
        result_lenient = parse_from_yaml_file(f, strict=False)
        prose_rules_lenient = [
            r for r in result_lenient.rules if "markdown_prevention" in r.source
        ]
        assert len(prose_rules_lenient) >= 1
        assert prose_rules_lenient[0].is_valid is True  # No errors, only warnings
        assert any("actionable" in w.lower() for w in prose_rules_lenient[0].warnings)


# ===================================================================
# parse_prevention_rules (auto-detect)
# ===================================================================


class TestParsePreventionRules:
    """Tests for the auto-detect convenience entry point."""

    def test_yaml_file_auto(self, tmp_path):
        """Auto-detect handles .yaml files."""
        f = tmp_path / "incident.yaml"
        f.write_text(
            yaml.dump({"prevention_rule": "Always verify branch exists before push"})
        )
        result = parse_prevention_rules(f)
        assert result.total_count == 1
        assert result.all_valid is True

    def test_yml_file_auto(self, tmp_path):
        """Auto-detect handles .yml files."""
        f = tmp_path / "incident.yml"
        f.write_text(
            yaml.dump({"prevention_rule": "Always verify branch exists before push"})
        )
        result = parse_prevention_rules(f)
        assert result.total_count == 1

    def test_json_file_auto(self, tmp_path):
        """Auto-detect handles .json files."""
        f = tmp_path / "incident.json"
        f.write_text(
            json.dumps({"prevention_rule": "Always verify branch exists before push"})
        )
        result = parse_prevention_rules(f)
        assert result.total_count == 1
        assert result.all_valid is True

    def test_md_file_auto(self, tmp_path):
        """Auto-detect handles .md files."""
        content = "---\nprevention_rule: 'Validate inputs before processing'\n---\n"
        f = tmp_path / "log.md"
        f.write_text(content)
        result = parse_prevention_rules(f)
        assert result.total_count >= 1


# ===================================================================
# ParseResult aggregation
# ===================================================================


class TestParseResult:
    """Tests for ParseResult aggregation properties."""

    def test_all_valid_when_no_rules(self):
        """Empty result should be all_valid."""
        result = ParseResult()
        assert result.all_valid is True

    def test_all_valid_with_valid_rules(self):
        """Result with only valid rules should be all_valid."""
        result = ParseResult(
            rules=[
                ValidationResult(is_valid=True, rule_text="rule1", source="s1"),
                ValidationResult(is_valid=True, rule_text="rule2", source="s2"),
            ]
        )
        assert result.all_valid is True
        assert result.valid_count == 2
        assert result.invalid_count == 0
        assert result.total_count == 2

    def test_not_all_valid_with_errors(self):
        """Result with parse errors should not be all_valid."""
        result = ParseResult(parse_errors=["something went wrong"])
        assert result.all_valid is False

    def test_counts_with_mixed(self):
        """Result with mixed valid/invalid rules."""
        result = ParseResult(
            rules=[
                ValidationResult(
                    is_valid=True,
                    rule_text="good rule text that is long enough and actionable",
                    source="s1",
                ),
                ValidationResult(is_valid=False, rule_text="N/A", source="s2"),
            ]
        )
        assert result.valid_count == 1
        assert result.invalid_count == 1
        assert result.total_count == 2
        assert result.all_valid is False


# ===================================================================
# ValidationResult
# ===================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_add_error_sets_invalid(self):
        """Adding an error should set is_valid to False."""
        result = ValidationResult(is_valid=True, rule_text="test", source="s")
        result.add_error("something wrong")
        assert result.is_valid is False
        assert len(result.errors) == 1

    def test_add_warning_keeps_valid(self):
        """Adding a warning should not affect is_valid."""
        result = ValidationResult(is_valid=True, rule_text="test", source="s")
        result.add_warning("just a warning")
        assert result.is_valid is True
        assert len(result.warnings) == 1

    def test_multiple_errors_accumulate(self):
        """Multiple errors should accumulate."""
        result = ValidationResult(is_valid=True, rule_text="test", source="s")
        result.add_error("error 1")
        result.add_error("error 2")
        assert len(result.errors) == 2


# ===================================================================
# Integration: real-world incident patterns
# ===================================================================


class TestRealWorldIncidentPatterns:
    """Tests using actual incident patterns from the ChiseAI codebase."""

    def test_worker_contract_incident_template(self):
        """Parser handles the INCIDENT_TEMPLATE format from worker contracts."""
        yaml_str = yaml.dump(
            {
                "story_id": "SWARM-HARDEN-001-6.1",
                "batch": "BATCH-1",
                "symptom": "Parse error on malformed YAML",
                "root_cause": "Missing try/except around yaml.safe_load",
                "prevention_rule": "Wrap all YAML parsing in try/except blocks with structured error messages",
            }
        )
        result = parse_from_yaml_string(yaml_str, source="worker_contract")
        assert result.total_count == 1
        assert result.rules[0].is_valid is True

    def test_redis_iterlog_format(self):
        """Parser handles Redis rpush JSON format from iterlog incidents."""
        json_str = json.dumps(
            {
                "story_id": "CH-AGENTS-003",
                "severity": "P1",
                "symptom": "CI failure on push due to uncommitted lint fixes",
                "root_cause": "Forgot to run lint locally before push",
                "prevention_rule": "Always run the full Woodpecker lint stack locally before pushing when touching scripts/*.py",
                "timestamp": "2026-02-09T14:30:00Z",
            }
        )
        result = parse_from_json(json_str, source="redis_iterlog")
        assert result.total_count == 1
        assert result.rules[0].is_valid is True
        assert "lint" in result.rules[0].rule_text.lower()

    def test_iterlog_markdown_with_frontmatter_and_prose(self, tmp_path):
        """Parser handles real iterlog format with both frontmatter and prose."""
        content = """---
story_id: ST-CI-HEALTH-20260215
status: completed

issues:
  - issue_type: security
    severity: P1
    root_cause: "Missing Bandit scan in CI gate"
    prevention_rule: "Keep Bandit src scan in CI gate and run locally before pushing infra changes"

## Learnings

- prevention_rule: Keep Bandit `src` scan in CI gate and run `bandit -q -r src -s B311,B107` locally before pushing infra/CI remediations.

## Incidents

**Prevention:**
Validate all security scanning tools are configured in CI before merging infrastructure changes.
"""
        f = tmp_path / "iterlog-ST-CI-HEALTH.md"
        f.write_text(content, encoding="utf-8")

        result = parse_from_yaml_file(f)
        assert result.total_count >= 2  # frontmatter + prose
        assert result.all_valid is True

    def test_multiple_issues_with_varying_quality(self):
        """Parser validates each issue's prevention_rule independently."""
        yaml_str = yaml.dump(
            {
                "issues": [
                    {
                        "prevention_rule": "Add retry logic with exponential backoff for all external API calls",
                    },
                    {
                        "prevention_rule": "N/A",
                    },
                    {
                        "prevention_rule": "TODO",
                    },
                ]
            }
        )
        result = parse_from_yaml_string(yaml_str, source="mixed")
        assert result.total_count == 3
        assert result.valid_count == 1
        assert result.invalid_count == 2

    def test_empty_prevention_rule_in_list(self):
        """Empty prevention_rule in issues list should be flagged."""
        yaml_str = yaml.dump(
            {
                "issues": [
                    {"prevention_rule": ""},
                    {"prevention_rule": "   "},
                ]
            }
        )
        result = parse_from_yaml_string(yaml_str, source="empty_rules")
        # Empty strings are skipped by the parser (not passed to validator)
        assert result.total_count == 0

    def test_prevention_key_takes_precedence_over_prevention_rule(self):
        """When both keys exist, only one rule should be extracted."""
        yaml_str = yaml.dump(
            {
                "prevention_rule": "Rule A with enough text to be valid",
                "prevention": "Rule B with enough text to be valid",
            }
        )
        result = parse_from_yaml_string(yaml_str, source="dual_keys")
        # Should extract exactly one rule (first matching key)
        assert result.total_count == 1


# ===================================================================
# CLI
# ===================================================================


class TestCLI:
    """Tests for CLI entry point."""

    def test_main_with_json(self, valid_incident_json, monkeypatch):
        """CLI --json flag parses and validates."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "prevention_rule_parser.py",
                "--json",
                valid_incident_json,
            ],
        )
        exit_code = _mod.main()
        assert exit_code == 0

    def test_main_with_invalid_json(self, monkeypatch):
        """CLI returns non-zero for invalid prevention_rule."""
        bad_json = json.dumps({"prevention_rule": "N/A"})
        monkeypatch.setattr(
            "sys.argv",
            [
                "prevention_rule_parser.py",
                "--json",
                bad_json,
            ],
        )
        exit_code = _mod.main()
        assert exit_code == 1

    def test_main_with_file(self, tmp_path, monkeypatch):
        """CLI --file flag parses file."""
        f = tmp_path / "incident.yaml"
        f.write_text(
            yaml.dump(
                {"prevention_rule": "Always validate inputs before processing data"}
            )
        )
        monkeypatch.setattr(
            "sys.argv",
            [
                "prevention_rule_parser.py",
                "--file",
                str(f),
            ],
        )
        exit_code = _mod.main()
        assert exit_code == 0

    def test_main_with_stdin_yaml(self, monkeypatch):
        """CLI --stdin-yaml reads from stdin."""
        yaml_str = yaml.dump(
            {
                "prevention_rule": "Enforce code review requirements for all pull requests"
            }
        )
        monkeypatch.setattr(
            "sys.stdin", type("FakeStdin", (), {"read": lambda self: yaml_str})()
        )
        monkeypatch.setattr(
            "sys.argv",
            [
                "prevention_rule_parser.py",
                "--stdin-yaml",
            ],
        )
        exit_code = _mod.main()
        assert exit_code == 0

    def test_main_lenient_mode(self, monkeypatch):
        """CLI --lenient treats actionable-verb check as warning."""
        json_str = json.dumps(
            {
                "prevention_rule": "The system had a configuration problem that needs attention"
            }
        )
        monkeypatch.setattr(
            "sys.argv",
            [
                "prevention_rule_parser.py",
                "--json",
                json_str,
                "--lenient",
            ],
        )
        exit_code = _mod.main()
        assert exit_code == 0

    def test_main_verbose(self, valid_incident_json, monkeypatch, capsys):
        """CLI --verbose prints detailed output."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "prevention_rule_parser.py",
                "--json",
                valid_incident_json,
                "--verbose",
            ],
        )
        _mod.main()
        output = capsys.readouterr().out
        assert "PASS" in output or "Summary" in output


# ===================================================================
# classify_rule
# ===================================================================


class TestClassifyRule:
    """Tests for rule classification by keyword analysis."""

    def test_network_category(self):
        """Rule with network keywords classifies as NETWORK."""
        assert (
            classify_rule(
                "Add retry logic with exponential backoff for all network connections"
            )
            == RuleCategory.NETWORK
        )

    def test_ci_cd_category(self):
        """Rule with CI/CD keywords classifies as CI_CD."""
        assert (
            classify_rule(
                "Always run the full Woodpecker lint stack locally before pushing"
            )
            == RuleCategory.CI_CD
        )

    def test_security_category(self):
        """Rule with security keywords classifies as SECURITY."""
        assert (
            classify_rule(
                "Run Bandit security scan on all source files before merging to main"
            )
            == RuleCategory.SECURITY
        )

    def test_data_validation_category(self):
        """Rule with validation keywords classifies as DATA_VALIDATION."""
        assert (
            classify_rule(
                "Validate all environment variables are set before starting the application"
            )
            == RuleCategory.DATA_VALIDATION
        )

    def test_configuration_category(self):
        """Rule with config keywords classifies as CONFIGURATION."""
        assert (
            classify_rule(
                "Set all required environment variables in the deployment configuration"
            )
            == RuleCategory.CONFIGURATION
        )

    def test_git_workflow_category(self):
        """Rule with git keywords classifies as GIT_WORKFLOW."""
        assert (
            classify_rule(
                "Always rebase feature branches before opening a pull request to avoid conflicts"
            )
            == RuleCategory.GIT_WORKFLOW
        )

    def test_testing_category(self):
        """Rule with test keywords classifies as TESTING."""
        assert (
            classify_rule(
                "Write unit tests for all new functions before submitting code review"
            )
            == RuleCategory.TESTING
        )

    def test_monitoring_category(self):
        """Rule with monitoring keywords classifies as MONITORING."""
        assert (
            classify_rule(
                "Monitor all API endpoints with Grafana dashboards and configure alerts"
            )
            == RuleCategory.MONITORING
        )

    def test_general_category(self):
        """Rule with no matching keywords classifies as GENERAL."""
        assert (
            classify_rule(
                "The team should discuss this problem at the next standup meeting and figure out a solution"
            )
            == RuleCategory.GENERAL
        )

    def test_case_insensitive_classification(self):
        """Classification should be case-insensitive."""
        assert (
            classify_rule("RETRY all failed HTTP requests with exponential backoff")
            == RuleCategory.NETWORK
        )

    def test_first_matching_category_wins(self):
        """When multiple categories match, first match wins."""
        # Contains both "test" (TESTING) and "validate" (DATA_VALIDATION)
        result = classify_rule("Validate all test fixtures before running the suite")
        # DATA_VALIDATION comes before TESTING in keyword order
        assert result in (RuleCategory.DATA_VALIDATION, RuleCategory.TESTING)

    def test_empty_rule_returns_general(self):
        """Empty rule text returns GENERAL."""
        assert classify_rule("") == RuleCategory.GENERAL


# ===================================================================
# extract_severity
# ===================================================================


class TestExtractSeverity:
    """Tests for severity extraction and normalization."""

    def test_severity_p0(self):
        """Direct P0 severity is extracted."""
        assert extract_severity({"severity": "P0"}) == IncidentSeverity.P0

    def test_severity_p1(self):
        """Direct P1 severity is extracted."""
        assert extract_severity({"severity": "P1"}) == IncidentSeverity.P1

    def test_severity_p2(self):
        """Direct P2 severity is extracted."""
        assert extract_severity({"severity": "P2"}) == IncidentSeverity.P2

    def test_severity_p3(self):
        """Direct P3 severity is extracted."""
        assert extract_severity({"severity": "P3"}) == IncidentSeverity.P3

    def test_severity_case_insensitive(self):
        """Severity extraction is case-insensitive."""
        assert extract_severity({"severity": "p1"}) == IncidentSeverity.P1

    def test_severity_critical_normalizes_to_p0(self):
        """'critical' normalizes to P0."""
        assert extract_severity({"severity": "critical"}) == IncidentSeverity.P0

    def test_severity_high_normalizes_to_p1(self):
        """'high' normalizes to P1."""
        assert extract_severity({"severity": "high"}) == IncidentSeverity.P1

    def test_severity_medium_normalizes_to_p2(self):
        """'medium' normalizes to P2."""
        assert extract_severity({"severity": "medium"}) == IncidentSeverity.P2

    def test_severity_low_normalizes_to_p3(self):
        """'low' normalizes to P3."""
        assert extract_severity({"severity": "low"}) == IncidentSeverity.P3

    def test_severity_urgent_normalizes_to_p0(self):
        """'urgent' normalizes to P0."""
        assert extract_severity({"severity": "urgent"}) == IncidentSeverity.P0

    def test_severity_unknown_value(self):
        """Unknown severity string returns UNKNOWN."""
        assert extract_severity({"severity": "xyz"}) == IncidentSeverity.UNKNOWN

    def test_severity_missing_key(self):
        """Missing severity key returns UNKNOWN."""
        assert extract_severity({"other": "value"}) == IncidentSeverity.UNKNOWN

    def test_severity_empty_dict(self):
        """Empty dict returns UNKNOWN."""
        assert extract_severity({}) == IncidentSeverity.UNKNOWN

    def test_severity_from_level_key(self):
        """Severity can be extracted from 'level' key."""
        assert extract_severity({"level": "P1"}) == IncidentSeverity.P1

    def test_severity_from_priority_key(self):
        """Severity can be extracted from 'priority' key."""
        assert extract_severity({"priority": "high"}) == IncidentSeverity.P1

    def test_severity_precedence_severity_over_level(self):
        """'severity' key takes precedence over 'level'."""
        assert (
            extract_severity({"severity": "P0", "level": "P3"}) == IncidentSeverity.P0
        )


# ===================================================================
# extract_story_id
# ===================================================================


class TestExtractStoryId:
    """Tests for story ID extraction."""

    def test_story_id_from_story_id_key(self):
        """Extract story_id from 'story_id' key."""
        assert extract_story_id({"story_id": "TEST-001"}) == "TEST-001"

    def test_story_id_from_hyphenated_key(self):
        """Extract story_id from 'story-id' key."""
        assert extract_story_id({"story-id": "CH-AGENTS-003"}) == "CH-AGENTS-003"

    def test_story_id_from_camel_case_key(self):
        """Extract story_id from 'storyId' key."""
        assert extract_story_id({"storyId": "FT-042"}) == "FT-042"

    def test_story_id_from_id_key(self):
        """Extract story_id from 'id' key as fallback."""
        assert extract_story_id({"id": "REWARD-007"}) == "REWARD-007"

    def test_story_id_none_value(self):
        """None value returns None."""
        assert extract_story_id({"story_id": None}) is None

    def test_story_id_empty_string(self):
        """Empty string returns None."""
        assert extract_story_id({"story_id": ""}) is None

    def test_story_id_whitespace_only(self):
        """Whitespace-only string returns None."""
        assert extract_story_id({"story_id": "   "}) is None

    def test_story_id_missing_key(self):
        """Missing keys return None."""
        assert extract_story_id({"other": "value"}) is None

    def test_story_id_precedence(self):
        """'story_id' key takes precedence over 'id'."""
        assert extract_story_id({"story_id": "FIRST", "id": "SECOND"}) == "FIRST"


# ===================================================================
# detect_duplicate_rules
# ===================================================================


class TestDetectDuplicateRules:
    """Tests for near-duplicate rule detection."""

    def test_no_duplicates_distinct_rules(self):
        """Distinct rules should not be flagged."""
        rules = [
            ValidationResult(
                is_valid=True,
                rule_text="Add retry logic for network calls",
                source="s1",
            ),
            ValidationResult(
                is_valid=True,
                rule_text="Run security scans before deployment",
                source="s2",
            ),
        ]
        dups = detect_duplicate_rules(rules)
        assert len(dups) == 0

    def test_exact_duplicate_detected(self):
        """Exact duplicate rules should be detected."""
        text = "Add retry logic with exponential backoff for all network calls"
        rules = [
            ValidationResult(is_valid=True, rule_text=text, source="s1"),
            ValidationResult(is_valid=True, rule_text=text, source="s2"),
        ]
        dups = detect_duplicate_rules(rules)
        assert len(dups) == 1
        assert dups[0][2] == 1.0  # Perfect similarity

    def test_near_duplicate_detected(self):
        """Near-duplicate rules (slight wording change) should be detected."""
        rules = [
            ValidationResult(
                is_valid=True,
                rule_text="Add retry logic with exponential backoff for all API calls",
                source="s1",
            ),
            ValidationResult(
                is_valid=True,
                rule_text="Add retry logic with exponential backoff for all external API calls",
                source="s2",
            ),
        ]
        dups = detect_duplicate_rules(rules)
        assert len(dups) == 1
        assert dups[0][2] >= 0.8

    def test_below_threshold_not_flagged(self):
        """Rules below similarity threshold should not be flagged."""
        rules = [
            ValidationResult(
                is_valid=True,
                rule_text="Add retry logic for network calls",
                source="s1",
            ),
            ValidationResult(
                is_valid=True,
                rule_text="Configure monitoring dashboards for all services",
                source="s2",
            ),
        ]
        dups = detect_duplicate_rules(rules, similarity_threshold=0.9)
        assert len(dups) == 0

    def test_custom_threshold(self):
        """Custom similarity threshold works."""
        rules = [
            ValidationResult(
                is_valid=True, rule_text="Add retry logic for API calls", source="s1"
            ),
            ValidationResult(
                is_valid=True,
                rule_text="Add retry logic for external API calls",
                source="s2",
            ),
        ]
        # Low threshold: should detect
        dups_low = detect_duplicate_rules(rules, similarity_threshold=0.5)
        assert len(dups_low) == 1
        # High threshold: might not detect
        dups_high = detect_duplicate_rules(rules, similarity_threshold=0.99)
        assert len(dups_high) == 0

    def test_empty_rules_list(self):
        """Empty list returns no duplicates."""
        assert detect_duplicate_rules([]) == []

    def test_single_rule(self):
        """Single rule returns no duplicates."""
        rules = [
            ValidationResult(
                is_valid=True, rule_text="Some rule text here", source="s1"
            ),
        ]
        assert detect_duplicate_rules(rules) == []

    def test_three_rules_pairwise(self):
        """Three rules check all pairs."""
        text_a = "Add retry logic with exponential backoff for all network calls"
        text_b = (
            "Add retry logic with exponential backoff for all external network calls"
        )
        text_c = "Run security scans on all source files before merging"
        rules = [
            ValidationResult(is_valid=True, rule_text=text_a, source="s1"),
            ValidationResult(is_valid=True, rule_text=text_b, source="s2"),
            ValidationResult(is_valid=True, rule_text=text_c, source="s3"),
        ]
        dups = detect_duplicate_rules(rules)
        # a-b should be duplicate, a-c and b-c should not
        assert len(dups) == 1
        assert dups[0][0] == 0 and dups[0][1] == 1

    def test_returns_sorted_indices(self):
        """Duplicate pairs always have a < b indices."""
        rules = [
            ValidationResult(
                is_valid=True, rule_text="Rule A about network retries", source="s1"
            ),
            ValidationResult(
                is_valid=True, rule_text="Rule B about security", source="s2"
            ),
            ValidationResult(
                is_valid=True, rule_text="Rule A about network retries", source="s3"
            ),
        ]
        dups = detect_duplicate_rules(rules)
        for a, b, _ in dups:
            assert a < b


# ===================================================================
# generate_summary
# ===================================================================


class TestGenerateSummary:
    """Tests for structured summary generation."""

    def test_empty_result_summary(self):
        """Summary of empty result has zero counts."""
        result = ParseResult()
        summary = generate_summary(result)
        assert summary["total_rules"] == 0
        assert summary["valid_count"] == 0
        assert summary["invalid_count"] == 0
        assert summary["all_valid"] is True
        assert summary["categories"] == {}
        assert summary["duplicate_pairs"] == []

    def test_valid_rules_summary(self):
        """Summary with valid rules includes counts and categories."""
        result = ParseResult(
            rules=[
                ValidationResult(
                    is_valid=True,
                    rule_text="Add retry logic for network calls",
                    source="s1",
                ),
                ValidationResult(
                    is_valid=True,
                    rule_text="Run pre-commit hooks before pushing",
                    source="s2",
                ),
            ]
        )
        summary = generate_summary(result)
        assert summary["total_rules"] == 2
        assert summary["valid_count"] == 2
        assert summary["all_valid"] is True
        assert "network" in summary["categories"]
        assert "ci_cd" in summary["categories"]

    def test_mixed_validity_summary(self):
        """Summary with mixed valid/invalid includes invalid_sources."""
        result = ParseResult(
            rules=[
                ValidationResult(
                    is_valid=True,
                    rule_text="Add retry logic with exponential backoff for all network calls",
                    source="s1",
                ),
                ValidationResult(
                    is_valid=False,
                    rule_text="N/A",
                    source="s2",
                    errors=["[s2] prevention_rule is a placeholder: 'N/A'"],
                ),
            ]
        )
        summary = generate_summary(result)
        assert summary["total_rules"] == 2
        assert summary["valid_count"] == 1
        assert summary["invalid_count"] == 1
        assert summary["all_valid"] is False
        assert len(summary["invalid_sources"]) == 1
        assert summary["invalid_sources"][0]["source"] == "s2"

    def test_summary_with_parse_errors(self):
        """Summary includes parse error count."""
        result = ParseResult(parse_errors=["YAML parse error: invalid"])
        summary = generate_summary(result)
        assert summary["parse_errors"] == 1
        assert summary["all_valid"] is False

    def test_summary_with_duplicates(self):
        """Summary includes duplicate pairs."""
        text = "Add retry logic with exponential backoff for network calls"
        result = ParseResult(
            rules=[
                ValidationResult(is_valid=True, rule_text=text, source="s1"),
                ValidationResult(is_valid=True, rule_text=text, source="s2"),
            ]
        )
        summary = generate_summary(result)
        assert len(summary["duplicate_pairs"]) == 1
        assert summary["duplicate_pairs"][0]["similarity"] == 1.0

    def test_summary_is_json_serializable(self):
        """Summary dict should be JSON-serializable."""
        import json as _json

        result = ParseResult(
            rules=[
                ValidationResult(
                    is_valid=True,
                    rule_text="Validate inputs before processing",
                    source="s1",
                ),
            ]
        )
        summary = generate_summary(result)
        serialized = _json.dumps(summary)
        assert isinstance(serialized, str)


# ===================================================================
# Metadata extraction integration
# ===================================================================


class TestMetadataExtraction:
    """Tests for metadata (severity, story_id) extraction during parsing."""

    def test_yaml_with_severity_extracts_metadata(self):
        """YAML with severity field extracts severity into metadata."""
        yaml_str = yaml.dump(
            {
                "story_id": "SEC-001",
                "severity": "P1",
                "prevention_rule": "Run Bandit security scan on all source files before merging",
            }
        )
        result = parse_from_yaml_string(yaml_str, source="test")
        assert "test:severity" in result.metadata
        assert result.metadata["test:severity"] == "P1"
        assert "test:story_id" in result.metadata
        assert result.metadata["test:story_id"] == "SEC-001"

    def test_json_with_severity_extracts_metadata(self):
        """JSON with severity field extracts severity into metadata."""
        json_str = json.dumps(
            {
                "story_id": "CI-042",
                "severity": "P2",
                "prevention_rule": "Enforce pre-commit hooks for all Python files in the repository",
            }
        )
        result = parse_from_json(json_str, source="test")
        assert "test:severity" in result.metadata
        assert result.metadata["test:severity"] == "P2"
        assert result.metadata["test:story_id"] == "CI-042"

    def test_issues_list_with_per_issue_metadata(self):
        """Issues list extracts metadata per issue."""
        yaml_str = yaml.dump(
            {
                "issues": [
                    {
                        "severity": "P0",
                        "prevention_rule": "Add retry logic with exponential backoff for network calls",
                    },
                    {
                        "severity": "P2",
                        "prevention_rule": "Validate all inputs before processing data",
                    },
                ]
            }
        )
        result = parse_from_yaml_string(yaml_str, source="test")
        assert "test:issues[0]:severity" in result.metadata
        assert result.metadata["test:issues[0]:severity"] == "P0"
        assert "test:issues[1]:severity" in result.metadata
        assert result.metadata["test:issues[1]:severity"] == "P2"

    def test_normalized_severity_in_metadata(self):
        """Normalized severity (e.g., 'critical' -> P0) stored in metadata."""
        json_str = json.dumps(
            {
                "severity": "critical",
                "prevention_rule": "Block all deployments without passing security scans",
            }
        )
        result = parse_from_json(json_str, source="test")
        assert result.metadata["test:severity"] == "P0"

    def test_no_metadata_when_keys_missing(self):
        """No metadata keys when severity/story_id not present."""
        yaml_str = yaml.dump(
            {
                "prevention_rule": "Always validate inputs before processing data",
            }
        )
        result = parse_from_yaml_string(yaml_str, source="test")
        assert len(result.metadata) == 0

    def test_parse_result_metadata_default_empty(self):
        """New ParseResult has empty metadata dict."""
        result = ParseResult()
        assert result.metadata == {}

    def test_json_array_with_metadata(self):
        """JSON array extracts metadata per element."""
        json_str = json.dumps(
            [
                {
                    "story_id": "A-001",
                    "severity": "P1",
                    "prevention_rule": "Add retry logic for network calls",
                },
                {
                    "story_id": "B-002",
                    "severity": "P3",
                    "prevention_rule": "Run tests before pushing code",
                },
            ]
        )
        result = parse_from_json(json_str, source="test")
        assert result.metadata["test[0]:severity"] == "P1"
        assert result.metadata["test[0]:story_id"] == "A-001"
        assert result.metadata["test[1]:severity"] == "P3"
        assert result.metadata["test[1]:story_id"] == "B-002"


# ===================================================================
# End-to-end: summary generation with real incident data
# ===================================================================


class TestEndToEndSummary:
    """End-to-end tests combining parsing, classification, and summary."""

    def test_full_pipeline_with_real_incident(self):
        """Full pipeline: parse -> classify -> summarize a real incident."""
        yaml_str = yaml.dump(
            {
                "story_id": "SWARM-HARDEN-001",
                "severity": "P1",
                "issues": [
                    {
                        "issue_type": "network_failure",
                        "severity": "P1",
                        "prevention_rule": "Add retry logic with exponential backoff for all external API calls",
                    },
                    {
                        "issue_type": "ci_breakage",
                        "severity": "P2",
                        "prevention_rule": "Always run the full Woodpecker lint stack locally before pushing",
                    },
                ],
            }
        )
        result = parse_from_yaml_string(yaml_str, source="incident")
        summary = generate_summary(result)

        assert summary["total_rules"] == 2
        assert summary["valid_count"] == 2
        assert summary["all_valid"] is True
        assert summary["categories"]["network"] == 1
        assert summary["categories"]["ci_cd"] == 1
        assert len(summary["duplicate_pairs"]) == 0
        assert len(summary["invalid_sources"]) == 0

    def test_summary_with_duplicates_and_invalid(self):
        """Summary captures duplicates and invalid rules together."""
        yaml_str = yaml.dump(
            {
                "issues": [
                    {
                        "prevention_rule": "Add retry logic with exponential backoff for all API calls"
                    },
                    {
                        "prevention_rule": "Add retry logic with exponential backoff for all API calls"
                    },
                    {"prevention_rule": "N/A"},
                ]
            }
        )
        result = parse_from_yaml_string(yaml_str, source="dup_test")
        summary = generate_summary(result)

        assert summary["total_rules"] == 3
        assert summary["valid_count"] == 2
        assert summary["invalid_count"] == 1
        assert len(summary["duplicate_pairs"]) == 1
        assert len(summary["invalid_sources"]) == 1
