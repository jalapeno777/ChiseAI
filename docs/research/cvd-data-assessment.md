# CVD Data Availability Assessment

> **Story**: ST-ICT-004
> **Date**: 2026-03-25
> **Status**: Assessment Complete

---

## Executive Summary

Cumulative Volume Delta (CVD) is a critical microstructure indicator that aggregates the difference between buy-initiated and sell-initiated volume over time. This assessment evaluates trade data availability across three major crypto derivatives exchanges — **Binance Futures**, **Bybit**, and **Bitget** — to determine feasibility of implementing a real-time CVD pipeline for ChiseAI.

**Key Findings**:

| Exchange        | Trade Endpoint                     | Real-time (WebSocket)          | Historical                    | Auth Required | Verdict    |
| --------------- | ---------------------------------- | ------------------------------ | ----------------------------- | ------------- | ---------- |
| Binance Futures | `/fapi/v1/trades`                  | `aggTrade` stream              | `/fapi/v1/aggTrades`          | No            | **Ready**  |
| Bybit V5        | `/v5/market/recent-trade`          | `publicTrade` stream           | `/v5/market/historical-trade` | No            | **Ready**  |
| Bitget V2 Mix   | `/api/v2/mix/market/recent-trades` | `trade` stream (via WebSocket) | Limited                       | No            | **Viable** |

**Recommendation**: Proceed with Binance Futures as the primary CVD source. Add Bybit as secondary. Defer Bitget historical to Phase 2 due to limited historical API coverage.

---

## Exchange Trade Endpoints

### Binance Futures (USDT-M)

**Trade Data REST Endpoint**:

- **Recent Trades**: `GET /fapi/v1/trades`
- **Aggregated Trades**: `GET /fapi/v1/aggTrades`
- **Historical AggTrades**: `GET /fapi/v1/aggTrades` (with `startTime`/`endTime`)
- **Base URL**: `https://fapi.binance.com`

**WebSocket Streams**:

- **Individual Symbol**: `wss://fstream.binance.com/ws/<symbol>@aggTrade`
- **All Symbols**: `wss://fstream.binance.com/ws/!aggTrade@arr`
- **Diff. Depth (alternative)**: `wss://fstream.binance.com/ws/<symbol>@depth20@100ms`

**CVD Relevance**: AggTrade events include `m: true` (is the buyer the market maker?) which directly indicates trade direction. `m=false` = buy (taker bought), `m=true` = sell (taker sold).

**Rate Limits**:

- REST: 2400 requests/min (weight-based)
- WebSocket: 5 messages/sec per connection; 10 incoming messages/sec per connection

**Response Fields (aggTrade)**:

```json
{
  "a": 123456789, // Aggregate trade ID
  "p": "4.001002", // Price
  "q": "200", // Quantity
  "f": 100, // First trade ID
  "l": 105, // Last trade ID
  "T": 1672531200000, // Timestamp
  "m": true // Is the buyer the market maker?
}
```

**CVD Calculation**: `delta = qty * (1 if m == false else -1)`, accumulate over window.

---

### Bybit V5 API

**Trade Data REST Endpoint**:

- **Recent Trades**: `GET /v5/market/recent-trade` (last 500 trades)
- **Historical Trades**: `GET /v5/market/historical-trade` (last 7 days)
- **Base URL**: `https://api.bybit.com`

**WebSocket Streams**:

- **Public Trade**: `ws://wss.bybit.com/v5/public/linear`
- **Subscribe**: `{"op": "subscribe", "args": ["publicTrade.BTCUSDT"]}`

**CVD Relevance**: Trade side is directly provided via `S` field: `Buy` or `Sell`.

**Rate Limits**:

- REST: 1200 requests/min (IP-based)
- WebSocket: 20 incoming messages/sec per connection

**Response Fields (recent-trade)**:

```json
{
  "symbol": "BTCUSDT",
  "side": "Buy",
  "price": "41000.00",
  "size": "0.001",
  "time": "1672531200000",
  "tradeId": "abc123"
}
```

**CVD Calculation**: `delta = size * (1 if S == "Buy" else -1)`, accumulate over window.

---

### Bitget V2 Mix API

**Trade Data REST Endpoint**:

- **Recent Trades**: `GET /api/v2/mix/market/recent-trades`
- **Historical Trades**: `GET /api/v2/mix/market/history-candles` (candles, not raw trades)
- **Base URL**: `https://api.bitget.com`

**WebSocket Streams**:

- **Public Trade**: `wss://wspap.bitget.com/v2/mix/public/USDT`
- **Subscribe**: `{"op": "subscribe", "args": [{"instType": "USDT-FUTURES", "channel": "trade", "instId": "BTCUSDT"}]}`

**CVD Relevance**: Trade side provided via `side` field: `buy` or `sell`.

**Rate Limits**:

- REST: 20 requests/sec (IP-based)
- WebSocket: 10 subscriptions/sec

**Response Fields (recent-trades)**:

