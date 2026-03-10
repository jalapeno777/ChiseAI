#!/usr/bin/env python3
"""Simplified LLM provider test - direct import and call.

This tests if individual providers can respond without timeouts or full provider chain.

SAFETY-LLM-001: LLM Provider direct test
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# Import providers directly
from llm.kimi_client import KimiClient
from llm.zai_client import ZaiClient
from llm.zhipu_client import ZhipuClient
from llm.minimax_client import MiniMaxClient


async def test_providers_directly():
    """Test each provider directly."""
    print("=" * 80)
    print("TESTING INDIVIDUAL LLM PROVIDERS")
    print("=" * 80)

    try:
        # Test KIMI
        print("Creating KimiClient...")
        kimi = KimiClient()
        result = await kimi.chat("Hello, this is a test 1.")

        # Test ZAI
        print("Creating ZaiClient...")
        zai = ZaiClient()
        result = await zai.chat("Hello, this is test 2.")

        # Test zhipu
        print("Creating ZhipuClient...")
        zhipu = ZhipuClient()
        result = await zhipu.chat("Hello, this is test 3.")

        # Test MiniMax
        print("Creating MiniMaxClient...")
        minimax = MiniMaxClient()
        result = await minimax.chat("Hello, this is test 4.")

        print("✅ All providers tested successfully")
        return True

    except asyncio.TimeoutError:
        print("❌ Test timed out after 15 seconds")
        return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_providers_directly())
    sys.exit(0 if success else 1)
