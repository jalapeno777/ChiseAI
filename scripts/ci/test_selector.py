#!/usr/bin/env python3
"""Intelligent test selector for local CI speed optimization.

Uses git diff to find changed files and maps them to relevant test files
using configurable patterns. Falls back to full suite when mapping is unclear.

Usage:
    python scripts/ci/test_selector.py [options]

Options:
    --full              Run complete test suite (ignore selection logic)
    --changed-only      Only return tests for changed files (default)
    --base-ref REF      Git ref to compare against (default: origin/main)
    --cache FILE        Cache file for mapping persistence
    --verbose           Print detailed mapping information
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Test file patterns
TEST_PATTERNS = [
    "test_{stem}.py",
    "{stem}_test.py",
    "test_{parent}/{stem}.py",
    "{parent}/test_{stem}.py",
]

# Directories to skip when mapping
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules", ".venv", "venv"}

# Files to skip
SKIP_FILES = {"__init__.py", "conftest.py", "pytest.ini", "setup.py", "tox.ini"}


def _run_git(*args: str, cwd: str | None = None) -> tuple[int, str]:
    """Run a git command and return (returncode, stdout)."""
    proc = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout.strip()


def get_changed_files(base_ref: str | None = None) -> list[str]:
    """Get list of changed files compared to base ref."""
    if base_ref is None:
        # Try to find a suitable base ref
        for candidate in ["origin/main", "main", "HEAD~1"]:
            rc, _ = _run_git("rev-parse", "--verify", candidate)
            if rc == 0:
                base_ref = candidate
                break

    if base_ref:
        rc, merge_base = _run_git("merge-base", "HEAD", base_ref)
        diff_base = merge_base if rc == 0 and merge_base else base_ref
        rc, out = _run_git("diff", "--name-only", f"{diff_base}...HEAD")
    else:
        rc, out = _run_git("diff", "--name-only", "HEAD~1..HEAD")

    if rc == 0 and out:
        return [line.strip() for line in out.splitlines() if line.strip()]

    rc, out = _run_git("show", "--pretty=", "--name-only", "HEAD")
    if rc == 0:
        return [line.strip() for line in out.splitlines() if line.strip()]

    return []


def _get_file_stem_and_parent(path: str) -> tuple[str, str]:
    """Extract stem (filename without extension) and parent directory."""
    p = Path(path)
    stem = p.stem
    parent = p.parent.name
    return stem, parent


def _matches_pattern(path: Path, pattern: str, stem: str, parent: str) -> bool:
    """Check if a path matches a given pattern."""
    try:
        expanded = pattern.format(stem=stem, parent=parent)
        # Handle nested paths
        if "/" in expanded:
            return str(path).endswith(expanded) or str(path).endswith(f"/{expanded}")
        return path.name == expanded
    except KeyError:
        return False


def find_tests_for_source(source_path: str, tests_root: str = "tests") -> list[str]:
    """Find test files that correspond to a source file.

    Maps source files to tests using patterns like:
    - src/foo/bar.py -> tests/test_bar.py, tests/foo/test_bar.py
    - src/bar.py -> tests/test_bar.py

    Args:
        source_path: Path to the source file
        tests_root: Root directory for tests

    Returns:
        List of paths to matching test files that exist
    """
    source = Path(source_path)
    if not source.exists() or source.is_dir():
        return []

    # Skip non-Python files
    if source.suffix != ".py":
        return []

    # Skip skipped files
    if source.name in SKIP_FILES or source.name.startswith("_"):
        return []

    stem, parent = _get_file_stem_and_parent(str(source))
    tests: list[str] = []

    for pattern in TEST_PATTERNS:
        candidate_name = pattern.format(stem=stem, parent=parent)
        # Try various locations
        for test_base in [
            Path(tests_root),
            Path("..") / tests_root,
            Path("tests"),
        ]:
            # Try exact match
            candidate = test_base / candidate_name
            if candidate.exists():
                tests.append(str(candidate))

            # Try with 'tests/' prefix if not already there
            if str(test_base) != tests_root:
                candidate = Path(tests_root) / candidate_name
                if candidate.exists() and candidate not in tests:
                    tests.append(str(candidate))

    # Also check for module-level test directories
    # e.g., src/strategy/dsl/foo.py -> tests/test_strong_system/test_program_synthesis/test_dsl.py
    module_parts = source.parts
    if "src" in module_parts:
        src_idx = module_parts.index("src")
        if src_idx >= 0 and len(module_parts) > src_idx + 1:
            module_path = "/".join(
                module_parts[src_idx + 1 : -1]
            )  # Remove 'src' and filename
            module_stem = stem

            # Look for tests in parallel directory structure
            for test_base in [Path(tests_root), Path("..") / tests_root]:
                # Check for tests/unit/{module}/test_{stem}.py
                for pattern in [
                    f"unit/{module_path}/test_{module_stem}.py",
                    f"test_{module_path}/test_{module_stem}.py",
                ]:
                    candidate = test_base / pattern
                    if candidate.exists() and candidate not in tests:
                        tests.append(str(candidate))

    return list(set(tests))  # Remove duplicates


def find_tests_for_changes(
    changed_files: list[str], tests_root: str = "tests"
) -> list[str]:
    """Find all tests needed for a list of changed files.

    Args:
        changed_files: List of changed file paths
        tests_root: Root directory for tests

    Returns:
        Deduplicated list of test file paths
    """
    all_tests: dict[str, bool] = {}

    for changed_file in changed_files:
        path = Path(changed_file)

        # Skip if already in skip dirs
        if any(part in SKIP_DIRS for part in path.parts):
            continue

        # If it's a test file itself, include it directly
        if "test_" in path.name or path.name.endswith("_test.py"):
            if path.exists():
                all_tests[str(path)] = True
            continue

        # If it's a source file, find corresponding tests
        if path.suffix == ".py" and str(path).startswith("src/"):
            tests = find_tests_for_source(str(path), tests_root)
            for test in tests:
                all_tests[test] = True

    return list(all_tests.keys())


def build_mapping_cache(changed_files: list[str], tests_root: str = "tests") -> dict:
    """Build a cache of source-to-test mappings for changed files."""
    cache = {
        "timestamp": datetime.now().isoformat(),
        "changed_files": changed_files,
        "mappings": {},
    }

    for changed_file in changed_files:
        path = Path(changed_file)
        if path.suffix == ".py" and str(path).startswith("src/"):
            tests = find_tests_for_source(str(path), tests_root)
            if tests:
                cache["mappings"][changed_file] = tests

    return cache


def load_cached_mappings(cache_file: str) -> dict | None:
    """Load cached mappings if still valid (less than 1 hour old)."""
    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file) as f:
            cache = json.load(f)

        # Check if cache is stale (older than 1 hour)
        cached_time = datetime.fromisoformat(cache.get("timestamp", "2000-01-01"))
        if datetime.now() - cached_time > timedelta(hours=1):
            return None

        return cache
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def save_mapping_cache(cache_file: str, cache: dict) -> None:
    """Save mapping cache to file."""
    os.makedirs(os.path.dirname(cache_file) or ".", exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=2)


def compute_file_hash(file_path: str) -> str | None:
    """Compute SHA256 hash of a file for change detection."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return None


