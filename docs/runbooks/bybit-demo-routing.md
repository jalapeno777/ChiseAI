# Bybit Demo Routing Runbook

**Story:** BYBIT-DEMO-003  
**Last Updated:** 2026-02-19  
**Status:** Active

## Overview

This runbook documents the authoritative routing policy for Bybit demo (paper trading) execution. It defines which operations use REST vs WebSocket and specifies the exact endpoints for each protocol.

## Authoritative Endpoints

| Environment | Protocol | URL |
|-------------|----------|-----|
| Demo REST | HTTPS | `https://api-demo.bybit.com` |
| Demo Private WS | WSS | `wss://stream-demo.bybit.com/v5/private` |
| Public Market WS | WSS | `wss://stream.bybit.com/v5/public/linear` |

**Important:** Public market WebSocket uses mainnet (stream.bybit.com) for all modes including demo. This ensures consistent market data across testnet, demo, and live.

## Routing Decision Matrix

### When to Use REST (api-demo.bybit.com)

| Operation | Endpoint Pattern | Auth Required |
|-----------|------------------|---------------|
| Get ticker/24hr stats | GET /v5/market/tickers | No |
| Get orderbook | GET /v5/market/orderbook | No |
| Get klines/candles | GET /v5/market/kline | No |
| Query account info | GET /v5/account/info | Yes |
| Query positions | GET /v5/position/list | Yes |
| Query fills/executions | GET /v5/execution/list | Yes |
| Query orders | GET /v5/order/list | Yes |
| Place order | POST /v5/order/create | Yes |
| Cancel order | POST /v5/order/cancel | Yes |
| Amend order | POST /v5/order/amend | Yes |

### When to Use Private WebSocket (stream-demo.bybit.com)

| Data Type | Channel | Auth Required |
|-----------|---------|---------------|
| Position updates | position | Yes |
| Order updates | order | Yes |
| Execution/fill updates | execution | Yes |
| Wallet updates | wallet | Yes |

### When to Use Public WebSocket (stream.bybit.com)

| Data Type | Channel | Auth Required |
|-----------|---------|---------------|
| Real-time tickers | tickers.{symbol} | No |
| Orderbook updates | orderbook.{depth}.{symbol} | No |
| Trade stream | publicTrade.{symbol} | No |
| Kline/ candles | kline.{interval}.{symbol} | No |

## Configuration

### Environment Variables

```bash
# Demo mode (recommended for paper trading)
export BYBIT_DEMO_API_KEY="your_demo_key"
export BYBIT_DEMO_API_SECRET="your_demo_secret"

# Or use testnet
export BYBIT_TESTNET_API_KEY="your_testnet_key"
export BYBIT_TESTNET_API_SECRET="your_testnet_secret"
```

### Code Configuration

```python
from data.exchange.bybit_connector import BybitConfig, BybitConnector

# Demo mode
demo_config = BybitConfig(demo=True)
connector = BybitConnector(demo_config)

# Testnet mode
testnet_config = BybitConfig(testnet=True)
connector = BybitConnector(testnet_config)

# Live mode (default)
live_config = BybitConfig()
connector = BybitConnector(live_config)
```

## Fallback Behavior

### WebSocket to REST Fallback

If WebSocket connection fails, the connector automatically falls back to REST polling:

1. **Detect failure:** Connection closed, auth failure, or timeout
2. **Log event:** `WARNING: WS fallback to REST for {operation}`
3. **Switch mode:** Use REST polling at 1-5s intervals
4. **Auto-retry WS:** Exponential backoff reconnect (1s, 2s, 4s, 8s... max 60s)
5. **Restore WS:** When reconnected, resume WebSocket streaming

### Demo REST Limitations

Some endpoints may have limitations in demo mode:

| Endpoint | Limitation | Fallback |
|----------|------------|----------|
| /v5/order/create | Demo may have rate limits | Implement client-side rate limiting |
| /v5/execution/list | Historical data may be limited | Cache recent fills locally |
| WebSocket auth | Demo keys may have different permissions | Validate key permissions on startup |

## Troubleshooting

### Issue: "Invalid API key" in demo mode

**Diagnosis:**
- Check key is prefixed with `R9K` (demo key format)
- Verify key is active in Bybit portal
- Ensure IP whitelist includes your server

**Resolution:**
```bash
# Test key validity
python scripts/test_bybit_auth.py --mode demo
```

### Issue: "Connection refused" on WebSocket

**Diagnosis:**
- Check firewall rules for outbound WSS (port 443)
- Verify URL format: `wss://stream-demo.bybit.com/v5/private`

**Resolution:**
```bash
# Test WebSocket connectivity
python scripts/test_bybit_websocket.py --endpoint private_demo
```

### Issue: Stale market data

**Diagnosis:**
- Check WebSocket heartbeat (should be every 30s)
- Verify no proxy/filter interfering with WebSocket

**Resolution:**
- Restart WebSocket connection
- Fall back to REST polling temporarily

## Validation Checklist

Before using demo mode in production:

- [ ] Demo API key valid (`python scripts/test_bybit_auth.py`)
- [ ] Private WebSocket connects (`python scripts/test_bybit_websocket.py`)
- [ ] Public WebSocket receives tickers
- [ ] REST endpoints respond with <500ms latency
- [ ] Order placement works (test with small qty)
- [ ] Fill notifications received via WebSocket
- [ ] Position updates received via WebSocket

## References

- Bybit API Documentation: https://bybit-exchange.github.io/docs/v5/intro
- Connector Source: `src/data/exchange/bybit_connector.py`
- Config: `config/bybit_endpoints.yaml`
- Tests: `tests/test_execution/test_bybit_connector.py`
