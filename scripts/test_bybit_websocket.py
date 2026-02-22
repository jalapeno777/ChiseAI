#!/usr/bin/env python3
"""
Bybit WebSocket Connectivity Test Script
Tests WebSocket connectivity for public and private endpoints.

For SAFETY-BYBIT-AUTH: WebSocket Auth Matrix
"""

import hashlib
import hmac
import json
import os
import ssl
import sys
import time
from datetime import UTC, datetime

# Add src to path for credential resolver
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config.bootstrap import bootstrap
from data.exchange.credential_resolver import (
    get_credential_resolution_status,
    resolve_bybit_credentials,
)

# WebSocket endpoints
WS_ENDPOINTS = {
    "public_linear": {
        "url": "wss://stream.bybit.com/v5/public/linear",
        "type": "public",
        "name": "Public Linear (Live)",
    },
    "public_linear_testnet": {
        "url": "wss://stream-testnet.bybit.com/v5/public/linear",
        "type": "public",
        "name": "Public Linear (Testnet)",
    },
    "private_demo": {
        "url": "wss://stream-demo.bybit.com/v5/private",
        "type": "private",
        "name": "Private (Demo)",
    },
    "private_live": {
        "url": "wss://stream.bybit.com/v5/private",
        "type": "private",
        "name": "Private (Live)",
    },
    "private_testnet": {
        "url": "wss://stream-testnet.bybit.com/v5/private",
        "type": "private",
        "name": "Private (Testnet)",
    },
}


def generate_ws_signature(api_secret, expires):
    """Generate Bybit WebSocket signature."""
    signature = hmac.new(
        api_secret.encode("utf-8"),
        f"GET/realtime{expires}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def test_websocket_public(url, timeout=10):
    """Test public WebSocket connection."""
    try:
        import websocket

        result = {
            "url": url,
            "status": "pending",
            "connected": False,
            "latency_ms": None,
            "error": None,
            "message_received": False,
        }

        start_time = time.time()

        def on_open(ws):
            result["connected"] = True
            result["latency_ms"] = int((time.time() - start_time) * 1000)
            # Subscribe to a public topic
            ws.send(json.dumps({"op": "subscribe", "args": ["tickers.BTCUSDT"]}))

        def on_message(ws, message):
            result["message_received"] = True
            result["last_message"] = message[:200] if len(message) > 200 else message
            ws.close()

        def on_error(ws, error):
            result["error"] = str(error)
            result["status"] = "fail"

        def on_close(ws, close_status_code, close_msg):
            if result["status"] == "pending":
                result["status"] = "success" if result["connected"] else "fail"

        # Create WebSocket connection with SSL
        ws = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            header={"User-Agent": "ChiseAI-AuthTest/1.0"},
        )

        # Run with timeout
        ws.run_forever(
            sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=5, ping_timeout=3
        )

        # Wait for completion or timeout
        wait_start = time.time()
        while result["status"] == "pending" and (time.time() - wait_start) < timeout:
            time.sleep(0.1)

        if result["status"] == "pending":
            result["status"] = "timeout"
            result["error"] = "Connection timed out"
            ws.close()

        return result

    except ImportError:
        return {
            "url": url,
            "status": "fail",
            "connected": False,
            "latency_ms": None,
            "error": "websocket-client library not installed (pip install websocket-client)",
            "message_received": False,
        }
    except Exception as e:
        return {
            "url": url,
            "status": "fail",
            "connected": False,
            "latency_ms": None,
            "error": str(e),
            "message_received": False,
        }


def test_websocket_private(url, api_key, api_secret, timeout=15):
    """Test private WebSocket connection with authentication."""
    try:
        import websocket

        result = {
            "url": url,
            "status": "pending",
            "connected": False,
            "authenticated": False,
            "latency_ms": None,
            "auth_latency_ms": None,
            "error": None,
            "auth_response": None,
        }

        start_time = time.time()
        auth_start_time = None

        def on_open(ws):
            result["connected"] = True
            result["latency_ms"] = int((time.time() - start_time) * 1000)

            # Send authentication request
            nonlocal auth_start_time
            auth_start_time = time.time()
            expires = int((time.time() + 10) * 1000)
            signature = generate_ws_signature(api_secret, expires)

            auth_msg = {"op": "auth", "args": [api_key, expires, signature]}
            ws.send(json.dumps(auth_msg))

        def on_message(ws, message):
            try:
                data = json.loads(message)

                # Check for auth response
                if data.get("op") == "auth" or "success" in data:
                    result["auth_response"] = json.dumps(data)[:300]
                    if data.get("success", False) or data.get("ret_msg") == "OK":
                        result["authenticated"] = True
                        result["auth_latency_ms"] = int(
                            (time.time() - auth_start_time) * 1000
                        )
                        result["status"] = "success"
                    else:
                        result["error"] = data.get(
                            "ret_msg", data.get("error", "Auth failed")
                        )
                        result["status"] = "fail"
                    ws.close()

                # Alternative auth success check
                if data.get("retCode") == 0 or data.get("success") == True:
                    result["authenticated"] = True
                    result["auth_response"] = json.dumps(data)[:300]
                    result["status"] = "success"
                    ws.close()

            except json.JSONDecodeError:
                result["last_message"] = message[:200]

        def on_error(ws, error):
            result["error"] = str(error)
            result["status"] = "fail"

        def on_close(ws, close_status_code, close_msg):
            if result["status"] == "pending":
                result["status"] = "fail"
                if not result["error"]:
                    result["error"] = (
                        f"Connection closed: {close_status_code} - {close_msg}"
                    )

        # Create WebSocket connection
        ws = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            header={"User-Agent": "ChiseAI-AuthTest/1.0"},
        )

        # Run with timeout
        ws.run_forever(
            sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=5, ping_timeout=3
        )

        # Wait for completion or timeout
        wait_start = time.time()
        while result["status"] == "pending" and (time.time() - wait_start) < timeout:
            time.sleep(0.1)

        if result["status"] == "pending":
            result["status"] = "timeout"
            result["error"] = "Authentication timed out"
            ws.close()

        return result

    except ImportError:
        return {
            "url": url,
            "status": "fail",
            "connected": False,
            "authenticated": False,
            "latency_ms": None,
            "auth_latency_ms": None,
            "error": "websocket-client library not installed (pip install websocket-client)",
            "auth_response": None,
        }
    except Exception as e:
        return {
            "url": url,
            "status": "fail",
            "connected": False,
            "authenticated": False,
            "latency_ms": None,
            "auth_latency_ms": None,
            "error": str(e),
            "auth_response": None,
        }


