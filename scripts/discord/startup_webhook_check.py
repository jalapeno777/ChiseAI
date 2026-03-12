#!/usr/bin/env python3
"""Deterministic startup validation for Discord webhooks.

Validates that Discord webhook URLs are configured and reachable on application startup.
Provides exit codes for integration with init systems and health checks.

Usage:
    python startup_webhook_check.py                    # Check all configured webhooks
    python startup_webhook_check.py --webhook-url URL  # Check specific webhook
    python startup_webhook_check.py --test-message MSG # Use custom test message
    python startup_webhook_check.py --timeout 10       # Set timeout in seconds
    python startup_webhook_check.py --json             # Output JSON for programmatic use
    python startup_webhook_check.py --quiet            # Minimal output, just exit code

Exit codes:
    0 - All validations passed
    1 - Webhook validation failed (misconfigured or unreachable)
    2 - Invalid arguments or usage error
    3 - Rate limited (respect Retry-After header)
    4 - Network timeout

Environment variables:
    DISCORD_WEBHOOK_URL      - Primary webhook URL
    DISCORD_STANDUP_WEBHOOK  - Standup webhook URL
    DISCORD_ALERTS_WEBHOOK   - Alerts webhook URL
    WEBHOOK_TIMEOUT_SECONDS  - Default timeout (default: 5)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class WebhookValidationResult:
    """Result of a webhook validation check.

    Attributes:
        webhook_name: Descriptive name for the webhook
        webhook_url: The URL that was validated
        success: Whether validation passed
        url_valid: Whether URL format is valid
        http_status: HTTP response status code
        response_time_ms: Time taken for HTTP request in milliseconds
        rate_limited: Whether rate limit was hit
        retry_after: Seconds to wait before retry (if rate limited)
        error_message: Error description if validation failed
        timestamp: When the check was performed
    """

    webhook_name: str
    webhook_url: str
    success: bool = False
    url_valid: bool = False
    http_status: int | None = None
    response_time_ms: float = 0.0
    rate_limited: bool = False
    retry_after: float | None = None
    error_message: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class WebhookValidator:
    """Validates Discord webhook configuration and connectivity.

    Performs deterministic validation of webhook URLs including:
    - URL format validation (Discord webhook URL pattern)
    - HTTP connectivity check
    - Rate limit header inspection
    - Response time measurement

    Attributes:
        timeout_seconds: Maximum time to wait for HTTP response
        max_content_length: Maximum test message length
    """

    # Discord webhook URL pattern
    DISCORD_WEBHOOK_PATTERN = re.compile(
        r"^https://discord\.com/api/webhooks/\d+/[\w-]+$"
    )

    # Alternative Discord webhook domains (for compatibility)
    DISCORD_WEBHOOK_ALT_PATTERN = re.compile(
        r"^https://(discord\.com|discordapp\.com)/api/webhooks/\d+/[\w-]+$"
    )

    def __init__(self, timeout_seconds: float = 5.0):
        """Initialize the validator.

        Args:
            timeout_seconds: Maximum time to wait for HTTP response (default: 5.0)
        """
        self.timeout_seconds = timeout_seconds
        self.max_content_length = 2000  # Discord limit

    def validate_url_format(self, url: str) -> tuple[bool, str | None]:
        """Validate webhook URL format.

        Args:
            url: The webhook URL to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url:
            return False, "URL is empty"

        if not url.startswith("https://"):
            return False, "URL must use HTTPS"

        if self.DISCORD_WEBHOOK_ALT_PATTERN.match(url):
            return True, None

        # Check for common mistakes
        if "discord.com" not in url and "discordapp.com" not in url:
            return False, "URL is not a Discord webhook URL"

        if "/api/webhooks/" not in url:
            return False, "URL missing /api/webhooks/ path"

        return False, "URL does not match expected Discord webhook format"

    def validate_connectivity(
        self,
        url: str,
        test_message: str = "ChiseAI webhook startup validation test",
    ) -> WebhookValidationResult:
        """Validate webhook connectivity by sending a test message.

        Args:
            url: The webhook URL to test
            test_message: Message to send for validation

        Returns:
            WebhookValidationResult with validation details
        """
        result = WebhookValidationResult(
            webhook_name="webhook",
            webhook_url=url,
        )

        # Validate URL format
        url_valid, error = self.validate_url_format(url)
        result.url_valid = url_valid

        if not url_valid:
            result.error_message = error
            return result

        # Prepare test payload
        payload = json.dumps(
            {
                "content": test_message[: self.max_content_length],
                "username": "ChiseAI-WebhookValidator",
            }
        ).encode("utf-8")

        # Prepare request
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ChiseAI-StartupWebhookCheck/1.0",
            },
            method="POST",
        )

        # Send request and measure time
        start_time = time.perf_counter()

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                result.response_time_ms = (time.perf_counter() - start_time) * 1000
                result.http_status = resp.status

                # Check for rate limit headers
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    result.rate_limited = True
                    result.retry_after = float(retry_after)

                # Check if successful (Discord returns 204 No Content on success)
                if resp.status in (200, 204):
                    result.success = True
                elif resp.status == 429:
                    result.rate_limited = True
                    result.error_message = f"Rate limited (HTTP {resp.status})"
                    if not result.retry_after:
                        result.retry_after = 5.0  # Default retry after
                else:
                    result.error_message = f"Unexpected HTTP status: {resp.status}"

        except urllib.error.HTTPError as e:
            result.response_time_ms = (time.perf_counter() - start_time) * 1000
            result.http_status = e.code

            if e.code == 429:
                result.rate_limited = True
                retry_after = e.headers.get("Retry-After", "5")
                result.retry_after = float(retry_after)
                result.error_message = f"Rate limited, retry after {retry_after}s"
            elif e.code in (401, 403, 404):
                result.error_message = f"Invalid webhook (HTTP {e.code})"
            else:
                result.error_message = f"HTTP error: {e.code}"

        except urllib.error.URLError as e:
            result.response_time_ms = (time.perf_counter() - start_time) * 1000
            result.error_message = f"Connection error: {e.reason}"

        except TimeoutError:
            result.response_time_ms = self.timeout_seconds * 1000
            result.error_message = f"Timeout after {self.timeout_seconds}s"

        except Exception as e:
            result.response_time_ms = (time.perf_counter() - start_time) * 1000
            result.error_message = f"Unexpected error: {e}"

        return result

    def validate_all_webhooks(
        self,
        webhooks: dict[str, str],
        test_message: str = "ChiseAI webhook startup validation test",
    ) -> list[WebhookValidationResult]:
        """Validate multiple webhooks.

        Args:
            webhooks: Dictionary mapping webhook names to URLs
            test_message: Message to send for validation

        Returns:
            List of validation results
        """
        results = []

        for name, url in webhooks.items():
            result = self.validate_connectivity(url, test_message)
            result.webhook_name = name
            results.append(result)

            # Respect rate limits between requests
            if result.rate_limited and result.retry_after:
                time.sleep(min(result.retry_after, 5.0))

        return results


