#!/usr/bin/env python3
"""Comprehensive LLM Provider Endpoint Probe Matrix.

Tests all endpoint+model combinations for each provider to determine
which configurations actually work. Outputs structured JSON results
with recommendations.

Usage:
    python scripts/probe_llm_providers.py
    python scripts/probe_llm_providers.py --output custom_results.json
    python scripts/probe_llm_providers.py --timeout 60

Environment Variables Required:
    KIMI_API_KEY - For KIMI provider tests
    ZAI_API_KEY or Z_AI_API_KEY - For Z.ai/Zhipu provider tests
    ZHIPU_API_KEY - For Zhipu provider tests (optional, falls back to ZAI_API_KEY)

Output:
    docs/tempmemories/llm_probe_results.json (default)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Test prompt for minimal chat completion
TEST_PROMPT = "Say 'OK' and nothing else."
TEST_SYSTEM_PROMPT = "You are a helpful assistant. Respond with minimal text."


@dataclass
class ProbeResult:
    """Result of probing a single endpoint+model combination."""

    provider: str
    endpoint_url: str
    model: str
    api_key_source: str
    success: bool
    status_code: int | None = None
    latency_ms: float = 0.0
    error_message: str | None = None
    error_category: str | None = None
    response_preview: str | None = None
    models_available: list[str] = field(default_factory=list)
    models_endpoint_works: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    test_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ProviderProbeConfig:
    """Configuration for probing a provider endpoint."""

    name: str
    endpoint_base: str
    models_endpoint: str
    chat_endpoint: str
    models_to_test: list[str]
    api_key_env: list[str]
    headers_format: str = "bearer"  # "bearer" or "api_key"
    request_format: str = "openai"  # "openai" or "custom"
    timeout: float = 30.0


# Define all endpoint+model combinations to test
PROBE_CONFIGS: list[ProviderProbeConfig] = [
    # KIMI - Current endpoint
    ProviderProbeConfig(
        name="KIMI (api.kimi.com/coding/v1)",
        endpoint_base="https://api.kimi.com/coding/v1",
        models_endpoint="/models",
        chat_endpoint="/chat/completions",
        models_to_test=["k2p5", "kimi-for-coding", "kimi-k2.5", "kimi-k2.5-coding"],
        api_key_env=["KIMI_API_KEY"],
    ),
    # KIMI - Moonshot official endpoint (research suggests this)
    ProviderProbeConfig(
        name="KIMI (api.moonshot.ai/v1)",
        endpoint_base="https://api.moonshot.ai/v1",
        models_endpoint="/models",
        chat_endpoint="/chat/completions",
        models_to_test=["kimi-k2.5", "kimi-k2.5-coding", "k2p5", "kimi-for-coding"],
        api_key_env=["KIMI_API_KEY"],
    ),
    # Z.ai - Current endpoint
    ProviderProbeConfig(
        name="Z.ai (api.z.ai)",
        endpoint_base="https://api.z.ai/api/paas/v4",
        models_endpoint="/models",
        chat_endpoint="/chat/completions",
        models_to_test=["glm-5", "glm-4.7", "glm-4.5", "glm-4"],
        api_key_env=["ZAI_API_KEY", "Z_AI_API_KEY"],
    ),
    # Zhipu - Official endpoint (research suggests this)
    ProviderProbeConfig(
        name="Zhipu (open.bigmodel.cn)",
        endpoint_base="https://open.bigmodel.cn/api/paas/v4",
        models_endpoint="/models",
        chat_endpoint="/chat/completions",
        models_to_test=["glm-5", "glm-4.7", "glm-4.5", "glm-4"],
        api_key_env=["ZHIPU_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"],
    ),
]


class LLMProviderProbe:
    """Probes LLM provider endpoints to test connectivity and model availability."""

    def __init__(self, timeout: float = 30.0):
        """Initialize the probe.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.results: list[ProbeResult] = []
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> LLMProviderProbe:
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            self.session = None

    def _get_api_key(self, env_vars: list[str]) -> tuple[str | None, str]:
        """Get API key from environment variables.

        Args:
            env_vars: List of environment variable names to check

        Returns:
            Tuple of (api_key, source_env_var)
        """
        for env_var in env_vars:
            key = os.getenv(env_var)
            if key:
                return key, env_var
        return None, env_vars[0] if env_vars else "unknown"

    async def _test_models_endpoint(
        self,
        config: ProviderProbeConfig,
        api_key: str,
    ) -> tuple[bool, list[str]]:
        """Test the /models endpoint to discover available models.

        Args:
            config: Provider probe configuration
            api_key: API key for authentication

        Returns:
            Tuple of (success, list of model IDs)
        """
        if not self.session:
            raise RuntimeError("Session not initialized")

        url = f"{config.endpoint_base}{config.models_endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            async with self.session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        models = data.get("data", [])
                        model_ids = [m.get("id", "unknown") for m in models]
                        return True, model_ids
                    except (json.JSONDecodeError, KeyError):
                        return True, []
                else:
                    return False, []
        except TimeoutError:
            logger.warning(f"Timeout testing {url}/models")
            return False, []
        except Exception as e:
            logger.warning(f"Error testing {url}/models: {e}")
            return False, []

    async def _test_chat_completion(
        self,
        config: ProviderProbeConfig,
        api_key: str,
        model: str,
    ) -> tuple[bool, int | None, float, str | None, str | None]:
        """Test the /chat/completions endpoint with a minimal request.

        Args:
            config: Provider probe configuration
            api_key: API key for authentication
            model: Model ID to test

        Returns:
            Tuple of (success, status_code, latency_ms, error_message, response_preview)
        """
        if not self.session:
            raise RuntimeError("Session not initialized")

        url = f"{config.endpoint_base}{config.chat_endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": TEST_SYSTEM_PROMPT},
                {"role": "user", "content": TEST_PROMPT},
            ],
            "temperature": 0.3,
            "max_tokens": 10,
            "stream": False,
        }

        start_time = time.time()
        try:
            async with self.session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                latency_ms = (time.time() - start_time) * 1000
                status_code = response.status

                if status_code == 200:
                    try:
                        data = await response.json()
                        choices = data.get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content", "")
                            preview = content[:100] if content else "<empty>"
                        else:
                            preview = "<no choices>"
                        return True, status_code, latency_ms, None, preview
                    except (json.JSONDecodeError, KeyError) as e:
                        return (
                            True,
                            status_code,
                            latency_ms,
                            None,
                            f"<parse error: {e}>",
                        )
                else:
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get("error", {}).get(
                            "message", str(error_data)
                        )
                    except (json.JSONDecodeError, ValueError):
                        error_text = await response.text()
                        error_msg = (
                            error_text[:200] if error_text else f"HTTP {status_code}"
                        )
                    return False, status_code, latency_ms, error_msg, None

        except TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            return False, None, latency_ms, f"Timeout after {self.timeout}s", None
        except aiohttp.ClientError as e:
            latency_ms = (time.time() - start_time) * 1000
            return False, None, latency_ms, f"Network error: {e}", None
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return False, None, latency_ms, f"Error: {e}", None

    def _classify_error(
        self, status_code: int | None, error_message: str | None
    ) -> str:
        """Classify error into category.

        Args:
            status_code: HTTP status code
            error_message: Error message

        Returns:
            Error category string
        """
        if status_code == 401:
            return "AUTH"
        elif status_code == 403:
            return "SCOPE/QUOTA"
        elif status_code == 429:
            return "RATE_LIMIT"
        elif status_code and status_code >= 500:
            return "SERVER_ERROR"
        elif status_code and status_code >= 400:
            return "CLIENT_ERROR"
        elif error_message:
            error_lower = error_message.lower()
            if "timeout" in error_lower:
                return "TIMEOUT"
            elif any(x in error_lower for x in ["connection", "network", "dns"]):
                return "NETWORK"
            else:
                return "UNKNOWN"
        return "UNKNOWN"

    async def probe_config(self, config: ProviderProbeConfig) -> list[ProbeResult]:
        """Probe all model combinations for a provider configuration.

        Args:
            config: Provider probe configuration

        Returns:
            List of probe results
        """
        results: list[ProbeResult] = []

        # Get API key
        api_key, key_source = self._get_api_key(config.api_key_env)
        if not api_key:
            logger.warning(
                f"Skipping {config.name}: No API key found "
                f"(checked: {', '.join(config.api_key_env)})"
            )
            # Create a result indicating missing key
            result = ProbeResult(
                provider=config.name,
                endpoint_url=config.endpoint_base,
                model="N/A",
                api_key_source=f"Missing (checked: {', '.join(config.api_key_env)})",
                success=False,
                error_message="API key not configured",
                error_category="NOT_CONFIGURED",
            )
            results.append(result)
            return results

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Probing: {config.name}")
        logger.info(f"Endpoint: {config.endpoint_base}")
        logger.info(f"API Key Source: {key_source}")
        logger.info(f"{'=' * 60}")

        # First, test /models endpoint
        logger.info("Testing /models endpoint...")
        models_works, available_models = await self._test_models_endpoint(
            config, api_key
        )
        logger.info(f"  /models endpoint: {'✓ WORKS' if models_works else '✗ FAILED'}")
        if available_models:
            logger.info(f"  Available models: {available_models}")

        # Test each model
        for model in config.models_to_test:
            logger.info(f"\n  Testing model: {model}")

            (
                success,
                status_code,
                latency_ms,
                error_msg,
                preview,
            ) = await self._test_chat_completion(config, api_key, model)

            error_category = self._classify_error(status_code, error_msg)

            result = ProbeResult(
                provider=config.name,
                endpoint_url=config.endpoint_base,
                model=model,
                api_key_source=key_source,
                success=success,
                status_code=status_code,
                latency_ms=round(latency_ms, 2),
                error_message=error_msg,
                error_category=error_category,
                response_preview=preview,
                models_available=available_models,
                models_endpoint_works=models_works,
            )
            results.append(result)

            status_icon = "✓" if success else "✗"
            logger.info(
                f"    {status_icon} Status: {status_code} | Latency: {latency_ms:.0f}ms"
            )
            if success:
                logger.info(f"    Response: {preview}")
            else:
                logger.info(
                    f"    Error: {error_msg[:100]}..."
                    if error_msg and len(error_msg) > 100
                    else f"    Error: {error_msg}"
                )

        return results

    async def run_probe_matrix(self) -> list[ProbeResult]:
        """Run the complete probe matrix.

        Returns:
            List of all probe results
        """
        logger.info("=" * 60)
        logger.info("LLM PROVIDER ENDPOINT PROBE MATRIX")
        logger.info("=" * 60)
        logger.info(f"Started: {datetime.now(UTC).isoformat()}")
        logger.info(f"Timeout: {self.timeout}s per request")
        logger.info("")

        all_results: list[ProbeResult] = []

        for config in PROBE_CONFIGS:
            results = await self.probe_config(config)
            all_results.extend(results)

        self.results = all_results
        return all_results

    def generate_summary(self) -> dict[str, Any]:
        """Generate summary statistics from probe results.

        Returns:
            Summary dictionary
        """
        if not self.results:
            return {"error": "No results available"}

        total_tests = len(self.results)
        successful_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - successful_tests

        # Group by provider
        by_provider: dict[str, dict[str, Any]] = {}
        for result in self.results:
            provider = result.provider
            if provider not in by_provider:
                by_provider[provider] = {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "working_models": [],
                    "failed_models": [],
                    "models_endpoint_works": False,
                }

            by_provider[provider]["total"] += 1
            if result.success:
                by_provider[provider]["successful"] += 1
                by_provider[provider]["working_models"].append(result.model)
            else:
                by_provider[provider]["failed"] += 1
                by_provider[provider]["failed_models"].append(
                    {
                        "model": result.model,
                        "error": result.error_message,
                        "category": result.error_category,
                    }
                )

            if result.models_endpoint_works:
                by_provider[provider]["models_endpoint_works"] = True
                by_provider[provider]["available_models"] = result.models_available

        # Generate recommendations
        recommendations: list[dict[str, str]] = []

        # Find best working configuration per provider type
        kimi_configs = {k: v for k, v in by_provider.items() if "KIMI" in k}
        zai_configs = {k: v for k, v in by_provider.items() if "Z.ai" in k}
        zhipu_configs = {k: v for k, v in by_provider.items() if "Zhipu" in k}

        # KIMI recommendation
        best_kimi = None
        for name, data in kimi_configs.items():
            if data["successful"] > 0:
                if best_kimi is None or data["successful"] > best_kimi[1]["successful"]:
                    best_kimi = (name, data)

        if best_kimi:
            recommendations.append(
                {
                    "provider": "KIMI",
                    "recommendation": f"Use {best_kimi[0]} with model(s): {', '.join(best_kimi[1]['working_models'][:2])}",
                    "priority": "1",
                }
            )
        else:
            recommendations.append(
                {
                    "provider": "KIMI",
                    "recommendation": "No working configuration found. Check KIMI_API_KEY.",
                    "priority": "1",
                }
            )

        # Z.ai/Zhipu recommendation
        best_z = None
        all_z_configs = {**zai_configs, **zhipu_configs}
        for name, data in all_z_configs.items():
            if data["successful"] > 0:
                if best_z is None or data["successful"] > best_z[1]["successful"]:
                    best_z = (name, data)

        if best_z:
            recommendations.append(
                {
                    "provider": "Z.ai/Zhipu",
                    "recommendation": f"Use {best_z[0]} with model(s): {', '.join(best_z[1]['working_models'][:2])}",
                    "priority": "2",
                }
            )
        else:
            recommendations.append(
                {
                    "provider": "Z.ai/Zhipu",
                    "recommendation": "No working configuration found. Check ZAI_API_KEY or ZHIPU_API_KEY.",
                    "priority": "2",
                }
            )

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": {
                "total_tests": total_tests,
                "successful": successful_tests,
                "failed": failed_tests,
                "success_rate": (
                    f"{(successful_tests / total_tests * 100):.1f}%"
                    if total_tests > 0
                    else "N/A"
                ),
            },
            "by_provider": by_provider,
            "recommendations": recommendations,
        }

    def save_results(self, output_path: str) -> None:
        """Save probe results to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        summary = self.generate_summary()

        output = {
            "probe_metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "probe_id": str(uuid.uuid4()),
                "timeout_seconds": self.timeout,
            },
            "summary": summary["summary"],
            "by_provider": summary["by_provider"],
            "recommendations": summary["recommendations"],
            "detailed_results": [r.to_dict() for r in self.results],
        }

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"\n✓ Results saved to: {output_path}")

    def print_summary(self) -> None:
        """Print summary report to console."""
        summary = self.generate_summary()

        print("\n" + "=" * 60)
        print("PROBE SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {summary['summary']['total_tests']}")
        print(f"Successful: {summary['summary']['successful']}")
        print(f"Failed: {summary['summary']['failed']}")
        print(f"Success Rate: {summary['summary']['success_rate']}")
        print("")

        print("BY PROVIDER:")
        print("-" * 60)
        for provider, data in summary["by_provider"].items():
            status = "✓ WORKING" if data["successful"] > 0 else "✗ NO WORKING MODELS"
            print(f"\n{provider}: {status}")
            print(
                f"  Working Models: {', '.join(data['working_models']) if data['working_models'] else 'None'}"
            )
            print(
                f"  /models Endpoint: {'✓' if data['models_endpoint_works'] else '✗'}"
            )
            if data.get("available_models"):
                print(f"  Discovered Models: {', '.join(data['available_models'])}")

        print("\n" + "=" * 60)
        print("RECOMMENDATIONS")
        print("=" * 60)
        for rec in summary["recommendations"]:
            print(f"\n[{rec['priority']}] {rec['provider']}:")
            print(f"    {rec['recommendation']}")

        print("\n" + "=" * 60)


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 if any provider works, 1 if all fail)
    """
    parser = argparse.ArgumentParser(
        description="Probe LLM provider endpoints and model combinations"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/tempmemories/llm_probe_results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        async with LLMProviderProbe(timeout=args.timeout) as probe:
            await probe.run_probe_matrix()
            probe.print_summary()
            probe.save_results(args.output)

            # Exit code based on whether any provider works
            any_success = any(r.success for r in probe.results)
            return 0 if any_success else 1

    except KeyboardInterrupt:
        logger.info("\nProbe interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Probe failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
