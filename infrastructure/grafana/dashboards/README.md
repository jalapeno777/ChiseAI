# ChiseAI Grafana Dashboards

This directory contains Grafana dashboard definitions for the ChiseAI trading system.

## Dashboards

### Data Freshness Dashboard (`data-freshness.json`)

Monitors data ingestion health across all exchange data sources.

**Features:**
- **Last Update Timestamps**: Real-time display of last update age per data source (Binance, Bybit, Bitget)
- **Freshness Alerting**: Color-coded status indicators
  - Green: Data fresh (< 3 minutes)
  - Yellow: Data stale (3-5 minutes)
  - Red: Alert threshold exceeded (> 5 minutes)
- **7-Day Trend Graph**: Historical freshness trends with configurable lookback (1, 3, 7, 14, 30 days)
- **Alert Threshold Configuration**: Adjustable via dashboard variable (default: 300 seconds)

**Data Source Requirements:**
- InfluxDB bucket: `chiseai`
- Measurement: `data_freshness`
- Fields: `last_update_age_seconds`, `last_update_timestamp`, `alert_status`
- Tags: `source` (binance, bybit, bitget)

### Backtest KPIs Dashboard (`backtest-kpis.json`)

Displays backtest performance metrics for trading strategies.

**Features:**
- **Strategy Selector**: Dropdown to filter by strategy_id
- **Time Range Selector**: Standard Grafana time picker with quick ranges
- **KPI Panels**:
  - Sharpe Ratio (thresholds: red < 1, yellow 1-2, green > 2)
  - Max Drawdown (thresholds: green < 10%, yellow 10-20%, red > 20%)
  - Win Rate (thresholds: red < 45%, yellow 45-55%, green > 55%)
  - Trade Count
- **Trend Graphs**: Time-series visualization of all KPIs over the selected time range
- **Strategy Comparison Table**: Side-by-side comparison of all strategies

**Data Source Requirements:**
- InfluxDB bucket: `chiseai`
- Measurement: `backtest_kpis`
- Fields: `sharpe_ratio`, `max_drawdown`, `win_rate`, `trade_count`, `timestamp`
- Tags: `strategy_id`

## Deployment

Dashboards are deployed via Terraform. See `infrastructure/terraform/dashboards.tf` for provisioning configuration.

### Manual Import

To import dashboards manually into Grafana:

1. Navigate to Grafana UI (http://localhost:3001)
2. Go to Dashboards → Import
3. Upload the JSON file or paste the JSON content
4. Select the InfluxDB datasource
5. Click Import

### Automated Deployment

```bash
# Deploy via Terraform
cd infrastructure/terraform
terraform init
terraform apply -target=docker_container.grafana
```

Dashboards are automatically provisioned via volume mounts when the Grafana container starts.

## Configuration

### Environment Variables

The dashboards use Grafana variables for flexible configuration:

- `${influxdb_datasource}`: InfluxDB datasource name
- `${influxdb_bucket}`: InfluxDB bucket name (default: `chiseai`)
- `${strategy_id}`: Strategy selector for backtest dashboard
- `${lookback_days}`: Trend lookback period for freshness dashboard
- `${alert_threshold_seconds}`: Freshness alert threshold

### InfluxDB Schema

#### Data Freshness Measurement

```flux
from(bucket: "chiseai")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "last_update_age_seconds")
  |> filter(fn: (r) => r.source == "binance")
```

#### Backtest KPIs Measurement

```flux
from(bucket: "chiseai")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "backtest_kpis")
  |> filter(fn: (r) => r._field == "sharpe_ratio")
  |> filter(fn: (r) => r.strategy_id == "strategy_001")
```

## Performance

- Dashboard load time: < 3 seconds for standard viewport
- Panel refresh rate: 30 seconds (configurable)
- Query optimization: Uses `aggregateWindow` for efficient time-series queries

## Testing

Run dashboard validation tests:

```bash
pytest tests/grafana/ -v
```

## References

- [Grafana Dashboard Schema](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/)
- [InfluxDB Flux Query Language](https://docs.influxdata.com/flux/v0/)
- [ChiseAI Architecture](../../docs/architecture.md)
