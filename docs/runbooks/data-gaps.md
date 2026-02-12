---
title: Data Gaps Runbook
category: alerting
severity: warning
estimated_time_to_resolve: 10-30 minutes
last_updated: 2026-02-11
maintainers: ops-team
---

# Data Gaps Runbook

## Problem Description

Missing or incomplete data points in the time-series data collected from exchange APIs. Data gaps can cause:
- Inaccurate backtesting results
- Poor signal generation quality
- Incomplete market visualization
- Incorrect position sizing calculations

## Symptoms and Indicators

### Primary Symptoms
1. **Freshness Dashboard Shows "No Data"** for extended periods
2. **Missing Data Points** in InfluxDB queries
3. **Grafana Panels Display "No Data"** or flat lines
4. **Data Quality Metrics Show Gaps** in expected data

### Secondary Indicators
- Increased data freshness age beyond thresholds
- Incomplete candle data (missing OHLCV points)
- Order book snapshot gaps
- Trade count anomalies

## Root Cause Analysis

### Common Causes (in order of frequency)

1. **Ingestion Pipeline Failures**
   - Data collector container crashes
   - Database connection pool exhaustion
   - Buffer overflow in ingestion process
   - Invalid data format causing parsing errors

2. **Network and Connectivity Issues**
   - Intermittent network connectivity
   - Firewall rules blocking data streams
   - DNS resolution failures
   - VPN tunnel drops

3. **Exchange API Issues**
   - API maintenance windows
   - Rate limiting preventing data collection
   - API endpoint changes
   - Exchange-side data processing delays

4. **Data Validation Failures**
   - Schema validation rejecting incoming data
   - Sanity checks failing (negative prices, impossible values)
   - Data quality checks rejecting malformed data

5. **Resource Constraints**
   - Memory pressure causing OOM kills
   - CPU saturation slowing processing
   - Disk space full preventing writes
   - Database connection limits reached

## Step-by-Step Resolution Procedures

### Phase 1: Detection and Assessment (2-5 minutes)

1. **Identify Gap Details**
   ```bash
   # Query InfluxDB for data gaps
   influx query 'from(bucket:"chiseai")
     |> range(start: -1h)
     |> filter(fn:(r) => r._measurement == "data_freshness")
     |> filter(fn:(r) => r.source == "binance")
     |> group(columns: ["source"])
     |> count()'
   ```

2. **Check Data Freshness Dashboard**
   - Navigate to Grafana Data Freshness dashboard
   - Identify affected data sources
   - Note timestamp of last successful data point

3. **Examine Ingestion Pipeline Logs**
   ```bash
   # Check data collector logs
   docker logs chiseai-data-collector --since 30m --tail 200

   # Look for error patterns
   docker logs chiseai-data-collector --since 30m | grep -iE "(error|failed|exception|gap)"
   ```

### Phase 2: Immediate Mitigation (5-10 minutes)

1. **Run Data Gap Detection Script**
   ```bash
   # Analyze data completeness
   ./scripts/ops/analyze_data_gaps.sh --source binance --lookback 1h

   # Output will show:
   # - Gap locations and durations
   # - Affected data types
   # - Recommended recovery actions
   ```

2. **Check Container Health**
   ```bash
   # Verify data collector is running
   docker ps --filter "name=chiseai-data-collector"

   # Check resource usage
   docker stats --no-stream chiseai-data-collector
   ```

3. **Attempt Automated Recovery**
   ```bash
   # Run the reconnect script to reset data flow
   ./scripts/ops/reconnect_data_source.sh --exchange binance --force
   ```

### Phase 3: Investigation (10-15 minutes)

1. **Check Network Connectivity**
   ```bash
   # Test connectivity to exchange
   curl -s --connect-timeout 5 https://api.binance.com/api/v3/ping

   # Test WebSocket stream
   curl -s --connect-timeout 5 wss://stream.binance.com:9443/ws/btcusdt@kline_1m

   # Check DNS resolution
   nslookup api.binance.com
   ```

2. **Verify API Rate Limits**
   ```bash
   # Check rate limit headers
   curl -sI https://api.binance.com/api/v3/time | grep -i ratelimit

   # Calculate current usage
   ./scripts/ops/check_rate_limits.sh --exchange binance
   ```

3. **Examine Resource Usage**
   ```bash
   # Check system resources
   free -h
   df -h
   top -bn1 | head -20

   # Check InfluxDB storage
   docker exec chiseai-influxdb influxd inspect report-tsi
   ```

4. **Check for Recent Changes**
   ```bash
   # Review recent deployments
   git log --oneline -10 --all -- "**/docker-compose*.yml" "**/data-collector*"

   # Check environment changes
   git diff main...HEAD -- "**/.env*" "**/docker-compose*.yml"
   ```

