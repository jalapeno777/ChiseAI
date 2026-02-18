#!/usr/bin/env python3
"""
Bybit API Authentication Test Script
Tests real authentication on both Testnet and Live endpoints.

For SAFETY-BYBIT-AUTH: Credential Resolution Fix
"""

import hashlib
import hmac
import json
import os
import sys
import time
from datetime import UTC, datetime

# Add src to path for credential resolver
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config.bootstrap import bootstrap

# Bootstrap environment first (must be before any env access)
bootstrap(load_env=True)

from data.exchange.credential_resolver import (
    get_credential_resolution_status,
    resolve_bybit_credentials,
)

# Try to use requests, fall back to urllib
try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.error
    import urllib.request

ENDPOINTS = {
    "testnet": {"url": "https://api-testnet.bybit.com", "name": "Testnet/Sandbox"},
    "live": {"url": "https://api.bybit.com", "name": "Live Account"},
    "demo": {"url": "https://api-demo.bybit.com", "name": "Demo Account"},
}

TEST_ENDPOINTS = ["/v5/account/wallet-balance", "/v5/position/list"]


def generate_signature(api_secret, timestamp, api_key, recv_window="10000"):
    """Generate Bybit API signature."""
    param_str = f"{timestamp}{api_key}{recv_window}"
    signature = hmac.new(
        api_secret.encode("utf-8"), param_str.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return signature


def get_server_timestamp(base_url):
    """Get server timestamp for synchronization."""
    try:
        url = f"{base_url}/v5/market/time"
        if HAS_REQUESTS:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Try timeNano first (in nanoseconds, convert to milliseconds)
                time_nano = data.get("result", {}).get("timeNano", 0)
                if time_nano:
                    return int(time_nano) // 1000000
                # Fall back to timeSecond (in seconds, convert to milliseconds)
                time_sec = data.get("result", {}).get("timeSecond", 0)
                if time_sec:
                    return int(time_sec) * 1000
        else:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                time_nano = data.get("result", {}).get("timeNano", 0)
                if time_nano:
                    return int(time_nano) // 1000000
                time_sec = data.get("result", {}).get("timeSecond", 0)
                if time_sec:
                    return int(time_sec) * 1000
    except Exception as e:
        print(f"    Warning: Could not sync with server time: {e}")
    return None


def test_endpoint_http_lib(base_url, endpoint, api_key, api_secret):
    """Test endpoint using urllib (no requests dependency)."""
    # Try to sync with server time first
    server_time = get_server_timestamp(base_url)
    if server_time:
        timestamp = str(int(server_time))
    else:
        timestamp = str(int(time.time() * 1000))

    recv_window = "10000"
    signature = generate_signature(api_secret, timestamp, api_key, recv_window)

    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json",
    }

    url = f"{base_url}{endpoint}"
    start_time = time.time()

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            latency_ms = int((time.time() - start_time) * 1000)

            # Check retCode in response to determine actual success
            ret_code = None
            try:
                response_data = json.loads(response_body)
                ret_code = response_data.get("retCode", -1)
                is_api_success = ret_code == 0
                api_error = (
                    response_data.get("retMsg", "Unknown error")
                    if not is_api_success
                    else None
                )
            except Exception:
                is_api_success = response.status == 200
                api_error = None if is_api_success else f"HTTP {response.status}"

            return {
                "status": "success" if is_api_success else "fail",
                "http_code": response.status,
                "latency_ms": latency_ms,
                "response_excerpt": sanitize_response(response_body),
                "error": api_error,
                "ret_code": ret_code if not is_api_success else 0,
            }
    except urllib.error.HTTPError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        # Parse retCode from error response
        ret_code = None
        try:
            error_data = json.loads(error_body)
            ret_code = error_data.get("retCode")
        except Exception:
            pass
        return {
            "status": "fail",
            "http_code": e.code,
            "latency_ms": latency_ms,
            "response_excerpt": sanitize_response(error_body),
            "error": f"HTTP {e.code}: {e.reason}",
            "ret_code": ret_code,
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "status": "fail",
            "http_code": 0,
            "latency_ms": latency_ms,
            "response_excerpt": None,
            "error": str(e),
            "ret_code": None,
        }


