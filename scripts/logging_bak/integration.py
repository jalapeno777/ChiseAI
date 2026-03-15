"""Integration module for paper trading logging and webhook validation.

This module provides integration points between:
- Paper trading checkpoint system (paper_checkpoint.py)
- Log rotation for paper trading logs
- Discord webhook validation

Usage:
    # In paper_checkpoint.py or startup scripts:
    from scripts.logging.integration import validate_startup_requirements

    result = validate_startup_requirements()
    if not result.success:
        sys.exit(1)
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add project root to path if needed
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.discord.startup_webhook_check import (
    WebhookValidator,
    get_configured_webhooks,
)
from scripts.logging.paper_log_rotation import get_paper_trading_logger


@dataclass
class StartupValidationResult:
    """Result of startup validation checks.

    Attributes:
        success: Whether all validations passed
        log_rotation_ready: Whether log rotation is configured
        webhook_valid: Whether webhook is reachable
        errors: List of error messages
        details: Additional details about the checks
    """

    success: bool = False
    log_rotation_ready: bool = False
    webhook_valid: bool = False
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def validate_log_rotation(
    log_dir: str = "logs/paper_trading",
) -> tuple[bool, dict[str, Any]]:
    """Validate that log rotation is properly configured.

    Args:
        log_dir: Directory for paper trading logs

    Returns:
        Tuple of (success, details)
    """
    details = {
        "log_dir": log_dir,
        "dir_exists": False,
        "can_write": False,
        "logger_created": False,
    }

    try:
        log_path = Path(log_dir)

        # Check if directory exists or can be created
        log_path.mkdir(parents=True, exist_ok=True)
        details["dir_exists"] = True

        # Check if we can write to the directory
        test_file = log_path / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            details["can_write"] = True
        except Exception as e:
            details["write_error"] = str(e)
            return False, details

        # Try creating a logger
        try:
            logger = get_paper_trading_logger(
                name="startup_validation",
                log_dir=log_dir,
                level=logging.DEBUG,
            )
            logger.info("Log rotation validation test")
            details["logger_created"] = True
        except Exception as e:
            details["logger_error"] = str(e)
            return False, details

        return True, details

    except Exception as e:
        details["error"] = str(e)
        return False, details


def validate_webhook(timeout_seconds: float = 5.0) -> tuple[bool, dict[str, Any]]:
    """Validate that Discord webhook is configured and reachable.

    Args:
        timeout_seconds: Timeout for webhook validation

    Returns:
        Tuple of (success, details)
    """
    details = {
        "webhooks_found": 0,
        "webhooks_valid": 0,
        "results": [],
    }

    try:
        # Get configured webhooks
        webhooks = get_configured_webhooks()
        details["webhooks_found"] = len(webhooks)

        if not webhooks:
            details["error"] = "No webhooks configured"
            return False, details

        # Validate each webhook
        validator = WebhookValidator(timeout_seconds=timeout_seconds)

        for name, url in webhooks.items():
            result = validator.validate_connectivity(url, "Startup validation test")
            result.webhook_name = name

            details["results"].append(
                {
                    "name": name,
                    "url_valid": result.url_valid,
                    "success": result.success,
                    "response_time_ms": result.response_time_ms,
                    "error": result.error_message,
                }
            )

            if result.success:
                details["webhooks_valid"] += 1

        # Success if at least one webhook is valid
        return details["webhooks_valid"] > 0, details

    except Exception as e:
        details["error"] = str(e)
        return False, details


def validate_startup_requirements(
    log_dir: str = "logs/paper_trading",
    webhook_timeout: float = 5.0,
) -> StartupValidationResult:
    """Validate all startup requirements for paper trading.

    Performs:
    1. Log rotation configuration check
    2. Discord webhook validation

    Args:
        log_dir: Directory for paper trading logs
        webhook_timeout: Timeout for webhook validation

    Returns:
        StartupValidationResult with all check results
    """
    result = StartupValidationResult()

    # Validate log rotation
    log_ok, log_details = validate_log_rotation(log_dir)
    result.log_rotation_ready = log_ok
    result.details["log_rotation"] = log_details

    if not log_ok:
        result.errors.append(
            f"Log rotation not ready: {log_details.get('error', 'Unknown error')}"
        )

    # Validate webhook
    webhook_ok, webhook_details = validate_webhook(webhook_timeout)
    result.webhook_valid = webhook_ok
    result.details["webhook"] = webhook_details

    if not webhook_ok:
        result.errors.append(
            f"Webhook validation failed: {webhook_details.get('error', 'Unknown error')}"
        )

    # Overall success requires both
    result.success = log_ok and webhook_ok

    return result


def integration_check() -> int:
    """Run integration check and print results.

    Returns:
        Exit code (0 = success, 1 = validation failed)
    """
    print("=" * 60)
    print("Paper Trading Startup Validation")
    print("=" * 60)
    print()

    result = validate_startup_requirements()

    # Log rotation status
    print("Log Rotation:")
    log_details = result.details.get("log_rotation", {})
    if result.log_rotation_ready:
        print(f"  ✓ Directory ready: {log_details.get('log_dir')}")
        print(f"  ✓ Can write: {log_details.get('can_write')}")
        print(f"  ✓ Logger created: {log_details.get('logger_created')}")
    else:
        print(f"  ✗ Failed: {log_details.get('error', 'Unknown error')}")

    print()

    # Webhook status
    print("Discord Webhook:")
    webhook_details = result.details.get("webhook", {})
    print(f"  Webhooks found: {webhook_details.get('webhooks_found', 0)}")
    print(f"  Webhooks valid: {webhook_details.get('webhooks_valid', 0)}")

    for res in webhook_details.get("results", []):
        status = "✓" if res["success"] else "✗"
        print(f"  {status} {res['name']}: {res['response_time_ms']:.1f}ms")
        if res["error"]:
            print(f"      Error: {res['error']}")

    print()
    print("=" * 60)

    if result.success:
        print("✓ All startup validations passed")
        print("=" * 60)
        return 0
    else:
        print("✗ Startup validation failed")
        print()
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(integration_check())