### Phase 4: Data Recovery (10-15 minutes)

1. **Attempt Historical Data Backfill**
   ```bash
   # Trigger backfill for missing period
   ./scripts/ops/backfill_data.sh \
     --source binance \
     --start_time "2026-02-11T10:00:00Z" \
     --end_time "2026-02-11T10:30:00Z"

   # Verify backfill completion
   ./scripts/ops/verify_data_integrity.sh --source binance
   ```

2. **If Backfill Fails, Manual Recovery**
   ```bash
   # Fetch historical data directly
   ./scripts/ops/fetch_historical.sh \
     --exchange binance \
     --symbol btcusdt \
     --interval 1m \
     --start_ts 1707645600000 \
     --end_ts 1707652800000
   ```

### Phase 5: Validation and Documentation (5 minutes)

1. **Verify Data Integrity**
   ```bash
   # Run data integrity checks
   ./scripts/ops/verify_data_integrity.sh --source binance --full

   # Check for any remaining gaps
   ./scripts/ops/analyze_data_gaps.sh --source binance --lookback 1h
   ```

2. **Update Monitoring**
   - Confirm Grafana panels now show data
   - Verify freshness metrics are within thresholds
   - Clear any stale alerts

3. **Document Incident**
   - Record gap duration and affected data
   - Note root cause and resolution steps
   - Update prevention measures if needed

## Estimated Time to Resolve

| Scenario | Estimated Time |
|----------|---------------|
| Transient network blip | 5-10 minutes |
| Container restart needed | 10-15 minutes |
| Backfill required (small gap) | 15-20 minutes |
| Backfill required (large gap) | 20-30 minutes |
| Exchange outage | Variable (30+ minutes) |

## Prevention Measures

### Proactive Monitoring

1. **Data Completeness Monitoring**
   - Track expected vs. actual data points per source
   - Alert when data completeness <99%
   - Monitor gap frequency and duration trends

2. **Pipeline Health Checks**
   - Heartbeat mechanism every 30 seconds
   - Alert if heartbeat missed for 60 seconds
   - Automated restart on heartbeat failure

3. **Resource Monitoring**
   - Memory usage alerts (>80%)
   - CPU usage alerts (>80%)
   - Disk space alerts (>80%)
   - Database connection pool monitoring

### Preventive Maintenance

1. **Capacity Planning**
   - Monitor data volume growth
   - Scale infrastructure proactively
   - Review InfluxDB retention policies

2. **Redundancy**
   - Implement data source redundancy
   - Consider multiple API endpoints
   - Buffer data locally during network issues

3. **Testing**
   - Regular backfill testing
   - Chaos engineering for data pipeline
   - Disaster recovery drills

## Related Alerts and Dashboards

### Grafana Dashboards
- [Data Freshness Dashboard](../infrastructure/grafana/dashboards/data-freshness.json)
- [Data Pipeline Health](../infrastructure/grafana/dashboards/pipeline-health.json)
- [System Resources](../infrastructure/grafana/dashboards/system-resources.json)

### Related Runbooks
- [API Disconnect](api-disconnect.md) - Often causes data gaps
- [Order Rejects](order-rejects.md) - May result from data gaps

### Alert Rules
- `Alert: DataGapDetected` - Triggered when gap > 60 seconds
- `Alert: DataCompletenessLow` - Triggered when <99% complete
- `Alert: IngestionPipelineDown` - Triggered when pipeline stops

## Escalation Path

### Level 1: Data Engineer (0-30 minutes)
- Investigates data quality issues
- Runs backfill and recovery procedures
- Documents findings

### Level 2: DevOps Engineer (30-60 minutes)
- Escalated for infrastructure issues
- Coordinates with cloud provider if needed
- Implements temporary workarounds

### Level 3: Platform Lead (60+ minutes)
- Escalated for persistent or widespread issues
- Coordinates with exchange support
- Makes decisions on SLA impacts

## Quick Reference Commands

```bash
# Quick gap analysis
./scripts/ops/analyze_data_gaps.sh --source binance

# Force reconnect
./scripts/ops/reconnect_data_source.sh --exchange binance --force

# Trigger backfill
./scripts/ops/backfill_data.sh --source binance --lookback 1h

# Verify data integrity
./scripts/ops/verify_data_integrity.sh --source binance --full

# Check pipeline health
./scripts/ops/health_check.sh --pipeline data-collector

# View recent errors
docker logs chiseai-data-collector --since 1h | grep -iE "(error|failed|exception)"
```

## References

- [InfluxDB Data Integrity Guide](https://docs.influxdata.com/influxdb/v2/write-data/best-practices/)
- [Binance Kline/Candlestick Data](https://developers.binance.com/docs/binance-trading-api/general)
- [Data Quality Monitoring Best Practices](https://www.ibm.com/topics/data-quality)
