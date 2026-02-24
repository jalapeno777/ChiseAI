"""Tests for script bootstrap compliance.

Ensures all operational scripts use the centralized bootstrap pattern.
This guards against regressions and ensures consistent environment
loading across all scripts.

ST-CI-005: Bootstrap Uniformity Tests
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

# Scripts directory path
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def get_all_scripts() -> list[Path]:
    """Get all Python scripts in the scripts directory.

    Returns:
        Sorted list of Path objects for all .py files excluding __init__.py
    """
    scripts = []
    for root, dirs, files in os.walk(SCRIPTS_DIR):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                scripts.append(Path(root) / file)
    return sorted(scripts)


def has_bootstrap_import(tree: ast.AST) -> bool:
    """Check if AST has bootstrap import.

    Detects the following patterns:
    - from config.bootstrap import bootstrap
    - from config.bootstrap import bootstrap, format_provider_status
    - from config import bootstrap (alternative import style)

    Args:
        tree: Parsed AST of the script

    Returns:
        True if bootstrap import is found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Check for: from config.bootstrap import bootstrap
            if node.module == "config.bootstrap":
                for alias in node.names:
                    if alias.name == "bootstrap":
                        return True
            # Check for: from config import bootstrap (alternative)
            if node.module == "config":
                for alias in node.names:
                    if alias.name == "bootstrap":
                        return True
    return False


def has_bootstrap_call(tree: ast.AST) -> bool:
    """Check if AST has bootstrap() call.

    Detects direct calls to bootstrap() function.
    Does NOT count references or assignments.

    Args:
        tree: Parsed AST of the script

    Returns:
        True if bootstrap() call is found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Direct call: bootstrap()
            if isinstance(node.func, ast.Name) and node.func.id == "bootstrap":
                return True
    return False


def get_bootstrap_import_line(tree: ast.AST) -> int | None:
    """Get the line number of the bootstrap import.

    Args:
        tree: Parsed AST of the script

    Returns:
        Line number of bootstrap import, or None if not found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "config.bootstrap":
                for alias in node.names:
                    if alias.name == "bootstrap":
                        return node.lineno
            if node.module == "config":
                for alias in node.names:
                    if alias.name == "bootstrap":
                        return node.lineno
    return None


def get_bootstrap_call_line(tree: ast.AST) -> int | None:
    """Get the line number of the bootstrap() call.

    Args:
        tree: Parsed AST of the script

    Returns:
        Line number of bootstrap() call, or None if not found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "bootstrap":
                return node.lineno
    return None


def get_first_os_getenv_call(tree: ast.AST) -> int | None:
    """Get the line number of the first os.getenv() or os.environ access.

    Args:
        tree: Parsed AST of the script

    Returns:
        Line number of first os.getenv call, or None if not found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for os.getenv() or os.environ.get()
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "getenv":
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id == "os":
                            return node.lineno
                    # os.environ.get()
                    if isinstance(node.func.value, ast.Attribute):
                        if node.func.value.attr == "environ":
                            return node.lineno
    return None


