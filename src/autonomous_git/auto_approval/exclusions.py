"""Exclusion list management for auto-approval."""

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ExclusionList:
    """Exclusion list configuration."""

    paths: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    title_patterns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paths": self.paths,
            "authors": self.authors,
            "title_patterns": self.title_patterns,
        }


class ExclusionManager:
    """Manages exclusion lists for auto-approval."""

    def __init__(
        self,
        paths: Optional[List[str]] = None,
        authors: Optional[List[str]] = None,
        title_patterns: Optional[List[str]] = None,
        config_path: Optional[str] = None,
    ):
        """Initialize exclusion manager.

        Args:
            paths: List of path patterns to exclude
            authors: List of author logins to exclude
            title_patterns: List of regex patterns for PR titles to exclude
            config_path: Path to YAML config file with exclusions
        """
        self.exclusions = ExclusionList()

        # Load from config file if provided
        if config_path and Path(config_path).exists():
            self._load_from_file(config_path)

        # Override with explicit values
        if paths:
            self.exclusions.paths.extend(paths)
        if authors:
            self.exclusions.authors.extend(authors)
        if title_patterns:
            self.exclusions.title_patterns.extend(title_patterns)

        # Compile title patterns
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.exclusions.title_patterns
        ]

        logger.info(
            f"ExclusionManager initialized: {len(self.exclusions.paths)} paths, "
            f"{len(self.exclusions.authors)} authors, "
            f"{len(self.exclusions.title_patterns)} title patterns"
        )

    def _load_from_file(self, config_path: str):
        """Load exclusions from YAML file."""
        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)

            if (
                data
                and "auto_approval" in data
                and "exclusions" in data["auto_approval"]
            ):
                ex = data["auto_approval"]["exclusions"]
                self.exclusions.paths.extend(ex.get("paths", []))
                self.exclusions.authors.extend(ex.get("authors", []))
                self.exclusions.title_patterns.extend(ex.get("title_patterns", []))

                logger.info(f"Loaded exclusions from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load exclusions from {config_path}: {e}")

    def is_path_excluded(self, file_path: str) -> bool:
        """Check if a file path matches any exclusion pattern.

        Args:
            file_path: File path to check

        Returns:
            True if path is excluded
        """
        import re

        for pattern in self.exclusions.paths:
            # Handle ** for recursive matching
            if "**" in pattern:
                # Convert ** pattern to match any directory depth
                # docs/**/*.md should match:
                # - docs/file.md
                # - docs/nested/file.md
                # - docs/deep/nested/file.md

                # Escape special regex chars first
                regex_pattern = re.escape(pattern)

                # Unescape ** and * since we want to handle them specially
                # re.escape turns ** into \*\* and * into \*
                regex_pattern = regex_pattern.replace(r"\*\*", "{{GLOBSTAR}}")
                regex_pattern = regex_pattern.replace(r"\*", "{{STAR}}")
                regex_pattern = regex_pattern.replace(r"\?", "{{QUESTION}}")

                # Handle **/ (matches any directory depth including zero)
                regex_pattern = regex_pattern.replace("{{GLOBSTAR}}/", "(?:.*/)?")

                # Handle /** (matches any trailing directories)
                regex_pattern = regex_pattern.replace("/{{GLOBSTAR}}", "(?:/.*)?")

                # Handle remaining ** (matches any characters including /)
                regex_pattern = regex_pattern.replace("{{GLOBSTAR}}", ".*")

                # Handle single * (matches any characters except /)
                regex_pattern = regex_pattern.replace("{{STAR}}", "[^/]*")

                # Handle ?
                regex_pattern = regex_pattern.replace("{{QUESTION}}", ".")

                regex_pattern = f"^{regex_pattern}$"

                if re.match(regex_pattern, file_path):
                    logger.debug(
                        f"Path '{file_path}' matches exclusion pattern '{pattern}'"
                    )
                    return True
            else:
                # Simple glob matching - fnmatch matches at any level by default
                # We need to be more strict: docs/*.md should NOT match docs/nested/file.md
                # Check if the path matches the pattern
                if fnmatch.fnmatch(file_path, pattern):
                    # Additional check: ensure directory depth matches
                    # Count directory separators in pattern and path
                    pattern_parts = pattern.split("/")
                    path_parts = file_path.split("/")

                    # If pattern has no wildcards for directories, enforce exact depth
                    has_dir_wildcard = any(
                        "*" in p or "?" in p for p in pattern_parts[:-1]
                    )
                    if not has_dir_wildcard and len(pattern_parts) != len(path_parts):
                        continue

                    logger.debug(
                        f"Path '{file_path}' matches exclusion pattern '{pattern}'"
                    )
                    return True
        return False

    def are_files_excluded(self, files: List[str]) -> tuple[bool, List[str]]:
        """Check if any files in a list are excluded.

        Args:
            files: List of file paths

        Returns:
            Tuple of (is_excluded, list_of_excluded_files)
        """
        excluded = [f for f in files if self.is_path_excluded(f)]
        return len(excluded) > 0, excluded

    def is_author_excluded(self, author: str) -> bool:
        """Check if an author is excluded.

        Args:
            author: Author login to check

        Returns:
            True if author is excluded
        """
        if author in self.exclusions.authors:
            logger.debug(f"Author '{author}' is in exclusion list")
            return True
        return False

    def is_title_excluded(self, title: str) -> bool:
        """Check if a PR title matches any exclusion pattern.

        Args:
            title: PR title to check

        Returns:
            True if title matches exclusion pattern
        """
        for pattern in self._compiled_patterns:
            if pattern.search(title):
                logger.debug(
                    f"Title '{title}' matches exclusion pattern '{pattern.pattern}'"
                )
                return True
        return False

    def is_pr_excluded(
        self,
        pr_number: int,
        title: str,
        author: str,
        files: Optional[List[str]] = None,
    ) -> tuple[bool, str]:
        """Check if a PR is excluded from auto-approval.

        Args:
            pr_number: PR number
            title: PR title
            author: PR author
            files: Optional list of changed files

        Returns:
            Tuple of (is_excluded, reason)
        """
        # Check author
        if self.is_author_excluded(author):
            return True, f"Author '{author}' is excluded"

        # Check title
        if self.is_title_excluded(title):
            return True, f"Title matches exclusion pattern"

        # Check files
        if files:
            is_excluded, excluded_files = self.are_files_excluded(files)
            if is_excluded:
                return True, f"Files excluded: {', '.join(excluded_files)}"

        return False, ""

    def add_path_exclusion(self, pattern: str):
        """Add a path exclusion pattern."""
        self.exclusions.paths.append(pattern)
        logger.info(f"Added path exclusion: {pattern}")

    def add_author_exclusion(self, author: str):
        """Add an author exclusion."""
        self.exclusions.authors.append(author)
        logger.info(f"Added author exclusion: {author}")

    def add_title_pattern(self, pattern: str):
        """Add a title pattern exclusion."""
        self.exclusions.title_patterns.append(pattern)
        self._compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
        logger.info(f"Added title pattern exclusion: {pattern}")

    def get_exclusions(self) -> ExclusionList:
        """Get current exclusion list."""
        return self.exclusions