def check_dependencies_changed(cache_file: str, changed_files: list[str]) -> bool:
    """Check if any dependencies (requirements, setup) changed since cache."""
    dep_patterns = [
        "requirements",
        "setup.py",
        "pyproject.toml",
        "setup.cfg",
        "poetry.lock",
    ]

    for changed in changed_files:
        for pattern in dep_patterns:
            if pattern in changed.lower():
                return True

    # Also check if cache has no mappings
    cache = load_cached_mappings(cache_file)
    return bool(not cache or not cache.get("mappings"))


def select_tests(
    full: bool = False,
    base_ref: str | None = None,
    cache_file: str | None = None,
    verbose: bool = False,
    tests_root: str = "tests",
) -> tuple[list[str], dict]:
    """Select tests to run based on changed files.

    Returns:
        Tuple of (test_files, metadata_dict)
    """
    metadata = {
        "mode": "full" if full else "selective",
        "changed_files": [],
        "selected_tests": [],
        "mapping_cache_used": False,
        "fallback_reason": None,
    }

    if full:
        # Run full suite - find all test files
        all_tests: list[str] = []
        for root, dirs, files in os.walk(tests_root):
            # Filter out skip dirs
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if (f.startswith("test_") or f.endswith("_test.py")) and f.endswith(
                    ".py"
                ):
                    if f not in SKIP_FILES:
                        all_tests.append(os.path.join(root, f))
        metadata["selected_tests"] = all_tests
        return all_tests, metadata

    # Selective mode - find changed files and map to tests
    changed_files = get_changed_files(base_ref)
    metadata["changed_files"] = changed_files

    if not changed_files:
        metadata["fallback_reason"] = "no_changed_files"
        return [], metadata

    # Check if we should use cache
    use_cache = False
    if cache_file:
        if not check_dependencies_changed(cache_file, changed_files):
            cached = load_cached_mappings(cache_file)
            if cached and cached.get("mappings"):
                use_cache = True
                metadata["mapping_cache_used"] = True

    if use_cache:
        cached = load_cached_mappings(cache_file)
        all_tests: dict[str, bool] = {}
        for source_file, tests in cached.get("mappings", {}).items():
            for test in tests:
                all_tests[test] = True
        selected = list(all_tests.keys())
    else:
        selected = find_tests_for_changes(changed_files, tests_root)

        # Cache the mappings
        if cache_file:
            cache = build_mapping_cache(changed_files, tests_root)
            save_mapping_cache(cache_file, cache)

    metadata["selected_tests"] = selected

    # If no tests found through mapping, fallback to syntax check only
    if not selected:
        # Find the changed Python files
        py_files = [f for f in changed_files if f.endswith(".py") and Path(f).exists()]
        if py_files:
            metadata["fallback_reason"] = "no_matching_tests_found"
        else:
            metadata["fallback_reason"] = "no_python_files_changed"

    return selected, metadata


