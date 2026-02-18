#!/usr/bin/env python3
"""Bybit Live Proof Test Harness

Validates connectivity to Bybit API endpoints (testnet and live),
performs authenticated health checks, and captures evidence.

For PAPER-LIVE-001: Endpoint Validation & Live Data Harness

Usage:
    python scripts/live_proof_harness.py [--mode {testnet,live,both}]

Environment Variables:
    BYBIT_API_KEY: Bybit API key
    BYBIT_API_SECRET: Bybit API secret
    BYBIT_MODE: Default mode (testnet|live)

Exit Codes:
    0: All tests passed
    1: Some tests failed
    2: Critical failure (both modes failed)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
import yaml


@dataclass
class EndpointConfig:
    """Configuration for a Bybit endpoint."""

    name: str
    description: str
    rest_base_url: str
    ws_public_url: str
    ws_private_url: str
    environment: str
    requires_auth: bool


@dataclass
class TestResult:
    """Result of a single test."""

    test_name: str
    endpoint: str
    success: bool
    latency_ms: float = 0.0
    timestamp: str = ""
    error_message: str = ""
    request_details: dict = field(default_factory=dict)
    response_details: dict = field(default_factory=dict)


@dataclass
class Evidence:
    """Collected evidence from all tests."""

    test_run_id: str
    timestamp: str
    mode_tested: str
    endpoint_urls: dict = field(default_factory=dict)
    auth_results: dict = field(default_factory=dict)
    market_data: dict = field(default_factory=dict)
    latency_measurements: dict = field(default_factory=dict)
    selected_primary: str = ""
    notes: list = field(default_factory=list)


class BybitProofHarness:
    """Harness for testing Bybit API connectivity and collecting evidence."""

    def __init__(self, config_path: str | None = None):
        """Initialize the harness.

        Args:
            config_path: Path to the YAML config file
        """
        self.config_path = config_path or "config/bybit_endpoints.yaml"
        self.config = self._load_config()
        self.api_key = os.getenv("BYBIT_API_KEY", "")
        self.api_secret = os.getenv("BYBIT_API_SECRET", "")
        self.recv_window = self.config.get("settings", {}).get("recv_window_ms", 5000)
        self.results: list[TestResult] = []
        self.evidence = Evidence(
            test_run_id=f"bybit-proof-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            timestamp=datetime.utcnow().isoformat(),
            mode_tested="",
        )

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f)
                return data.get("bybit", {})
        except FileNotFoundError:
            print(
                f"Warning: Config file not found at {self.config_path}, using defaults"
            )
            return self._default_config()
        except yaml.YAMLError as e:
            print(f"Error parsing config: {e}, using defaults")
            return self._default_config()

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "endpoints": {
                "testnet": {
                    "rest_base_url": "https://api-testnet.bybit.com",
                    "ws_public_url": "wss://stream-testnet.bybit.com/v5/public/linear",
                    "ws_private_url": "wss://stream-testnet.bybit.com/v5/private",
                },
                "live": {
                    "rest_base_url": "https://api.bybit.com",
                    "ws_public_url": "wss://stream.bybit.com/v5/public/linear",
                    "ws_private_url": "wss://stream.bybit.com/v5/private",
                },
            },
            "settings": {
                "recv_window_ms": 5000,
                "latency_threshold_ms": {"market_data": 100, "authenticated": 500},
            },
            "test_symbols": ["BTCUSDT", "ETHUSDT"],
        }

    def _get_endpoint_config(self, mode: str) -> EndpointConfig:
        """Get endpoint configuration for a mode."""
        endpoints = self.config.get("endpoints", {})
        ep = endpoints.get(mode, {})
        return EndpointConfig(
            name=ep.get("name", mode),
            description=ep.get("description", ""),
            rest_base_url=ep.get("rest_base_url", ""),
            ws_public_url=ep.get("ws_public_url", ""),
            ws_private_url=ep.get("ws_private_url", ""),
            environment=ep.get("environment", mode),
            requires_auth=ep.get("requires_auth", True),
        )

    def _generate_signature(
        self, timestamp: str, api_secret: str, payload: str = ""
    ) -> str:
        """Generate HMAC signature for authenticated requests."""
        param_str = timestamp + self.api_key + str(self.recv_window) + payload
        return hmac.new(
            api_secret.encode(), param_str.encode(), hashlib.sha256
        ).hexdigest()

    async def test_connectivity(self, mode: str) -> TestResult:
        """Test basic connectivity to endpoint.

        Args:
            mode: Endpoint mode (testnet|live)

        Returns:
            TestResult with connectivity status
        """
        ep = self._get_endpoint_config(mode)
        url = f"{ep.rest_base_url}/v5/market/time"

        print(f"\n🌐 Testing connectivity to {mode}...")
        print(f"   URL: {url}")

        start_time = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    data = await resp.json()

                    success = resp.status == 200 and data.get("retCode") == 0

                    result = TestResult(
                        test_name=f"connectivity_{mode}",
                        endpoint=url,
                        success=success,
                        latency_ms=latency_ms,
                        timestamp=datetime.utcnow().isoformat(),
                        error_message=""
                        if success
                        else data.get("retMsg", "Unknown error"),
                        request_details={"method": "GET", "url": url},
                        response_details={
                            "status": resp.status,
                            "retCode": data.get("retCode"),
                            "retMsg": data.get("retMsg"),
                            "time": data.get("result", {}).get("timeSecond"),
                        },
                    )

                    status = "✅" if success else "❌"
                    print(
                        f"   {status} Connectivity: {'OK' if success else 'FAILED'} ({latency_ms:.2f}ms)"
                    )

                    return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return TestResult(
                test_name=f"connectivity_{mode}",
                endpoint=url,
                success=False,
                latency_ms=latency_ms,
                timestamp=datetime.utcnow().isoformat(),
                error_message=str(e),
                request_details={"method": "GET", "url": url},
                response_details={},
            )

    async def test_authenticated_health(self, mode: str) -> TestResult:
        """Test authenticated endpoint access.

        Args:
            mode: Endpoint mode (testnet|live)

        Returns:
            TestResult with authentication status
        """
        ep = self._get_endpoint_config(mode)
        url = f"{ep.rest_base_url}/v5/account/info"

        print(f"\n🔐 Testing authenticated health check ({mode})...")
        print(f"   URL: {url}")

        if not self.api_key or not self.api_secret:
            print(f"   ⚠️  Skipping auth test - no API credentials provided")
            return TestResult(
                test_name=f"auth_{mode}",
                endpoint=url,
                success=False,
                timestamp=datetime.utcnow().isoformat(),
                error_message="No API credentials provided (BYBIT_API_KEY/BYBIT_API_SECRET)",
            )

        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, self.api_secret)

        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(self.recv_window),
            "X-BAPI-SIGN": signature,
        }

        start_time = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    data = await resp.json()

                    # retCode 0 = success, retCode 10003 = invalid API key
                    success = resp.status == 200 and data.get("retCode") == 0

                    result = TestResult(
                        test_name=f"auth_{mode}",
                        endpoint=url,
                        success=success,
                        latency_ms=latency_ms,
                        timestamp=datetime.utcnow().isoformat(),
                        error_message=data.get("retMsg", "") if not success else "",
                        request_details={
                            "method": "GET",
                            "url": url,
                            "headers": {
                                k: v for k, v in headers.items() if k != "X-BAPI-SIGN"
                            },
                        },
                        response_details={
                            "status": resp.status,
                            "retCode": data.get("retCode"),
                            "retMsg": data.get("retMsg"),
                            "result": data.get("result", {}),
                        },
                    )

                    status = "✅" if success else "❌"
                    print(
                        f"   {status} Authentication: {'OK' if success else 'FAILED'} ({latency_ms:.2f}ms)"
                    )
                    if not success:
                        print(f"   Error: {data.get('retMsg', 'Unknown error')}")

                    return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return TestResult(
                test_name=f"auth_{mode}",
                endpoint=url,
                success=False,
                latency_ms=latency_ms,
                timestamp=datetime.utcnow().isoformat(),
                error_message=str(e),
                request_details={"method": "GET", "url": url},
                response_details={},
            )

    async def test_market_data(self, mode: str, symbol: str) -> TestResult:
        """Test market data fetch for a symbol.

        Args:
            mode: Endpoint mode (testnet|live)
            symbol: Trading pair symbol (e.g., BTCUSDT)

        Returns:
            TestResult with market data
        """
        ep = self._get_endpoint_config(mode)
        url = f"{ep.rest_base_url}/v5/market/tickers"

        print(f"\n📊 Testing market data fetch ({mode}/{symbol})...")
        print(f"   URL: {url}?category=linear&symbol={symbol}")

        start_time = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params={"category": "linear", "symbol": symbol},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    data = await resp.json()

                    success = resp.status == 200 and data.get("retCode") == 0
                    ticker_data = (
                        data.get("result", {}).get("list", [{}])[0] if success else {}
                    )

                    result = TestResult(
                        test_name=f"market_data_{mode}_{symbol}",
                        endpoint=url,
                        success=success,
                        latency_ms=latency_ms,
                        timestamp=datetime.utcnow().isoformat(),
                        error_message=data.get("retMsg", "") if not success else "",
                        request_details={
                            "method": "GET",
                            "url": url,
                            "params": {"category": "linear", "symbol": symbol},
                        },
                        response_details={
                            "status": resp.status,
                            "retCode": data.get("retCode"),
                            "symbol": ticker_data.get("symbol"),
                            "lastPrice": ticker_data.get("lastPrice"),
                            "bid1Price": ticker_data.get("bid1Price"),
                            "ask1Price": ticker_data.get("ask1Price"),
                            "volume24h": ticker_data.get("volume24h"),
                        },
                    )

                    threshold = (
                        self.config.get("settings", {})
                        .get("latency_threshold_ms", {})
                        .get("market_data", 100)
                    )
                    latency_ok = latency_ms < threshold

                    status = (
                        "✅" if success and latency_ok else "⚠️" if success else "❌"
                    )
                    print(
                        f"   {status} Market Data: {'OK' if success else 'FAILED'} ({latency_ms:.2f}ms)"
                    )
                    if success:
                        print(f"       Price: ${ticker_data.get('lastPrice', 'N/A')}")
                        print(
                            f"       Volume 24h: {ticker_data.get('volume24h', 'N/A')}"
                        )
                        if not latency_ok:
                            print(
                                f"       ⚠️  Latency exceeds threshold ({threshold}ms)"
                            )

                    return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return TestResult(
                test_name=f"market_data_{mode}_{symbol}",
                endpoint=url,
                success=False,
                latency_ms=latency_ms,
                timestamp=datetime.utcnow().isoformat(),
                error_message=str(e),
                request_details={
                    "method": "GET",
                    "url": url,
                    "params": {"symbol": symbol},
                },
                response_details={},
            )

    async def run_mode_tests(self, mode: str) -> list[TestResult]:
        """Run all tests for a specific mode.

        Args:
            mode: Endpoint mode (testnet|live)

        Returns:
            List of test results
        """
        print(f"\n{'=' * 60}")
        print(f"🧪 TESTING MODE: {mode.upper()}")
        print(f"{'=' * 60}")

        results = []

        # Test 1: Basic connectivity
        result = await self.test_connectivity(mode)
        results.append(result)

        # Test 2: Authenticated health check
        result = await self.test_authenticated_health(mode)
        results.append(result)

        # Test 3: Market data for test symbols
        symbols = self.config.get("test_symbols", ["BTCUSDT", "ETHUSDT"])
        for symbol in symbols:
            result = await self.test_market_data(mode, symbol)
            results.append(result)

        return results

    def compile_evidence(self, results: list[TestResult]) -> Evidence:
        """Compile evidence from test results.

        Args:
            results: List of test results

        Returns:
            Evidence object
        """
        evidence = self.evidence

        # Collect endpoint URLs
        for mode in ["testnet", "live"]:
            ep = self._get_endpoint_config(mode)
            evidence.endpoint_urls[mode] = {
                "rest": ep.rest_base_url,
                "ws_public": ep.ws_public_url,
                "ws_private": ep.ws_private_url,
            }

        # Collect auth results
        for r in results:
            if r.test_name.startswith("auth_"):
                mode = r.test_name.replace("auth_", "")
                evidence.auth_results[mode] = {
                    "success": r.success,
                    "latency_ms": r.latency_ms,
                    "error": r.error_message,
                    "timestamp": r.timestamp,
                }

        # Collect market data
        for r in results:
            if r.test_name.startswith("market_data_"):
                parts = r.test_name.split("_")
                if len(parts) >= 4:
                    mode = parts[2]
                    symbol = parts[3]
                    if symbol not in evidence.market_data:
                        evidence.market_data[symbol] = {}
                    evidence.market_data[symbol][mode] = {
                        "success": r.success,
                        "price": r.response_details.get("lastPrice"),
                        "latency_ms": r.latency_ms,
                        "timestamp": r.timestamp,
                    }

        # Collect latency measurements
        for r in results:
            evidence.latency_measurements[r.test_name] = {
                "latency_ms": r.latency_ms,
                "success": r.success,
                "timestamp": r.timestamp,
            }

        # Determine primary mode
        testnet_auth = evidence.auth_results.get("testnet", {}).get("success", False)
        live_auth = evidence.auth_results.get("live", {}).get("success", False)

        if testnet_auth:
            evidence.selected_primary = "testnet"
            evidence.notes.append(
                "Testnet authenticated successfully - selected as primary"
            )
        elif live_auth:
            evidence.selected_primary = "live"
            evidence.notes.append(
                "Testnet auth failed, live authenticated - selected live as primary"
            )
        else:
            # Check if public endpoints work
            testnet_connectivity = any(
                r.success for r in results if r.test_name == "connectivity_testnet"
            )
            if testnet_connectivity:
                evidence.selected_primary = "testnet (public only)"
                evidence.notes.append(
                    "No authenticated access, using testnet public endpoints"
                )
            else:
                evidence.selected_primary = "none"
                evidence.notes.append("CRITICAL: Both testnet and live failed")

        return evidence

    def save_evidence(self, evidence: Evidence, output_dir: str = "_bmad-output"):
        """Save evidence to file.

        Args:
            evidence: Evidence object
            output_dir: Directory to save evidence
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        filename = f"{evidence.test_run_id}-evidence.json"
        filepath = Path(output_dir) / filename

        evidence_dict = {
            "test_run_id": evidence.test_run_id,
            "timestamp": evidence.timestamp,
            "mode_tested": evidence.mode_tested,
            "endpoint_urls": evidence.endpoint_urls,
            "auth_results": evidence.auth_results,
            "market_data": evidence.market_data,
            "latency_measurements": evidence.latency_measurements,
            "selected_primary": evidence.selected_primary,
            "notes": evidence.notes,
        }

        with open(filepath, "w") as f:
            json.dump(evidence_dict, f, indent=2)

        print(f"\n📝 Evidence saved to: {filepath}")
        return filepath

    def print_summary(self, results: list[TestResult], evidence: Evidence):
        """Print test summary."""
        print(f"\n{'=' * 60}")
        print("📋 TEST SUMMARY")
        print(f"{'=' * 60}")

        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed

        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} {'⚠️' if failed > 0 else ''}")

        print(f"\n🔌 Endpoint URLs Tested:")
        for mode, urls in evidence.endpoint_urls.items():
            print(f"   {mode}:")
            print(f"      REST: {urls['rest']}")
            print(f"      WS Public: {urls['ws_public']}")
            print(f"      WS Private: {urls['ws_private']}")

        print(f"\n🔐 Authentication Results:")
        for mode, result in evidence.auth_results.items():
            status = "✅" if result["success"] else "❌"
            print(f"   {mode}: {status} {'OK' if result['success'] else 'FAILED'}")
            if not result["success"] and result["error"]:
                print(f"      Error: {result['error']}")

        print(f"\n📈 Market Data Evidence:")
        for symbol, modes in evidence.market_data.items():
            print(f"   {symbol}:")
            for mode, data in modes.items():
                status = "✅" if data["success"] else "❌"
                print(
                    f"      {mode}: {status} Price=${data.get('price', 'N/A')} ({data['latency_ms']:.2f}ms)"
                )

        print(f"\n⏱️  Latency Measurements:")
        threshold = (
            self.config.get("settings", {})
            .get("latency_threshold_ms", {})
            .get("market_data", 100)
        )
        for test_name, data in evidence.latency_measurements.items():
            status = "✅" if data["latency_ms"] < threshold else "⚠️"
            print(f"   {test_name}: {data['latency_ms']:.2f}ms {status}")

        print(f"\n🎯 Selected Primary Mode: {evidence.selected_primary}")

        if evidence.notes:
            print(f"\n📝 Notes:")
            for note in evidence.notes:
                print(f"   - {note}")

    async def run(self, mode: str = "both") -> int:
        """Run the full test harness.

        Args:
            mode: Test mode (testnet|live|both)

        Returns:
            Exit code (0=success, 1=partial, 2=critical)
        """
        print("=" * 60)
        print("🚀 BYBIT LIVE PROOF TEST HARNESS")
        print("=" * 60)
        print(f"Test Run ID: {self.evidence.test_run_id}")
        print(f"Timestamp: {self.evidence.timestamp}")
        print(f"API Key Present: {'Yes' if self.api_key else 'No'}")
        print(f"API Secret Present: {'Yes' if self.api_secret else 'No'}")

        all_results = []

        modes_to_test = []
        if mode == "both":
            modes_to_test = ["testnet", "live"]
        else:
            modes_to_test = [mode]

        self.evidence.mode_tested = ",".join(modes_to_test)

        for test_mode in modes_to_test:
            results = await self.run_mode_tests(test_mode)
            all_results.extend(results)

        # Compile and save evidence
        evidence = self.compile_evidence(all_results)
        self.save_evidence(evidence)

        # Print summary
        self.print_summary(all_results, evidence)

        # Determine exit code
        total_tests = len(all_results)
        passed_tests = sum(1 for r in all_results if r.success)

        # Check if both modes failed auth (critical)
        testnet_auth_ok = evidence.auth_results.get("testnet", {}).get("success", False)
        live_auth_ok = evidence.auth_results.get("live", {}).get("success", False)

        if not testnet_auth_ok and not live_auth_ok and self.api_key:
            print(f"\n❌ CRITICAL: Both testnet and live authentication failed")
            return 2
        elif passed_tests < total_tests:
            print(f"\n⚠️  WARNING: Some tests failed ({passed_tests}/{total_tests})")
            return 1
        else:
            print(f"\n✅ SUCCESS: All tests passed ({passed_tests}/{total_tests})")
            return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Bybit Live Proof Test Harness")
    parser.add_argument(
        "--mode",
        choices=["testnet", "live", "both"],
        default="both",
        help="Test mode (default: both)",
    )
    parser.add_argument(
        "--config", default="config/bybit_endpoints.yaml", help="Path to config file"
    )

    args = parser.parse_args()

    harness = BybitProofHarness(config_path=args.config)
    exit_code = asyncio.run(harness.run(mode=args.mode))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
