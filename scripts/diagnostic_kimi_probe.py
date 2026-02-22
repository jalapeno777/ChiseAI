#!/usr/bin/env python3
"""KIMI API Authentication and Model Access Diagnostic Probe.

This script performs comprehensive diagnostics on KIMI API connectivity:
1. Verifies API key loading from environment
2. Tests /models endpoint connectivity
3. Tests /chat/completions endpoint with minimal request
4. Captures latency, status codes, and errors
5. Produces structured JSON output with root cause analysis

Usage:
    python scripts/diagnostic_kimi_probe.py

Output:
    - JSON to stdout
    - Evidence file at _bmad-output/kimi_probe_<timestamp>.json

For: CH-KIMI-DIAG-001
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first (must be before any env access)
bootstrap(load_env=True)

from config.env_loader import load_kimi_config


class KimiDiagnosticProbe:
    """Diagnostic probe for KIMI API authentication and model access."""

    # KIMI API endpoints
    MODELS_URL = "https://api.kimi.com/coding/v1/models"
    CHAT_COMPLETIONS_URL = "https://api.kimi.com/coding/v1/chat/completions"

    # Root cause matrix mappings
    ROOT_CAUSE_MAP = {
        401: (
            "auth",
            "Invalid or expired API key. Check KIMI_API_KEY environment variable.",
        ),
        403: (
            "scope",
            "Insufficient permissions or scope. Verify API key has required access.",
        ),
        404: (
            "model",
            "Endpoint or model not found. Verify URL and model ID are correct.",
        ),
        429: (
            "rate_limit",
            "Rate limit exceeded. Wait and retry with exponential backoff.",
        ),
    }

    def __init__(self) -> None:
        """Initialize the diagnostic probe."""
        self.probe_id = str(uuid.uuid4())[:12]
        self.timestamp = datetime.now(UTC)
        self.api_key: str | None = None
        self.config: dict[str, Any] = {}

        # Results storage
        self.results = {
            "probe_id": self.probe_id,
            "timestamp": self.timestamp.isoformat(),
            "kimi_api_key_loaded": False,
            "models_endpoint": {
                "url": self.MODELS_URL,
                "status_code": None,
                "success": False,
                "models_available": [],
                "error": None,
                "latency_ms": None,
                "headers": {},
            },
            "chat_completions_endpoint": {
                "url": self.CHAT_COMPLETIONS_URL,
                "model_used": None,
                "status_code": None,
                "success": False,
                "latency_ms": None,
                "response_preview": None,
                "error": None,
                "headers": {},
            },
            "root_cause_matrix": {
                "primary_issue": "none",
                "recommendation": "All tests passed successfully",
            },
        }

    async def run(self) -> dict[str, Any]:
        """Run all diagnostic tests.

        Returns:
            Dictionary with complete diagnostic results
        """
        logger.info("=" * 70)
        logger.info("KIMI API DIAGNOSTIC PROBE")
        logger.info("=" * 70)
        logger.info(f"Probe ID: {self.probe_id}")
        logger.info(f"Timestamp: {self.timestamp.isoformat()}")
        logger.info("")

        # Step 1: Load configuration and API key
        self._step1_load_config()

        # Step 2: Test /models endpoint
        await self._step2_test_models_endpoint()

        # Step 3: Test /chat/completions endpoint
        await self._step3_test_chat_completions()

        # Step 4: Analyze root cause if failures occurred
        self._step4_root_cause_analysis()

        # Step 5: Save evidence and return
        return await self._step5_save_and_report()

    def _step1_load_config(self) -> None:
        """Step 1: Load KIMI configuration and API key."""
        logger.info("-" * 70)
        logger.info("STEP 1: Loading KIMI Configuration")
        logger.info("-" * 70)

        try:
            self.config = load_kimi_config()
            self.api_key = self.config.get("api_key")

            if self.api_key:
                # Mask API key for logging (show first 8 and last 4 chars)
                masked_key = f"{self.api_key[:8]}...{self.api_key[-4:]}"
                logger.info(f"✓ API Key loaded: {masked_key}")
                logger.info(f"✓ Base URL: {self.config.get('base_url')}")
                logger.info(f"✓ Default model: {self.config.get('model')}")
                self.results["kimi_api_key_loaded"] = True
            else:
                logger.error("✗ API Key NOT loaded - KIMI_API_KEY not set")
                self.results["kimi_api_key_loaded"] = False
                self.results["root_cause_matrix"] = {
                    "primary_issue": "auth",
                    "recommendation": "Set KIMI_API_KEY environment variable in .env file",
                }

        except Exception as e:
            logger.error(f"✗ Failed to load configuration: {e}")
            self.results["kimi_api_key_loaded"] = False
            self.results["root_cause_matrix"] = {
                "primary_issue": "config",
                "recommendation": f"Configuration error: {e}",
            }

        logger.info("")

    async def _step2_test_models_endpoint(self) -> None:
        """Step 2: Test the /models endpoint."""
        logger.info("-" * 70)
        logger.info("STEP 2: Testing /models Endpoint")
        logger.info("-" * 70)
        logger.info(f"URL: {self.MODELS_URL}")

        if not self.api_key:
            logger.warning("⚠ Skipping - API key not available")
            self.results["models_endpoint"]["error"] = "API key not loaded"
            return

        start_time = time.perf_counter()

        try:
            async with aiohttp.ClientSession() as session, session.get(
                self.MODELS_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                latency_ms = (time.perf_counter() - start_time) * 1000

                self.results["models_endpoint"]["status_code"] = response.status
                self.results["models_endpoint"]["latency_ms"] = round(latency_ms, 2)

                # Capture non-sensitive headers
                self.results["models_endpoint"]["headers"] = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in ("authorization", "set-cookie")
                }

                response_text = await response.text()

                if response.status == 200:
                    try:
                        data = json.loads(response_text)
                        models = data.get("data", [])
                        self.results["models_endpoint"]["models_available"] = [
                            m.get("id", "unknown") for m in models
                        ]
                        self.results["models_endpoint"]["success"] = True
                        logger.info(f"✓ Success - Status: {response.status}")
                        logger.info(f"✓ Latency: {latency_ms:.2f}ms")
                        logger.info(f"✓ Models available: {len(models)}")
                        for model in models[:5]:  # Show first 5
                            logger.info(f"  - {model.get('id', 'unknown')}")
                        if len(models) > 5:
                            logger.info(f"  ... and {len(models) - 5} more")
                    except json.JSONDecodeError as e:
                        self.results["models_endpoint"][
                            "error"
                        ] = f"JSON parse error: {e}"
                        logger.error(f"✗ JSON parse error: {e}")
                else:
                    self.results["models_endpoint"][
                        "error"
                    ] = f"HTTP {response.status}: {response_text[:200]}"
                    logger.error(f"✗ Failed - Status: {response.status}")
                    logger.error(f"✗ Response: {response_text[:200]}")

        except aiohttp.ClientError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.results["models_endpoint"]["latency_ms"] = round(latency_ms, 2)
            self.results["models_endpoint"]["error"] = f"Connection error: {e}"
            logger.error(f"✗ Connection error: {e}")
        except TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.results["models_endpoint"]["latency_ms"] = round(latency_ms, 2)
            self.results["models_endpoint"]["error"] = "Request timeout (>30s)"
            logger.error("✗ Request timeout (>30s)")
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.results["models_endpoint"]["latency_ms"] = round(latency_ms, 2)
            self.results["models_endpoint"]["error"] = f"Unexpected error: {e}"
            logger.error(f"✗ Unexpected error: {e}")

        logger.info("")

    async def _step3_test_chat_completions(self) -> None:
        """Step 3: Test the /chat/completions endpoint."""
        logger.info("-" * 70)
        logger.info("STEP 3: Testing /chat/completions Endpoint")
        logger.info("-" * 70)
        logger.info(f"URL: {self.CHAT_COMPLETIONS_URL}")

        if not self.api_key:
            logger.warning("⚠ Skipping - API key not available")
            self.results["chat_completions_endpoint"]["error"] = "API key not loaded"
            return

        model = self.config.get("model", "k2p5")
        self.results["chat_completions_endpoint"]["model_used"] = model

        start_time = time.perf_counter()

        try:
            async with aiohttp.ClientSession() as session, session.post(
                self.CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Say 'KIMI diagnostic test successful'",
                        }
                    ],
                    "max_tokens": 50,
                    "temperature": 0.1,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                latency_ms = (time.perf_counter() - start_time) * 1000

                self.results["chat_completions_endpoint"][
                    "status_code"
                ] = response.status
                self.results["chat_completions_endpoint"]["latency_ms"] = round(
                    latency_ms, 2
                )

                # Capture non-sensitive headers
                self.results["chat_completions_endpoint"]["headers"] = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in ("authorization", "set-cookie")
                }

                response_text = await response.text()

                if response.status == 200:
                    try:
                        data = json.loads(response_text)
                        choices = data.get("choices", [])
                        if choices:
                            content = (
                                choices[0].get("message", {}).get("content", "")
                            )
                            preview = (
                                content[:200] if content else "(empty response)"
                            )
                        else:
                            preview = "(no choices in response)"

                        self.results["chat_completions_endpoint"][
                            "response_preview"
                        ] = preview
                        self.results["chat_completions_endpoint"]["success"] = True
                        logger.info(f"✓ Success - Status: {response.status}")
                        logger.info(f"✓ Latency: {latency_ms:.2f}ms")
                        logger.info(f"✓ Model: {model}")
                        logger.info(f"✓ Response preview: {preview}")
                    except json.JSONDecodeError as e:
                        self.results["chat_completions_endpoint"][
                            "error"
                        ] = f"JSON parse error: {e}"
                        logger.error(f"✗ JSON parse error: {e}")
                else:
                    self.results["chat_completions_endpoint"][
                        "error"
                    ] = f"HTTP {response.status}: {response_text[:200]}"
                    logger.error(f"✗ Failed - Status: {response.status}")
                    logger.error(f"✗ Response: {response_text[:200]}")

        except aiohttp.ClientError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.results["chat_completions_endpoint"]["latency_ms"] = round(
                latency_ms, 2
            )
            self.results["chat_completions_endpoint"][
                "error"
            ] = f"Connection error: {e}"
            logger.error(f"✗ Connection error: {e}")
        except TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.results["chat_completions_endpoint"]["latency_ms"] = round(
                latency_ms, 2
            )
            self.results["chat_completions_endpoint"][
                "error"
            ] = "Request timeout (>30s)"
            logger.error("✗ Request timeout (>30s)")
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.results["chat_completions_endpoint"]["latency_ms"] = round(
                latency_ms, 2
            )
            self.results["chat_completions_endpoint"][
                "error"
            ] = f"Unexpected error: {e}"
            logger.error(f"✗ Unexpected error: {e}")

        logger.info("")

    def _step4_root_cause_analysis(self) -> None:
        """Step 4: Analyze root cause if failures occurred."""
        logger.info("-" * 70)
        logger.info("STEP 4: Root Cause Analysis")
        logger.info("-" * 70)

        # Collect all errors
        errors = []

        if not self.results["kimi_api_key_loaded"]:
            errors.append(("config", "API key not loaded from environment"))

        models_status = self.results["models_endpoint"].get("status_code")
        if models_status and models_status != 200:
            if models_status in self.ROOT_CAUSE_MAP:
                issue, recommendation = self.ROOT_CAUSE_MAP[models_status]
                errors.append((issue, f"Models endpoint: {recommendation}"))
            elif models_status >= 500:
                errors.append(
                    ("server", f"Models endpoint: Server error {models_status}")
                )
            else:
                errors.append(("unknown", f"Models endpoint: HTTP {models_status}"))

        chat_status = self.results["chat_completions_endpoint"].get("status_code")
        if chat_status and chat_status != 200:
            if chat_status in self.ROOT_CAUSE_MAP:
                issue, recommendation = self.ROOT_CAUSE_MAP[chat_status]
                errors.append((issue, f"Chat endpoint: {recommendation}"))
            elif chat_status >= 500:
                errors.append(("server", f"Chat endpoint: Server error {chat_status}"))
            else:
                errors.append(("unknown", f"Chat endpoint: HTTP {chat_status}"))

        # Check for connection errors
        models_error = self.results["models_endpoint"].get("error", "")
        chat_error = self.results["chat_completions_endpoint"].get("error", "")

        if "Connection error" in str(models_error) or "Connection error" in str(
            chat_error
        ):
            errors.append(("network", "Network connectivity issue to api.kimi.com"))

        if (
            "timeout" in str(models_error).lower()
            or "timeout" in str(chat_error).lower()
        ):
            errors.append(
                ("network", "Request timeout - possible network latency issue")
            )

        # Determine primary issue
        if errors:
            # Priority order for primary issue
            priority = [
                "config",
                "auth",
                "scope",
                "network",
                "rate_limit",
                "server",
                "model",
                "unknown",
            ]
            primary_issue = "unknown"
            for p in priority:
                for issue, _ in errors:
                    if issue == p:
                        primary_issue = p
                        break
                if primary_issue != "unknown":
                    break

            # Build recommendation
            recommendations = [rec for _, rec in errors]
            recommendation = " | ".join(recommendations)

            self.results["root_cause_matrix"] = {
                "primary_issue": primary_issue,
                "recommendation": recommendation,
            }

            logger.warning(f"⚠ Primary issue: {primary_issue}")
            logger.warning(f"⚠ Recommendation: {recommendation}")
        else:
            logger.info("✓ No issues detected - all tests passed")

        logger.info("")

    async def _step5_save_and_report(self) -> dict[str, Any]:
        """Step 5: Save evidence to file and return results.

        Returns:
            Complete diagnostic results dictionary
        """
        logger.info("-" * 70)
        logger.info("STEP 5: Saving Evidence")
        logger.info("-" * 70)

        # Create output directory
        output_dir = "_bmad-output"
        os.makedirs(output_dir, exist_ok=True)

        # Generate filename with timestamp
        timestamp_str = self.timestamp.strftime("%Y%m%d_%H%M%S")
        evidence_file = os.path.join(output_dir, f"kimi_probe_{timestamp_str}.json")

        # Save to file
        with open(evidence_file, "w") as f:
            json.dump(self.results, f, indent=2)

        logger.info(f"✓ Evidence saved: {evidence_file}")
        logger.info("")
        logger.info("=" * 70)
        logger.info("DIAGNOSTIC SUMMARY")
        logger.info("=" * 70)

        # Print summary
        overall_success = (
            self.results["kimi_api_key_loaded"]
            and self.results["models_endpoint"].get("success", False)
            and self.results["chat_completions_endpoint"].get("success", False)
        )

        if overall_success:
            logger.info("✓ OVERALL STATUS: SUCCESS")
        else:
            logger.warning("✗ OVERALL STATUS: FAILED")

        logger.info(
            f"  API Key Loaded: {'✓ Yes' if self.results['kimi_api_key_loaded'] else '✗ No'}"
        )
        logger.info(
            f"  Models Endpoint: "
            f"{'✓ Success' if self.results['models_endpoint'].get('success') else '✗ Failed'} "
            f"({self.results['models_endpoint'].get('status_code', 'N/A')})"
        )
        logger.info(
            f"  Chat Endpoint: "
            f"{'✓ Success' if self.results['chat_completions_endpoint'].get('success') else '✗ Failed'} "
            f"({self.results['chat_completions_endpoint'].get('status_code', 'N/A')})"
        )
        logger.info(
            f"  Primary Issue: {self.results['root_cause_matrix']['primary_issue']}"
        )
        logger.info("=" * 70)

        return self.results


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    probe = KimiDiagnosticProbe()
    results = await probe.run()

    # Output JSON to stdout
    print(json.dumps(results, indent=2))

    # Determine exit code
    overall_success = (
        results["kimi_api_key_loaded"]
        and results["models_endpoint"].get("success", False)
        and results["chat_completions_endpoint"].get("success", False)
    )

    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
