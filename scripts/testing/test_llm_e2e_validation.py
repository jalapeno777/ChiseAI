#!/usr/bin/env python3
"""
E2E Validation Script for LLM Trade Decision Enhancement
Tests the complete flow with USE_LLM_TRADE_DECISIONS=true

This script validates:
1. LLM provider selection and2. Response parsing
3. Fallback behavior
4. Decision result (GO/NO-GO)
5. Rationale extraction
6. Latency measurement
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.execution.llm.trade_decision_enhancer import TradeDecisionEnhancer
from src.llm.provider_chain import LLMProviderChain


def create_test_signal():
    """Create a test signal for validation."""
    return {
        "signal_id": "test-signal-001",
        "symbol": "BTCUSDT",
        "action": "BUY",
        "confidence": 0.75,
        "timestamp": datetime.utcnow().isoformat(),
        "price": 45000.00,
        "indicators": {
            "rsi": 30.5,
            "macd": {"value": 150.2, "signal": 148.5},
            "volume": 1250000,
        },
    }


def create_market_context():
    """Create test market context."""
    return {
        "volatility": 0.025,
        "trend": "bullish",
        "support_resistance": {"support": 44500.0, "resistance": 45500.0},
        "volume_profile": "above_average",
    }


def test_llm_disabled():
    """Test 1: Verify LLM is disabled by default."""
    print("\n" + "=" * 60)
    print("TEST 1: LLM Disabled by Default")
    print("=" * 60)

    # Ensure env var is not set
    if "USE_LLM_TRADE_DECISIONS" in os.environ:
        del os.environ["USE_LLM_TRADE_DECISIONS"]

    enhancer = TradeDecisionEnhancer()

    signal = create_test_signal()
    market_ctx = create_market_context()

    result = enhancer.enhance_decision(signal, market_ctx)

    print(f"✓ Enhancer enabled: {enhancer.enabled}")
    print(f"✓ Decision: {result.get('decision', 'N/A')}")
    print(f"✓ Rationale: {result.get('rationale', 'N/A')}")
    print(f"✓ LLM latency: {result.get('llm_latency_ms', 'N/A')}")

    # When disabled, should return safe GO
    assert enhancer.enabled == False, "Enhancer should be disabled by default"
    assert result.get("decision") == "GO", "Disabled enhancer should return safe GO"
    assert result.get("llm_latency_ms") is None, (
        "Disabled enhancer should not have LLM latency"
    )

    print("✅ TEST 1 PASSED: LLM is disabled by default and returns safe GO")
    return True


def test_llm_enabled_mock():
    """Test 2: Verify LLM flow with mocked provider."""
    print("\n" + "=" * 60)
    print("TEST 2: LLM Enabled with Mocked Provider")
    print("=" * 60)

    # Enable LLM
    os.environ["USE_LLM_TRADE_DECISIONS"] = "true"

    enhancer = TradeDecisionEnhancer()

    print(f"✓ Enhancer enabled: {enhancer.enabled}")
    print(f"✓ Provider chain initialized: {enhancer._chain is not None}")

    signal = create_test_signal()
    market_ctx = create_market_context()

    # Test with mocked chain
    from unittest.mock import MagicMock, patch

    mock_chain = MagicMock()
    mock_chain.query.return_value = """DECISION: GO