def get_configured_webhooks(explicit_url: str | None = None) -> dict[str, str]:
    """Get all configured webhook URLs from environment.

    Args:
        explicit_url: Optional explicit webhook URL to include

    Returns:
        Dictionary mapping webhook names to URLs
    """
    webhooks = {}

    # Add explicit URL if provided
    if explicit_url:
        webhooks["explicit"] = explicit_url

    # Check environment variables
    env_vars = [
        ("primary", "DISCORD_WEBHOOK_URL"),
        ("standup", "DISCORD_STANDUP_WEBHOOK"),
        ("alerts", "DISCORD_ALERTS_WEBHOOK"),
        ("chise", "CHISE_DISCORD_WEBHOOK_URL"),
    ]

    for name, var in env_vars:
        value = os.getenv(var)
        if value:
            webhooks[name] = value

    return webhooks


def format_results_text(results: list[WebhookValidationResult]) -> str:
    """Format validation results as human-readable text.

    Args:
        results: List of validation results

    Returns:
        Formatted text output
    """
    lines = [
        "=" * 60,
        "Discord Webhook Startup Validation",
        "=" * 60,
        f"Timestamp: {datetime.now(UTC).isoformat()}",
        "",
    ]

    all_passed = True

    for result in results:
        status = "✅ PASS" if result.success else "❌ FAIL"
        lines.append(f"\n{status} - {result.webhook_name}")
        lines.append(f"  URL valid: {'Yes' if result.url_valid else 'No'}")

        if result.http_status:
            lines.append(f"  HTTP status: {result.http_status}")

        lines.append(f"  Response time: {result.response_time_ms:.2f}ms")

        if result.rate_limited:
            lines.append(f"  Rate limited: Yes (retry after {result.retry_after}s)")

        if result.error_message:
            lines.append(f"  Error: {result.error_message}")
            all_passed = False
        elif not result.success:
            all_passed = False

    lines.extend(
        [
            "",
            "=" * 60,
            f"Overall: {'✅ All passed' if all_passed else '❌ Some failed'}",
            "=" * 60,
        ]
    )

    return "\n".join(lines)


