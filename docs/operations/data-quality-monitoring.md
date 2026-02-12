# Data Quality Monitoring Operations Guide

## Overview

This guide covers the operation of the data quality monitoring system implemented in ST-DATA-004. The system monitors data freshness and detects gaps across multiple data sources (Binance, Bybit, Bitget) with configurable thresholds and Discord alerting.

## Components

### 1. DataFreshnessMonitor

Monitors the freshness of data from each source. Data is considered stale if it exceeds the configured threshold (default: 5 minutes).

**Key Features:**
- Per-source freshness tracking
- Configurable thresholds per source
- Alert cooldown to prevent spam
- Historical metrics storage for trending

### 2. GapDetector

Detects gaps in time-series data within 60 seconds of occurrence.

**Key Features:**
- Real-time gap detection
- Severity classification (info/warning/critical)
- Gap history tracking
- Configurable detection window

### 3. DataQualityDiscordSender

Sends alerts to Discord #alerts channel with formatted embeds.

**Key Features:**
- Freshness alerts for stale data
- Gap alerts with severity indicators
- Recovery notices when issues resolve
- Rate limiting and duplicate suppression

### 4. GrafanaMetricsExporter

Exports metrics to InfluxDB for Grafana visualization.

**Key Features:**
- Freshness trends over time
- Gap history visualization
- Last update timestamps per source
- Pre-configured dashboard templates

## Configuration

### Environment Variables

#### Source Configuration
```bash
# Symbols to monitor per exchange
DQ_BINANCE_SYMBOLS="BTC/USDT,ETH/USDT,SOL/USDT"
DQ_BYBIT_SYMBOLS="BTC/USDT,ETH/USDT,SOL/USDT"
DQ_BITGET_SYMBOLS="BTC/USDT,ETH/USDT,SOL/USDT"

# Timeframes to monitor
DQ_TIMEFRAMES="1m,5m,15m,1h"
```

#### Freshness Configuration
```bash
# Default freshness threshold (5 minutes)
DQ_FRESHNESS_THRESHOLD_SECONDS=300

# Alert cooldown to prevent spam
DQ_FRESHNESS_ALERT_COOLDOWN=60

# Per-source thresholds (optional)
DQ_FRESHNESS_THRESHOLD_BINANCE=300
DQ_FRESHNESS_THRESHOLD_BYBIT=300
DQ_FRESHNESS_THRESHOLD_BITGET=300
```

#### Gap Detection Configuration
```bash
# Enable/disable gap detection
DQ_GAP_DETECTION_ENABLED=true

# Target detection latency (60 seconds)
DQ_GAP_DETECTION_WINDOW=60
```

#### Discord Configuration
```bash
# Discord webhook URL for alerts
DQ_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# Channel name for alerts
DQ_DISCORD_ALERTS_CHANNEL="alerts"

# Send recovery notices when issues resolve
DQ_DISCORD_RECOVERY_NOTICES=true
```

#### InfluxDB Configuration (for Grafana)
```bash
DQ_INFLUX_URL="http://localhost:8086"
DQ_INFLUX_TOKEN="your-token"
DQ_INFLUX_ORG="chiseai"
DQ_INFLUX_BUCKET="chiseai"
```

#### Monitoring Configuration
```bash
# Monitoring interval
DQ_MONITORING_INTERVAL=60

# Enable continuous monitoring
DQ_ENABLE_CONTINUOUS_MONITORING=true
```

## Usage

### Basic Usage

```python
from monitoring.data_quality import (
    DataQualityMonitor,
    DataSource,
    SourceConfig,
)
from monitoring.data_quality.config import DataQualityConfig

# Load configuration from environment
config = DataQualityConfig.from_env()

# Create monitor
monitor = DataQualityMonitor(
    source_configs=config.get_source_configs(),
    freshness_cooldown_seconds=config.freshness_alert_cooldown,
    gap_detection_window_seconds=config.gap_detection_window_seconds,
)

# Add Discord alert handler
from monitoring.data_quality.discord_sender import create_discord_alert_handler

handler = create_discord_alert_handler(
    webhook_url=config.discord_webhook_url,
    alerts_channel=config.discord_alerts_channel,
)
monitor.add_alert_handler(handler)

# Check data quality
freshness, gaps = await monitor.check_data_quality(
    source=DataSource.BINANCE,
    symbol="BTC/USDT",
    timeframe="1m",
    data=ohlcv_data,
    expected_interval_ms=60000,
)
```

### Continuous Monitoring

```python
# Start continuous monitoring
await monitor.start_monitoring(interval_seconds=60)

# ... run for some time ...

# Stop monitoring
await monitor.stop_monitoring()
```

