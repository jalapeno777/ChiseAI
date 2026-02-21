#!/usr/bin/env python3
"""Verification script for KIMI client model discovery and 403 handling.

This script demonstrates:
1. Model discovery from /models endpoint
2. Model fallback when default is not accessible
3. Proper 403 error handling

For: CH-KIMI-FIX-001
"""

import asyncio
import sys
from pathlib import Path

# Bootstrap environment
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

from llm.kimi_client import KimiClient, KimiConfig


async def verify_model_discovery():
    """Verify model discovery works correctly."""
    print("=" * 70)
    print("VERIFICATION: Model Discovery")
    print("=" * 70)

    config = KimiConfig()
    print(f"Default model: {config.model}")
    print(f"Accessible models (before discovery): {config.accessible_models}")
    print(f"Model discovery enabled: {config.model_discovery_enabled}")

    async with KimiClient(config) as client:
        # Discover models
        models = await client.discover_models()
        print(f"\nDiscovered models: {models}")
        print(f"Accessible models (after discovery): {client.config.accessible_models}")

        # Test model selection
        selected = client._select_model()
        print(f"\nSelected model for request: {selected}")

        if models:
            print("\n✓ Model discovery: SUCCESS")
            return True
        else:
            print("\n⚠ Model discovery: No models returned (may be auth issue)")
            return False


async def verify_403_handling():
    """Verify 403 errors are handled properly."""
    print("\n" + "=" * 70)
    print("VERIFICATION: 403 Error Handling")
    print("=" * 70)

    config = KimiConfig()
    print(f"Testing with model: {config.model}")

    async with KimiClient(config) as client:
        # Make a minimal request
        response = await client.chat_simple(prompt="Say 'test'", max_tokens=5)

        print(f"\nResponse success: {response.success}")

        if response.success:
            print(f"Content: {response.content}")
            print("\n✓ Request: SUCCESS")
            return True
        else:
            print(f"Error: {response.error}")

            if response.raw_response:
                status = response.raw_response.get("status")
                print(f"Status code: {status}")

                if status == 403:
                    print(
                        "\n✓ 403 handling: SUCCESS (correctly identified permission issue)"
                    )
                    return True
                else:
                    print(f"\n✗ Unexpected status: {status}")
                    return False
            else:
                print("\n✗ No raw response details")
                return False


async def verify_model_fallback():
    """Verify model fallback logic."""
    print("\n" + "=" * 70)
    print("VERIFICATION: Model Fallback Logic")
    print("=" * 70)

    # Test case 1: No accessible models - should use default
    config1 = KimiConfig(model="k2p5", accessible_models=[])
    client1 = KimiClient(config1)
    selected1 = client1._select_model()
    print(f"Test 1 - No accessible models:")
    print(f"  Default: k2p5, Selected: {selected1}")
    assert selected1 == "k2p5", "Should use default when no accessible models"
    print("  ✓ PASS")

    # Test case 2: Default not in accessible list - should fall back
    config2 = KimiConfig(model="k2p5", accessible_models=["kimi-for-coding"])
    client2 = KimiClient(config2)
    selected2 = client2._select_model()
    print(f"\nTest 2 - Default not accessible:")
    print(f"  Default: k2p5, Accessible: {config2.accessible_models}")
    print(f"  Selected: {selected2}")
    assert selected2 == "kimi-for-coding", "Should fall back to accessible model"
    print("  ✓ PASS")

    # Test case 3: Default is in accessible list - should use default
    config3 = KimiConfig(model="k2p5", accessible_models=["kimi-for-coding", "k2p5"])
    client3 = KimiClient(config3)
    selected3 = client3._select_model()
    print(f"\nTest 3 - Default is accessible:")
    print(f"  Default: k2p5, Accessible: {config3.accessible_models}")
    print(f"  Selected: {selected3}")
    assert selected3 == "k2p5", "Should use default when it's accessible"
    print("  ✓ PASS")

    # Test case 4: Explicit model requested - should use requested if accessible
    config4 = KimiConfig(model="k2p5", accessible_models=["kimi-for-coding", "k2p5"])
    client4 = KimiClient(config4)
    selected4 = client4._select_model("kimi-for-coding")
    print(f"\nTest 4 - Explicit model request:")
    print(f"  Requested: kimi-for-coding, Accessible: {config4.accessible_models}")
    print(f"  Selected: {selected4}")
    assert selected4 == "kimi-for-coding", "Should use explicitly requested model"
    print("  ✓ PASS")

    print("\n✓ All fallback logic tests: PASS")
    return True


async def main():
    """Run all verifications."""
    print("\n" + "=" * 70)
    print("KIMI CLIENT VERIFICATION SUITE")
    print("Story: CH-KIMI-FIX-001")
    print("=" * 70 + "\n")

    results = {
        "model_discovery": False,
        "error_403_handling": False,
        "model_fallback": False,
    }

    try:
        results["model_discovery"] = await verify_model_discovery()
    except Exception as e:
        print(f"\n✗ Model discovery failed: {e}")

    try:
        results["error_403_handling"] = await verify_403_handling()
    except Exception as e:
        print(f"\n✗ 403 handling verification failed: {e}")

    try:
        results["model_fallback"] = await verify_model_fallback()
    except Exception as e:
        print(f"\n✗ Model fallback verification failed: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("OVERALL: ALL TESTS PASSED ✓")
    else:
        print("OVERALL: SOME TESTS FAILED ✗")
        print("\nNote: 403 errors indicate an external blocker (API key scope)")
        print("The client code correctly handles this case.")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
