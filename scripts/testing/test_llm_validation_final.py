#!/usr/bin/env python3
"""Final validation test for LLM trade decision enhancement.

This script validates that the LLM system can respond with a real provider
when enabled, using a short timeout to avoid long waits.

SAFETY-LLM-001: LLM Trade Decision Validation
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any

# Add project root to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.execution.llm.trade_decision_enhancer import (
    TradeDecisionEnhancer,
    TradeDecision,
)


@dataclass
class MockSignal:
    """Mock trading signal for testing."""

    token: str = "BTCUSDT"
    symbol: str = "BTCUSDT"
    direction: str = "LONG"
    confidence: float = 0.75
    base_score: float = 0.82
    contributing_factors: list[dict[str, Any]] = None

    def __post_init__(self):
        if self.contributing_factors is None:
            self.contributing_factors = [
                {"name": "momentum", "score": 0.85},
                {"name": "volume", "score": 0.78},
                {"name": "trend", "score": 0.82},
            ]


async def run_validation():
    """Run LLM validation test with real provider call."""

    # Set environment variables
    os.environ["USE_LLM_TRADE_DECISIONS"] = "true"
    os.environ["LLM_DECISION_TIMEOUT_MS"] = "10000"  # 10 second timeout for testing

    print("=" * 80)
    print("LLM TRADE DECISION VALIDATION (WITH REAL PROVIDER CALL)")
    print("=" * 80)
    print()

    # Show environment
    print("Environment Settings:")
    print(f"  USE_LLM_TRADE_DECISIONS: {os.getenv('USE_LLM_TRADE_DECISIONS')}")
    print(f"  LLM_DECISION_TIMEOUT_MS: {os.getenv('LLM_DECISION_TIMEOUT_MS')}")
    print()

    # Create enhancer with explicit enable
    print("Creating TradeDecisionEnhancer with enabled=True...")
    enhancer = TradeDecisionEnhancer(enabled=True, timeout_ms=10000)

    # Check health
    health = enhancer.get_health()
    print(f"Enhancer Health:")
    print(f"  enabled: {health['enabled']}")
    print(f"  chain_initialized: {health['chain_initialized']}")
    print(f"  provider_chain_available: {health['provider_chain_available']}")
    print()

    # Verify enabled and chain
    if not health["enabled"]:
        print("❌ FAIL: enhancer.enabled is False (should be True)")
        return False

    if not health["chain_initialized"]:
        print("❌ FAIL: enhancer._chain is None (chain failed to initialize)")
        print("   This indicates LLM provider chain initialization failure")
        return False

    print("✓ Enhancer is enabled and chain is initialized")
    print()

    # Create mock signal
    signal = MockSignal()
    print(f"Testing with mock signal: {signal.symbol} {signal.direction}")
    print()

    # Test enhancement with timeout
    print("Calling enhance_decision() with 10s timeout...")
    print("(This will attempt to query real LLM providers)")
    print()

    try:
        result = await asyncio.wait_for(
            enhancer.enhance_decision(signal),
            timeout=15.0,  # Slightly longer than internal timeout
        )

        print(f"✓ Received response from enhancer")
        print()
        print(f"Result:")
        print(f"  go_no_go: {result.go_no_go}")
        print(f"  confidence: {result.confidence}")
        print(f"  provider: {result.provider}")
        print(f"  fallback_used: {result.fallback_used}")
        print(f"  latency_ms: {result.latency_ms:.2f}")
        print(
            f"  rationale: {result.rationale[:150]}..."
            if len(result.rationale) > 150
            else f"  rationale: {result.rationale}"
        )
        print()

        # Validate result
        issues = []

        # Check provider
        if result.provider == "none":
            issues.append(
                "provider is 'none' (indicates enhancer was disabled or chain was None)"
            )

        # Check confidence
        if result.confidence is None or result.confidence < 0:
            issues.append("confidence is missing or invalid")

        # Check rationale
        if result.rationale == "LLM enhancement disabled or unavailable":
            issues.append(
                "rationale shows 'disabled or unavailable' (indicates enhancer was disabled or chain was None)"
            )

        # Check for actual LLM response
        if result.provider in ["timeout", "error"]:
            issues.append(
                f"provider is '{result.provider}' (indicates LLM call failed)"
            )

        if issues:
            print("❌ VALIDATION FAILED:")
            for issue in issues:
                print(f"   - {issue}")
            print()
            print("This indicates the LLM system is NOT functioning correctly")
            return False

        print("✓ Result validation passed")
        print()

        # Success!
        print("=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        print(f"✓ Provider responded: {result.provider}")
        print(f"✓ Confidence: {result.confidence}")
        print(f"✓ Latency: {result.latency_ms:.2f}ms")
        print(f"✓ Fallback used: {result.fallback_used}")
        print()

        if result.fallback_used:
            print("NOTE: Fallback provider was used (not primary KIMI)")
            print("This is acceptable but indicates primary provider may have issues")
        else:
            print("✓ Primary provider (KIMI) responded successfully")

        print()
        print("VERDICT: ✓ PASS - LLM system functioning correctly")
        print("=" * 80)

        return True

    except asyncio.TimeoutError:
        print("❌ FAIL: Test timed out after 15 seconds")
        print("   This indicates LLM providers are not responding")
        return False

    except Exception as e:
        print(f"❌ FAIL: Exception during enhance_decision(): {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_validation())
    sys.exit(0 if success else 1)