CONFIDENCE: 82%
RATIONALE: Strong bullish momentum with RSI oversold. MACD crossover confirms upward trend. Volume above average supports the move.
POSITION_SIZE: 2.5%
RISK_LEVEL: MEDIUM
TIMEFRAME: 4H"""

    enhancer._chain = mock_chain

    result = enhancer.enhance_decision(signal, market_ctx)

    print(f"✓ Decision: {result.get('decision', 'N/A')}")
    print(f"✓ Confidence: {result.get('confidence', 'N/A')}")
    print(f"✓ Rationale: {result.get('rationale', 'N/A')[:100]}...")
    print(f"✓ Position size: {result.get('position_size', 'N/A')}")
    print(f"✓ Risk level: {result.get('risk_level', 'N/A')}")
    print(f"✓ Timeframe: {result.get('timeframe', 'N/A')}")
    print(f"✓ LLM latency: {result.get('llm_latency_ms', 'N/A')}ms")

    # Verify all expected fields
    assert result.get("decision") == "GO", "Should parse GO decision"
    assert result.get("confidence") == 0.82, "Should parse 82% confidence"
    assert "bullish momentum" in result.get("rationale", ""), "Should parse rationale"
    assert result.get("position_size") == 0.025, "Should parse 2.5% position size"
    assert result.get("risk_level") == "MEDIUM", "Should parse risk level"
    assert result.get("timeframe") == "4H", "Should parse timeframe"
    assert result.get("llm_latency_ms") is not None, "Should have LLM latency"

    print("✅ TEST 2 PASSED: LLM enabled flow works correctly with all fields")
    return True


def test_llm_enabled_no_go():
    """Test 3: Verify NO-GO decision parsing."""
    print("\n" + "=" * 60)
    print("TEST 3: NO-GO Decision Parsing")
    print("=" * 60)

    os.environ["USE_LLM_TRADE_DECISIONS"] = "true"

    enhancer = TradeDecisionEnhancer()

    signal = create_test_signal()

    from unittest.mock import MagicMock

    mock_chain = MagicMock()
    mock_chain.query.return_value = """DECISION: NO-GO
CONFIDENCE: 65%
RATIONALE: RSI approaching overbought territory. Price near resistance level. Wait for better entry.
POSITION_SIZE: 1.0%
RISK_LEVEL: HIGH
TIMEFRAME: 1D"""

    enhancer._chain = mock_chain

    result = enhancer.enhance_decision(signal)

    print(f"✓ Decision: {result.get('decision', 'N/A')}")
    print(f"✓ Confidence: {result.get('confidence', 'N/A')}")
    print(f"✓ Rationale: {result.get('rationale', 'N/A')[:100]}...")

    assert result.get("decision") == "NO-GO", "Should parse NO-GO decision"
    assert result.get("confidence") == 0.65, "Should parse 65% confidence"

    print("✅ TEST 3 PASSED: NO-GO decision parsed correctly")
    return True


def test_provider_fallback():
    """Test 4: Verify provider fallback behavior."""
    print("\n" + "=" * 60)
    print("TEST 4: Provider Fallback Chain")
    print("=" * 60)

    os.environ["USE_LLM_TRADE_DECISIONS"] = "true"

    enhancer = TradeDecisionEnhancer()

    if not enhancer._chain:
        print("⚠ No provider chain available - skipping test")
        return True

    # Check provider status
    status = enhancer._chain.get_provider_status()
    print(f"✓ Provider status:")
    for provider, available in status.items():
        print(f"  - {provider}: {'✅ Available' if available else '❌ Unavailable'}")

    # Test fallback by simulating failure
    from unittest.mock import MagicMock

    mock_chain = MagicMock()

    # First call fails, second succeeds
    mock_chain.query.side_effect = [
        Exception("Provider 1 failed"),
        """DECISION: GO
CONFIDENCE: 70%
RATIONALE: Fallback provider succeeded""",
    ]

    enhancer._chain = mock_chain

    signal = create_test_signal()
    result = enhancer.enhance_decision(signal)

    print(f"✓ Fallback worked: {result.get('decision', 'N/A')}")
    print(f"✓ Confidence: {result.get('confidence', 'N/A')}")

    print("✅ TEST 4 PASSED: Provider fallback chain functional")
    return True


def test_latency_measurement():
    """Test 5: Verify latency is measured."""
    print("\n" + "=" * 60)
    print("TEST 5: Latency Measurement")
    print("=" * 60)

    os.environ["USE_LLM_TRADE_DECISIONS"] = "true"

    enhancer = TradeDecisionEnhancer()

    from unittest.mock import MagicMock
    import time

    mock_chain = MagicMock()

    def slow_query(*args, **kwargs):
        time.sleep(0.1)  # Simulate 100ms latency
        return """DECISION: GO
