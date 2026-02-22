"""
Runbook parser for extracting executable steps from markdown files.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunbookStep:
    """Represents a single executable step in a runbook."""

    name: str
    command: str | None = None
    script: str | None = None
    description: str | None = None
    timeout: int | None = None
    verify: str | None = None

    def is_executable(self) -> bool:
        """Check if this step has an executable action."""
        return self.command is not None or self.script is not None


@dataclass
class RunbookMetadata:
    """Metadata extracted from runbook frontmatter."""

    title: str | None = None
    category: str | None = None
    severity: str | None = None
    executable: bool = False
    estimated_time: str | None = None
    maintainers: list[str] = field(default_factory=list)
    story_id: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ParsedRunbook:
    """A fully parsed runbook with metadata and content."""

    name: str
    path: Path
    metadata: RunbookMetadata
    steps: list[RunbookStep]
    raw_content: str

    @property
    def is_executable(self) -> bool:
        """Check if runbook has any executable steps."""
        return self.metadata.executable and any(
            step.is_executable() for step in self.steps
        )


class RunbookParser:
    """Parse runbook markdown files to extract executable steps."""

    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    CODE_BLOCK_PATTERN = re.compile(r"```bash\n(.*?)\n```", re.DOTALL)

    def __init__(self, runbooks_dir: Path | None = None):
        """
        Initialize the parser.

        Args:
            runbooks_dir: Directory containing runbook markdown files.
                         Defaults to docs/runbooks/ relative to repo root.
        """
        if runbooks_dir is None:
            # Find repo root by looking for .git or pyproject.toml
            current = Path.cwd()
            while current != current.parent:
                if (current / ".git").exists() or (current / "pyproject.toml").exists():
                    break
                current = current.parent
            runbooks_dir = current / "docs" / "runbooks"

        self.runbooks_dir = Path(runbooks_dir)

    def list_runbooks(self) -> list[str]:
        """List all available runbook names."""
        if not self.runbooks_dir.exists():
            return []

        runbooks = []
        for path in self.runbooks_dir.glob("*.md"):
            runbooks.append(path.stem)
        return sorted(runbooks)

    def parse(self, runbook_name: str) -> ParsedRunbook:
        """
        Parse a runbook by name.

        Args:
            runbook_name: Name of the runbook (without .md extension)

        Returns:
            ParsedRunbook object

        Raises:
            FileNotFoundError: If runbook doesn't exist
            ValueError: If runbook format is invalid
        """
        path = self.runbooks_dir / f"{runbook_name}.md"

        if not path.exists():
            raise FileNotFoundError(f"Runbook not found: {path}")

        content = path.read_text()

        # Parse frontmatter
        metadata = self._parse_frontmatter(content)

        # Parse steps from frontmatter or extract from content
        steps = self._parse_steps(metadata, content)

        return ParsedRunbook(
            name=runbook_name,
            path=path,
            metadata=metadata,
            steps=steps,
            raw_content=content,
        )

    def _parse_frontmatter(self, content: str) -> RunbookMetadata:
        """Extract YAML frontmatter from markdown content."""
        match = self.FRONTMATTER_PATTERN.match(content)

        if not match:
            return RunbookMetadata()

        frontmatter_text = match.group(1)

        # Simple YAML-like parsing (sufficient for our use case)
        metadata = RunbookMetadata()

        for line in frontmatter_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if key == "title":
                    metadata.title = value
                elif key == "category":
                    metadata.category = value
                elif key == "severity":
                    metadata.severity = value
                elif key == "executable":
                    metadata.executable = value.lower() in ("true", "yes", "1")
                elif key == "estimated_time_to_resolve":
                    metadata.estimated_time = value
                elif key == "maintainers":
                    metadata.maintainers = [m.strip() for m in value.split(",")]
                elif key == "story_id":
                    metadata.story_id = value

        # Parse steps array if present
        if "steps:" in frontmatter_text:
            metadata.steps = self._parse_steps_yaml(frontmatter_text)

        return metadata

    def _parse_steps_yaml(self, frontmatter: str) -> list[dict[str, Any]]:
        """Parse steps array from YAML frontmatter."""
        steps = []
        in_steps = False
        current_step: dict[str, Any] | None = None
        indent_level = 0

        for line in frontmatter.split("\n"):
            stripped = line.strip()

            if stripped == "steps:":
                in_steps = True
                indent_level = len(line) - len(line.lstrip()) + 2
                continue

            if not in_steps:
                continue

            # Check if we're still in steps section
            if line.strip() and not line.startswith(" " * indent_level):
                if not line.strip().startswith("-"):
                    break

            # Parse step entry
            if stripped.startswith("- name:"):
                if current_step:
                    steps.append(current_step)
                value = stripped.split(":", 1)[1].strip()
                # Only strip matching outer quotes
                value = self._strip_yaml_quotes(value)
                current_step = {"name": value}
            elif current_step and ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip().lstrip("-").strip()
                value = value.strip()
                # Only strip matching outer quotes
                value = self._strip_yaml_quotes(value)
                current_step[key] = value

        if current_step:
            steps.append(current_step)

        return steps

    def _strip_yaml_quotes(self, value: str) -> str:
        """Strip matching outer quotes from a YAML value."""
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                return value[1:-1]
        return value

    def _parse_steps(
        self, metadata: RunbookMetadata, content: str
    ) -> list[RunbookStep]:
        """Extract executable steps from metadata and content."""
        steps = []

        # First, try to use steps defined in frontmatter
        if metadata.steps:
            for step_data in metadata.steps:
                step = RunbookStep(
                    name=step_data.get("name", "Unnamed Step"),
                    command=step_data.get("command"),
                    script=step_data.get("script"),
                    description=step_data.get("description"),
                    timeout=(
                        int(step_data["timeout"]) if "timeout" in step_data else None
                    ),
                    verify=step_data.get("verify"),
                )
                steps.append(step)

        # If no steps in frontmatter, try to extract from markdown content
        if not steps:
            steps = self._extract_steps_from_content(content)

        return steps

    def _extract_steps_from_content(self, content: str) -> list[RunbookStep]:
        """Extract steps from markdown content by finding bash code blocks."""
        steps = []

        # Find all bash code blocks
        for match in self.CODE_BLOCK_PATTERN.finditer(content):
            code = match.group(1).strip()

            # Skip if it's just a comment or example
            if not code or code.startswith("#"):
                continue

            # Try to find a preceding heading for the step name
            # Look back from the match position
            pre_content = content[: match.start()]
            lines = pre_content.split("\n")

            step_name = "Execute command"
            for line in reversed(lines[-10:]):  # Look at last 10 lines
                if line.startswith("### "):
                    step_name = line[4:].strip()
                    break
                elif line.startswith("## "):
                    step_name = line[3:].strip()
                    break
                elif line.startswith("**") and line.endswith("**"):
                    step_name = line.strip("*").strip()
                    break

            # Create a step for each significant command
            # Split on newlines but keep related commands together
            command_lines = [
                cmd.strip()
                for cmd in code.split("\n")
                if cmd.strip() and not cmd.strip().startswith("#")
            ]

            if command_lines:
                # Join related commands (those ending with \)
                full_command = " ".join(command_lines)
                step = RunbookStep(name=step_name, command=full_command)
                steps.append(step)

        return steps
