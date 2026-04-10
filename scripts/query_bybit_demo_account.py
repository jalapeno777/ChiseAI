#!/usr/bin/env python3
"""
Bybit Demo Account Query Script (READ-ONLY)
Uses direct HTTP requests with HMAC signing (same pattern as bybit_connector.py)

SECURITY: Credentials MUST come from environment variables.
DO NOT hardcode credentials in this file.
Required env vars: BYBIT_DEMO_API_KEY, BYBIT_DEMO_API_SECRET
"""

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from datetime import datetime
from typing import Any

import requests

# Load from environment — NEVER hardcode
API_KEY = os.getenv("BYBIT_DEMO_API_KEY", "")
API_SECRET = os.getenv("BYBIT_DEMO_API_SECRET", "")

# Fail-fast with clear error if not set
if not API_KEY or not API_SECRET:
    raise OSError(
        "BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET environment variables are required. "
        "Set them in your .env file or environment before running this script."
    )

BASE_URL = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"

# Time offset between local and server (synced on first request)
_time_offset_ms = 0


def sync_server_time() -> None:
    """Synchronize local time with Bybit server time."""
    global _time_offset_ms
    try:
        url = f"{BASE_URL}/v5/market/time"
        response = requests.get(url)
        data = response.json()
        if data.get("retCode") == 0:
            result = data.get("result", {})
            server_time_nano = result.get("timeNano", 0)
            if server_time_nano:
                server_time_ms = int(server_time_nano) // 1_000_000
            else:
                server_time_ms = int(result.get("timeSecond", 0)) * 1000
            local_time_ms = int(time.time() * 1000)
            _time_offset_ms = server_time_ms - local_time_ms
            print(f"[TIME SYNC] Offset: {_time_offset_ms}ms")
    except Exception as e:
        print(f"[TIME SYNC] Failed: {e}")


def get_timestamp() -> str:
    """Get timestamp adjusted for server time offset."""
    local_time_ms = int(time.time() * 1000)
    adjusted_time_ms = local_time_ms + _time_offset_ms
    return str(adjusted_time_ms)


def generate_signature(timestamp: str, payload: str = "") -> str:
    """Generate signature same as bybit_connector.py"""
    param_str = timestamp + API_KEY + RECV_WINDOW + payload
    return hmac.new(
        API_SECRET.encode(),
        param_str.encode(),
        hashlib.sha256,
    ).hexdigest()