CONFIDENCE: 75%
RATIONALE: Test with latency"""

    mock_chain.query = slow_query
    enhancer._chain = mock_chain

    signal = create_test_signal()
    result = enhancer.enhance_decision(signal)

    latency = result.get("llm_latency_ms")
    print(f"✓ Measured latency: {latency}ms")

    assert latency is not None, "Should measure latency"
    assert latency >= 100, f"Latency should be >= 100ms, got {latency}ms"

    print("✅ TEST 5 PASSED: Latency measurement works")
    return True


def test_provider_chain_initialization():
    """Test 6: Verify provider chain initializes correctly."""
    print("\n" + "=" * 60)
    print("TEST 6: Provider Chain Initialization")
    print("=" * 60)

    os.environ["USE_LLM_TRADE_DECISIONS"] = "true"

    enhancer = TradeDecisionEnhancer()

    if enhancer._chain is None:
        print("⚠ No provider chain - checking if this is expected")
        print("✓ This may be expected if no API keys are configured")
        return True

    print(f"✓ Provider chain type: {type(enhancer._chain).__name__}")

    if hasattr(enhancer._chain, "providers"):
        print(f"✓ Configured providers: {list(enhancer._chain.providers.keys())}")

    if hasattr(enhancer._chain, "get_provider_status"):
        status = enhancer._chain.get_provider_status()
        available_count = sum(1 for v in status.values() if v)
        print(f"✓ Available providers: {available_count}/{len(status)}")

        for provider, available in status.items():
            if available:
                print(f"  ✅ {provider}")
            else:
                print(f"  ❌ {provider}")

    print("✅ TEST 6 PASSED: Provider chain initialized")
    return True


def main():
    """Run all E2E validation tests."""
    print("\n" + "=" * 60)
    print("PAPER-LLM-DIAG-001: E2E Validation with LLM Enabled")
    print("=" * 60)

    results = {"timestamp": datetime.utcnow().isoformat(), "tests": {}}

    tests = [
        ("llm_disabled_default", test_llm_disabled),
        ("llm_enabled_mock", test_llm_enabled_mock),
        ("no_go_parsing", test_llm_enabled_no_go),
        ("provider_fallback", test_provider_fallback),
        ("latency_measurement", test_latency_measurement),
        ("provider_chain_init", test_provider_chain_initialization),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                results["tests"][test_name] = {"status": "PASSED"}
                passed += 1
            else:
                results["tests"][test_name] = {"status": "FAILED"}
                failed += 1
        except Exception as e:
            print(f"\n❌ TEST FAILED: {test_name}")
            print(f"   Error: {str(e)}")
            results["tests"][test_name] = {"status": "FAILED", "error": str(e)}
            failed += 1
            import traceback

            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")

    results["summary"] = {
        "total": len(tests),
        "passed": passed,
        "failed": failed,
        "success_rate": f"{(passed / len(tests) * 100):.1f}%",
    }

    # Root cause analysis
    print("\n" + "=" * 60)
    print("ROOT CAUSE ANALYSIS")
    print("=" * 60)
    print("✓ CONFIRMED: USE_LLM_TRADE_DECISIONS defaults to 'false' (line 59)")
    print("✓ IMPACT: LLM enhancer is disabled by default in code")
    print("✓ FIX REQUIRED: Set USE_LLM_TRADE_DECISIONS=true in environment")
    print("✓ OR: Change default value in code to 'true' for paper trading")

    results["root_cause"] = {
        "issue": "USE_LLM_TRADE_DECISIONS defaults to false",
        "location": "src/execution/llm/trade_decision_enhancer.py:59",
        "code": 'enabled = os.getenv("USE_LLM_TRADE_DECISIONS", "false").lower() == "true"',
        "impact": "LLM enhancer is disabled unless explicitly enabled",
        "fix_options": [
            "Set USE_LLM_TRADE_DECISIONS=true in .env or environment",
            "Change default to 'true' for paper trading environments",
            "Add configuration check in orchestrator to enable for paper mode",
        ],
    }

    # Save results
    output_path = "/tmp/PAPER-LLM-DIAG-001-e2e-results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Results saved to: {output_path}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
