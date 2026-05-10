# Verify Paper Trading Live Data

## Purpose

Verify that the paper trading pipeline is receiving **live** (non-simulator) data by checking:

- Fill prices match live Bybit ticker
- OHLCV has recent data
- No trades closing at `entry_price`
- Trade duration > 5 minutes
- P&L is non-zero

## Quick Smoke Test

Run this from the host:

```bash
# 1. Check Bybit demo account balance
curl -X GET "https://api-testnet.bybit.vip/v5/account/wallet-balance" \
  -H "X-BAPI-API-KEY: $BYBIT_DEMO_API_KEY" \
  -H "X-BAPI-SIGN: $BYBIT_DEMO_API_SECRET" \
  -H "X-BAPI-SIGN-TYPE: 2" \
  -H "X-BAPI-TIMESTAMP: $(date +%s000)" \
  -H "X-BAPI-RECV-WINDOW: 5000"

# 2. Check live ticker
curl -X GET "https://api-testnet.bybit.vip/v5/market/tickers?category=spot&symbol=BTCUSDT"

# 3. Check Docker containers running
docker compose ps | grep -E "ohlcv|bybit|paper"
```

If any smoke test fails, **stop here** and investigate before proceeding.

## Step 1: Verify Fill Prices Match Live Ticker

### Method A: Compare Order Fill vs Ticker

1. Get current live BTC/USDT ask price:

```bash
curl -s "https://api-testnet.bybit.vip/v5/market/tickers?category=spot&symbol=BTCUSDT" \
  | jq '.result.list[0] | {ask1Price, bid1Price}'
```

2. Check recent trade fills from logs:

```bash
docker compose logs --tail=200 ohlcv-ingestion 2>&1 | grep -i "fill\|execute\|order" | tail -20
```

3. Compare: Fill price should be within 0.1% of live ticker. If fills are exactly `entry_price` or vary wildly, suspect simulator mode.

### Method B: Verify `FORCE_SIMULATOR_MODE=false`

```bash
grep "FORCE_SIMULATOR_MODE" .env
# Expected: FORCE_SIMULATOR_MODE=false
```

If `FORCE_SIMULATOR_MODE=true`, all fills are simulator-generated and not valid for live trading proof.

## Step 2: Verify OHLCV Has Recent Data

### Check InfluxDB for Latest Candle

```bash
# Query latest BTC/USDT 1m candle
curl -G "http://localhost:18087/api/v2/query?org=chiseai" \
  -H "Authorization: Token $INFLUXDB_TOKEN" \
  --data-urlencode 'db=chiseai' \
  --data-urlencode 'q=SELECT * FROM ohlcv WHERE symbol='\''BTC/USDT'\'' AND timeframe='\''1m'\'' ORDER BY time DESC LIMIT 5'
```

### Verify Timestamp is Recent

- Timestamp should be within the last 2-3 minutes
- If candles are stale (>5 min old), ingestion is not working
- Check `docker compose logs ohlcv-ingestion` for errors

### Check Multiple Timeframes

```bash
# Verify 1m, 5m, 15m, 1h all have recent data
for tf in 1m 5m 15m 1h; do
  echo "=== $tf ==="
  curl -G "http://localhost:18087/api/v2/query?org=chiseai" \
    -H "Authorization: Token $INFLUXDB_TOKEN" \
    --data-urlencode 'db=chiseai' \
    --data-urlencode "q=SELECT last(*) FROM ohlcv WHERE symbol='BTC/USDT' AND timeframe='$tf'"
done
```

## Step 3: No Trades Close at entry_price

### Find Trades with Short Duration

```bash
# Look for trades where exit_price == entry_price (indicates immediate close)
docker compose logs --tail=1000 paper-trading 2>&1 | grep -i "CLOSE\|exit\|position" \
  | grep -E "price.*entry_price|exit.*entry" | head -10
```

### Check Trade Duration in InfluxDB

