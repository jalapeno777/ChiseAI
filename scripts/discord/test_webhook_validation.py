#!/usr/bin/env python3
"""Test script for webhook validation functionality.

This script tests the startup webhook validation without requiring actual webhooks.

Usage:
    python test_webhook_validation.py              # Run all tests
    python test_webhook_validation.py --verbose    # Show detailed output

Exit codes:
    0 - All tests passed
    1 - One or more tests failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.discord.startup_webhook_check import (
    WebhookValidationResult,
    WebhookValidator,
    format_results_json,
    format_results_text,
    get_configured_webhooks,
)


class WebhookValidationTest:
    """Test suite for webhook validation functionality."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.tests_run = 0
        self.tests_passed = 0
        self.errors = []

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def test_url_format_validation(self) -> bool:
        """Test URL format validation."""
        self.tests_run += 1
        test_name = "URL Format Validation"

        try:
            validator = WebhookValidator()

            # Valid URL
            valid, error = validator.validate_url_format(
                "https://discord.com/api/webhooks/123456/abcdef"
            )
            if not valid:
                self.errors.append(f"{test_name}: Valid URL rejected")
                self.log(f"✗ {test_name} failed: Valid URL rejected")
                return False

            # Invalid URL - wrong domain
            valid, error = validator.validate_url_format(
                "https://example.com/api/webhooks/123456/abcdef"
            )
            if valid:
                self.errors.append(f"{test_name}: Invalid URL accepted")
                self.log(f"✗ {test_name} failed: Invalid URL accepted")
                return False

            # Invalid URL - not HTTPS
            valid, error = validator.validate_url_format(
                "http://discord.com/api/webhooks/123456/abcdef"
            )
            if valid:
                self.errors.append(f"{test_name}: HTTP URL accepted")
                self.log(f"✗ {test_name} failed: HTTP URL accepted")
                return False

            # Empty URL
            valid, error = validator.validate_url_format("")
            if valid:
                self.errors.append(f"{test_name}: Empty URL accepted")
                self.log(f"✗ {test_name} failed: Empty URL accepted")
                return False

            self.tests_passed += 1
            self.log(f"✓ {test_name} passed")
            return True

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_validation_result_dataclass(self) -> bool:
        """Test the validation result dataclass."""
        self.tests_run += 1
        test_name = "Validation Result Dataclass"

        try:
            result = WebhookValidationResult(
                webhook_name="test",
                webhook_url="https://example.com",
                success=True,
                url_valid=True,
                http_status=204,
                response_time_ms=100.0,
            )

            # Check to_dict works
            data = result.to_dict()
            if data["webhook_name"] != "test":
                self.errors.append(f"{test_name}: to_dict failed")
                self.log(f"✗ {test_name} failed: to_dict failed")
                return False

            self.tests_passed += 1
            self.log(f"✓ {test_name} passed")
            return True

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_get_configured_webhooks(self) -> bool:
        """Test getting configured webhooks."""
        self.tests_run += 1
        test_name = "Get Configured Webhooks"

        try:
            # Test with explicit URL
            webhooks = get_configured_webhooks("https://example.com/webhook")
            if "explicit" not in webhooks:
                self.errors.append(f"{test_name}: Explicit URL not included")
                self.log(f"✗ {test_name} failed: Explicit URL not included")
                return False

            self.tests_passed += 1
            self.log(f"✓ {test_name} passed")
            return True

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_format_results(self) -> bool:
        """Test result formatting functions."""
        self.tests_run += 1
        test_name = "Format Results"

        try:
            results = [
                WebhookValidationResult(
                    webhook_name="test1",
                    webhook_url="https://example.com/1",
                    success=True,
                    url_valid=True,
                    http_status=204,
                    response_time_ms=100.0,
                ),
                WebhookValidationResult(
                    webhook_name="test2",
                    webhook_url="https://example.com/2",
                    success=False,
                    url_valid=False,
                    error_message="Invalid URL",
                ),
            ]

            # Test text format
            text_output = format_results_text(results)
            if "test1" not in text_output or "test2" not in text_output:
                self.errors.append(f"{test_name}: Text format missing webhooks")
                self.log(f"✗ {test_name} failed: Text format missing webhooks")
                return False

            # Test JSON format
            json_output = format_results_json(results)
            if '"webhook_name": "test1"' not in json_output:
                self.errors.append(f"{test_name}: JSON format incorrect")
                self.log(f"✗ {test_name} failed: JSON format incorrect")
                return False

            self.tests_passed += 1
            self.log(f"✓ {test_name} passed")
            return True

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_invalid_webhook_connectivity(self) -> bool:
        """Test connectivity check with invalid webhook."""
        self.tests_run += 1
        test_name = "Invalid Webhook Connectivity"

        try:
            validator = WebhookValidator(timeout_seconds=2.0)

            # Test with invalid URL format
            result = validator.validate_connectivity("not-a-valid-url", "Test message")

            if result.success:
                self.errors.append(f"{test_name}: Invalid URL succeeded")
                self.log(f"✗ {test_name} failed: Invalid URL succeeded")
                return False

            if result.url_valid:
                self.errors.append(f"{test_name}: URL marked as valid")
                self.log(f"✗ {test_name} failed: URL marked as valid")
                return False

            self.tests_passed += 1
            self.log(f"✓ {test_name} passed")
            return True

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def run_all_tests(self) -> bool:
        """Run all tests and return overall result."""
        print("=" * 60)
        print("Webhook Validation Test Suite")
        print("=" * 60)
        print()

        # Run tests
        self.test_url_format_validation()
        self.test_validation_result_dataclass()
        self.test_get_configured_webhooks()
        self.test_format_results()
        self.test_invalid_webhook_connectivity()

        # Print summary
        print()
        print("=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {self.tests_run - self.tests_passed}")

        if self.errors:
            print()
            print("Errors:")
            for error in self.errors:
                print(f"  - {error}")

        print()

        if self.tests_passed == self.tests_run:
            print("✓ All tests passed!")
            return True
        else:
            print("✗ Some tests failed")
            return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test webhook validation functionality"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    test_suite = WebhookValidationTest(verbose=args.verbose)
    all_passed = test_suite.run_all_tests()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
