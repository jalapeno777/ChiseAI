---
title: API Disconnect Runbook
category: alerting
severity: critical
estimated_time_to_resolve: 5-15 minutes
last_updated: 2026-02-11
maintainers: ops-team
---

# API Disconnect Runbook

## Problem Description

Exchange API connections (Binance, Bybit, Bitget) have become unresponsive or disconnected, preventing the system from:
- Receiving real-time market data
- Executing trades
- Monitoring positions

## Symptoms and Indicators

### Primary Symptoms
1. **Data Freshness Panels Show Red/Stale** (>300 seconds since last update)
2. **Grafana Alert: "Data Source Unavailable"**
3. **Order Execution Failures** - orders not being placed or filled
4. **Connection Error Logs** in the application logs:
   ```
   ERROR: ExchangeAPIConnectionFailed: Unable to connect to Bybit
   ERROR: WebSocket disconnected for Binance stream
   ```

### Secondary Indicators
- InfluxDB shows gap in data ingestion metrics
- Position tracking panels show "No Data"
- Trading bot logs show reconnection attempts

## Root Cause Analysis

### Common Causes (in order of frequency)

1. **Network Connectivity Issues**
   - Firewall rules blocking outbound connections
   - DNS resolution failures
   - Network latency spikes causing timeouts

2. **Exchange API Rate Limiting**
   - Exceeded API rate limits
   - IP address blacklisted due to too many requests
   - API key permissions revoked or expired

3. **Exchange Server Issues**
   - Scheduled maintenance windows
   - Unexpected outages
   - API version deprecation

4. **Authentication Failures**
   - API key expired or rotated
   - IP whitelist missing
   - Permissions changed

5. **Application-Level Issues**
   - WebSocket connection not properly maintained
   - Resource exhaustion (memory/CPU)
   - Unhandled exceptions causing connection drops

## Step-by-Step Resolution Procedures

### Phase 1: Initial Assessment (1-2 minutes)

1. **Check Grafana Data Freshness Dashboard**
   - Navigate to: `Grafana > Dashboards > ChiseAI - Data Freshness`
   - Identify which data sources are affected (Binance, Bybit, Bitget)
   - Note the time since last update for each source

2. **Check Application Logs**
   ```bash
   # Connect to container and check logs
   docker logs chiseai-api --tail 100 | grep -i "error\|disconnect\|failed"

   # For specific exchange
   docker logs chiseai-api --tail 100 | grep -i "bybit"
   ```

3. **Verify External Status Pages**
   - Check Binance status: https://status.binance.com/
   - Check Bybit status: https://status.bybit.com/
   - Check Bitget status: https://status.bitget.com/

### Phase 2: Immediate Mitigation (2-5 minutes)

1. **Execute Automated Remediation Script**
   ```bash
   # Run the reconnect script for affected exchange(s)
   ./scripts/ops/reconnect_data_source.sh --exchange bybit --force
   ```

2. **Verify Connection Status**
   ```bash
   # Check if data collection is healthy
   docker ps --filter "name=chiseai" --format "{{.Names}}: {{.Status}}"
   ```

3. **If automated remediation fails, proceed to manual steps:**

   a. **Restart the Data Collection Container**
   ```bash
   docker restart chiseai-data-collector
   sleep 30
   docker logs chiseai-data-collector --tail 50
   ```

   b. **Verify API Key Validity**
   ```bash
   # Check environment variables exist
   echo $BYBIT_API_KEY
   echo $BYBIT_API_SECRET
   ```

### Phase 3: Deep Investigation (5-10 minutes)

1. **Network Connectivity Test**
   ```bash
   # Test DNS resolution
   nslookup api.bybit.com

   # Test TCP connection
   curl -v --connect-timeout 10 https://api.bybit.com/v5/market/tickers

   # Test WebSocket endpoint
   curl -v --connect-timeout 10 wss://stream.bybit.com/v5/public/btc
   ```

2. **Check Rate Limit Status**
   ```bash
   # View rate limit headers from API response
   curl -I https://api.bybit.com/v5/market/tickers | grep -i "x-ratelimit"
   ```

3. **Review Recent Configuration Changes**
   ```bash
   # Check for recent deployments
   git log --oneline -10 --all -- "**/docker-compose*.yml" "**/.env*"

   # Check for API key rotations
   git log --oneline -10 --all -- "**/*.env*"
   ```

