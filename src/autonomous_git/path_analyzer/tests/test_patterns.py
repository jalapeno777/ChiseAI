"""Tests for patterns module."""

import tempfile
from pathlib import Path

import pytest

from autonomous_git.path_analyzer.patterns import (
    PathPatternMatcher,
    Pattern,
    PatternType,
    SemanticRule,
)


class TestPattern:
    """Test Pattern dataclass."""

    def test_pattern_compilation(self):
        """Test that patterns compile correctly."""
        pattern = Pattern(pattern=r"^docs/.*\.md$", description="Markdown docs")
        assert pattern.compiled is not None
        assert pattern.matches("docs/readme.md") is True
        assert pattern.matches("docs/api.md") is True
        assert pattern.matches("src/main.py") is False

    def test_pattern_anchoring(self):
        """Test that patterns are properly anchored."""
        pattern = Pattern(pattern=r".*_test\.py$", description="Test files")
        # Pattern should match files ending with _test.py
        assert pattern.matches("foo_test.py") is True
        assert pattern.matches("bar_test.py") is True
        # Should not match files starting with test_
        assert pattern.matches("test_foo.py") is False
        # Should not match non-py files
        assert pattern.matches("test_foo.pyc") is False


class TestSemanticRule:
    """Test SemanticRule dataclass."""

    def test_rule_creation(self):
        """Test creating a semantic rule."""
        rule = SemanticRule(
            name="test_rule", pattern=r"def\s+\w+\(", threshold=3, action="flag"
        )
        assert rule.name == "test_rule"
        assert rule.threshold == 3
        assert rule.action == "flag"

    def test_content_matching(self):
        """Test matching content."""
        rule = SemanticRule(
            name="import_check",
            pattern=r"import\s+os",
        )
        assert rule.matches_content("import os") is True
        assert rule.matches_content("import sys") is False


class TestPathPatternMatcher:
    """Test PathPatternMatcher class."""

    def test_default_initialization(self):
        """Test initialization without config."""
        matcher = PathPatternMatcher()
        assert len(matcher.safe_patterns) > 0
        assert len(matcher.complex_patterns) > 0

    def test_safe_pattern_matching(self):
        """Test matching safe patterns."""
        matcher = PathPatternMatcher()

        # Safe patterns
        assert matcher.is_safe("docs/readme.md") is True
        assert matcher.is_safe("tests/test_foo.py") is True
        assert matcher.is_safe("LICENSE") is True
        assert matcher.is_safe(".gitignore") is True

    def test_complex_pattern_matching(self):
        """Test matching complex patterns."""
        matcher = PathPatternMatcher()

        # Complex patterns
        assert matcher.is_complex(".woodpecker.yml") is True
        assert matcher.is_complex("infrastructure/terraform/main.tf") is True
        assert matcher.is_complex("src/package/__init__.py") is True
        assert matcher.is_complex("AGENTS.md") is True

    def test_classify_path_safe(self):
        """Test classifying safe paths."""
        matcher = PathPatternMatcher()

        pattern_type, pattern = matcher.classify_path("docs/readme.md")
        assert pattern_type == PatternType.SAFE
        assert pattern is not None

    def test_classify_path_complex(self):
        """Test classifying complex paths."""
        matcher = PathPatternMatcher()

        pattern_type, pattern = matcher.classify_path(".woodpecker.yml")
        assert pattern_type == PatternType.COMPLEX
        assert pattern is not None

    def test_classify_path_no_match(self):
        """Test classifying paths with no match."""
        matcher = PathPatternMatcher()

        pattern_type, pattern = matcher.classify_path("unknown/file.xyz")
        assert pattern_type is None
        assert pattern is None

    def test_complex_takes_priority(self):
        """Test that complex patterns take priority."""
        matcher = PathPatternMatcher()

        # AGENTS.md matches both a complex pattern and could match doc patterns
        pattern_type, pattern = matcher.classify_path("AGENTS.md")
        assert pattern_type == PatternType.COMPLEX

    def test_custom_config_loading(self):
        """Test loading custom config file."""
        config_content = """
path_patterns:
  safe:
    - pattern: "^custom/.*$"
      description: "Custom safe files"
  complex:
    - pattern: "^danger/.*$"
      description: "Dangerous files"
  semantic_rules: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            matcher = PathPatternMatcher(config_path=config_path)

            assert matcher.is_safe("custom/file.txt") is True
            assert matcher.is_complex("danger/file.txt") is True
            assert (
                matcher.is_safe("docs/readme.md") is False
            )  # Default patterns not loaded
        finally:
            Path(config_path).unlink()

    def test_config_validation_error(self):
        """Test config validation catches missing sections."""
        config_content = """
path_patterns:
  safe:
    - pattern: "^test$"
      description: "Test"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            with pytest.raises(ValueError, match="complex"):
                PathPatternMatcher(config_path=config_path)
        finally:
            Path(config_path).unlink()

    def test_get_semantic_rules(self):
        """Test getting semantic rules."""
        matcher = PathPatternMatcher()
        rules = matcher.get_semantic_rules()

        assert len(rules) >= 0
        # Verify we get a copy
        rules.append(None)
        assert len(matcher.semantic_rules) < len(rules)

    def test_reload(self):
        """Test config reload."""
        matcher = PathPatternMatcher()
        original_count = len(matcher.safe_patterns)

        # Reload should reload same config
        matcher.reload()
        assert len(matcher.safe_patterns) == original_count

    def test_pattern_descriptions(self):
        """Test that patterns have descriptions."""
        matcher = PathPatternMatcher()

        for pattern in matcher.safe_patterns:
            assert pattern.description is not None
            assert len(pattern.description) > 0

        for pattern in matcher.complex_patterns:
            assert pattern.description is not None
            assert len(pattern.description) > 0