def make_signed_request(method: str, endpoint: str, params: dict = None) -> dict:
    """Make signed request to Bybit V5 API demo endpoint."""
    timestamp = get_timestamp()
    headers = {
        "Content-Type": "application/json",
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
    }

    url = f"{BASE_URL}{endpoint}"
    payload = ""

    if method == "GET" and params:
        # Build query string using urlencode to match what requests will send
        # Sorted to ensure consistent ordering
        sorted_params = sorted(params.items())
        encoded_params = urllib.parse.urlencode(sorted_params, safe="")
        payload = encoded_params
        headers["X-BAPI-SIGN"] = generate_signature(timestamp, payload)
    else:
        headers["X-BAPI-SIGN"] = generate_signature(timestamp, payload)

    if method == "GET":
        response = requests.get(
            url, headers=headers, params=sorted_params if params else None
        )
    else:
        response = requests.post(url, headers=headers, json=params)

    data = response.json()

    if data.get("retCode") != 0:
        error_msg = data.get("retMsg", f"HTTP {response.status_code}")
        raise ValueError(f"Bybit API error: {error_msg}")

    return data


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def format_timestamp(ts: int | None, fmt: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    """Format Unix timestamp to UTC string."""
    if ts is None:
        return "N/A"
    try:
        dt = datetime.fromtimestamp(ts / 1000, tz=datetime.UTC)
        return dt.strftime(fmt)
    except Exception:
        return str(ts)


def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def print_balance() -> None:
    """Query and print account balance."""
    print_section("ACCOUNT BALANCE (Wallet Overview)")
    try:
        data = make_signed_request(
            "GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}
        )

        result = data.get("result", {})
        list_data = result.get("list", [])

        if not list_data:
            print("No wallet data found.")
            return

        for account in list_data:
            coin_data = account.get("coin", [])
            for coin in coin_data:
                coin_name = coin.get("coin", "UNKNOWN")
                total = safe_float(coin.get("walletBalance", 0))
                free = safe_float(coin.get("availableToWithdraw", 0))
                used = total - free

                print(f"\n{coin_name} Wallet:")
                print(f"  Total:  {total:>15.6f}")
                print(f"  Free:   {free:>15.6f}")
                print(f"  Used:   {used:>15.6f}")

    except Exception as e:
        print(f"[ERROR] Failed to fetch balance: {e}")


def print_positions() -> None:
    """Query and print open positions."""
    print_section("OPEN POSITIONS")
    try:
        data = make_signed_request(
            "GET", "/v5/position/list", {"category": "linear", "settleCoin": "USDT"}
        )

        result = data.get("result", {})
        list_data = result.get("list", [])

        if not list_data:
            print("No open positions found.")
            return

        for pos in list_data:
            symbol = pos.get("symbol", "UNKNOWN")
            side = pos.get("side", "UNKNOWN")
            size = safe_float(pos.get("size", 0))

            if size == 0:
                continue

            entry_price = safe_float(pos.get("entryPrice", 0))
            unrealized_pnl = safe_float(pos.get("unrealizedPnl", 0))
            leverage = pos.get("leverage", "0")

            print(f"\nSymbol: {symbol}")
            print(f"  Side:          {side}")
            print(f"  Size:          {size}")
            print(f"  Entry Price:   {entry_price}")
            print(f"  Unrealized PnL:{unrealized_pnl:>15.6f}")
            print(f"  Leverage:      {leverage}x")

    except Exception as e:
        print(f"[ERROR] Failed to fetch positions: {e}")


def print_open_orders() -> None:
    """Query and print open orders."""
    print_section("OPEN ORDERS (Pending)")
    try:
        # Query open orders for USDT linear contracts
        data = make_signed_request(
            "GET", "/v5/order/realtime", {"category": "linear", "settleCoin": "USDT"}
        )

        result = data.get("result", {})
        list_data = result.get("list", [])

        if not list_data:
            print("No open orders found.")
            return

        for order in list_data:
            order_id = order.get("orderId", "UNKNOWN")
            order_link_id = order.get("orderLinkId", "")
            symbol = order.get("symbol", "UNKNOWN")
            side = order.get("side", "UNKNOWN")
            order_type = order.get("orderType", "UNKNOWN")
            price = order.get("price", "0")
            qty = order.get("qty", "0")
            filled = order.get("cumExecQty", "0")
            ts = int(order.get("createdTime", 0))

            print(f"\n  Order ID: {order_id}")
            if order_link_id:
                print(f"  Link ID:  {order_link_id}")
            print(f"  Symbol:   {symbol}")
            print(f"  Type:     {order_type}")
            print(f"  Side:     {side}")
            print(f"  Price:    {price}")
            print(f"  Qty:      {qty}")
            print(f"  Filled:   {filled}")
            print(f"  Created:  {format_timestamp(ts)}")

    except Exception as e:
        print(f"[ERROR] Failed to fetch open orders: {e}")


def print_order_history() -> None:
    """Query and print order history - looking for specific order IDs."""
    print_section("ORDER HISTORY (Closed Orders)")
    print("[INFO] Specifically looking for order IDs: c0005d65, 70698946")

    target_order_ids = ["c0005d65", "70698946"]
    found_orders = []
    all_orders = []

    try:
        # Fetch order history with cursor pagination
        cursor = ""
        limit = 50
        max_iterations = 10

        for iteration in range(max_iterations):
            params = {"category": "linear", "limit": limit}
            if cursor:
                params["cursor"] = cursor

            data = make_signed_request("GET", "/v5/order/history", params)

            result = data.get("result", {})
            list_data = result.get("list", [])

            if not list_data:
                break

            for order in list_data:
                order_id = order.get("orderId", "")
                order_link_id = order.get("orderLinkId", "")
                symbol = order.get("symbol", "UNKNOWN")
                side = order.get("side", "UNKNOWN")
                order_type = order.get("orderType", "UNKNOWN")
                price = order.get("price", "0")
                qty = order.get("qty", "0")
                filled = order.get("cumExecQty", "0")
                status = order.get("orderStatus", "UNKNOWN")
                ts = int(order.get("updatedTime", 0))

                all_orders.append(
                    {
                        "orderId": order_id,
                        "orderLinkId": order_link_id,
                        "symbol": symbol,
                        "side": side,
                        "type": order_type,
                        "price": price,
                        "qty": qty,
                        "filled": filled,
                        "status": status,
                        "time": format_timestamp(ts),
                    }
                )

                # Check if this is a target order (check both orderId and orderLinkId)
                is_target = (
                    order_id in target_order_ids or order_link_id in target_order_ids
                )

                if is_target:
                    found_orders.append(order)
                    print("\n  === TARGET ORDER FOUND ===")
                    print(f"  Order ID: {order_id}")
                    if order_link_id:
                        print(f"  Link ID:  {order_link_id}")
                    print(f"  Symbol:   {symbol}")
                    print(f"  Type:     {order_type}")
                    print(f"  Side:     {side}")
                    print(f"  Price:    {price}")
                    print(f"  Qty:      {qty}")
                    print(f"  Filled:   {filled}")
                    print(f"  Status:   {status}")
                    print(f"  Time:     {format_timestamp(ts)}")

            # Check if there are more pages
            cursor = result.get("nextPageCursor", "")
            if not cursor:
                break

        print(f"\n[SUMMARY] Total orders in history: {len(all_orders)}")

        if not found_orders:
            print("[INFO] Target order IDs NOT FOUND in order history.")
            print("\n[DEBUG] Showing recent orders for reference:")
            for o in all_orders[:5]:
                print(
                    f"  - orderId={o['orderId']}, linkId={o['orderLinkId']}, symbol={o['symbol']}, status={o['status']}"
                )

    except Exception as e:
        print(f"[ERROR] Failed to fetch order history: {e}")


def print_trade_history() -> None:
    """Query and print trade history for today (2026-04-06)."""
    print_section("TRADE HISTORY (Today's Trades)")
    today_date = "2026-04-06"
    print(f"[INFO] Filtering for trades on: {today_date}")

    target_order_ids = ["c0005d65", "70698946"]

    try:
        # Fetch trades with cursor pagination
        cursor = ""
        limit = 50
        max_iterations = 10
        all_trades = []

        for iteration in range(max_iterations):
            params = {"category": "linear", "limit": limit}
            if cursor:
                params["cursor"] = cursor

            trade_data = make_signed_request("GET", "/v5/execution/list", params)

            result = trade_data.get("result", {})
            list_data = result.get("list", [])

            if not list_data:
                break

            for trade in list_data:
                order_id = trade.get("orderId", "")
                exec_id = trade.get("execId", "")
                symbol = trade.get("symbol", "UNKNOWN")
                side = trade.get("side", "UNKNOWN")
                exec_price = safe_float(trade.get("execPrice", 0))
                exec_qty = safe_float(trade.get("execQty", 0))
                exec_fee = safe_float(trade.get("execFee", 0))
                ts = int(trade.get("execTime", 0))
                ts_str = format_timestamp(ts)

                all_trades.append(
                    {
                        "orderId": order_id,
                        "execId": exec_id,
                        "symbol": symbol,
                        "side": side,
                        "price": exec_price,
                        "qty": exec_qty,
                        "fee": exec_fee,
                        "time": ts_str,
                        "is_today": today_date in ts_str,
                    }
                )

                # Check if it's today's trade
                is_today = today_date in ts_str

                # Check if related to target orders
                is_target_related = order_id in target_order_ids or any(
                    tid in exec_id for tid in target_order_ids
                )

                # Print today's trades
                if is_today:
                    marker = " <-- TARGET RELATED" if is_target_related else ""
                    print(f"\n  Order ID:  {order_id}{marker}")
                    print(f"  Exec ID:   {exec_id}")
                    print(f"  Symbol:    {symbol}")
                    print(f"  Side:      {side}")
                    print(f"  Price:     {exec_price}")
                    print(f"  Qty:       {exec_qty}")
                    print(f"  Fee:       {exec_fee}")
                    print(f"  Time:      {ts_str}")

            # Check if there are more pages
            cursor = result.get("nextPageCursor", "")
            if not cursor:
                break

        today_count = sum(1 for t in all_trades if t["is_today"])
        print(f"\n[SUMMARY] Trades on {today_date}: {today_count}")
        print(f"[SUMMARY] Total trades fetched: {len(all_trades)}")

        if today_count == 0:
            print(f"\n[INFO] No trades found for {today_date}")

    except Exception as e:
        print(f"[ERROR] Failed to fetch trade history: {e}")


def query_fills_48h() -> dict:
    """Query execution list (fills) for last 48 hours."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (48 * 60 * 60 * 1000)
    
    all_fills = []
    cursor = ""
    limit = 50
    max_iterations = 20
    
    for _ in range(max_iterations):
        params = {"category": "linear", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        
        data = make_signed_request("GET", "/v5/execution/list", params)
        result = data.get("result", {})
        list_data = result.get("list", [])
        
        if not list_data:
            break
        
        for fill in list_data:
            exec_time_ms = int(fill.get("execTime", 0))
            if exec_time_ms < start_ms:
                # We've gone past the 48h window
                return {"fills": all_fills, "truncated": True}
            all_fills.append(fill)
        
        cursor = result.get("nextPageCursor", "")
        if not cursor:
            break
    
    return {"fills": all_fills, "truncated": False}


def query_orders_48h() -> dict:
    """Query order history for last 48 hours."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (48 * 60 * 60 * 1000)
    
    all_orders = []
    cursor = ""
    limit = 50
    max_iterations = 20
    
    for _ in range(max_iterations):
        params = {"category": "linear", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        
        data = make_signed_request("GET", "/v5/order/history", params)
        result = data.get("result", {})
        list_data = result.get("list", [])
        
        if not list_data:
            break
        
        for order in list_data:
            updated_ms = int(order.get("updatedTime", 0))
            created_ms = int(order.get("createdTime", 0))
            latest_ms = max(updated_ms, created_ms)
            if latest_ms < start_ms:
                return {"orders": all_orders, "truncated": True}
            all_orders.append(order)
        
        cursor = result.get("nextPageCursor", "")
        if not cursor:
            break
    
    return {"orders": all_orders, "truncated": False}


def main() -> None:
    """Main entry point."""
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--48h":
        # Focused 48h query mode
        sync_server_time()
        
        print("[QUERY] Fetching fills for last 48h...")
        fills_result = query_fills_48h()
        fills = fills_result["fills"]
        
        print("[QUERY] Fetching orders for last 48h...")
        orders_result = query_orders_48h()
        orders = orders_result["orders"]
        
        # Compute stats
        newest_fill_ts = None
        if fills:
            newest_fill_ts = max(int(f.get("execTime", 0)) for f in fills)
        
        sample_fill_ids = []
        for f in fills[:5]:
            sample_fill_ids.append(f.get("execId", ""))
        
        # Output as JSON
        output = {
            "fills_count": len(fills),
            "orders_count": len(orders),
            "fills_truncated": fills_result["truncated"],
            "orders_truncated": orders_result["truncated"],
            "newest_fill_utc": format_timestamp(newest_fill_ts) if newest_fill_ts else None,
            "newest_fill_epoch_ms": newest_fill_ts,
            "sample_fill_ids": sample_fill_ids,
            "sample_fills": [
                {
                    "execId": f.get("execId", ""),
                    "orderId": f.get("orderId", ""),
                    "symbol": f.get("symbol", ""),
                    "side": f.get("side", ""),
                    "execPrice": f.get("execPrice", ""),
                    "execQty": f.get("execQty", ""),
                    "execFee": f.get("execFee", ""),
                    "execTime": format_timestamp(int(f.get("execTime", 0))),
                }
                for f in fills[:5]
            ],
            "sample_orders": [
                {
                    "orderId": o.get("orderId", ""),
                    "orderLinkId": o.get("orderLinkId", ""),
                    "symbol": o.get("symbol", ""),
                    "side": o.get("side", ""),
                    "orderType": o.get("orderType", ""),
                    "price": o.get("price", ""),
                    "qty": o.get("qty", ""),
                    "cumExecQty": o.get("cumExecQty", ""),
                    "orderStatus": o.get("orderStatus", ""),
                    "createdTime": format_timestamp(int(o.get("createdTime", 0))),
                    "updatedTime": format_timestamp(int(o.get("updatedTime", 0))),
                }
                for o in orders[:5]
            ],
        }
        
        print(json.dumps(output, indent=2))
        return
    
    # Default: full account query
    print("=" * 70)
    print(" BYBIT DEMO ACCOUNT QUERY (READ-ONLY)")
    print(" Using direct HTTP requests with HMAC signing")
    print("=" * 70)
    print(f"\nRun at: {datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Sync time with server first
    print("\n[INFO] Syncing time with Bybit server...")
    sync_server_time()

    print(f"\n[INFO] Using Bybit Demo API ({BASE_URL})")
    print(f"[INFO] API Key prefix: {API_KEY[:4]}...")

    # Query and print all sections
    print_balance()
    print_positions()
    print_open_orders()
    print_order_history()
    print_trade_history()

    print("\n" + "=" * 70)
    print(" END OF REPORT")
    print("=" * 70)


if __name__ == "__main__":
    main()
