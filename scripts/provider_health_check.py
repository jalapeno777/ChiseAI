#!/usr/bin/env python3
"""Provider Health Check Script

Tests all LLM providers and reports their status.
Shows which errors are occurring and provides specific remediation steps.
Can be run manually or in CI.

For LLM-PROVIDER-FIX-001: Provider endpoint and model fixes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config.env_loader import (
    diagnose_provider_availability,
    discover_kimi_config,
    discover_minimax_config,
    discover_zai_config,
    discover_zhipu_config,
)


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_header(title: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_status(provider: str, status: str, message: str = "") -> None:
    """Print a status line with color coding."""
    if status == "OK":
        status_color = Colors.GREEN
        icon = "✓"
    elif status == "FAIL":
        status_color = Colors.RED
        icon = "✗"
    elif status == "WARN":
        status_color = Colors.YELLOW
        icon = "⚠"
    else:
        status_color = Colors.CYAN
        icon = "ℹ"

    print(
        f"  {status_color}{icon}{Colors.RESET} {provider:15} {status_color}{status}{Colors.RESET}"
    )
    if message:
        print(f"      {message}")


def check_environment() -> dict[str, Any]:
    """Check environment configuration for all providers."""
    results = {
        "kimi": discover_kimi_config(),
        "zai": discover_zai_config(),
        "zhipu": discover_zhipu_config(),
        "minimax": discover_minimax_config(),
    }
    return results


async def test_kimi_connection() -> dict[str, Any]:
    """Test KIMI API connection."""
    from src.llm.kimi_client import KimiClient, KimiConfig

    config = discover_kimi_config()
    if not config["enabled"]:
        return {
            "status": "SKIP",
            "error": "KIMI_API_KEY not configured",
            "remediation": "Set KIMI_API_KEY environment variable",
        }

    try:
        async with KimiClient(KimiConfig()) as client:
            health = await client.health_check()

        if health["healthy"]:
            return {
                "status": "OK",
                "model": health.get("model", "unknown"),
                "message": "Connection successful",
            }
        else:
            error = health.get("error", "Unknown error")
            remediation = get_remediation("kimi", error)
            return {
                "status": "FAIL",
                "error": error,
                "remediation": remediation,
            }
    except Exception as e:
        error_msg = str(e)
        remediation = get_remediation("kimi", error_msg)
        return {
            "status": "FAIL",
            "error": error_msg,
            "remediation": remediation,
        }


async def test_zai_connection() -> dict[str, Any]:
    """Test Z.ai (Zhipu) API connection."""
    from src.llm.zai_client import ZaiClient, ZaiConfig

    config = discover_zai_config()
    if not config["enabled"]:
        return {
            "status": "SKIP",
            "error": "Z_AI_API_KEY not configured",
            "remediation": "Set Z_AI_API_KEY environment variable",
        }

    try:
        async with ZaiClient(ZaiConfig()) as client:
            health = await client.health_check()

        if health["healthy"]:
            return {
                "status": "OK",
                "model": health.get("model", "unknown"),
                "message": "Connection successful",
            }
        else:
            error = health.get("error", "Unknown error")
            remediation = get_remediation("zai", error)
            return {
                "status": "FAIL",
                "error": error,
                "remediation": remediation,
            }
    except Exception as e:
        error_msg = str(e)
        remediation = get_remediation("zai", error_msg)
        return {
            "status": "FAIL",
            "error": error_msg,
            "remediation": remediation,
        }


async def test_zhipu_connection() -> dict[str, Any]:
    """Test Zhipu API connection."""
    from src.llm.zhipu_client import ZhipuClient

    config = discover_zhipu_config()
    if not config["enabled"]:
        return {
            "status": "SKIP",
            "error": "ZHIPU_API_KEY not configured",
            "remediation": "Set ZHIPU_API_KEY environment variable",
        }

    try:
        client = ZhipuClient()
        is_healthy = client.health_check()

        if is_healthy:
            return {
                "status": "OK",
                "model": config.get("model", "glm-5"),
                "message": "Connection successful",
            }
        else:
            return {
                "status": "FAIL",
                "error": "Health check failed",
                "remediation": "Check API key and endpoint configuration",
            }
    except Exception as e:
        error_msg = str(e)
        remediation = get_remediation("zhipu", error_msg)
        return {
            "status": "FAIL",
            "error": error_msg,
            "remediation": remediation,
        }


def get_remediation(provider: str, error: str) -> str:
    """Get specific remediation steps based on error."""
    error_lower = error.lower()

    # KIMI-specific errors
    if provider == "kimi":
        if "coding agent" in error_lower or "only available" in error_lower:
            return (
                "The KIMI API key requires Coding Agent access. "
                "This is a special access tier. Consider:\n"
                "  1. Using the standard Moonshot API endpoint (https://api.moonshot.cn/v1)\n"
                "  2. Contacting Moonshot support for Coding Agent access\n"
                "  3. Using Z.ai/Zhipu as fallback provider"
            )
        if "401" in error or "authentication" in error_lower:
            return (
                "Invalid API key. Check:\n"
                "  1. KIMI_API_KEY is set correctly\n"
                "  2. Key has not expired\n"
                "  3. Key has not been revoked"
            )
        if "429" in error or "rate limit" in error_lower:
            return (
                "Rate limit exceeded. Solutions:\n"
                "  1. Wait before retrying\n"
                "  2. Reduce request frequency\n"
                "  3. Upgrade your API plan"
            )

    # Z.ai/Zhipu-specific errors
    if provider in ("zai", "zhipu"):
        if (
            "insufficient balance" in error_lower
            or "no resource package" in error_lower
        ):
            return (
                "Account has insufficient balance. Solutions:\n"
                "  1. Add credits to your Z.ai account at https://www.z.ai/\n"
                "  2. Purchase a resource package\n"
                "  3. Use KIMI as primary provider instead"
            )
        if "401" in error or "authentication" in error_lower:
            return (
                "Invalid API key. Check:\n"
                "  1. ZHIPU_API_KEY or Z_AI_API_KEY is set correctly\n"
                "  2. Key has not expired\n"
                "  3. Key has not been revoked"
            )
        if "429" in error or "rate limit" in error_lower:
            return (
                "Rate limit exceeded. Solutions:\n"
                "  1. Wait before retrying\n"
                "  2. Reduce request frequency\n"
                "  3. Check your quota at https://open.bigmodel.cn/"
            )

    # Generic errors
    if "connection" in error_lower or "network" in error_lower:
        return (
            "Network connectivity issue. Check:\n"
            "  1. Internet connection\n"
            "  2. Firewall settings\n"
            "  3. DNS resolution"
        )
    if "timeout" in error_lower:
        return (
            "Request timed out. Solutions:\n"
            "  1. Retry the request\n"
            "  2. Check provider status page\n"
            "  3. Increase timeout settings"
        )

    return "Check provider documentation and API key configuration"


async def run_all_tests() -> dict[str, Any]:
    """Run all provider tests."""
    results = {
        "environment": check_environment(),
        "connections": {},
    }

    # Run connection tests concurrently
    connection_tests = {
        "kimi": test_kimi_connection(),
        "zai": test_zai_connection(),
        "zhipu": test_zhipu_connection(),
    }

    results["connections"] = {
        name: await test for name, test in connection_tests.items()
    }

    return results


def print_results(results: dict[str, Any]) -> None:
    """Print formatted test results."""
    print_header("LLM Provider Health Check")

    # Environment Configuration
    print(f"{Colors.BOLD}Environment Configuration:{Colors.RESET}")
    for provider, config in results["environment"].items():
        status = "OK" if config["enabled"] else "SKIP"
        message = (
            f"Model: {config.get('model', 'N/A')}, URL: {config.get('base_url', 'N/A')}"
        )
        if not config["enabled"]:
            message = config.get("reason", "API key not configured")
        print_status(provider.upper(), status, message)

    # Connection Tests
    print(f"\n{Colors.BOLD}Connection Tests:{Colors.RESET}")
    for provider, result in results["connections"].items():
        status = result["status"]
        if status == "OK":
            message = f"{result.get('message', 'Success')} - Model: {result.get('model', 'N/A')}"
        elif status == "SKIP":
            message = result.get("error", "Not configured")
        else:
            message = result.get("error", "Unknown error")

        print_status(provider.upper(), status, message)

        # Print remediation for failures
        if status == "FAIL" and "remediation" in result:
            print(f"\n  {Colors.YELLOW}Remediation:{Colors.RESET}")
            for line in result["remediation"].split("\n"):
                print(f"    {line}")
            print()


def print_summary(results: dict[str, Any]) -> int:
    """Print summary and return exit code."""
    print_header("Summary")

    total = len(results["connections"])
    ok = sum(1 for r in results["connections"].values() if r["status"] == "OK")
    failed = sum(1 for r in results["connections"].values() if r["status"] == "FAIL")
    skipped = sum(1 for r in results["connections"].values() if r["status"] == "SKIP")

    print(f"  Total providers: {total}")
    print(f"  {Colors.GREEN}✓ Working:{Colors.RESET} {ok}")
    print(f"  {Colors.RED}✗ Failed:{Colors.RESET} {failed}")
    print(f"  {Colors.YELLOW}⚠ Skipped:{Colors.RESET} {skipped}")

    # Recommendations
    print(f"\n{Colors.BOLD}Recommendations:{Colors.RESET}")
    if ok == 0:
        print(
            f"  {Colors.RED}No providers are working!{Colors.RESET} "
            "Check your API keys and network connectivity."
        )
    elif ok == 1:
        print(
            f"  {Colors.YELLOW}Only one provider working.{Colors.RESET} "
            "Consider configuring additional providers for fallback."
        )
    else:
        print(
            f"  {Colors.GREEN}Multiple providers available.{Colors.RESET} "
            "Fallback chain is properly configured."
        )

    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")

    return 0 if failed == 0 else 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check LLM provider health and configuration"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show errors",
    )
    args = parser.parse_args()

    # Run tests
    results = asyncio.run(run_all_tests())

    if args.json:
        print(json.dumps(results, indent=2))
        return (
            0
            if all(r["status"] != "FAIL" for r in results["connections"].values())
            else 1
        )

    if not args.quiet:
        print_results(results)

    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