def print_verbose_output(metadata: dict) -> None:
    """Print detailed mapping information."""
    print("=== Test Selection Metadata ===")
    print(f"Mode: {metadata['mode']}")
    print(f"Mapping cache used: {metadata['mapping_cache_used']}")
    print(f"Fallback reason: {metadata['fallback_reason']}")
    print(f"\nChanged files ({len(metadata['changed_files'])}):")
    for f in metadata["changed_files"][:20]:
        print(f"  - {f}")
    if len(metadata["changed_files"]) > 20:
        print(f"  ... and {len(metadata['changed_files']) - 20} more")
    print(f"\nSelected tests ({len(metadata['selected_tests'])}):")
    for t in metadata["selected_tests"][:20]:
        print(f"  - {t}")
    if len(metadata["selected_tests"]) > 20:
        print(f"  ... and {len(metadata['selected_tests']) - 20} more")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Intelligent test selector for local CI optimization"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run complete test suite (ignore selection logic)",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        default=True,
        help="Only return tests for changed files (default)",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Git ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--cache",
        default=".bmad-test-cache.json",
        help="Cache file for mapping persistence",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed mapping information",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (for machine parsing)",
    )
    parser.add_argument(
        "--tests-root",
        default="tests",
        help="Root directory for tests (default: tests)",
    )

    args = parser.parse_args()

    try:
        selected, metadata = select_tests(
            full=args.full,
            base_ref=args.base_ref,
            cache_file=args.cache,
            verbose=args.verbose,
            tests_root=args.tests_root,
        )

        if args.verbose:
            print_verbose_output(metadata)

        if args.json:
            print(
                json.dumps(
                    {
                        "tests": selected,
                        "metadata": metadata,
                    },
                    indent=2,
                )
            )
        else:
            for test in sorted(selected):
                print(test)

        return 0 if selected or metadata["fallback_reason"] else 1

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