### Grafana Integration

```python
from monitoring.data_quality.grafana_integration import GrafanaMetricsExporter

# Create exporter
exporter = GrafanaMetricsExporter(
    influx_url=config.influx_url,
    influx_token=config.influx_token,
    influx_org=config.influx_org,
    influx_bucket=config.influx_bucket,
)

# Export metrics
await exporter.export_freshness_metric(freshness_metrics)
await exporter.export_gap_alert(gap_alert)

# Query trends
freshness_trends = await exporter.query_freshness_trends(hours=24)
gap_history = await exporter.query_gap_history(hours=24)
```

## Grafana Dashboard

### Dashboard Panels

1. **Data Freshness by Source**: Time series showing data age per source
2. **Stale Data Sources**: Count of sources with stale data
3. **Data Gaps (24h)**: Table of detected gaps
4. **Last Update per Source**: Timestamp of most recent data per source

### Flux Queries

#### Freshness Trend
```flux
from(bucket: "chiseai")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "data_age_seconds")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
```

#### Stale Data Count
```flux
from(bucket: "chiseai")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "is_stale")
  |> last()
  |> group(columns: ["source"])
  |> sum()
```

#### Gap Count
```flux
from(bucket: "chiseai")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "data_gaps")
  |> filter(fn: (r) => r._field == "expected_candles")
  |> count()
  |> group(columns: ["source", "symbol"])
```

## Alerting

### Discord Alert Format

**Freshness Alert:**
```
🚨 Data Quality Alert: Stale data from BINANCE

Stale Data Alert
Data for BTC/USDT (1m) is stale
• Age: 6.7 minutes
• Threshold: 5.0 minutes
• Staleness: 1.7 minutes over threshold

Source: BINANCE
Symbol: BTC/USDT
Timeframe: 1m
Staleness: 1.7 min
Timestamp: 2026-02-11 12:34:56 UTC
```

**Gap Alert:**
```
⚠️ Data Quality Alert: Gap detected in BINANCE

Data Gap Detected
Missing data detected for BTC/USDT (1m)
• Missing candles: 3
• Gap duration: 180 seconds
• Gap start: 12:30:00
• Gap end: 12:33:00

Source: BINANCE
Symbol: BTC/USDT
Timeframe: 1m
Missing Candles: 3
Severity: WARNING
Detected At: 12:34:56 UTC
```

## Troubleshooting

### Common Issues

#### No Alerts Received
1. Check Discord webhook URL is configured correctly
2. Verify `DQ_DISCORD_WEBHOOK_URL` environment variable
3. Check alert cooldown hasn't suppressed the alert

#### Metrics Not Appearing in Grafana
1. Verify InfluxDB connection settings
2. Check `chiseai` bucket exists
3. Ensure exporter is being called after checks

#### False Positive Gap Alerts
1. Adjust gap detection tolerance
2. Check expected interval matches actual data interval
3. Verify market hours (gaps during market closure are expected)

### Health Checks

```python
# Check monitor health
metrics = monitor.get_all_metrics()
print(f"Total monitored: {metrics['freshness']['total_monitored']}")
print(f"Stale count: {metrics['freshness']['stale_count']}")
print(f"Active gaps: {metrics['gaps']['active_count']}")

# Check Discord sender
print(f"Active alerts: {sender.get_active_alert_count()}")

# Check Grafana exporter
last_updates = await exporter.get_last_update_per_source()
for source, info in last_updates.items():
    print(f"{source.value}: {info['timestamp']}")
```

## Performance Considerations

- **Memory**: Metrics history is limited to 10,000 entries by default
- **CPU**: Gap detection is O(n) where n is data points
- **Network**: Discord alerts respect rate limits
- **Storage**: InfluxDB retention policy should be configured

## Maintenance

### Regular Tasks

1. **Review Alert Thresholds**: Adjust based on data patterns
2. **Clean Old Metrics**: Purge metrics older than retention period
3. **Update Source Lists**: Add/remove symbols as needed
4. **Monitor Alert Fatigue**: Review and tune alert frequency

### Log Analysis

```bash
# Check for freshness alerts
grep "Stale data detected" /var/log/chiseai/monitoring.log

# Check for gap alerts
grep "Detected gap" /var/log/chiseai/monitoring.log

# Check Discord send status
grep "Sent.*alert to Discord" /var/log/chiseai/monitoring.log
```

## API Reference

See module docstrings for detailed API documentation:
- `monitoring.data_quality`: Core monitoring classes
- `monitoring.data_quality.discord_sender`: Discord integration
- `monitoring.data_quality.grafana_integration`: Grafana/InfluxDB integration
- `monitoring.data_quality.config`: Configuration classes
