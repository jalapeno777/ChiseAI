"""
Tests for the runbook parser module.
"""

from pathlib import Path

import pytest

from runbooks.parser import ParsedRunbook, RunbookMetadata, RunbookParser, RunbookStep


class TestRunbookParser:
    """Tests for RunbookParser class."""

    def test_init_with_default_path(self):
        """Test parser initialization with default path."""
        parser = RunbookParser()
        assert parser.runbooks_dir is not None
        assert "docs" in str(parser.runbooks_dir)
        assert "runbooks" in str(parser.runbooks_dir)

    def test_init_with_custom_path(self, tmp_path):
        """Test parser initialization with custom path."""
        custom_dir = tmp_path / "custom_runbooks"
        custom_dir.mkdir()
        parser = RunbookParser(custom_dir)
        assert parser.runbooks_dir == custom_dir

    def test_list_runbooks_empty_directory(self, tmp_path):
        """Test listing runbooks in empty directory."""
        parser = RunbookParser(tmp_path)
        runbooks = parser.list_runbooks()
        assert runbooks == []

    def test_list_runbooks_with_files(self, tmp_path):
        """Test listing runbooks with markdown files."""
        (tmp_path / "test1.md").write_text("# Test 1")
        (tmp_path / "test2.md").write_text("# Test 2")
        (tmp_path / "not_a_runbook.txt").write_text("Not a runbook")

        parser = RunbookParser(tmp_path)
        runbooks = parser.list_runbooks()

        assert "test1" in runbooks
        assert "test2" in runbooks
        assert "not_a_runbook" not in runbooks
        assert len(runbooks) == 2

    def test_parse_nonexistent_runbook(self, tmp_path):
        """Test parsing a runbook that doesn't exist."""
        parser = RunbookParser(tmp_path)
        with pytest.raises(FileNotFoundError):
            parser.parse("nonexistent")

    def test_parse_simple_runbook(self, tmp_path):
        """Test parsing a simple runbook."""
        content = """---
title: Test Runbook
category: test
executable: true
---

# Test Runbook

This is a test runbook.
"""
        (tmp_path / "simple.md").write_text(content)

        parser = RunbookParser(tmp_path)
        runbook = parser.parse("simple")

        assert runbook.name == "simple"
        assert runbook.metadata.title == "Test Runbook"
        assert runbook.metadata.category == "test"
        assert runbook.metadata.executable is True

    def test_parse_runbook_with_steps(self, tmp_path):
        """Test parsing a runbook with executable steps in frontmatter."""
        content = """---
title: Test Runbook
executable: true
steps:
  - name: "Step 1"
    command: "echo hello"
  - name: "Step 2"
    script: "scripts/test.sh"
---

# Test Runbook
"""
        (tmp_path / "with_steps.md").write_text(content)

        parser = RunbookParser(tmp_path)
        runbook = parser.parse("with_steps")

        assert len(runbook.steps) == 2
        assert runbook.steps[0].name == "Step 1"
        assert runbook.steps[0].command == "echo hello"
        assert runbook.steps[1].name == "Step 2"
        assert runbook.steps[1].script == "scripts/test.sh"

    def test_parse_runbook_with_bash_blocks(self, tmp_path):
        """Test extracting steps from bash code blocks."""
        content = """---
title: Test Runbook
---

# Test Runbook

## Section 1

```bash
echo "Hello World"
```

## Section 2

```bash
ls -la
```
"""
        (tmp_path / "with_bash.md").write_text(content)

        parser = RunbookParser(tmp_path)
        runbook = parser.parse("with_bash")

        # Should extract steps from bash blocks
        assert len(runbook.steps) >= 1

    def test_parse_frontmatter_all_fields(self, tmp_path):
        """Test parsing all frontmatter fields."""
        content = """---
title: Full Test
category: emergency
severity: critical
executable: true
estimated_time_to_resolve: 15 minutes
maintainers: alice, bob
story_id: ST-TEST-001
---

# Full Test
"""
        (tmp_path / "full.md").write_text(content)

        parser = RunbookParser(tmp_path)
        runbook = parser.parse("full")

        assert runbook.metadata.title == "Full Test"
        assert runbook.metadata.category == "emergency"
        assert runbook.metadata.severity == "critical"
        assert runbook.metadata.executable is True
        assert runbook.metadata.estimated_time == "15 minutes"
        assert runbook.metadata.maintainers == ["alice", "bob"]
        assert runbook.metadata.story_id == "ST-TEST-001"


class TestRunbookStep:
    """Tests for RunbookStep class."""

    def test_step_is_executable_with_command(self):
        """Test that step with command is executable."""
        step = RunbookStep(name="Test", command="echo hello")
        assert step.is_executable() is True

    def test_step_is_executable_with_script(self):
        """Test that step with script is executable."""
        step = RunbookStep(name="Test", script="test.sh")
        assert step.is_executable() is True

    def test_step_is_not_executable_without_action(self):
        """Test that step without command or script is not executable."""
        step = RunbookStep(name="Test")
        assert step.is_executable() is False

    def test_step_with_all_fields(self):
        """Test step with all optional fields."""
        step = RunbookStep(
            name="Full Step",
            command="echo test",
            description="A test step",
            timeout=60,
            verify="test",
        )
        assert step.name == "Full Step"
        assert step.command == "echo test"
        assert step.description == "A test step"
        assert step.timeout == 60
        assert step.verify == "test"


class TestParsedRunbook:
    """Tests for ParsedRunbook class."""

    def test_is_executable_with_executable_steps(self):
        """Test is_executable property with executable steps."""
        metadata = RunbookMetadata(executable=True)
        steps = [RunbookStep(name="Step 1", command="echo hello")]
        runbook = ParsedRunbook(
            name="test",
            path=Path("test.md"),
            metadata=metadata,
            steps=steps,
            raw_content="",
        )
        assert runbook.is_executable is True

    def test_is_not_executable_without_flag(self):
        """Test is_executable property without executable flag."""
        metadata = RunbookMetadata(executable=False)
        steps = [RunbookStep(name="Step 1", command="echo hello")]
        runbook = ParsedRunbook(
            name="test",
            path=Path("test.md"),
            metadata=metadata,
            steps=steps,
            raw_content="",
        )
        assert runbook.is_executable is False

    def test_is_not_executable_without_steps(self):
        """Test is_executable property without executable steps."""
        metadata = RunbookMetadata(executable=True)
        steps = [RunbookStep(name="Step 1")]  # No command or script
        runbook = ParsedRunbook(
            name="test",
            path=Path("test.md"),
            metadata=metadata,
            steps=steps,
            raw_content="",
        )
        assert runbook.is_executable is False
