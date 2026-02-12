# ST-OPS-008: Datasource Health

## Story Metadata

| Field | Value |
|-------|-------|
| **Story ID** | ST-OPS-008 |
| **Title** | Datasource Health Monitoring |
| **Story Points** | 7 |
| **Epic ID** | EP-OPS-001 |
| **Sprint ID** | p0-7 |
| **Status** | Planned |

## Description

Implement comprehensive datasource health monitoring and alerting system for all Grafana datasources. This includes automated health checks, connectivity monitoring, query performance tracking, and proactive alerting when datasources become unavailable or degraded.

## Features Delivered

1. **Health Check Service**
   - Periodic health checks for all configured datasources
   - InfluxDB connectivity and query execution tests
   - Response time measurement and threshold alerting

2. **Datasource Status Dashboard**
   - Real-time datasource health status panel
   - Historical uptime/availability metrics
   - Query performance trends per datasource

3. **Automated Alerting**
   - Discord notifications for datasource failures
   - Configurable alert thresholds (response time, error rate)
   - Alert escalation for prolonged outages

4. **Self-Healing Capabilities**
   - Automatic datasource reconnection attempts
   - Connection pool management
   - Circuit breaker pattern for failing datasources

## Dependencies

- ST-OPS-001: Grafana Dashboards (completed - datasource infrastructure exists)
- ST-OPS-004: Taiga Sync (completed - alerting infrastructure exists)
- ST-DATA-004: Data Quality Monitoring (completed - monitoring patterns established)

## Acceptance Criteria

- [ ] AC1: Health check service runs every 60 seconds
- [ ] AC2: Service monitors InfluxDB datasource connectivity
- [ ] AC3: Health status written to InfluxDB for trending
- [ ] AC4: Discord alert sent when datasource fails health check
- [ ] AC5: Dashboard panel shows current datasource status
- [ ] AC6: Historical health metrics available for 30 days
- [ ] AC7: Service implements exponential backoff for reconnection

## Scope Globs

```yaml
implementation:
  - src/operations/datasource_health/**
  - infrastructure/terraform/datasource-health.tf
documentation:
  - docs/operations/datasource-health-monitoring.md
tests:
  - tests/operations/test_datasource_health.py
  - tests/integration/test_datasource_health_e2e.py
```

## Verification Steps

1. Deploy health check service: `docker compose up datasource-health`
2. Verify health check logs: `docker logs chiseai-datasource-health`
3. Check InfluxDB for health metrics: query `datasource_health` measurement
4. Stop InfluxDB container and verify Discord alert is sent
5. Restart InfluxDB and confirm recovery notification
6. View datasource health dashboard panel in Grafana
7. Verify 30-day retention of health metrics

## Notes

- Health checks should be lightweight (simple `SHOW DATABASES` query)
- Store health metrics in separate InfluxDB bucket for isolation
- Consider implementing health check for multiple datasource types
- Alert throttling to prevent spam during intermittent failures
