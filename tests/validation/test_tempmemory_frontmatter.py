"""Tests for tempmemory frontmatter validation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

# Add the scripts/validation directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from validate_tempmemory_frontmatter import (
    extract_frontmatter,
    validate_date,
    validate_file,
    validate_frontmatter,
)


class TestExtractFrontmatter(TestCase):
    """Tests for frontmatter extraction."""

    def test_extract_valid_frontmatter(self):
        """Test extracting valid frontmatter."""
        path = Path("docs/tempmemories/test_valid.md")
        frontmatter, error = extract_frontmatter(path)
        self.assertIsNone(error)
        self.assertIsNotNone(frontmatter)
        self.assertEqual(frontmatter["type"], "decision")
        self.assertEqual(frontmatter["story_id"], "ST-123")

    def test_extract_no_frontmatter(self):
        """Test extracting from file without frontmatter."""
        path = Path("docs/tempmemories/README.md")
        frontmatter, error = extract_frontmatter(path)
        # README might not have frontmatter, so we just check it doesn't error
        # The actual result depends on whether README.md has frontmatter

    def test_extract_missing_closing_delimiter(self):
        """Test extracting with missing closing delimiter."""
        # Create a temp file with missing closing delimiter
        content = """---
type: decision
story_id: ST-123
# Missing closing ---
"""
        path = Path("/tmp/test_missing_closing.md")
        path.write_text(content)
        frontmatter, error = extract_frontmatter(path)
        self.assertIsNone(frontmatter)
        self.assertIsNotNone(error)
        self.assertIn("missing closing", error)
        path.unlink()


class TestValidateDate(TestCase):
    """Tests for date validation."""

    def test_valid_iso_datetime(self):
        """Test valid ISO 8601 datetime."""
        error = validate_date("2024-01-15T10:30:00")
        self.assertIsNone(error)

    def test_valid_iso_datetime_with_z(self):
        """Test valid ISO 8601 datetime with Z suffix."""
        error = validate_date("2024-01-15T10:30:00Z")
        self.assertIsNone(error)

    def test_valid_date_only(self):
        """Test valid date only (no time)."""
        error = validate_date("2024-01-15")
        self.assertIsNone(error)

    def test_invalid_date(self):
        """Test invalid date format."""
        error = validate_date("invalid-date")
        self.assertIsNotNone(error)
        self.assertIn("ISO 8601", error)


class TestValidateFrontmatter(TestCase):
    """Tests for frontmatter validation."""

    def test_valid_frontmatter(self):
        """Test validating valid frontmatter."""
        frontmatter = {
            "type": "decision",
            "story_id": "ST-123",
            "created": "2024-01-15T10:30:00",
            "tags": ["architecture", "design"],
            "author": "dev",
            "priority": "high",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertEqual(errors, [])

    def test_missing_required_type(self):
        """Test missing required 'type' field."""
        frontmatter = {
            "story_id": "ST-123",
            "created": "2024-01-15T10:30:00",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("type" in e and "missing" in e for e in errors))

    def test_missing_required_story_id(self):
        """Test missing required 'story_id' field."""
        frontmatter = {
            "type": "decision",
            "created": "2024-01-15T10:30:00",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("story_id" in e and "missing" in e for e in errors))

    def test_missing_required_created(self):
        """Test missing required 'created' field."""
        frontmatter = {
            "type": "decision",
            "story_id": "ST-123",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("created" in e and "missing" in e for e in errors))

    def test_invalid_type_value(self):
        """Test invalid type value."""
        frontmatter = {
            "type": "invalid-type",
            "story_id": "ST-123",
            "created": "2024-01-15T10:30:00",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("type" in e and "must be one of" in e for e in errors))

    def test_valid_type_values(self):
        """Test all valid type values."""
        valid_types = ["decision", "pattern", "summary", "anti-pattern"]
        for type_value in valid_types:
            frontmatter = {
                "type": type_value,
                "story_id": "ST-123",
                "created": "2024-01-15T10:30:00",
            }
            errors = validate_frontmatter(frontmatter, Path("test.md"))
            self.assertEqual(errors, [], f"Type '{type_value}' should be valid")

    def test_empty_story_id(self):
        """Test empty story_id."""
        frontmatter = {
            "type": "decision",
            "story_id": "",
            "created": "2024-01-15T10:30:00",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("story_id" in e and "empty" in e for e in errors))

    def test_invalid_date_format(self):
        """Test invalid date format."""
        frontmatter = {
            "type": "decision",
            "story_id": "ST-123",
            "created": "not-a-date",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("created" in e and "ISO 8601" in e for e in errors))

    def test_tags_not_a_list(self):
        """Test tags field that is not a list."""
        frontmatter = {
            "type": "decision",
            "story_id": "ST-123",
            "created": "2024-01-15T10:30:00",
            "tags": "not-a-list",
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("tags" in e and "list" in e for e in errors))

    def test_tags_item_not_string(self):
        """Test tags with non-string item."""
        frontmatter = {
            "type": "decision",
            "story_id": "ST-123",
            "created": "2024-01-15T10:30:00",
            "tags": [123, 456],
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("tags" in e and "string" in e for e in errors))

    def test_author_not_string(self):
        """Test author field that is not a string."""
        frontmatter = {
            "type": "decision",
            "story_id": "ST-123",
            "created": "2024-01-15T10:30:00",
            "author": 123,
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("author" in e and "string" in e for e in errors))

    def test_priority_not_string(self):
        """Test priority field that is not a string."""
        frontmatter = {
            "type": "decision",
            "story_id": "ST-123",
            "created": "2024-01-15T10:30:00",
            "priority": 123,
        }
        errors = validate_frontmatter(frontmatter, Path("test.md"))
        self.assertTrue(any("priority" in e and "string" in e for e in errors))


class TestValidateFile(TestCase):
    """Tests for file validation."""

    def test_validate_valid_file(self):
        """Test validating a valid tempmemory file."""
        path = Path("docs/tempmemories/test_valid.md")
        errors = validate_file(path)
        self.assertEqual(errors, [])

    def test_validate_invalid_type_file(self):
        """Test validating a file with invalid type."""
        path = Path("docs/tempmemories/test_invalid_type.md")
        errors = validate_file(path)
        self.assertTrue(len(errors) > 0)

    def test_validate_missing_required_file(self):
        """Test validating a file with missing required fields."""
        path = Path("docs/tempmemories/test_missing_required.md")
        errors = validate_file(path)
        self.assertTrue(len(errors) > 0)

    def test_validate_invalid_date_file(self):
        """Test validating a file with invalid date."""
        path = Path("docs/tempmemories/test_invalid_date.md")
        errors = validate_file(path)
        self.assertTrue(len(errors) > 0)

    def test_skip_non_tempmemory_files(self):
        """Test that non-tempmemory files are skipped."""
        path = Path("docs/tempmemories/README.md")
        errors = validate_file(path)
        # README.md might not have frontmatter, so it should be skipped (no errors)
        self.assertEqual(errors, [])

    def test_skip_non_md_files(self):
        """Test that non-markdown files are skipped."""
        path = Path("docs/tempmemories/test.txt")
        errors = validate_file(path)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    import unittest

    unittest.main()