def format_results_json(results: list[WebhookValidationResult]) -> str:
    """Format validation results as JSON.

    Args:
        results: List of validation results

    Returns:
        JSON string
    """
    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "results": [r.to_dict() for r in results],
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "rate_limited": sum(1 for r in results if r.rate_limited),
        },
    }
    return json.dumps(data, indent=2)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = success, 1 = validation failed, 2 = usage error,
                  3 = rate limited, 4 = timeout)
    """
    parser = argparse.ArgumentParser(
        description="Validate Discord webhook configuration on startup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Check all configured webhooks
  %(prog)s --webhook-url URL                  # Check specific webhook
  %(prog)s --test-message "Custom message"    # Use custom test message
  %(prog)s --timeout 10                       # Set 10 second timeout
  %(prog)s --json                             # Output JSON format
  %(prog)s --quiet                            # Minimal output, exit code only

Environment variables:
  DISCORD_WEBHOOK_URL      - Primary webhook URL
  DISCORD_STANDUP_WEBHOOK  - Standup webhook URL
  DISCORD_ALERTS_WEBHOOK   - Alerts webhook URL
  WEBHOOK_TIMEOUT_SECONDS  - Default timeout

Exit codes:
  0 - All validations passed
  1 - Webhook validation failed
  2 - Invalid arguments
  3 - Rate limited
  4 - Network timeout
        """,
    )

    parser.add_argument(
        "--webhook-url",
        help="Specific webhook URL to validate (overrides environment)",
    )
    parser.add_argument(
        "--test-message",
        default="ChiseAI webhook startup validation test",
        help="Test message to send (default: startup validation test)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "5")),
        help="Timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format for programmatic use",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output, exit code only",
    )

    args = parser.parse_args()

    # Validate timeout
    if args.timeout <= 0 or args.timeout > 60:
        if not args.quiet:
            print("Error: Timeout must be between 0.1 and 60 seconds", file=sys.stderr)
        return 2

    # Get webhooks to validate
    webhooks = get_configured_webhooks(args.webhook_url)

    if not webhooks:
        if not args.quiet:
            print("Error: No webhook URLs configured", file=sys.stderr)
            print("Set DISCORD_WEBHOOK_URL or use --webhook-url", file=sys.stderr)
        return 2

    # Validate webhooks
    validator = WebhookValidator(timeout_seconds=args.timeout)
    results = validator.validate_all_webhooks(webhooks, args.test_message)

    # Output results
    if args.json:
        print(format_results_json(results))
    elif not args.quiet:
        print(format_results_text(results))

    # Determine exit code
    all_passed = all(r.success for r in results)
    any_rate_limited = any(r.rate_limited for r in results)
    any_timeout = any(
        r.error_message and "timeout" in r.error_message.lower() for r in results
    )

    if all_passed:
        return 0
    elif any_timeout:
        return 4
    elif any_rate_limited:
        return 3
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