def test_endpoint_requests(base_url, endpoint, api_key, api_secret):
    """Test endpoint using requests library."""
    # Try to sync with server time first
    server_time = get_server_timestamp(base_url)
    if server_time:
        timestamp = str(int(server_time))
    else:
        timestamp = str(int(time.time() * 1000))

    recv_window = "10000"
    signature = generate_signature(api_secret, timestamp, api_key, recv_window)

    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json",
    }

    url = f"{base_url}{endpoint}"
    start_time = time.time()

    try:
        response = requests.get(url, headers=headers, timeout=10)
        latency_ms = int((time.time() - start_time) * 1000)

        # Check retCode in response to determine actual success
        ret_code = None
        try:
            response_data = response.json()
            ret_code = response_data.get("retCode", -1)
            is_api_success = ret_code == 0
            api_error = (
                response_data.get("retMsg", "Unknown error")
                if not is_api_success
                else None
            )
        except Exception:
            is_api_success = response.status_code == 200
            api_error = None if is_api_success else f"HTTP {response.status_code}"

        return {
            "status": "success" if is_api_success else "fail",
            "http_code": response.status_code,
            "latency_ms": latency_ms,
            "response_excerpt": sanitize_response(response.text),
            "error": api_error,
            "ret_code": ret_code if not is_api_success else 0,
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "status": "fail",
            "http_code": 0,
            "latency_ms": latency_ms,
            "response_excerpt": None,
            "error": str(e),
            "ret_code": None,
        }


def sanitize_response(response_text):
    """Sanitize response to remove sensitive data while preserving structure."""
    if not response_text:
        return None

    try:
        data = json.loads(response_text)
        # Mask any potentially sensitive fields
        if isinstance(data, dict):
            for key in list(data.keys()):
                if any(
                    sensitive in key.lower()
                    for sensitive in ["key", "secret", "token", "password", "signature"]
                ):
                    data[key] = "[MASKED]"
        return json.dumps(data, indent=2)
    except json.JSONDecodeError:
        # If not valid JSON, return truncated text
        if len(response_text) > 500:
            return response_text[:500] + "... [truncated]"
        return response_text


