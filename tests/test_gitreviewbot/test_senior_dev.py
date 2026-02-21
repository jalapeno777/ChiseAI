"""Tests for SeniorDev reviewer."""

import pytest

from autonomous_git.gitreviewbot.senior_dev import SeniorDevReviewer


@pytest.fixture
def reviewer():
    """Create a SeniorDevReviewer for testing."""
    return SeniorDevReviewer()


class TestSeniorDevReviewer:
    """Test SeniorDevReviewer."""

    async def test_review_clean_code(self, reviewer):
        """Test reviewing clean code."""
        diff = """diff --git a/src/test.py b/src/test.py
+def hello():
+    return "Hello, World!"
"""

        result = await reviewer.review(
            pr_title="ST-123: Add hello function",
            story_id="ST-123",
            diff=diff,
            files=["src/test.py"],
        )

        assert result.role == "SeniorDev"
        assert result.confidence > 0
        assert result.duration_ms is not None

    async def test_review_with_todo(self, reviewer):
        """Test reviewing code with TODO."""
        diff = """diff --git a/src/test.py b/src/test.py
+def process():
+    # TODO: implement this
+    pass
"""

        result = await reviewer.review(
            pr_title="ST-123: Add process function",
            story_id="ST-123",
            diff=diff,
            files=["src/test.py"],
        )

        assert result.role == "SeniorDev"
        # Mock review should find the TODO
        assert any("TODO" in f.message for f in result.findings)

    async def test_review_with_debug_print(self, reviewer):
        """Test reviewing code with debug print."""
        diff = """diff --git a/src/debug.py b/src/debug.py
+def debug_func():
+    print("Debug info")
+    return 42
"""

        result = await reviewer.review(
            pr_title="ST-123: Add debug function",
            story_id="ST-123",
            diff=diff,
            files=["src/debug.py"],
        )

        assert result.role == "SeniorDev"
        # Mock review should find the print statement
        assert any("print" in f.message.lower() for f in result.findings)

    async def test_review_large_diff(self, reviewer):
        """Test reviewing large diff."""
        # Create a large diff
        lines = [f"+line {i}\n" for i in range(1000)]
        diff = "diff --git a/src/large.py b/src/large.py\n" + "".join(lines)

        result = await reviewer.review(
            pr_title="ST-123: Large change",
            story_id="ST-123",
            diff=diff,
            files=["src/large.py"],
        )

        assert result.role == "SeniorDev"
        # Should suggest breaking into smaller PRs
        assert any(
            "large" in f.message.lower() or "smaller" in f.message.lower()
            for f in result.findings
        )


class TestParseResponse:
    """Test response parsing."""

    def test_parse_valid_json(self, reviewer):
        """Test parsing valid JSON response."""
        response = """
        {
            "findings": [
                {
                    "file": "test.py",
                    "line": 10,
                    "severity": "warning",
                    "message": "Consider refactoring",
                    "suggestion": "Use list comprehension"
                }
            ],
            "summary": "Code review complete",
            "confidence": 85,
            "blockers": []
        }
        """

        result = reviewer._parse_response(response)

        assert len(result["findings"]) == 1
        assert result["confidence"] == 85.0
        assert result["summary"] == "Code review complete"

    def test_parse_json_with_markdown(self, reviewer):
        """Test parsing JSON wrapped in markdown."""
        response = """
        ```json
        {
            "findings": [],
            "summary": "LGTM",
            "confidence": 95,
            "blockers": []
        }
        ```
        """

        result = reviewer._parse_response(response)

        assert result["confidence"] == 95.0

    def test_parse_invalid_json(self, reviewer):
        """Test parsing invalid JSON."""
        response = "This is not JSON"

        result = reviewer._parse_response(response)

        assert result["findings"] == []
        assert result["confidence"] == 50.0


class TestExtractJson:
    """Test JSON extraction."""

    def test_extract_from_markdown(self, reviewer):
        """Test extracting JSON from markdown code block."""
        text = """
        Some text before
        ```json
        {"key": "value"}
        ```
        Some text after
        """

        result = reviewer._extract_json(text)

        assert result == '{"key": "value"}'

    def test_extract_without_markers(self, reviewer):
        """Test extracting JSON without markdown markers."""
        text = 'Some text {"key": "value"} more text'

        result = reviewer._extract_json(text)

        assert result == '{"key": "value"}'

    def test_extract_no_json(self, reviewer):
        """Test extracting when no JSON present."""
        text = "No JSON here"

        result = reviewer._extract_json(text)

        assert result is None


class TestMockReview:
    """Test mock review generation."""

    def test_mock_review_clean(self, reviewer):
        """Test mock review for clean code."""
        diff = "+def clean():\n+    pass\n"

        response = reviewer._mock_review(diff, ["test.py"])

        assert "findings" in response
        assert "confidence" in response

    def test_mock_review_with_todo(self, reviewer):
        """Test mock review finds TODO."""
        diff = "+def func():\n+    # TODO: fix\n+    pass\n"

        response = reviewer._mock_review(diff, ["test.py"])

        assert "TODO" in response
        assert "findings" in response

    def test_mock_review_with_print(self, reviewer):
        """Test mock review finds print."""
        diff = '+def func():\n+    print("debug")\n+    return 1\n'

        response = reviewer._mock_review(diff, ["module.py"])

        assert "print" in response.lower()


class TestErrorHandling:
    """Test error handling."""

    def test_timeout_result(self, reviewer):
        """Test timeout result generation."""
        result = reviewer._timeout_result()

        assert result["blockers"] == ["Review timeout"]
        assert result["confidence"] == 50.0

    def test_error_result(self, reviewer):
        """Test error result generation."""
        result = reviewer._error_result("Connection failed")

        assert "Connection failed" in result["blockers"][0]
        assert result["confidence"] == 0.0