```bash
# Query trades with duration < 300 seconds
curl -G "http://localhost:18087/api/v2/query?org=chiseai" \
  -H "Authorization: Token $INFLUXDB_TOKEN" \
  --data-urlencode 'db=chiseai' \
  --data-urlencode 'q=SELECT * FROM trades WHERE duration < 300 ORDER BY time DESC LIMIT 10'
```

**Expected**: No trades with `duration < 300` seconds. If found, indicates `MIN_HOLD_SECONDS` is being violated.

## Step 4: Trade Duration > 5 Minutes

### Check Trade History

```bash
# Query recent trades and their durations
curl -G "http://localhost:18087/api/v2/query?org=chiseai" \
  -H "Authorization: Token $INFLUXDB_TOKEN" \
  --data-urlencode 'db=chiseai' \
  --data-urlencode 'q=SELECT symbol, side, entry_price, exit_price, duration, pnl FROM trades ORDER BY time DESC LIMIT 20'
```

### Verify Minimum Duration

All trades should have `duration >= 300` seconds (5 minutes). Flag any trade with `duration < 300`.

## Step 5: P&L is Non-Zero

### Check P&L Values

```bash
# Query P&L for recent trades
curl -G "http://localhost:18087/api/v2/query?org=chiseai" \
  -H "Authorization: Token $INFLUXDB_TOKEN" \
  --data-urlencode 'db=chiseai' \
  --data-urlencode 'q=SELECT symbol, pnl, roi_percent FROM trades WHERE pnl != 0 ORDER BY time DESC LIMIT 20'
```

**Expected**: Mix of positive and negative P&L values. If ALL P&L are exactly `0.0`, trades are not being closed properly or live data is not being used.

### Check P&L Distribution

```bash
# Aggregate P&L stats
curl -G "http://localhost:18087/api/v2/query?org=chiseai" \
  -H "Authorization: Token $INFLUXDB_TOKEN" \
  --data-urlencode 'db=chiseai' \
  --data-urlencode 'q=SELECT count(pnl) as trade_count, sum(pnl) as total_pnl, mean(pnl) as avg_pnl FROM trades'
```

## Verification Checklist

| Check                        | Command                                        | Pass Condition              |
| ---------------------------- | ---------------------------------------------- | --------------------------- |
| Bybit API reachable          | `curl api-testnet.bybit.vip/v5/market/tickers` | Returns JSON with BTCUSDT   |
| Live fill prices             | Compare log fills vs ticker                    | Within 0.1%                 |
| `FORCE_SIMULATOR_MODE=false` | `grep ENV`                                     | Value is `false`            |
| OHLCV recent (1m)            | InfluxDB query                                 | Timestamp < 3 min old       |
| OHLCV all timeframes         | InfluxDB query                                 | All 4 TFs have data         |
| No trades at entry_price     | Log grep                                       | No exact entry_price closes |
| Trade duration >= 300s       | InfluxDB query                                 | All trades >= 5 min         |
| P&L non-zero                 | InfluxDB query                                 | At least some trades != 0   |

## Troubleshooting Failed Checks

### Fill Prices Don't Match Ticker

1. Verify `FORCE_SIMULATOR_MODE=false` in `.env`
2. Check if Bybit demo API is returning stale data
3. Inspect `docker compose logs ohlcv-ingestion` for fill price source

### OHLCV Stale

1. Check `docker compose logs ohlcv-ingestion` for errors
2. Verify InfluxDB credentials and connectivity
3. Check INGEST_INTERVAL_SECONDS is reasonable

### Trades Closing at entry_price

1. Verify `MIN_HOLD_SECONDS=300` in `.env`
2. Check trade close logic in paper trading service
3. Look for SL/TP triggering incorrectly

### P&L All Zero

1. Check trade close logic - P&L calculation may be disabled
2. Verify exit_price is being recorded
3. Confirm P&L formula: `(exit_price - entry_price) * size`

## Related Documentation

- [OHLCV Ingestion Deployment](../deployment/ohlcv-ingestion.md)
- [Paper Trading Operations](../runbooks/paper-trading-operations.md)
- [Bybit Demo Routing](../runbooks/bybit-demo-routing.md)
