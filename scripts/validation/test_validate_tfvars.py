#!/usr/bin/env python3
"""Test cases for validate_tfvars.py"""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validate_tfvars import (
    check_file,
    fix_file,
    is_placeholder,
    looks_like_secret,
    parse_tfvars_line,
)


def test_is_placeholder():
    """Test placeholder detection"""
    print("Testing is_placeholder()...")

    # Should be detected as placeholders
    assert is_placeholder('"CHANGE_ME"')
    assert is_placeholder('"change-me"')
    assert is_placeholder('"change_me"')
    assert is_placeholder('"your-api-key"')
    assert is_placeholder('"your_token"')
    assert is_placeholder('"placeholder"')
    assert is_placeholder('"example"')
    assert is_placeholder('"dummy"')
    assert is_placeholder('"fake"')
    assert is_placeholder('"test-only"')
    assert is_placeholder('"replace-me"')
    assert is_placeholder('"insert-here"')
    assert is_placeholder('"todo"')
    assert is_placeholder('"xxx"')
    assert is_placeholder('"admin"')
    assert is_placeholder('"password"')
    assert is_placeholder('"secret"')
    assert is_placeholder('"token"')
    assert is_placeholder('""')
    assert is_placeholder("")

    # Should NOT be placeholders
    assert not is_placeholder('"e1df8c79-5252-4cca-9f02-ff9dfb50fb7f"')
    assert not is_placeholder('"REDACTED_WOODPECKER_DB_PASSWORD"')
    assert not is_placeholder('"sk-abc123xyz789"')

    print("✓ All placeholder tests passed")


def test_looks_like_secret():
    """Test secret detection"""
    print("\nTesting looks_like_secret()...")

    # Should be detected as secrets
    is_secret, reason = looks_like_secret('"e1df8c79-5252-4cca-9f02-ff9dfb50fb7f"')
    assert is_secret, f"UUID should be secret: {reason}"
    assert "UUID" in reason

    is_secret, reason = looks_like_secret('"REDACTED_WOODPECKER_DB_PASSWORD"')
    assert is_secret, f"Base64-like should be secret: {reason}"
    assert "base64" in reason.lower()

    is_secret, reason = looks_like_secret('"REDACTED_TAIGA_SECRET_KEY"')
    assert is_secret, f"Long high-entropy should be secret: {reason}"

    is_secret, reason = looks_like_secret('"REDACTED_TAIGA_DB_PASSWORD"')
    assert is_secret, f"Mixed-case alphanumeric should be secret: {reason}"

    # Should NOT be secrets
    is_secret, reason = looks_like_secret('"CHANGE_ME"')
    assert not is_secret, f"CHANGE_ME should not be secret: {reason}"

    is_secret, reason = looks_like_secret('"change-me"')
    assert not is_secret, f"change-me should not be secret: {reason}"

    is_secret, reason = looks_like_secret('""')
    assert not is_secret, f"Empty string should not be secret: {reason}"

    is_secret, reason = looks_like_secret('"admin"')
    assert not is_secret, f"admin should not be secret: {reason}"

    is_secret, reason = looks_like_secret('"admin123"')
    assert not is_secret, f"admin123 should not be secret: {reason}"

    print("✓ All secret detection tests passed")


def test_parse_tfvars_line():
    """Test line parsing"""
    print("\nTesting parse_tfvars_line()...")

    # Valid assignments
    result = parse_tfvars_line('var_name = "value"')
    assert result == ("var_name", '"value"'), f"Got {result}"

    result = parse_tfvars_line("var_name=value")
    assert result == ("var_name", "value"), f"Got {result}"

    result = parse_tfvars_line('  var_name   =   "value"  ')
    assert result == ("var_name", '"value"'), f"Got {result}"

    # Comments and empty lines
    assert parse_tfvars_line("# comment") is None
    assert parse_tfvars_line("") is None
    assert parse_tfvars_line("   ") is None

    print("✓ All line parsing tests passed")


