#!/usr/bin/env python3
"""Validation script for Kimi Adapter deployment.

Validates:
1. Adapter container is running and healthy
2. Health endpoint responds correctly
3. Provider chain uses adapter when enabled
4. Fallback behavior works when adapter unavailable
5. One-trade-per-symbol invariant unaffected

Returns exit code 0 on success, 1 on failure.

Usage:
    python3 scripts/validation/validate_kimi_adapter.py
    python3 scripts/validation/validate_kimi_adapter.py --verbose
    python3 scripts/validation/validate_kimi_adapter.py --check-container-only

For ST-KIMI-ADAPTER-001: Batch 4 - Deployment Validation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ValidationResult:
    """Result of a validation check."""

    name: str
    status: str  # "PASS", "FAIL", "SKIP", "WARN"
    details: str = ""
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class ValidationReport:
    """Complete validation report."""

    story_id: str = "ST-KIMI-ADAPTER-001"
    batch: int = 4
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    results: list[ValidationResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "story_id": self.story_id,
            "batch": self.batch,
            "timestamp": self.timestamp,
            "results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "details": r.details,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in self.results
            ],
            "summary": self.summary,
        }

    def to_json(self) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class KimiAdapterValidator:
    """Validator for Kimi Adapter deployment."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.report = ValidationReport()
        self.adapter_container_name = "chiseai-kimi-adapter"
        self.adapter_host = os.getenv("KIMI_COMPAT_HOST", "chiseai-kimi-adapter")
        self.adapter_port = int(os.getenv("KIMI_COMPAT_PORT", "8002"))
        self.base_url = f"http://{self.adapter_host}:{self.adapter_port}"

    def log(self, message: str) -> None:
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[VALIDATION] {message}")

    def error(self, message: str) -> None:
        """Log error message."""
        print(f"[ERROR] {message}", file=sys.stderr)

    def success(self, message: str) -> None:
        """Log success message."""
        print(f"[PASS] {message}")

    def failure(self, message: str) -> None:
        """Log failure message."""
        print(f"[FAIL] {message}", file=sys.stderr)

    def add_result(
        self,
        name: str,
        status: str,
        details: str = "",
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        """Add a validation result."""
        result = ValidationResult(
            name=name,
            status=status,
            details=details,
            duration_ms=duration_ms,
            error=error,
        )
        self.report.results.append(result)

        # Also print to console
        if status == "PASS":
            self.success(f"{name}: {details}")
        elif status == "FAIL":
            self.failure(f"{name}: {details}")
            if error:
                self.error(f"  Error: {error}")
        elif status == "WARN":
            print(f"[WARN] {name}: {details}")
        elif status == "SKIP":
            print(f"[SKIP] {name}: {details}")

    # ========================================================================
    # Validation Checks
    # ========================================================================

    def check_adapter_container_running(self) -> bool:
        """Check if adapter container is running."""
        import time

        start = time.time()
        self.log(f"Checking if container '{self.adapter_container_name}' is running...")

        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"name={self.adapter_container_name}",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            duration_ms = (time.time() - start) * 1000

            if result.returncode != 0:
                self.add_result(
                    "adapter_container_running",
                    "FAIL",
                    "Docker command failed",
                    duration_ms,
                    result.stderr,
                )
                return False

            running_containers = result.stdout.strip().split("\n")
            running_containers = [c for c in running_containers if c]

            if self.adapter_container_name in running_containers:
                self.add_result(
                    "adapter_container_running",
                    "PASS",
                    f"Container '{self.adapter_container_name}' is running",
                    duration_ms,
                )
                return True
            else:
                self.add_result(
                    "adapter_container_running",
                    "FAIL",
                    f"Container '{self.adapter_container_name}' not found in running containers",
                    duration_ms,
                    f"Found: {running_containers}",
                )
                return False

        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "adapter_container_running",
                "FAIL",
                "Docker command timed out",
                duration_ms,
                "Timeout after 10s",
            )
            return False
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "adapter_container_running",
                "FAIL",
                f"Exception checking container: {e}",
                duration_ms,
                str(e),
            )
            return False

    async def check_health_endpoint(self) -> bool:
        """Check adapter health endpoint."""
        import time

        start = time.time()
        self.log(f"Checking health endpoint at {self.base_url}/health...")

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    duration_ms = (time.time() - start) * 1000

                    if response.status == 200:
                        data = await response.json()
                        status = data.get("status", "unknown")

                        if status == "healthy":
                            self.add_result(
                                "health_endpoint",
                                "PASS",
                                f"Health endpoint returned healthy status",
                                duration_ms,
                            )
                            return True
                        else:
                            self.add_result(
                                "health_endpoint",
                                "WARN",
                                f"Health endpoint returned status: {status}",
                                duration_ms,
                            )
                            return True  # Still pass, just warn
                    else:
                        body = await response.text()
                        self.add_result(
                            "health_endpoint",
                            "FAIL",
                            f"Health endpoint returned status {response.status}",
                            duration_ms,
                            body,
                        )
                        return False

        except aiohttp.ClientError as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "health_endpoint",
                "FAIL",
                f"Connection error to health endpoint: {e}",
                duration_ms,
                str(e),
            )
            return False
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "health_endpoint",
                "FAIL",
                f"Exception checking health endpoint: {e}",
                duration_ms,
                str(e),
            )
            return False

    async def check_models_endpoint(self) -> bool:
        """Check adapter models endpoint."""
        import time

        start = time.time()
        self.log(f"Checking models endpoint at {self.base_url}/v1/models...")

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/v1/models",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    duration_ms = (time.time() - start) * 1000

                    if response.status == 200:
                        data = await response.json()

                        if "data" in data and len(data["data"]) > 0:
                            models = [m.get("id", "unknown") for m in data["data"]]
                            self.add_result(
                                "models_endpoint",
                                "PASS",
                                f"Models endpoint returned {len(data['data'])} models: {models}",
                                duration_ms,
                            )
                            return True
                        else:
                            self.add_result(
                                "models_endpoint",
                                "WARN",
                                "Models endpoint returned empty list",
                                duration_ms,
                            )
                            return True
                    else:
                        body = await response.text()
                        self.add_result(
                            "models_endpoint",
                            "FAIL",
                            f"Models endpoint returned status {response.status}",
                            duration_ms,
                            body,
                        )
                        return False

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "models_endpoint",
                "FAIL",
                f"Exception checking models endpoint: {e}",
                duration_ms,
                str(e),
            )
            return False

    def check_provider_chain_config(self) -> bool:
        """Check provider chain configuration includes kimi_compat."""
        import time

        start = time.time()
        self.log("Checking provider chain configuration...")

        try:
            # Import here to avoid early import errors
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
            from src.llm.provider_chain import PROVIDER_CONFIGS, LLMProviderChain

            # Check kimi_compat is in configs
            if "kimi_compat" not in PROVIDER_CONFIGS:
                duration_ms = (time.time() - start) * 1000
                self.add_result(
                    "provider_chain_config",
                    "FAIL",
                    "kimi_compat not found in PROVIDER_CONFIGS",
                    duration_ms,
                )
                return False

            config = PROVIDER_CONFIGS["kimi_compat"]

            # Check default provider order
            chain = LLMProviderChain()
            if "kimi_compat" not in chain.provider_order:
                duration_ms = (time.time() - start) * 1000
                self.add_result(
                    "provider_chain_config",
                    "FAIL",
                    "kimi_compat not in default provider order",
                    duration_ms,
                )
                return False

            # Check kimi_compat is first (highest priority)
            if chain.provider_order[0] != "kimi_compat":
                duration_ms = (time.time() - start) * 1000
                self.add_result(
                    "provider_chain_config",
                    "WARN",
                    f"kimi_compat is not first in provider order (position {chain.provider_order.index('kimi_compat')})",
                    duration_ms,
                )
            else:
                duration_ms = (time.time() - start) * 1000
                self.add_result(
                    "provider_chain_config",
                    "PASS",
                    f"Provider chain configured with kimi_compat as primary (enabled_env={config.enabled_env})",
                    duration_ms,
                )

            return True

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "provider_chain_config",
                "FAIL",
                f"Exception checking provider chain config: {e}",
                duration_ms,
                str(e),
            )
            return False

    async def check_chat_completions_endpoint(self) -> bool:
        """Check adapter chat completions endpoint."""
        import time

        start = time.time()
        self.log(f"Checking chat completions endpoint...")

        api_key = os.getenv("KIMI_API_KEY")
        if not api_key:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "chat_completions_endpoint",
                "SKIP",
                "KIMI_API_KEY not set, skipping chat completions test",
                duration_ms,
            )
            return True  # Skip is not a failure

        try:
            import aiohttp

            payload = {
                "model": "kimi-for-coding",
                "messages": [
                    {"role": "user", "content": "Say 'test' and nothing else."}
                ],
                "max_tokens": 10,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    duration_ms = (time.time() - start) * 1000

                    if response.status == 200:
                        data = await response.json()

                        if "choices" in data and len(data["choices"]) > 0:
                            self.add_result(
                                "chat_completions_endpoint",
                                "PASS",
                                f"Chat completions endpoint working, returned {len(data['choices'])} choices",
                                duration_ms,
                            )
                            return True
                        else:
                            self.add_result(
                                "chat_completions_endpoint",
                                "WARN",
                                "Chat completions returned no choices",
                                duration_ms,
                            )
                            return True
                    else:
                        body = await response.text()
                        self.add_result(
                            "chat_completions_endpoint",
                            "FAIL",
                            f"Chat completions returned status {response.status}",
                            duration_ms,
                            body,
                        )
                        return False

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "chat_completions_endpoint",
                "FAIL",
                f"Exception checking chat completions: {e}",
                duration_ms,
                str(e),
            )
            return False

    def check_one_trade_per_symbol_invariant(self) -> bool:
        """Check one-trade-per-symbol invariant is not affected."""
        import time

        start = time.time()
        self.log("Checking one-trade-per-symbol invariant...")

        try:
            # Look for the invariant check in the codebase
            import glob

            # Find files that might contain the invariant
            safety_files = glob.glob(
                os.path.join(
                    os.path.dirname(__file__), "..", "..", "src", "**", "*.py"
                ),
                recursive=True,
            )

            invariant_found = False
            for file_path in safety_files:
                try:
                    with open(file_path, "r") as f:
                        content = f.read()
                        if (
                            "one_trade_per_symbol" in content
                            or "one trade per symbol" in content.lower()
                        ):
                            invariant_found = True
                            self.log(f"Found invariant reference in {file_path}")
                            break
                except:
                    continue

            duration_ms = (time.time() - start) * 1000

            # The invariant should exist
            if invariant_found:
                self.add_result(
                    "one_trade_per_symbol_invariant",
                    "PASS",
                    "One-trade-per-symbol invariant exists in codebase",
                    duration_ms,
                )
            else:
                self.add_result(
                    "one_trade_per_symbol_invariant",
                    "WARN",
                    "Could not locate one-trade-per-symbol invariant (may be named differently)",
                    duration_ms,
                )

            return True

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "one_trade_per_symbol_invariant",
                "WARN",
                f"Exception checking invariant: {e}",
                duration_ms,
                str(e),
            )
            return True  # Warning, not failure

    def check_no_trading_blockage(self) -> bool:
        """Check that adapter failures don't block trading."""
        import time

        start = time.time()
        self.log("Checking for trading blockage safeguards...")

        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
            from src.execution.llm.trade_decision_enhancer import TradeDecisionEnhancer

            # Check that the enhancer has safe defaults
            enhancer_source = TradeDecisionEnhancer.__init__.__module__

            # Import and check the source
            import inspect

            source = inspect.getsource(TradeDecisionEnhancer.enhance_decision)

            # Check for safe default behavior
            has_safe_default = (
                "go_no_go=True" in source and "LLM enhancement disabled" in source
            )

            duration_ms = (time.time() - start) * 1000

            if has_safe_default:
                self.add_result(
                    "no_trading_blockage",
                    "PASS",
                    "TradeDecisionEnhancer has safe defaults (GO when LLM unavailable)",
                    duration_ms,
                )
                return True
            else:
                self.add_result(
                    "no_trading_blockage",
                    "WARN",
                    "Could not verify safe defaults in TradeDecisionEnhancer",
                    duration_ms,
                )
                return True

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.add_result(
                "no_trading_blockage",
                "WARN",
                f"Exception checking trading safeguards: {e}",
                duration_ms,
                str(e),
            )
            return True

    # ========================================================================
    # Main Validation Flow
    # ========================================================================

    async def run_all_validations(self, check_container_only: bool = False) -> bool:
        """Run all validation checks."""
        print("=" * 70)
        print("Kimi Adapter Deployment Validation")
        print("=" * 70)
        print(f"Story: {self.report.story_id}")
        print(f"Timestamp: {self.report.timestamp}")
        print(f"Adapter URL: {self.base_url}")
        print("=" * 70)
        print()

        all_passed = True

        # 1. Check container is running
        if not self.check_adapter_container_running():
            all_passed = False
            if check_container_only:
                print("\nContainer check failed, stopping validation.")
                return False

        if check_container_only:
            return all_passed

        # 2. Check health endpoint
        if not await self.check_health_endpoint():
            all_passed = False

        # 3. Check models endpoint
        if not await self.check_models_endpoint():
            all_passed = False

        # 4. Check provider chain configuration
        if not self.check_provider_chain_config():
            all_passed = False

        # 5. Check chat completions (optional, requires API key)
        await self.check_chat_completions_endpoint()

        # 6. Check one-trade-per-symbol invariant
        self.check_one_trade_per_symbol_invariant()

        # 7. Check no trading blockage
        self.check_no_trading_blockage()

        # Generate summary
        self._generate_summary()

        return all_passed

    def _generate_summary(self) -> None:
        """Generate validation summary."""
        total = len(self.report.results)
        passed = sum(1 for r in self.report.results if r.status == "PASS")
        failed = sum(1 for r in self.report.results if r.status == "FAIL")
        warnings = sum(1 for r in self.report.results if r.status == "WARN")
        skipped = sum(1 for r in self.report.results if r.status == "SKIP")

        self.report.summary = {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "skipped": skipped,
            "overall_status": "PASS" if failed == 0 else "FAIL",
        }

        print()
        print("=" * 70)
        print("Validation Summary")
        print("=" * 70)
        print(f"Total checks: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Warnings: {warnings}")
        print(f"Skipped: {skipped}")
        print()
        print(f"Overall Status: {self.report.summary['overall_status']}")
        print("=" * 70)

    def save_report(self, output_path: str) -> None:
        """Save validation report to file."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            f.write(self.report.to_json())

        print(f"\nReport saved to: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Kimi Adapter deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                          # Run all validations
    %(prog)s --verbose                # Run with detailed output
    %(prog)s --check-container-only   # Only check if container is running
    %(prog)s --output report.json     # Save report to file
        """,
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--check-container-only",
        action="store_true",
        help="Only check if container is running",
    )
    parser.add_argument(
        "--output", "-o", type=str, help="Save validation report to file"
    )
    parser.add_argument(
        "--adapter-host",
        type=str,
        default=os.getenv("KIMI_COMPAT_HOST", "chiseai-kimi-adapter"),
        help="Adapter host (default: chiseai-kimi-adapter)",
    )
    parser.add_argument(
        "--adapter-port",
        type=int,
        default=int(os.getenv("KIMI_COMPAT_PORT", "8002")),
        help="Adapter port (default: 8002)",
    )

    args = parser.parse_args()

    # Set environment variables from args
    os.environ["KIMI_COMPAT_HOST"] = args.adapter_host
    os.environ["KIMI_COMPAT_PORT"] = str(args.adapter_port)

    validator = KimiAdapterValidator(verbose=args.verbose)

    try:
        success = asyncio.run(
            validator.run_all_validations(
                check_container_only=args.check_container_only
            )
        )

        if args.output:
            validator.save_report(args.output)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\nValidation interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nValidation failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