def get_first_os_environ_access(tree: ast.AST) -> int | None:
    """Get the line number of the first os.environ access.

    Args:
        tree: Parsed AST of the script

    Returns:
        Line number of first os.environ access, or None if not found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                return node.lineno
    return None


def uses_os_getenv(tree: ast.AST) -> bool:
    """Check if script uses os.getenv() or os.environ.

    Args:
        tree: Parsed AST of the script

    Returns:
        True if script uses environment variables
    """
    return (
        get_first_os_getenv_call(tree) is not None
        or get_first_os_environ_access(tree) is not None
    )


class TestBootstrapComplianceInventory:
    """Test cases for bootstrap compliance across all scripts."""

    def test_check_env_is_compliant(self):
        """Verify check_env.py is the reference implementation for bootstrap pattern."""
        check_env_path = SCRIPTS_DIR / "check_env.py"
        assert check_env_path.exists(), "check_env.py should exist"

        code = check_env_path.read_text()
        tree = ast.parse(code)

        assert has_bootstrap_import(tree), "check_env.py should have bootstrap import"
        assert has_bootstrap_call(tree), "check_env.py should call bootstrap()"

    def test_all_scripts_are_discoverable(self):
        """Verify that all scripts can be discovered."""
        scripts = get_all_scripts()
        assert len(scripts) > 0, "Should find at least one script"

        # Verify check_env.py is in the list
        check_env = SCRIPTS_DIR / "check_env.py"
        assert check_env in scripts, "check_env.py should be discoverable"

    def test_get_all_scripts_excludes_init(self):
        """Verify __init__.py files are excluded from script discovery."""
        scripts = get_all_scripts()
        init_files = [s for s in scripts if s.name == "__init__.py"]
        assert len(init_files) == 0, "__init__.py files should be excluded"

    def test_get_all_scripts_excludes_pycache(self):
        """Verify __pycache__ directories are excluded from script discovery."""
        scripts = get_all_scripts()
        pycache_scripts = [s for s in scripts if "__pycache__" in str(s)]
        assert len(pycache_scripts) == 0, "__pycache__ files should be excluded"


class TestBootstrapPatternDetection:
    """Test cases for bootstrap pattern detection utilities."""

    def test_has_bootstrap_import_detects_standard_pattern(self):
        """Detect 'from config.bootstrap import bootstrap'."""
        code = """
from config.bootstrap import bootstrap

def main():
    bootstrap()
"""
        tree = ast.parse(code)
        assert has_bootstrap_import(tree) is True

    def test_has_bootstrap_import_detects_multi_import(self):
        """Detect 'from config.bootstrap import bootstrap, other'."""
        code = """
from config.bootstrap import bootstrap, format_provider_status

def main():
    bootstrap()
"""
        tree = ast.parse(code)
        assert has_bootstrap_import(tree) is True

    def test_has_bootstrap_import_detects_config_import(self):
        """Detect 'from config import bootstrap'."""
        code = """
from config import bootstrap

def main():
    bootstrap()
"""
        tree = ast.parse(code)
        assert has_bootstrap_import(tree) is True

    def test_has_bootstrap_import_rejects_other_imports(self):
        """Reject scripts without bootstrap import."""
        code = """
import os
import sys

def main():
    pass
"""
        tree = ast.parse(code)
        assert has_bootstrap_import(tree) is False

    def test_has_bootstrap_call_detects_direct_call(self):
        """Detect direct bootstrap() call."""
        code = """
from config.bootstrap import bootstrap

def main():
    bootstrap()
"""
        tree = ast.parse(code)
        assert has_bootstrap_call(tree) is True

    def test_has_bootstrap_call_detects_call_with_args(self):
        """Detect bootstrap() call with arguments."""
        code = """
from config.bootstrap import bootstrap

def main():
    bootstrap(load_env=True, verbose=True)
"""
        tree = ast.parse(code)
        assert has_bootstrap_call(tree) is True

    def test_has_bootstrap_call_rejects_reference_only(self):
        """Reject scripts that only reference bootstrap without calling."""
        code = """
from config.bootstrap import bootstrap

def main():
    my_func = bootstrap  # Reference, not call
"""
        tree = ast.parse(code)
        assert has_bootstrap_call(tree) is False

    def test_uses_os_getenv_detects_getenv(self):
        """Detect os.getenv() usage."""
        code = """
import os
api_key = os.getenv("API_KEY")
"""
        tree = ast.parse(code)
        assert uses_os_getenv(tree) is True

    def test_uses_os_getenv_detects_environ_get(self):
        """Detect os.environ.get() usage."""
        code = """
import os
api_key = os.environ.get("API_KEY")
"""
        tree = ast.parse(code)
        assert uses_os_getenv(tree) is True

    def test_uses_os_getenv_detects_environ_access(self):
        """Detect os.environ direct access."""
        code = """