def test_check_file():
    """Test file checking"""
    print("\nTesting check_file()...")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tfvars.template", delete=False
    ) as f:
        f.write('woodpecker_gitea_client = "e1df8c79-5252-4cca-9f02-ff9dfb50fb7f"\n')
        f.write('woodpecker_gitea_secret = "CHANGE_ME"\n')
        f.write("# This is a comment\n")
        f.write('influxdb_token = "YOUR_INFLUXDB_TOKEN_HERE"\n')
        f.write('grafana_admin_password = "admin123"\n')
        temp_path = Path(f.name)

    try:
        findings = check_file(temp_path)

        # Should find 1 secret (UUID only - YOUR_INFLUXDB_TOKEN_HERE is a placeholder)
        assert (
            len(findings) == 1
        ), f"Expected 1 finding (UUID only), got {len(findings)}: {findings}"

        # Check specific finding is the UUID on line 1
        line_nums = [f[0] for f in findings]
        assert 1 in line_nums, "Should find UUID secret on line 1"

        print("✓ File checking tests passed")
    finally:
        os.unlink(temp_path)


def test_fix_file():
    """Test file fixing"""
    print("\nTesting fix_file()...")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tfvars.template", delete=False
    ) as f:
        f.write('woodpecker_gitea_client = "e1df8c79-5252-4cca-9f02-ff9dfb50fb7f"\n')
        f.write('woodpecker_gitea_secret = "CHANGE_ME"\n')
        f.write('influxdb_token = "YOUR_INFLUXDB_TOKEN_HERE"\n')
        temp_path = Path(f.name)

    try:
        # Get findings first
        findings = check_file(temp_path)
        assert (
            len(findings) == 1
        ), f"Expected 1 finding (UUID only), got {len(findings)}: {findings}"

        # Fix the file
        replacements = fix_file(temp_path, findings)
        assert (
            replacements == 1
        ), f"Expected 1 replacement (UUID only), got {replacements}"

        # Verify file was fixed
        with open(temp_path) as f:
            content = f.read()

        assert "CHANGE_ME" in content
        assert "e1df8c79-5252-4cca-9f02-ff9dfb50fb7f" not in content
        assert (
            "YOUR_INFLUXDB_TOKEN_HERE" in content
        ), "Placeholder should be present after fix"

        # Verify no more secrets
        new_findings = check_file(temp_path)
        assert (
            len(new_findings) == 0
        ), f"Should have no findings after fix: {new_findings}"

        print("✓ File fixing tests passed")
    finally:
        os.unlink(temp_path)


def test_edge_cases():
    """Test edge cases"""
    print("\nTesting edge cases...")

    # Mixed case with numbers (high entropy)
    is_secret, reason = looks_like_secret('"AbCdEfGhIjKlMnOpQrStUvWxYz123456"')
    assert is_secret, f"Mixed case with numbers should be secret: {reason}"

    # Hex string
    is_secret, reason = looks_like_secret(
        '"a1b2c3d4e5f6789012345678901234567890abcdef"'
    )
    assert is_secret, f"Long hex should be secret: {reason}"

    # Short values should not be secrets
    is_secret, reason = looks_like_secret('"abc123"')
    assert not is_secret, f"Short value should not be secret: {reason}"

    # Values with special characters (not base64)
    is_secret, reason = looks_like_secret('"hello@world#123"')
    assert not is_secret, f"Value with special chars should not be secret: {reason}"

    # Test that admin123 is treated as placeholder (contains "admin")
    is_secret, reason = looks_like_secret('"admin123"')
    assert not is_secret, f"admin123 should be placeholder: {reason}"

    print("✓ Edge case tests passed")


if __name__ == "__main__":
    print("=" * 60)
    print("Running validate_tfvars.py tests")
    print("=" * 60)

    test_is_placeholder()
    test_looks_like_secret()
    test_parse_tfvars_line()
    test_check_file()
    test_fix_file()
    test_edge_cases()

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