### Phase 4: Recovery Validation (2-5 minutes)

1. **Verify Data Flow Restoration**
   - Confirm Data Freshness panels show <60 seconds for affected sources
   - Check InfluxDB for recent data points:
   ```bash
   influx query 'from(bucket:"chiseai") |> range(start:-5m) |> filter(fn:(r) => r._measurement == "data_freshness") |> last()'
   ```

2. **Validate Trading Functionality**
   - Check if order execution is resuming
   - Verify position tracking is updating

3. **Document the Incident**
   - Record incident details in incident log
   - Note root cause and resolution steps taken

## Estimated Time to Resolve

| Scenario | Estimated Time |
|----------|---------------|
| Network blip (automated recovery) | 1-2 minutes |
| API rate limiting (wait it out) | 5-10 minutes |
| Configuration issue (key rotation) | 10-15 minutes |
| Exchange outage (wait for fix) | Variable (15-60+ minutes) |

## Prevention Measures

### Proactive Monitoring
1. **Health Check Endpoints**
   - Monitor `/health` endpoints for all services
   - Set up synthetic checks every 30 seconds

2. **Data Freshness Alerts**
   - Alert threshold: 180 seconds (warning), 300 seconds (critical)
   - Alert aggregation window: 2 minutes to prevent flapping

3. **Rate Limit Tracking**
   - Monitor rate limit headers in API responses
   - Alert when approaching limits (80% threshold)

### Preventive Maintenance
1. **Regular API Key Rotation**
   - Rotate API keys every 90 days
   - Update IP whitelist proactively

2. **Redundant Connections**
   - Configure backup API endpoints where available
   - Implement automatic failover logic

3. **Resource Monitoring**
   - Monitor container memory/CPU usage
   - Set up alerts for resource exhaustion (>80%)

## Related Alerts and Dashboards

### Grafana Dashboards
- [Data Freshness Dashboard](../infrastructure/grafana/dashboards/data-freshness.json)
- [API Health Dashboard](../infrastructure/grafana/dashboards/api-health.json)
- [System Health Dashboard](../infrastructure/grafana/dashboards/system-health.json)

### Related Runbooks
- [Data Gaps](data-gaps.md) - Related: overlapping issue
- [Order Rejects](order-rejects.md) - May result from API disconnect

### Alert Rules
- `Alert: DataSourceStale` - Triggered when data age > 180s
- `Alert: APIConnectionFailed` - Triggered on connection error
- `Alert: RateLimitApproaching` - Triggered at 80% of rate limit

## Escalation Path

### Level 1: On-Call Engineer (0-15 minutes)
- Primary responder for all API disconnect alerts
- Follows runbook procedures
- Attempts automated remediation first

### Level 2: DevOps Engineer (15-30 minutes)
- Escalated if Level 1 cannot resolve within 15 minutes
- Investigates configuration/network issues
- Coordinates with exchange support if needed

### Level 3: Platform Lead (30+ minutes)
- Escalated for persistent issues or widespread outages
- Coordinates with exchange relationships
- Makes decisions on workaround implementations

### Contact Information
- **Level 1**: PagerDuty rotation
- **Level 2**: DevOps Slack channel #devops-oncall
- **Level 3**: ops-team@chiseai.slack.com

## Post-Incident Actions

1. **Document Root Cause**
   - Update this runbook with any new findings
   - Add to incident log in `docs/tempmemories/`

2. **Review Alert Effectiveness**
   - Did the alert fire at the right time?
   - Were there false positives?
   - Adjust thresholds as needed

3. **Implement Preventive Measures**
   - Add monitoring for discovered gaps
   - Update automated remediation scripts
   - Consider architecture improvements

## Quick Reference Commands

```bash
# Quick health check
./scripts/ops/health_check.sh

# Reconnect specific exchange
./scripts/ops/reconnect_data_source.sh --exchange bybit

# Restart data collector
docker restart chiseai-data-collector

# Check recent logs
docker logs chiseai-api --tail 200 | grep -E "(ERROR|WARN|disconnect)"

# View connection status
docker exec chiseai-api netstat -ant | grep -E "443|8086"
```

## References

- [Grafana Alerting Documentation](https://grafana.com/docs/grafana/latest/alerting/)
- [Bybit API Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [Binance API Documentation](https://developers.binance.com/)
- [Bitget API Documentation](https://bitgetlimited.github.io/apidoc/en/spot)