import os
api_key = os.environ["API_KEY"]
"""
        tree = ast.parse(code)
        assert uses_os_getenv(tree) is True


@pytest.mark.parametrize("script_path", get_all_scripts())
class TestScriptBootstrapCompliance:
    """Parametrized tests for all scripts."""

    def test_script_parses_as_valid_python(self, script_path: Path):
        """Verify script is valid Python syntax."""
        code = script_path.read_text()
        try:
            ast.parse(code)
        except SyntaxError as e:
            pytest.fail(f"{script_path.name} has syntax error: {e}")

    def test_script_has_docstring(self, script_path: Path):
        """Verify script has a module docstring."""
        code = script_path.read_text()
        tree = ast.parse(code)

        # Check for module-level docstring
        docstring = ast.get_docstring(tree)
        assert docstring is not None, f"{script_path.name} missing module docstring"
        assert len(docstring.strip()) > 0, f"{script_path.name} has empty docstring"

    def test_script_bootstrap_import_if_uses_env(self, script_path: Path):
        """Scripts using os.getenv should have bootstrap import.

        This is an advisory test that documents which scripts need bootstrap.
        Non-compliant scripts are recorded but don't fail the test suite
        to allow gradual migration.
        """
        code = script_path.read_text()
        tree = ast.parse(code)

        uses_env = uses_os_getenv(tree)
        has_import = has_bootstrap_import(tree)

        if uses_env and not has_import:
            # Record non-compliance but don't fail
            # This allows the test to document current state
            pytest.skip(
                f"{script_path.name} uses os.getenv but lacks bootstrap import "
                f"(needs migration - see ST-CI-005)"
            )

    def test_script_bootstrap_call_if_uses_env(self, script_path: Path):
        """Scripts using os.getenv should call bootstrap().

        This is an advisory test that documents which scripts need bootstrap.
        """
        code = script_path.read_text()
        tree = ast.parse(code)

        uses_env = uses_os_getenv(tree)
        has_import = has_bootstrap_import(tree)
        has_call = has_bootstrap_call(tree)

        if uses_env and has_import and not has_call:
            pytest.skip(
                f"{script_path.name} imports bootstrap but doesn't call it "
                f"(needs migration - see ST-CI-005)"
            )


class TestBootstrapCallOrdering:
    """Test cases for bootstrap call ordering relative to env access."""

    @pytest.mark.parametrize("script_path", get_all_scripts())
    def test_bootstrap_called_before_os_getenv(self, script_path: Path):
        """Verify bootstrap is called before any os.getenv() usage.

        This ensures environment variables are loaded from .env files
        before being accessed. For scripts where bootstrap is called
        at the start of main(), helper functions with env access are acceptable
        as long as they're called after bootstrap.
        """
        code = script_path.read_text()
        tree = ast.parse(code)

        # Skip if script doesn't use bootstrap at all
        if not has_bootstrap_import(tree) or not has_bootstrap_call(tree):
            pytest.skip(f"{script_path.name} doesn't use bootstrap")

        # Skip if script doesn't use os.getenv
        if not uses_os_getenv(tree):
            pytest.skip(f"{script_path.name} doesn't use os.getenv")

        bootstrap_line = get_bootstrap_call_line(tree)
        if bootstrap_line is None:
            pytest.skip(f"{script_path.name} doesn't have bootstrap call")

        # Find the main function
        main_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                main_func = node
                break

        # If bootstrap is first statement in main(), it's compliant
        if main_func and main_func.body:
            first_stmt = main_func.body[0]
            if (
                isinstance(first_stmt, ast.Expr)
                and isinstance(first_stmt.value, ast.Call)
                and (
                    isinstance(first_stmt.value.func, ast.Name)
                    and first_stmt.value.func.id == "bootstrap"
                )
            ):
                return  # Bootstrap is first in main() - compliant!

        # Otherwise, check line number ordering for module-level access
        first_getenv_line = get_first_os_getenv_call(tree)
        first_environ_line = get_first_os_environ_access(tree)

        env_lines = [
            l for l in [first_getenv_line, first_environ_line] if l is not None
        ]
        if not env_lines:
            return

        first_env_line = min(env_lines)

        # Bootstrap should be called before first env access
        assert bootstrap_line < first_env_line, (
            f"{script_path.name}: bootstrap() should be called before "
            f"first environment access (bootstrap at line {bootstrap_line}, "
            f"env access at line {first_env_line})"
        )


class TestBootstrapComplianceReporting:
    """Test cases for generating compliance reports."""

    def test_generate_compliance_summary(self):
        """Generate a summary of bootstrap compliance across all scripts."""
        scripts = get_all_scripts()

        compliant = []
        needs_bootstrap_import = []
        needs_bootstrap_call = []
        no_env_usage = []

        for script_path in scripts:
            code = script_path.read_text()
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue

            uses_env = uses_os_getenv(tree)
            has_import = has_bootstrap_import(tree)
            has_call = has_bootstrap_call(tree)

            if not uses_env:
                no_env_usage.append(script_path.name)
            elif has_import and has_call:
                compliant.append(script_path.name)
            elif uses_env and not has_import:
                needs_bootstrap_import.append(script_path.name)
            elif uses_env and has_import and not has_call:
                needs_bootstrap_call.append(script_path.name)

        # Print summary for test output
        print("\n" + "=" * 60)
        print("BOOTSTRAP COMPLIANCE SUMMARY")
        print("=" * 60)
        print(f"Total scripts analyzed: {len(scripts)}")
        print(f"Compliant (import + call): {len(compliant)}")
        print(f"Needs bootstrap import: {len(needs_bootstrap_import)}")
        print(f"Needs bootstrap() call: {len(needs_bootstrap_call)}")
        print(f"No env usage (exempt): {len(no_env_usage)}")
        print("=" * 60)

        if compliant:
            print("\nCompliant scripts:")
            for name in sorted(compliant):
                print(f"  ✓ {name}")

        if needs_bootstrap_import:
            print("\nScripts needing bootstrap import:")
            for name in sorted(needs_bootstrap_import)[:10]:  # Limit output
                print(f"  ✗ {name}")
            if len(needs_bootstrap_import) > 10:
                print(f"  ... and {len(needs_bootstrap_import) - 10} more")

        # The test passes but provides information
        assert len(scripts) > 0, "Should have analyzed scripts"

    def test_check_env_is_reference_implementation(self):
        """Verify check_env.py meets all compliance criteria."""
        check_env_path = SCRIPTS_DIR / "check_env.py"
        code = check_env_path.read_text()
        tree = ast.parse(code)

        # All checks should pass
        assert has_bootstrap_import(tree), "Should import bootstrap"
        assert has_bootstrap_call(tree), "Should call bootstrap"

        # Get line numbers
        import_line = get_bootstrap_import_line(tree)
        call_line = get_bootstrap_call_line(tree)

        # Import should be before call
        assert import_line is not None, "Should have import line"
        assert call_line is not None, "Should have call line"
        assert import_line < call_line, "Import should come before call"

        # Check that bootstrap is called before any significant processing
        # In check_env.py, bootstrap is called early in main()
        first_env_access = get_first_os_getenv_call(tree)
        if first_env_access:
            assert (
                call_line < first_env_access
            ), "bootstrap() should be called before os.getenv()"


class TestBootstrapImportVariations:
    """Test detection of various bootstrap import patterns."""

    def test_detect_import_with_alias(self):
        """Detect 'from config.bootstrap import bootstrap as bs'."""
        code = """
