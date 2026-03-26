"""Version checker for local CI consistency validation.

Compares tool versions between local installation and CI Docker images.

The CI images use date-based tags (e.g., py311-20260323). This module maps those
image tags to known tool versions so we can detect drift between local and CI.
"""

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ToolVersion:
    """Represents a tool's version information."""

    name: str
    local_version: str | None
    ci_version: str | None
    local_available: bool
    ci_docker_image: str


# Known tool versions for each CI image tag.
# Format: "YYYYMMDD" -> {"tool": "version", ...}
# Updated when CI images are rebuilt.
CI_IMAGE_VERSIONS = {
    "20260323": {
        "python": "3.11.9",
        "black": "25.1.0",
        "ruff": "0.9.5",
        "mypy": "1.14.1",
        "bandit": "1.7.10",
        "pytest": "8.3.4",
    },
    "20260324": {
        "python": "3.11.9",
        "black": "25.1.0",
        "ruff": "0.9.5",
        "mypy": "1.14.1",
        "bandit": "1.7.10",
        "pytest": "8.3.4",
    },
}

# Map of tool names to their CI Docker image patterns
CI_TOOL_PATTERNS = {
    "python": {
        "ci_image": "chiseai-ci-tools:py311-20260323",
    },
    "black": {
        "ci_image": "chiseai-ci-lint:py311-20260323",
    },
    "ruff": {
        "ci_image": "chiseai-ci-lint:py311-20260323",
    },
    "mypy": {
        "ci_image": "chiseai-ci-lint:py311-20260323",
    },
    "bandit": {
        "ci_image": "chiseai-ci-tools:py311-20260323",
    },
    "pytest": {
        "ci_image": "chiseai-ci-tools:py311-20260323",
    },
}


def get_local_tool_version(tool_name: str) -> str | None:
    """Get the locally installed version of a tool."""
    version_funcs = {
        "python": _get_python_version,
        "black": lambda: _get_pip_package_version("black"),
        "ruff": lambda: _get_pip_package_version("ruff"),
        "mypy": lambda: _get_pip_package_version("mypy"),
        "bandit": lambda: _get_pip_package_version("bandit"),
        "pytest": lambda: _get_pip_package_version("pytest"),
    }

    func = version_funcs.get(tool_name)
    if func:
        try:
            return func()
        except Exception:
            return None
    return None


def _get_python_version() -> str | None:
    """Get Python version."""
    try:
        result = subprocess.run(
            ["python", "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            match = re.search(r"Python (\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass

    # Try python3
    try:
        result = subprocess.run(
            ["python3", "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            match = re.search(r"Python (\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def _get_pip_package_version(package_name: str) -> str | None:
    """Get installed package version via pip."""
    try:
        result = subprocess.run(
            ["pip", "show", package_name], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            match = re.search(r"Version: (\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def get_ci_tool_version(
    tool_name: str, woodpecker_yaml_path: str = ".woodpecker/ci.yaml"
) -> str | None:
    """Extract expected CI tool version from woodpecker CI configuration.

    Uses the CI image tag date to look up known tool versions from CI_IMAGE_VERSIONS.
    """
    try:
        # Read the CI yaml to find the image version
        ci_yaml_path = Path(woodpecker_yaml_path)
        if not ci_yaml_path.exists():
            # Try alternative path
            ci_yaml_path = Path(".woodpecker/ci.yaml")

        content = ci_yaml_path.read_text()

        # Find the most recent image tag for this tool
        # Map tool names to CI image base names
        tool_to_image = {
            "python": "chiseai-ci-tools",
            "black": "chiseai-ci-lint",
            "ruff": "chiseai-ci-lint",
            "mypy": "chiseai-ci-lint",
            "bandit": "chiseai-ci-tools",
            "pytest": "chiseai-ci-tools",
        }

        image_base = tool_to_image.get(tool_name, "chiseai-ci-tools")

        # Extract image tag date (e.g., py311-20260323 -> 20260323)
        image_pattern = rf"{image_base}:py\d+-(\d{{8}})"
        matches = re.findall(image_pattern, content)

        if matches:
            # Use the most recent image tag
            image_date = matches[-1]

            # Look up known versions for this image
            if image_date in CI_IMAGE_VERSIONS:
                return CI_IMAGE_VERSIONS[image_date].get(tool_name)

            # If image date is not in our known versions, return the date as info
            # This indicates we need to update CI_IMAGE_VERSIONS
            return f"{image_date} (unverified)"

        # Also check pipeline.yaml for simpler version references
        pipeline_yaml = Path(".woodpecker/pipeline.yaml")
        if pipeline_yaml.exists():
            content = pipeline_yaml.read_text()
            # Look for python version in matrix
            if tool_name == "python":
                match = re.search(r'PYTHON_VERSION.*?"(\d+\.\d+)"', content)
                if match:
                    return match.group(1)

    except Exception:
        pass

    return None


def check_tool_versions(tools: list[str] | None = None) -> list[ToolVersion]:
    """Check versions of specified tools or all known tools.

    Args:
        tools: List of tool names to check. If None, checks all known tools.

    Returns:
        List of ToolVersion objects with version information.
    """
    if tools is None:
        tools = list(CI_TOOL_PATTERNS.keys())

    results = []
    for tool in tools:
        if tool not in CI_TOOL_PATTERNS:
            continue

        pattern = CI_TOOL_PATTERNS[tool]
        local_version = get_local_tool_version(tool)
        ci_version = get_ci_tool_version(tool)

        results.append(
            ToolVersion(
                name=tool,
                local_version=local_version,
                ci_version=ci_version,
                local_available=local_version is not None,
                ci_docker_image=pattern["ci_image"],
            )
        )

    return results


def detect_version_drift(results: list[ToolVersion]) -> list[ToolVersion]:
    """Detect tools with version mismatches.

    Returns tools where local version differs from CI version.
    Note: Some tools (like python) may have different but compatible versions.
    Skips tools where CI version is unknown or unverified.
    """
    drift = []
    for result in results:
        if not result.local_available:
            continue

        # Skip if CI version is unknown or unverified
        if not result.ci_version or "(unverified)" in str(result.ci_version):
            continue

        # Python version check - allow minor version differences
        if result.name == "python":
            if result.local_version and result.ci_version:
                local_parts = result.local_version.split(".")
                ci_parts = result.ci_version.split(".")
                # Major and minor should match
                if local_parts[0] != ci_parts[0] or local_parts[1] != ci_parts[1]:
                    drift.append(result)
        else:
            # For other tools, exact version match required
            if result.local_version != result.ci_version:
                drift.append(result)

    return drift


def format_version_report(results: list[ToolVersion], drift: list[ToolVersion]) -> str:
    """Format version check results as a readable report."""
    lines = ["=" * 60, "TOOL VERSION REPORT", "=" * 60, ""]

    for result in results:
        status = "✓" if result in drift else "○"
        local = result.local_version or "NOT INSTALLED"
        ci = result.ci_version or "UNKNOWN"

        lines.append(f"{status} {result.name.upper()}")
        lines.append(f"  Local: {local}")
        lines.append(f"  CI:    {ci} ({result.ci_docker_image})")
        lines.append("")

    if drift:
        lines.append("-" * 60)
        lines.append(f"VERSION DRIFT DETECTED: {len(drift)} tool(s)")
        lines.append("-" * 60)
        for d in drift:
            lines.append(f"  • {d.name}: local={d.local_version}, ci={d.ci_version}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    results = check_tool_versions()
    drift = detect_version_drift(results)

    print(format_version_report(results, drift))

    # Exit with error if drift detected
    sys.exit(1 if drift else 0)
