"""Path pattern configuration and matching."""

import re
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class PatternType(Enum):
    """Types of path patterns."""

    SAFE = "safe"
    COMPLEX = "complex"


@dataclass
class Pattern:
    """A single path pattern definition."""

    pattern: str
    description: str
    compiled: re.Pattern = None

    def __post_init__(self):
        if self.compiled is None:
            self.compiled = re.compile(self.pattern)

    def matches(self, path: str) -> bool:
        """Check if a path matches this pattern."""
        return bool(self.compiled.match(path))


@dataclass
class SemanticRule:
    """Semantic analysis rule configuration."""

    name: str
    pattern: str
    threshold: Optional[int] = None
    action: str = "flag_for_review"
    compiled: re.Pattern = None

    def __post_init__(self):
        if self.compiled is None:
            self.compiled = re.compile(self.pattern, re.MULTILINE)

    def matches_content(self, content: str) -> bool:
        """Check if content matches this rule."""
        return bool(self.compiled.search(content))


class PathPatternMatcher:
    """Matches file paths against configured patterns."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with optional custom config path."""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"

        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self.safe_patterns: List[Pattern] = []
        self.complex_patterns: List[Pattern] = []
        self.semantic_rules: List[SemanticRule] = []
        self._load_config()

    def _load_config(self) -> None:
        """Load and validate pattern configuration."""
        if not self.config_path.exists():
            self._load_defaults()
            return

        with open(self.config_path, "r") as f:
            self._config = yaml.safe_load(f)

        self._validate_config()
        self._compile_patterns()

    def _load_defaults(self) -> None:
        """Load default patterns when config file is missing."""
        self._config = {
            "path_patterns": {
                "safe": [
                    {"pattern": r"^docs/.*\.md$", "description": "Documentation files"},
                    {
                        "pattern": r"^\.opencode/skills/.*\.md$",
                        "description": "Skill documentation",
                    },
                    {"pattern": r"^tests/.*\.py$", "description": "Test files"},
                    {
                        "pattern": r"^tests/.*\.yaml$",
                        "description": "Test configuration",
                    },
                    {"pattern": r"^.*\.md$", "description": "Markdown files"},
                    {"pattern": r"^LICENSE.*$", "description": "License files"},
                    {"pattern": r"^\.gitignore$", "description": "Git ignore file"},
                ],
                "complex": [
                    {
                        "pattern": r"^\.woodpecker\.yml$",
                        "description": "CI/CD configuration",
                    },
                    {
                        "pattern": r"^infrastructure/terraform/.*",
                        "description": "Infrastructure code",
                    },
                    {
                        "pattern": r"^src/.*/__init__\.py$",
                        "description": "Package initialization files",
                    },
                    {"pattern": r"^AGENTS\.md$", "description": "Agent configuration"},
                    {"pattern": r"^\.opencode/agent/.*", "description": "Agent files"},
                    {
                        "pattern": r"^docs/bmm-workflow-status\.yaml$",
                        "description": "Workflow status",
                    },
                ],
                "semantic_rules": [
                    {
                        "name": "cross_module_import",
                        "pattern": r"from\s+src\.([^\.]+)\.import",
                        "threshold": 2,
                        "action": "flag_for_review",
                    },
                    {
                        "name": "test_deletion",
                        "pattern": r".*_test\.py$",
                        "action": "flag_for_review",
                    },
                ],
            }
        }
        self._compile_patterns()

    def _validate_config(self) -> None:
        """Validate configuration schema."""
        if "path_patterns" not in self._config:
            raise ValueError("Config must contain 'path_patterns' section")

        for section in ["safe", "complex"]:
            if section not in self._config["path_patterns"]:
                raise ValueError(f"Config missing '{section}' patterns section")

    def _compile_patterns(self) -> None:
        """Compile regex patterns."""
        patterns_config = self._config.get("path_patterns", {})

        # Compile safe patterns
        self.safe_patterns = [
            Pattern(
                pattern=p["pattern"],
                description=p["description"],
            )
            for p in patterns_config.get("safe", [])
        ]

        # Compile complex patterns
        self.complex_patterns = [
            Pattern(
                pattern=p["pattern"],
                description=p["description"],
            )
            for p in patterns_config.get("complex", [])
        ]

        # Compile semantic rules
        self.semantic_rules = [
            SemanticRule(
                name=r["name"],
                pattern=r["pattern"],
                threshold=r.get("threshold"),
                action=r.get("action", "flag_for_review"),
            )
            for r in patterns_config.get("semantic_rules", [])
        ]

    def classify_path(
        self, path: str
    ) -> Tuple[Optional[PatternType], Optional[Pattern]]:
        """
        Classify a single path.

        Returns:
            Tuple of (pattern_type, matched_pattern) or (None, None) if no match
        """
        # Check complex patterns first (higher priority)
        for pattern in self.complex_patterns:
            if pattern.matches(path):
                return PatternType.COMPLEX, pattern

        # Then check safe patterns
        for pattern in self.safe_patterns:
            if pattern.matches(path):
                return PatternType.SAFE, pattern

        return None, None

    def is_safe(self, path: str) -> bool:
        """Check if a path is safe (matches safe patterns)."""
        pattern_type, _ = self.classify_path(path)
        return pattern_type == PatternType.SAFE

    def is_complex(self, path: str) -> bool:
        """Check if a path is complex (matches complex patterns)."""
        pattern_type, _ = self.classify_path(path)
        return pattern_type == PatternType.COMPLEX

    def get_semantic_rules(self) -> List[SemanticRule]:
        """Get all semantic analysis rules."""
        return self.semantic_rules.copy()

    def reload(self) -> None:
        """Reload configuration from disk."""
        self._load_config()