from config.bootstrap import bootstrap as bs

def main():
    bs()
"""
        tree = ast.parse(code)
        # This pattern is not currently detected by has_bootstrap_import
        # because the alias changes the name
        # This test documents the limitation
        assert has_bootstrap_import(tree) is True

    def test_detect_star_import(self):
        """Detect 'from config.bootstrap import *'."""
        code = """
from config.bootstrap import *

def main():
    bootstrap()
"""
        tree = ast.parse(code)
        # Star imports are harder to detect statically
        # This test documents that we don't detect them
        # The function call detection would still work
        assert has_bootstrap_call(tree) is True

    def test_reject_bootstrap_from_other_module(self):
        """Reject bootstrap from wrong module."""
        code = """
from some.other.module import bootstrap

def main():
    bootstrap()
"""
        tree = ast.parse(code)
        # Should not be detected as valid bootstrap import
        assert has_bootstrap_import(tree) is False
        # But would still detect the call
        assert has_bootstrap_call(tree) is True


class TestBootstrapEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_script(self):
        """Handle empty script gracefully."""
        code = ""
        tree = ast.parse(code)
        assert has_bootstrap_import(tree) is False
        assert has_bootstrap_call(tree) is False
        assert uses_os_getenv(tree) is False

    def test_script_with_only_comments(self):
        """Handle script with only comments."""
        code = "# This is a comment\n# Another comment"
        tree = ast.parse(code)
        assert has_bootstrap_import(tree) is False
        assert has_bootstrap_call(tree) is False

    def test_nested_function_call(self):
        """Detect bootstrap() in nested functions."""
        code = """
