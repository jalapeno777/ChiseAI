"""Configuration comparator for local CI consistency validation.

Compares configuration settings between local (pyproject.toml) and CI (.woodpecker/*.yaml).
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ConfigDrift:
    """Represents a configuration drift between local and CI."""

    category: str  # e.g., "black", "ruff", "mypy"
    setting: str  # e.g., "line-length"
    local_value: Any
    ci_value: Any
    severity: str = "medium"  # low, medium, high


@dataclass
class ConfigComparison:
    """Result of configuration comparison."""

    drifts: list[ConfigDrift] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    analyzed_categories: list[str] = field(default_factory=list)


def parse_pyproject_toml() -> dict[str, dict[str, Any]]:
    """Parse pyproject.toml and extract tool configurations."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        return {}

    content = pyproject_path.read_text()
    configs = {}

    # Parse [tool.black]
    black_match = re.search(r"\[tool\.black\]\s*\n(.*?)(?=\n\[|\Z)", content, re.DOTALL)
    if black_match:
        configs["black"] = _parse_key_value_pairs(black_match.group(1))

    # Parse [tool.ruff] and [tool.ruff.lint]
    ruff_match = re.search(r"\[tool\.ruff\]\s*\n(.*?)(?=\n\[|\Z)", content, re.DOTALL)
    if ruff_match:
        configs["ruff"] = _parse_key_value_pairs(ruff_match.group(1))

    ruff_lint_match = re.search(
        r"\[tool\.ruff\.lint\]\s*\n(.*?)(?=\n\[|\Z)", content, re.DOTALL
    )
    if ruff_lint_match:
        if "ruff" not in configs:
            configs["ruff"] = {}
        configs["ruff"]["lint"] = _parse_key_value_pairs(ruff_lint_match.group(1))

    # Parse [tool.mypy]
    mypy_sections = re.findall(
        r"\[tool\.mypy\]\s*\n(.*?)(?=\n\[\[|\n\[|\Z)", content, re.DOTALL
    )
    if mypy_sections:
        configs["mypy"] = _parse_key_value_pairs(mypy_sections[0])

    # Parse [tool.pytest.ini_options]
    pytest_match = re.search(
        r"\[tool\.pytest\.ini_options\]\s*\n(.*?)(?=\n\[|\Z)", content, re.DOTALL
    )
    if pytest_match:
        configs["pytest"] = _parse_key_value_pairs(pytest_match.group(1))

    # Parse [tool.bandit]
    bandit_match = re.search(
        r"\[tool\.bandit\]\s*\n(.*?)(?=\n\[|\Z)", content, re.DOTALL
    )
    if bandit_match:
        configs["bandit"] = _parse_key_value_pairs(bandit_match.group(1))

    return configs


