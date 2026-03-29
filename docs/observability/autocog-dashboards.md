# Autocog Grafana Dashboards

> **Story**: ST-AUTOCOG-O-003 | **Status**: Documented (pending Grafana availability)
> **Last checked**: 2026-03-29

## Current State

- **Grafana container**: Not running (no `grafana` container found via `docker ps`)
- **Grafana port 3001**: Connection refused on both `localhost` and `host.docker.internal`
- **Existing dashboards**: No dashboards found with "autocog" or "autonomous" in title (search blocked by Grafana unavailability)

## Action Required

Grafana must be running before dashboards can be created or verified. Check:

```bash
# Check if Grafana container exists but is stopped
docker ps -a --format '{{.Names}} {{.Status}}' | grep -i grafana

# If it exists but is stopped, start it
docker start <container_name>

# If it doesn't exist, check terraform/infrastructure for Grafana provisioning
# infrastructure/terraform/ should contain Grafana container definitions
```

## Recommended Dashboard: "Autocog Operations"

When Grafana is available, create a dashboard titled **"Autocog Operations"** with the following panels:

### Panel 1: Cycle Run Frequency

- **Type**: Time series
- **Metric**: `autocog_cycle_runs_total` (counter)
- **Query**: `rate(autocog_cycle_runs_total[1h])`
- **Purpose**: Shows how often autocog cycles run per hour. Expected: ~1-2 cycles/day in steady state.
- **Alert threshold**: < 1 cycle/24h (stale)

### Panel 2: Cycle Success Rate

- **Type**: Stat / Gauge
- **Metric**: `autocog_cycle_success_total` vs `autocog_cycle_failure_total`
- **Query**: `rate(autocog_cycle_success_total[24h]) / sum(rate(autocog_cycle_success_total[24h]), rate(autocog_cycle_failure_total[24h]))`
- **Purpose**: Percentage of cycles that complete successfully.
- **Alert threshold**: < 80%

### Panel 3: Self-Assessment Score Over Time

- **Type**: Time series
- **Metric**: `autocog_self_assessment_score` (gauge)
- **Query**: `autocog_self_assessment_score`
- **Purpose**: Tracks the brain's self-assessment quality score over time. Trend direction indicates improvement or regression.

### Panel 4: Notification Volume

- **Type**: Time series
- **Metric**: `autocog_notifications_sent_total` (counter, labeled by severity)
- **Query**: `sum by (severity) (rate(autocog_notifications_sent_total[1h]))`
- **Purpose**: Verify spam reduction. After O-001 fix, high-severity notifications should be minimal; low-severity should be batched.
- **Alert threshold**: > 10 high-severity notifications/hour

### Panel 5: Experiment Outcomes

- **Type**: Pie chart or Stat panel
- **Metric**: `autocog_experiment_outcomes_total` (counter, labeled by outcome: promoted/rolled_back/abandoned)
- **Query**: `sum by (outcome) (autocog_experiment_outcomes_total)`
- **Purpose**: Shows distribution of experiment results. Healthy system should have mostly "promoted" outcomes.

### Panel 6: Recommendation Severity Distribution

- **Type**: Bar chart
- **Metric**: `autocog_recommendations_total` (counter, labeled by severity)
- **Query**: `sum by (severity) (rate(autocog_recommendations_total[24h]))`
- **Purpose**: Shows breakdown of low/medium/high/critical recommendations generated.

## Required Prometheus Metrics

The following metrics must be exported by the autocog system (via `src/autonomous_cognition/`) for these dashboards to work:

| Metric Name                         | Type    | Labels     | Description                    |
| ----------------------------------- | ------- | ---------- | ------------------------------ |
| `autocog_cycle_runs_total`          | Counter | -          | Total autocog cycle executions |
| `autocog_cycle_success_total`       | Counter | -          | Successful cycle completions   |
| `autocog_cycle_failure_total`       | Counter | -          | Failed cycle completions       |
| `autocog_self_assessment_score`     | Gauge   | -          | Brain self-assessment score    |
| `autocog_notifications_sent_total`  | Counter | `severity` | Notifications dispatched       |
| `autocog_experiment_outcomes_total` | Counter | `outcome`  | Experiment results             |
| `autocog_recommendations_total`     | Counter | `severity` | Recommendations generated      |

## Dashboard Variables

- `datasource`: Prometheus datasource selector (for multi-env support)
- `severity`: Multi-select for notification/recommendation severity filtering

## Next Steps

1. **Start Grafana**: Ensure Grafana container is running and accessible on port 3001
2. **Verify metrics exist**: Check Prometheus for autocog metric names
3. **Create dashboard**: Use Grafana API or UI to create the "Autocog Operations" dashboard
4. **Add alerts**: Configure Grafana alert rules for the thresholds above
5. **Update this doc**: Replace this section with actual dashboard URL(s) once created