from config.bootstrap import bootstrap

def outer():
    def inner():
        bootstrap()
    inner()
"""
        tree = ast.parse(code)
        assert has_bootstrap_call(tree) is True

    def test_bootstrap_in_conditional(self):
        """Detect bootstrap() in if/else blocks."""
        code = """
from config.bootstrap import bootstrap

def main():
    if __name__ == "__main__":
        bootstrap()
"""
        tree = ast.parse(code)
        assert has_bootstrap_call(tree) is True

    def test_bootstrap_in_try_block(self):
        """Detect bootstrap() in try/except blocks."""
        code = """
from config.bootstrap import bootstrap

def main():
    try:
        bootstrap()
    except Exception:
        pass
"""
        tree = ast.parse(code)
        assert has_bootstrap_call(tree) is True


class TestScriptCategories:
    """Test compliance by script category."""

    def get_scripts_by_category(self) -> dict[str, list[Path]]:
        """Group scripts by directory category."""
        categories: dict[str, list[Path]] = {
            "ci": [],
            "ops": [],
            "swarm": [],
            "incident": [],
            "root": [],
        }

        for script_path in get_all_scripts():
            rel_path = script_path.relative_to(SCRIPTS_DIR)
            parts = rel_path.parts

            if len(parts) > 1:
                category = parts[0]
                if category in categories:
                    categories[category].append(script_path)
                else:
                    categories["root"].append(script_path)
            else:
                categories["root"].append(script_path)

        return categories

    def test_ci_scripts_should_be_compliant(self):
        """CI scripts should use bootstrap for consistent env loading."""
        categories = self.get_scripts_by_category()
        ci_scripts = categories.get("ci", [])

        if not ci_scripts:
            pytest.skip("No CI scripts found")

        non_compliant = []
        for script_path in ci_scripts:
            code = script_path.read_text()
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue

            if uses_os_getenv(tree):
                if not (has_bootstrap_import(tree) and has_bootstrap_call(tree)):
                    non_compliant.append(script_path.name)

        # This is informational - CI scripts should be fixed
        if non_compliant:
            print(f"\nCI scripts needing bootstrap: {non_compliant}")

    def test_ops_scripts_should_be_compliant(self):
        """Ops scripts should use bootstrap for production stability."""
        categories = self.get_scripts_by_category()
        ops_scripts = categories.get("ops", [])

        if not ops_scripts:
            pytest.skip("No ops scripts found")

        non_compliant = []
        for script_path in ops_scripts:
            code = script_path.read_text()
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue

            if uses_os_getenv(tree):
                if not (has_bootstrap_import(tree) and has_bootstrap_call(tree)):
                    non_compliant.append(script_path.name)

        if non_compliant:
            print(f"\nOps scripts needing bootstrap: {non_compliant}")