def _parse_key_value_pairs(text: str) -> dict[str, Any]:
    """Parse key = value pairs from TOML section."""
    result: dict[str, Any] = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Handle simple key = value
        match = re.match(r"^(\w+)\s*=\s*(.+)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()

            # Parse list values
            if value.startswith("[") and value.endswith("]"):
                result[key] = _parse_list_value(value)
            # Parse boolean
            elif value.lower() in ("true", "false"):
                result[key] = value.lower() == "true"
            # Parse number
            elif value.isdigit():
                result[key] = int(value)
            # Remove quotes from string
            elif (
                value.startswith('"')
                and value.endswith('"')
                or value.startswith("'")
                and value.endswith("'")
            ):
                result[key] = value[1:-1]
            else:
                result[key] = value

    return result


def _parse_list_value(value: str) -> list[str]:
    """Parse a TOML list value."""
    # Remove brackets
    inner = value[1:-1].strip()
    if not inner:
        return []

    items = []
    for item in inner.split(","):
        item = item.strip()
        if (
            item.startswith('"')
            and item.endswith('"')
            or item.startswith("'")
            and item.endswith("'")
        ):
            item = item[1:-1]
        items.append(item)

    return items


def extract_ci_config_from_yaml(
    ci_yaml_path: str = ".woodpecker/ci.yaml",
) -> dict[str, Any]:
    """Extract tool configuration from Woodpecker CI YAML files."""
    configs: dict[str, Any] = {}

    # Read ci.yaml
    ci_path = Path(ci_yaml_path)
    if ci_path.exists():
        content = ci_path.read_text()

        # Extract black config from lint commands
        black_match = re.search(r"black.*?--check.*?(--diff)?\s*(\S+\.py)?", content)
        if black_match:
            # Black in CI uses default settings, line-length=88 from pyproject.toml
            configs["black"] = {"ci_default": True}

        # Extract ruff config
        ruff_match = re.search(r"ruff check", content)
        if ruff_match:
            configs["ruff"] = {"ci_default": True}

        # Extract mypy config
        mypy_match = re.search(r"mypy \S+", content)
        if mypy_match:
            configs["mypy"] = {"ci_default": True}

        # Extract pytest config
        pytest_match = re.search(r"pytest[^\n]+", content)
        if pytest_match:
            configs["pytest"] = {"ci_default": True}

    # Also check pipeline.yaml for simpler CI config
    pipeline_path = Path(".woodpecker/pipeline.yaml")
    if pipeline_path.exists():
        content = pipeline_path.read_text()

        # Extract pip install commands to get versions
        pip_installs = re.findall(r"pip install (\S+)", content)
        if pip_installs:
            configs["pip_versions"] = pip_installs

        # Extract python version from matrix
        py_versions = re.findall(r'"(\d+\.\d+)"', content)
        if py_versions:
            configs["python_versions"] = py_versions

    return configs


def compare_black_config(
    local: dict[str, Any], ci: dict[str, Any]
) -> list[ConfigDrift]:
    """Compare black configuration between local and CI."""
    drifts = []

    local_line_length = local.get("line-length", 88)
    ci_line_length = 88  # CI default from pyproject.toml

    if local_line_length != ci_line_length:
        drifts.append(
            ConfigDrift(
                category="black",
                setting="line-length",
                local_value=local_line_length,
                ci_value=ci_line_length,
                severity="high",
            )
        )

    local_target = local.get("target-version", ["py311"])
    if local_target:
        local_target_str = (
            ",".join(local_target)
            if isinstance(local_target, list)
            else str(local_target)
        )
    else:
        local_target_str = "unknown"

    # CI uses py311
    if "py311" not in local_target_str:
        drifts.append(
            ConfigDrift(
                category="black",
                setting="target-version",
                local_value=local_target_str,
                ci_value="py311",
                severity="medium",
            )
        )

    return drifts


def compare_ruff_config(local: dict[str, Any], ci: dict[str, Any]) -> list[ConfigDrift]:
    """Compare ruff configuration between local and CI."""
    drifts = []

    local_line_length = local.get("line-length", 88)
    if local_line_length != 88:
        drifts.append(
            ConfigDrift(
                category="ruff",
                setting="line-length",
                local_value=local_line_length,
                ci_value=88,
                severity="high",
            )
        )

    # Compare lint rules - check both top-level and lint-specific select
    local_select = local.get("select", [])
    lint_select = (
        local.get("lint", {}).get("select", [])
        if isinstance(local.get("lint"), dict)
        else []
    )

    # Use lint-specific select if available, otherwise use top-level
    if lint_select:
        local_select = lint_select

    if isinstance(local_select, list):
        local_select = ",".join(sorted(local_select))
    elif not local_select:  # Empty list or empty string
        local_select = ""
    else:
        local_select = str(local_select)

    # CI uses: E, F, I, B, UP, SIM (sorted)
    ci_select = "B,E,F,I,SIM,UP"

    if local_select != ci_select:
        drifts.append(
            ConfigDrift(
                category="ruff",
                setting="select (lint rules)",
                local_value=local_select if local_select else "(not set)",
                ci_value=ci_select,
                severity="medium",
            )
        )

    return drifts


def compare_mypy_config(local: dict[str, Any], ci: dict[str, Any]) -> list[ConfigDrift]:
    """Compare mypy configuration between local and CI."""
    drifts = []

    local_python_version = local.get("python_version", "3.11")
    if local_python_version != "3.11":
        drifts.append(
            ConfigDrift(
                category="mypy",
                setting="python_version",
                local_value=local_python_version,
                ci_value="3.11",
                severity="medium",
            )
        )

    # Check key settings
    for setting in ["warn_return_any", "warn_unused_configs", "disallow_untyped_defs"]:
        local_val = local.get(setting, False)
        ci_val = True  # CI uses True for these
        if local_val != ci_val:
            drifts.append(
                ConfigDrift(
                    category="mypy",
                    setting=setting,
                    local_value=local_val,
                    ci_value=ci_val,
                    severity="low",
                )
            )

    return drifts


def compare_pytest_config(
    local: dict[str, Any], ci: dict[str, Any]
) -> list[ConfigDrift]:
    """Compare pytest configuration between local and CI."""
    drifts = []

    # Check addopts for critical settings
    local_addopts = local.get("addopts", "")
    if local_addopts:
        # CI uses -v --tb=short --import-mode=importlib
        if "--import-mode=importlib" not in local_addopts:
            drifts.append(
                ConfigDrift(
                    category="pytest",
                    setting="addopts (import-mode)",
                    local_value=local_addopts,
                    ci_value="-v --tb=short --import-mode=importlib",
                    severity="medium",
                )
            )

    # Check testpaths
    local_testpaths = local.get("testpaths", ["tests"])
    if local_testpaths != ["tests"]:
        drifts.append(
            ConfigDrift(
                category="pytest",
                setting="testpaths",
                local_value=(
                    ",".join(local_testpaths)
                    if isinstance(local_testpaths, list)
                    else local_testpaths
                ),
                ci_value="tests",
                severity="low",
            )
        )

    return drifts


def compare_configurations() -> ConfigComparison:
    """Compare all tool configurations between local and CI."""
    comparison = ConfigComparison()

    # Parse local config
    local_config = parse_pyproject_toml()
    comparison.analyzed_categories = list(local_config.keys())

    # Extract CI config
    ci_config = extract_ci_config_from_yaml()

    # Compare each tool
    if "black" in local_config:
        comparison.drifts.extend(
            compare_black_config(local_config["black"], ci_config.get("black", {}))
        )

    if "ruff" in local_config:
        comparison.drifts.extend(
            compare_ruff_config(local_config["ruff"], ci_config.get("ruff", {}))
        )

    if "mypy" in local_config:
        comparison.drifts.extend(
            compare_mypy_config(local_config["mypy"], ci_config.get("mypy", {}))
        )

    if "pytest" in local_config:
        comparison.drifts.extend(
            compare_pytest_config(local_config["pytest"], ci_config.get("pytest", {}))
        )

    return comparison


def format_config_report(comparison: ConfigComparison) -> str:
    """Format configuration comparison as a readable report."""
    lines = ["=" * 60, "CONFIGURATION COMPARISON REPORT", "=" * 60, ""]

    if not comparison.drifts:
        lines.append("○ No configuration drift detected")
        lines.append("")
        return "\n".join(lines)

    # Group by severity
    by_severity: dict[str, list[ConfigDrift]] = {"high": [], "medium": [], "low": []}
    for drift in comparison.drifts:
        by_severity[drift.severity].append(drift)

    for severity in ["high", "medium", "low"]:
        drifts = by_severity[severity]
        if not drifts:
            continue

        symbol = "✗" if severity == "high" else "⚠" if severity == "medium" else "○"
        lines.append(f"{symbol} {severity.upper()} severity: {len(drifts)} drift(s)")
        lines.append("-" * 40)

        for drift in drifts:
            lines.append(f"  {drift.category}.{drift.setting}")
            lines.append(f"    Local: {drift.local_value}")
            lines.append(f"    CI:    {drift.ci_value}")

        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    comparison = compare_configurations()

    print(format_config_report(comparison))

    # Exit with error if high severity drifts
    high_drifts = [d for d in comparison.drifts if d.severity == "high"]
    sys.exit(1 if high_drifts else 0)