def run_websocket_tests():
    """Run WebSocket connectivity tests."""
    print("=" * 70)
    print("BYBIT WEBSOCKET CONNECTIVITY TEST")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print()

    # Get credentials
    cred_status = get_credential_resolution_status()
    credentials = resolve_bybit_credentials()

    print("-" * 70)
    print("CREDENTIAL RESOLUTION")
    print("-" * 70)
    print(f"Env file loaded: {cred_status['env_file_loaded']}")

    if credentials:
        print(f"✅ Credentials resolved: {credentials.source}")
        print(f"   API Key prefix: {credentials.api_key[:4]}...")
    else:
        print("❌ No credentials available")
    print()

    results = {
        "timestamp": datetime.now(UTC).isoformat(),
        "credentials_present": credentials is not None,
        "credentials_source": credentials.source if credentials else None,
        "credentials_key_prefix": credentials.api_key[:4] if credentials else None,
        "tests": {},
    }

    # Test public endpoints
    print("-" * 70)
    print("PUBLIC WEBSOCKET TESTS")
    print("-" * 70)

    for endpoint_id, config in WS_ENDPOINTS.items():
        if config["type"] != "public":
            continue

        print(f"\nTesting {config['name']}...")
        print(f"  URL: {config['url']}")

        result = test_websocket_public(config["url"])
        results["tests"][endpoint_id] = {
            "name": config["name"],
            "type": "public",
            "url": config["url"],
            **result,
        }

        status_icon = "✅" if result["status"] == "success" else "❌"
        print(f"  {status_icon} Status: {result['status']}")
        print(f"     Connected: {result['connected']}")
        if result["latency_ms"]:
            print(f"     Latency: {result['latency_ms']}ms")
        if result["message_received"]:
            print(f"     Message received: Yes")
        if result["error"]:
            print(f"     Error: {result['error']}")

    # Test private endpoints
    print("\n" + "-" * 70)
    print("PRIVATE WEBSOCKET TESTS (with authentication)")
    print("-" * 70)

    if not credentials:
        print("❌ Skipping private tests - no credentials available")
        for endpoint_id, config in WS_ENDPOINTS.items():
            if config["type"] == "private":
                results["tests"][endpoint_id] = {
                    "name": config["name"],
                    "type": "private",
                    "url": config["url"],
                    "status": "skipped",
                    "error": "No credentials available",
                }
    else:
        for endpoint_id, config in WS_ENDPOINTS.items():
            if config["type"] != "private":
                continue

            print(f"\nTesting {config['name']}...")
            print(f"  URL: {config['url']}")

            result = test_websocket_private(
                config["url"], credentials.api_key, credentials.api_secret
            )
            results["tests"][endpoint_id] = {
                "name": config["name"],
                "type": "private",
                "url": config["url"],
                **result,
            }

            status_icon = "✅" if result["status"] == "success" else "❌"
            print(f"  {status_icon} Status: {result['status']}")
            print(f"     Connected: {result['connected']}")
            print(f"     Authenticated: {result['authenticated']}")
            if result["latency_ms"]:
                print(f"     Connection latency: {result['latency_ms']}ms")
            if result["auth_latency_ms"]:
                print(f"     Auth latency: {result['auth_latency_ms']}ms")
            if result["auth_response"]:
                print(f"     Auth response: {result['auth_response'][:100]}...")
            if result["error"]:
                print(f"     Error: {result['error']}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    public_success = sum(
        1
        for t in results["tests"].values()
        if t.get("type") == "public" and t.get("status") == "success"
    )
    public_total = sum(
        1 for t in results["tests"].values() if t.get("type") == "public"
    )
    private_success = sum(
        1
        for t in results["tests"].values()
        if t.get("type") == "private" and t.get("status") == "success"
    )
    private_total = sum(
        1 for t in results["tests"].values() if t.get("type") == "private"
    )

    print(f"Public WebSocket: {public_success}/{public_total} successful")
    print(f"Private WebSocket: {private_success}/{private_total} successful")

    if credentials:
        print(f"\nKey prefix used: {credentials.api_key[:4]}...")

    return results


def main():
    """Main entry point."""
    bootstrap(load_env=True)

    # Ensure output directory exists
    os.makedirs("_bmad-output", exist_ok=True)

    # Run tests
    results = run_websocket_tests()

    # Add metadata
    results["test_script"] = "scripts/test_bybit_websocket.py"
    results["version"] = "1.0.0"

    # Write evidence file
    output_path = "_bmad-output/bybit-websocket-evidence.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 70}")
    print(f"Evidence written to: {output_path}")
    print("=" * 70)

    # Return exit code
    public_tests = [t for t in results["tests"].values() if t.get("type") == "public"]
    if not any(t.get("status") == "success" for t in public_tests):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