```json
{
  "symbol": "BTCUSDT",
  "side": "buy",
  "price": "41000",
  "size": "0.01",
  "ts": "1672531200000",
  "tradeId": "1234567890"
}
```

**CVD Calculation**: `delta = size * (1 if side == "buy" else -1)`, accumulate over window.

**Note**: Bitget historical raw trades API is limited. For backtesting, candle data may need to be used as a proxy.

---

## Data Availability Matrix

| Feature                      | Binance Futures                  | Bybit V5          | Bitget V2 Mix          |
| ---------------------------- | -------------------------------- | ----------------- | ---------------------- |
| **Real-time trades (REST)**  | Yes (last 500)                   | Yes (last 500)    | Yes (recent)           |
| **Real-time trades (WS)**    | Yes (aggTrade)                   | Yes (publicTrade) | Yes (trade)            |
| **Historical trades (raw)**  | Yes (full history via aggTrades) | Yes (7 days)      | Limited (candles only) |
| **Trade direction field**    | `m` (maker side)                 | `S` (Buy/Sell)    | `side` (buy/sell)      |
| **Auth required**            | No                               | No                | No                     |
| **Rate limit (REST)**        | 2400/min                         | 1200/min          | 1200/min               |
| **WS message rate**          | 10 msg/s/conn                    | 20 msg/s/conn     | Varies                 |
| **Aggregated trade support** | Yes (aggTrade)                   | No (individual)   | No (individual)        |
| **Multi-symbol WS**          | Yes (`!aggTrade@arr`)            | Per-connection    | Per-channel            |
| **USDT-M perpetual**         | Yes                              | Yes               | Yes                    |
| **Documentation quality**    | Excellent                        | Good              | Adequate               |

---

## Implementation Recommendations

### Phase 1: Binance CVD (Immediate)

1. **Use `aggTrade` WebSocket stream** for real-time CVD
2. **REST fallback**: `/fapi/v1/aggTrades` with `startTime`/`endTime` for gap-fill
3. **Direction mapping**: `m=false` → buyer (taker bought) = +volume; `m=true` → seller (taker sold) = -volume
4. **Accumulation windows**: 1s, 5s, 15s, 1m rolling windows
5. **Code location**: Add `trades_url` property to `BinanceConfig` (completed)

### Phase 2: Bybit CVD (Secondary)

1. **Use `publicTrade` WebSocket** for real-time CVD
2. **Direction mapping**: `S="Buy"` → +volume; `S="Sell"` → -volume
3. **Historical backfill**: Limited to 7 days; use for validation only

### Phase 3: Bitget CVD (Defer)

1. **Real-time viable** via WebSocket `trade` channel
2. **Historical**: Use candle data as proxy; raw trade history not fully available
3. **Priority**: Low — only if multi-exchange CVD divergence signals are needed

### Architecture Notes

- CVD should be computed **per-symbol** and stored as a time series
- Consider **delta normalization** (CVD / total volume) for cross-symbol comparison
- WebSocket reconnection with **gap-fill** from REST API is critical for data integrity
- All three exchanges use **public endpoints** — no API keys required for trade data

---

## Risks & Mitigations

| Risk                                    | Severity | Mitigation                                                                                         |
| --------------------------------------- | -------- | -------------------------------------------------------------------------------------------------- |
| WebSocket disconnection causes CVD gaps | High     | Implement automatic reconnection with REST-based gap fill using last known trade ID/timestamp      |
| Rate limiting on historical backfill    | Medium   | Batch requests with pagination; respect weight limits; cache locally                               |
| Trade direction interpretation errors   | Medium   | Write unit tests per exchange mapping; validate against known price movement direction             |
| Binance `m` field semantics confusion   | High     | `m=true` means buyer IS the maker (i.e., SELL-initiated trade). Document clearly and test.         |
| Clock skew between exchanges            | Low      | Use exchange-provided timestamps; normalize to UTC                                                 |
| Bybit 7-day historical limit            | Low      | Accept limitation; use for validation only; rely on real-time for production                       |
| AggTrade vs individual trade semantics  | Medium   | Binance aggTrades combine multiple orders at same price/time — sum quantities within each aggTrade |

---

## Appendix: API Reference Links

- **Binance Futures API**: <https://binance-docs.github.io/apidocs/futures/en/>
- **Binance WebSocket Streams**: <https://binance-docs.github.io/apidocs/futures/en/#websocket-market-streams>
- **Binance AggTrade Endpoint**: <https://binance-docs.github.io/apidocs/futures/en/#compressed-aggregate-trades-list>
- **Bybit V5 API**: <https://bybit-exchange.github.io/docs/v5/market/>
- **Bybit Recent Trade**: <https://bybit-exchange.github.io/docs/v5/market/recent-trade>
- **Bybit Historical Trade**: <https://bybit-exchange.github.io/docs/v5/market/historical-trade>
- **Bitget V2 API**: <https://www.bitget.com/api-doc/common/intro>
- **Bitget Mix Market**: <https://www.bitget.com/api-doc/spot/market/Get-Recent-Trades>