def run_auth_tests():
    """Run authentication tests on both endpoints."""
    print("=" * 70)
    print("BYBIT API AUTHENTICATION TEST")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print()

    # Step 1: Get credential resolution status
    print("-" * 70)
    print("CREDENTIAL RESOLUTION")
    print("-" * 70)

    cred_status = get_credential_resolution_status()

    print(f"Env file loaded: {cred_status['env_file_loaded']}")
    print(f"Env file path: {cred_status['env_file_path']}")
    print()
    print("Checked credential pairs (in priority order):")
    for check in cred_status["checks"]:
        status_icon = "✅" if check["complete"] else "❌"
        print(
            f"  {status_icon} {check['key_var']}: "
            f"key={'✓' if check['key_present'] else '✗'}, "
            f"secret={'✓' if check['secret_present'] else '✗'}"
        )
    print()

    # Step 2: Resolve credentials
    credentials = resolve_bybit_credentials()
    credentials_present = credentials is not None

    if credentials_present:
        print("✅ Credentials resolved successfully")
        print(f"   Source: {credentials.source}")
        print(f"   Testnet mode: {credentials.testnet_mode}")
        print(f"   API Key (masked): {credentials.get_masked_key()}")
        print(f"   API Secret (masked): {credentials.get_masked_secret()}")
        print()
    else:
        print("❌ BLOCKED: No credentials available")
        print("\nChecked credential pairs (in priority order):")
        for check in cred_status["checks"]:
            print(f"  - {check['key_var']} / {check['secret_var']}")
        return {
            "credentials_source": "none",
            "credentials_present": False,
            "testnet": None,
            "live": None,
            "selected_mode": None,
            "selection_reason": "BLOCKED: No credentials available",
            "credential_resolution": cred_status,
        }

    # Choose test function
    test_func = test_endpoint_requests if HAS_REQUESTS else test_endpoint_http_lib
    print(f"Using: {'requests' if HAS_REQUESTS else 'urllib'} library")
    print()

    results = {
        "credentials_source": credentials.source,
        "credentials_present": True,
        "credentials_masked_key": credentials.get_masked_key(),
        "testnet_mode": credentials.testnet_mode,
        "env_file_loaded": credentials.env_file_loaded,
        "testnet": {},
        "live": {},
        "demo": {},
    }

    # Test each endpoint mode
    for mode, config in ENDPOINTS.items():
        print(f"\n{'=' * 70}")
        print(f"Testing {config['name']} ({mode})")
        print(f"Base URL: {config['url']}")
        print("=" * 70)

        mode_results = {"url": config["url"], "auth_tests": []}

        any_success = False
        ret_code_10003_seen = False

        for endpoint in TEST_ENDPOINTS:
            print(f"\n  Testing {endpoint}...")
            result = test_func(
                config["url"],
                endpoint,
                credentials.api_key,
                credentials.api_secret,
            )

            test_result = {"endpoint": endpoint, **result}
            mode_results["auth_tests"].append(test_result)

            status_icon = "✅" if result["status"] == "success" else "❌"
            print(f"    {status_icon} Status: {result['status']}")
            print(f"       HTTP Code: {result['http_code']}")
            print(f"       Latency: {result['latency_ms']}ms")

            if result["error"]:
                print(f"       Error: {result['error']}")
                if result.get("ret_code") == 10003:
                    ret_code_10003_seen = True
                    print("       ⚠️  retCode 10003: Invalid API key")

            if result["status"] == "success":
                any_success = True

            # Small delay between requests
            time.sleep(0.5)

        results[mode] = mode_results
        mode_results["overall_status"] = "success" if any_success else "fail"
        mode_results["ret_code_10003_seen"] = ret_code_10003_seen

    # Determine selected mode
    testnet_success = results.get("testnet", {}).get("overall_status") == "success"
    live_success = results.get("live", {}).get("overall_status") == "success"
    demo_success = results.get("demo", {}).get("overall_status") == "success"
    testnet_ret10003 = results.get("testnet", {}).get("ret_code_10003_seen", False)
    live_ret10003 = results.get("live", {}).get("ret_code_10003_seen", False)
    demo_ret10003 = results.get("demo", {}).get("ret_code_10003_seen", False)

    if demo_success:
        selected_mode = "demo"
        selection_reason = "Demo authentication successful"
    elif testnet_success and live_success:
        selected_mode = "testnet"
        selection_reason = (
            "Both modes work; testnet selected as safer default for development"
        )
    elif testnet_success:
        selected_mode = "testnet"
        selection_reason = "Testnet authentication successful, live/demo failed"
    elif live_success:
        selected_mode = "live"
        selection_reason = "Live authentication successful, testnet/demo failed"
    else:
        selected_mode = None
        if testnet_ret10003 or live_ret10003 or demo_ret10003:
            selection_reason = "Authentication failed with retCode 10003 (invalid key)"
        else:
            selection_reason = "All endpoint authentication attempts failed"

    results["selected_mode"] = selected_mode
    results["selection_reason"] = selection_reason
    results["ret_code_10003_seen"] = testnet_ret10003 or live_ret10003 or demo_ret10003

    # Add diagnostic info to results
    results["diagnostics"] = {
        "credentials_checked": [
            "Environment variables: BYBIT_DEMO_API_KEY, BYBIT_DEMO_API_SECRET",
            "Environment variables: BYBIT_API_KEY, BYBIT_API_SECRET",
            "Environment variables: BYBIT_TESTNET_API_KEY, BYBIT_TESTNET_API_SECRET",
            ".env file in repo root (explicitly loaded)",
        ],
        "ret_code_10003_analysis": (
            {
                "meaning": "Invalid API key or signature",
                "common_causes": [
                    "API key is expired or revoked",
                    "API key is for wrong environment (testnet vs live)",
                    "Signature generation issue (timestamp sync, encoding)",
                    "API key permissions insufficient",
                    "IP restrictions enabled but current IP not whitelisted",
                ],
                "credential_source_used": credentials.source if credentials else None,
                "recommended_actions": [
                    f"Verify {credentials.source} is valid and active in Bybit portal",
                    "Check if key is for testnet or live environment",
                    "Ensure system time is synchronized (NTP enabled)",
                    "Verify API key has 'Read' permissions for Account and Position",
                    "Check IP whitelist settings in Bybit API management",
                    "Try generating new API keys if issues persist",
                ],
            }
            if (testnet_ret10003 or live_ret10003 or demo_ret10003)
            else None
        ),
        "failure_analysis": (
            None
            if (testnet_success or live_success or demo_success)
            else {
                "issue": "Credentials found but authentication failed on all endpoints",
                "possible_causes": [
                    "API keys are expired or revoked",
                    "API keys are for a different account/environment",
                    "API keys need IP whitelisting",
                    "Demo account keys may need specific configuration",
                ],
                "recommended_actions": [
                    "Verify API keys are active in Bybit account settings",
                    "Generate new API keys if necessary",
                    "Check if IP restrictions are enabled",
                    "Ensure keys have required permissions (read account, positions)",
                ],
            }
        ),
    }

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"Testnet Status: {'✅ SUCCESS' if testnet_success else '❌ FAIL'}")
    print(f"Live Status: {'✅ SUCCESS' if live_success else '❌ FAIL'}")
    print(f"Demo Status: {'✅ SUCCESS' if demo_success else '❌ FAIL'}")
    print(f"\nSelected Mode: {selected_mode or 'NONE'}")
    print(f"Reason: {selection_reason}")

    if testnet_ret10003 or live_ret10003 or demo_ret10003:
        print("\n⚠️  retCode 10003 (Invalid Key) detected!")
        print("   This usually means the API key is invalid for the environment.")
        print(f"   Key source used: {credentials.source}")
        print(f"   Masked key: {credentials.get_masked_key()}")

    # Add diagnostic info
    if not testnet_success and not live_success and not demo_success:
        print("\n📋 Diagnostic Information:")
        if testnet_ret10003 or live_ret10003 or demo_ret10003:
            print("  Authentication failed with retCode 10003 (invalid key)")
            print("  Common causes:")
            print("    - API key is expired or revoked")
            print("    - API key is for wrong environment (testnet vs live)")
            print("    - Signature generation issue (timestamp sync)")
            print("    - IP restrictions enabled")
            print("\n  Recommended actions:")
            print(f"    1. Verify {credentials.source} is valid in Bybit portal")
            print("    2. Check if key is for testnet or live environment")
            print("    3. Ensure system time is synchronized (NTP)")
            print("    4. Verify API key permissions")
            print("    5. Check IP whitelist settings")
        else:
            print("  Credentials were found but authentication failed.")
            print("  See failure_analysis in output for details.")

    return results


def main():
    """Main entry point."""
    # Ensure output directory exists
    os.makedirs("_bmad-output", exist_ok=True)

    # Run tests
    results = run_auth_tests()

    # Add timestamp to results
    results["timestamp"] = datetime.now(UTC).isoformat()
    results["test_script"] = "scripts/test_bybit_auth.py"
    results["version"] = "2.0.0"  # Updated with credential resolver

    # Write evidence file
    output_path = "_bmad-output/bybit-auth-evidence.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 70}")
    print(f"Evidence written to: {output_path}")
    print("=" * 70)

    # Return exit code
    if not results["credentials_present"]:
        return 1
    if results["selected_mode"] is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
