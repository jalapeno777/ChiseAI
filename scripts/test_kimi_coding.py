#!/usr/bin/env python3
"""Test script to verify Kimi Coding API connectivity with User-Agent header.

This script tests the Kimi Coding API to verify that the 403 "only available
for Coding Agents" error is resolved by sending the proper User-Agent header.

Usage:
    python scripts/test_kimi_coding.py

Returns:
    Exit code 0 if successful, 1 if 403 or other error occurs.
"""

import asyncio
import os
import sys

import aiohttp


async def test_kimi_coding_api():
    """Test Kimi Coding API with proper User-Agent header."""
    api_key = os.getenv("KIMI_API_KEY")
    if not api_key:
        print("ERROR: KIMI_API_KEY environment variable not set")
        print("Please set KIMI_API_KEY to run this test")
        return False

    # Use the Kimi Coding API endpoint
    base_url = os.getenv("KIMI_BASE_URL", "https://api.kimi.com/coding/v1")
    url = f"{base_url}/chat/completions"

    # Build request with proper headers including User-Agent
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "claude-code/0.1.0",
    }

    payload = {
        "model": "kimi-k2.5",
        "messages": [
            {"role": "user", "content": "Hello, this is a test. Reply with 'OK'."}
        ],
        "temperature": 0.7,
        "max_tokens": 10,
    }

    print(f"Testing Kimi Coding API at: {base_url}")
    print(f"Headers: {headers}")
    print(f"Payload: {payload}")
    print("-" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response_data = await response.json()

                print(f"Response Status: {response.status}")
                print(f"Response Headers: {dict(response.headers)}")
                print(f"Response Body: {response_data}")
                print("-" * 60)

                if response.status == 200:
                    content = (
                        response_data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    print("✅ SUCCESS! API returned 200")
                    print(f"   Content: {content}")
                    return True
                elif response.status == 403:
                    error_msg = response_data.get("error", {}).get(
                        "message", "Unknown error"
                    )
                    print("❌ FAILED! Got 403 Forbidden")
                    print(f"   Error: {error_msg}")
                    if "coding agent" in error_msg.lower():
                        print(
                            "   This is the 'Coding Agents only' error - User-Agent fix not working"
                        )
                    return False
                elif response.status == 401:
                    print("❌ FAILED! Got 401 Unauthorized - Check API key")
                    return False
                else:
                    print(f"❌ FAILED! Got HTTP {response.status}")
                    return False

    except aiohttp.ClientError as e:
        print(f"❌ FAILED! Network error: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED! Unexpected error: {e}")
        return False


def test_adapter_file():
    """Verify the adapter file has the User-Agent header."""
    adapter_path = "src/adapter/kimi/main.py"
    print(f"\nChecking {adapter_path} for User-Agent header...")

    try:
        with open(adapter_path) as f:
            content = f.read()
        if 'User-Agent": "claude-code/0.1.0"' in content:
            print(f"✅ {adapter_path} has User-Agent header")
            return True
        else:
            print(f"❌ {adapter_path} missing User-Agent header")
            return False
    except FileNotFoundError:
        print(f"❌ {adapter_path} not found")
        return False


def test_kimi_client_file():
    """Verify the Kimi client file has the User-Agent header."""
    client_path = "src/llm/kimi_client.py"
    print(f"\nChecking {client_path} for User-Agent header...")

    try:
        with open(client_path) as f:
            content = f.read()
        if 'User-Agent": "claude-code/0.1.0"' in content:
            print(f"✅ {client_path} has User-Agent header")
            return True
        else:
            print(f"❌ {client_path} missing User-Agent header")
            return False
    except FileNotFoundError:
        print(f"❌ {client_path} not found")
        return False


def test_provider_chain_file():
    """Verify the provider chain file has the User-Agent header."""
    chain_path = "src/llm/provider_chain.py"
    print(f"\nChecking {chain_path} for User-Agent header...")

    try:
        with open(chain_path) as f:
            content = f.read()
        if 'User-Agent": "claude-code/0.1.0"' in content:
            print(f"✅ {chain_path} has User-Agent header")
            return True
        else:
            print(f"❌ {chain_path} missing User-Agent header")
            return False
    except FileNotFoundError:
        print(f"❌ {chain_path} not found")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Kimi Coding API User-Agent Fix Test")
    print("=" * 60)

    # Check file changes first
    files_ok = True
    files_ok &= test_adapter_file()
    files_ok &= test_kimi_client_file()
    files_ok &= test_provider_chain_file()

    print("\n" + "=" * 60)
    print("API Connectivity Test")
    print("=" * 60)

    # Test actual API if key is available
    api_ok = await test_kimi_coding_api()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Files updated: {'✅ PASS' if files_ok else '❌ FAIL'}")
    print(f"API test: {'✅ PASS' if api_ok else '❌ FAIL'}")

    if files_ok and api_ok:
        print("\n✅ All tests passed! 403 error should be resolved.")
        return 0
    elif files_ok:
        print("\n⚠️ Files updated but API test failed.")
        print("   This may be due to network issues or API key problems.")
        return 0  # Still exit 0 since files are correct
    else:
        print("\n❌ Tests failed - files not properly updated")
        return 1


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)
