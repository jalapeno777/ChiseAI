# OHLCV Ingestion Service Deployment

## Overview

The OHLCV Ingestion service collects candlestick (OHLCV) data from the Bybit exchange and writes it to InfluxDB for use by trading pipelines and backtesting systems.

## What the Service Does

- Connects to Bybit API (live or demo) for price feed data
- Collects Open-High-Low-Close-Volume (OHLCV) candles at configurable timeframes
- Ingests data into InfluxDB with proper tagging (symbol, timeframe, exchange)
- Runs on a configurable interval (default: 60 seconds)

## Environment Variables

| Variable                  | Default                         | Description                                         |
| ------------------------- | ------------------------------- | --------------------------------------------------- |
| `EXCHANGE_ID`             | `bybit`                         | Exchange identifier                                 |
| `SYMBOLS`                 | `BTC/USDT,ETH/USDT`             | Trading pair symbols                                |
| `TIMEFRAMES`              | `1m,5m,15m,1h`                  | Candle timeframes to collect                        |
| `INGEST_INTERVAL_SECONDS` | `60`                            | How often to fetch and ingest data                  |
| `ACTIONABLE_THRESHOLD`    | `0.75`                          | Signal confidence threshold                         |
| `FORCE_SIMULATOR_MODE`    | `false`                         | `false` = live fill prices, `true` = simulator only |
| `MIN_HOLD_SECONDS`        | `300`                           | Minimum position hold time (5 min)                  |
| `SLTP_POLL_INTERVAL`      | `20`                            | SL/TP monitoring poll interval (seconds)            |
| `INFLUXDB_URL`            | `http://chiseai-influxdb:18087` | InfluxDB endpoint                                   |
| `INFLUXDB_ORG`            | `chiseai`                       | InfluxDB organization                               |
| `INFLUXDB_BUCKET`         | `chiseai`                       | InfluxDB bucket                                     |
| `INFLUXDB_TOKEN`          | _(required)_                    | InfluxDB authentication token                       |
| `BYBIT_DEMO_API_KEY`      | _(required)_                    | Bybit API key                                       |
| `BYBIT_DEMO_API_SECRET`   | _(required)_                    | Bybit API secret                                    |

## Docker Compose Commands

### Start the Service

```bash
docker compose up -d ohlcv-ingestion
```

Or from the project root:

```bash
docker compose -f infrastructure/docker-compose.yml up -d ohlcv-ingestion
```

### Stop the Service

```bash
docker compose stop ohlcv-ingestion
docker compose rm -f ohlcv-ingestion
```

### View Logs

```bash
docker compose logs -f ohlcv-ingestion
```

### Restart the Service

```bash
docker compose restart ohlcv-ingestion
```

## Verifying the Service is Running

### Check Docker Container Status

```bash
docker compose ps ohlcv-ingestion
```

The container should show status `Up`.

### Check Container Health

```bash
docker inspect chiseai-ohlcv-ingestion-1 --format='{{.State.Health.Status}}'
```

### View Recent Logs

```bash
docker compose logs --tail=50 ohlcv-ingestion
```

Look for entries like:

- `OHLCV ingestion cycle complete` — indicates successful data collection
- `Connected to InfluxDB` — confirms InfluxDB connectivity
- Any `ERROR` or `WARN` entries may indicate issues

### Verify InfluxDB Data Arrival

Query InfluxDB directly to confirm OHLCV data is being written:

```bash
curl -G "http://localhost:18087/api/v2/query?org=chiseai" \
  -H "Authorization: Token YOUR_INFLUXDB_TOKEN" \
  --data-urlencode 'db=chiseai' \
  --data-urlencode 'q=SELECT * FROM ohlcv WHERE symbol='\''BTC/USDT'\'' AND timeframe='\''1m'\'' ORDER BY time DESC LIMIT 10'
```

### Check Grafana Dashboard

If Grafana is available, the **ChiseAI Overview** dashboard shows:

- InfluxDB write success/failure rates
- OHLCV ingestion latency
- Container health status

## Troubleshooting

### Service Won't Start

1. Check that `.env` file exists with required variables
2. Verify InfluxDB is running: `docker compose ps influxdb`
3. Check logs: `docker compose logs ohlcv-ingestion`

### No Data in InfluxDB

1. Verify Bybit API credentials are valid
2. Check network connectivity from container: `docker exec chiseai-ohlcv-ingestion-1 ping host.docker.internal`
3. Confirm InfluxDB bucket exists and token has write permissions

### High Ingestion Latency

1. Check `INGEST_INTERVAL_SECONDS` is not too aggressive
2. Monitor container resource usage: `docker stats`
3. Review logs for API rate limiting events

## Related Documentation

- [Verify Paper Trading Live Data Runbook](../runbooks/verify-paper-trading-live-data.md)
- [Paper Trading Operations](../runbooks/paper-trading-operations.md)
- [InfluxDB Retention](../runbooks/influxdb-retention.md)
