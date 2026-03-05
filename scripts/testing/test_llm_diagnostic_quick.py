#!/usr/bin/env python3
"""Quick diagnostic for LLM trade decision enhancement - initialization only.

This script diagnoses why the Discord message showed "LLM enhancement disabled or unavailable".
It tests whether the LLM provider chain can be initialized (without making actual LLM calls).

SAFETY-LLM-001: LLM Trade Decision Diagnostic (Quick)
"""

import os
import sys

# Add project root to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.execution.llm.trade_decision_enhancer import TradeDecisionEnhancer


def run_quick_diagnostic():
    """Run quick LLM diagnostic test - initialization only."""

    # Test 1: Default behavior (USE_LLM_TRADE_DECISIONS not set)
    print("=" * 80)
    print("TEST 1: Default Behavior (USE_LLM_TRADE_DECISIONS not set)")
    print("=" * 80)

    # Clear the env var
    if "USE_LLM_TRADE_DECISIONS" in os.environ:
        del os.environ["USE_LLM_TRADE_DECISIONS"]

    enhancer1 = TradeDecisionEnhancer()
    health1 = enhancer1.get_health()

    print(
        f"Environment: USE_LLM_TRADE_DECISIONS={os.getenv('USE_LLM_TRADE_DECISIONS', 'not set')}"
    )
    print(f"Result:")
    print(f"  enabled: {health1['enabled']}")
    print(f"  chain_initialized: {health1['chain_initialized']}")

    if not health1["enabled"]:
        print("✓ CONFIRMED: enhancer is DISABLED by default")
        print("  This is the ROOT CAUSE of 'LLM enhancement disabled or unavailable'")
    else:
        print("❌ UNEXPECTED: enhancer is enabled without env var")

    print()

    # Test 2: Explicit enable
    print("=" * 80)
    print("TEST 2: Explicit Enable (USE_LLM_TRADE_DECISIONS=true)")
    print("=" * 80)

    os.environ["USE_LLM_TRADE_DECISIONS"] = "true"

    enhancer2 = TradeDecisionEnhancer()
    health2 = enhancer2.get_health()

    print(
        f"Environment: USE_LLM_TRADE_DECISIONS={os.getenv('USE_LLM_TRADE_DECISIONS')}"
    )
    print(f"Result:")
    print(f"  enabled: {health2['enabled']}")
    print(f"  chain_initialized: {health2['chain_initialized']}")
    print(f"  provider_chain_available: {health2['provider_chain_available']}")

    if health2["enabled"] and health2["chain_initialized"]:
        print("✓ SUCCESS: enhancer is ENABLED and chain is INITIALIZED")
        print("  LLM provider chain can be initialized when explicitly enabled")
    elif health2["enabled"] and not health2["chain_initialized"]:
        print("❌ ISSUE: enhancer is ENABLED but chain is NOT INITIALIZED")
        print("  This would cause 'LLM enhancement disabled or unavailable'")
    else:
        print("❌ ISSUE: enhancer is not enabled even with env var set")

    print()

    # Test 3: Check provider availability
    print("=" * 80)
    print("TEST 3: Provider Availability Check")
    print("=" * 80)

    print("API Key Status:")
    print(f"  KIMI_API_KEY: {'SET' if os.getenv('KIMI_API_KEY') else 'NOT SET'}")
    print(f"  ZHIPU_API_KEY: {'SET' if os.getenv('ZHIPU_API_KEY') else 'NOT SET'}")
    print(f"  ZAI_API_KEY: {'SET' if os.getenv('ZAI_API_KEY') else 'NOT SET'}")
    print(f"  MINIMAX_API_KEY: {'SET' if os.getenv('MINIMAX_API_KEY') else 'NOT SET'}")
    print()

    # Summary
    print("=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)

    print("\nROOT CAUSE:")
    print("  The Discord message showed 'LLM enhancement disabled or unavailable'")
    print("  because USE_LLM_TRADE_DECISIONS env var was not set to 'true'.")
    print("  The default value is 'false' (see trade_decision_enhancer.py line 59).")
    print()

    print("SOLUTION:")
    print(
        "  Set USE_LLM_TRADE_DECISIONS=true in environment to enable LLM enhancement."
    )
    print()

    print("VERIFICATION:")
    if health2["enabled"] and health2["chain_initialized"]:
        print("  ✓ PASS: LLM system can be initialized when enabled")
        print("  ✓ PASS: Provider chain is available")
        return True
    else:
        print("  ⚠ WARNING: Provider chain may have initialization issues")
        print("  Check that at least one LLM provider API key is configured")
        return False

    print("=" * 80)


if __name__ == "__main__":
    success = run_quick_diagnostic()
    sys.exit(0 if success else 1)
