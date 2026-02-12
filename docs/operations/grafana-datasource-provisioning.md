# Grafana Datasource Provisioning Runbook

## Overview

This runbook describes how Grafana is configured to automatically provision the InfluxDB datasource and dashboards on startup using environment variables and provisioning files stored in the repository.

## Required Environment Variables

When running `terraform apply`, you must set the following environment variable:

```bash
export TF_VAR_influxdb_token="your-influxdb-api-token-here"
```

This token is passed to the Grafana container via the `INFLUXDB_TOKEN` environment variable, which is then used by the datasource provisioning configuration.

## Provisioning Configuration

### Datasource Provisioning

The datasource is defined in `infrastructure/grafana/provisioning/datasources/datasource.yaml`:

```yaml
apiVersion: 1

datasources:
  - name: ChiseAI InfluxDB
    type: influxdb
    access: proxy
    url: http://chiseai-influxdb:18087
    isDefault: true
    editable: true
    jsonData:
      version: Flux
      organization: chiseai
      defaultBucket: chiseai
      tlsSkipVerify: true
    secureJsonData:
      token: ${INFLUXDB_TOKEN}
    uid: chiseai-influxdb
```

The `${INFLUXDB_TOKEN}` placeholder is interpolated by Grafana using the environment variable.

### Dashboard Provisioning

Dashboards are provisioned from `infrastructure/grafana/provisioning/dashboards/dashboard.yaml`:

```yaml
apiVersion: 1

providers:
  - name: 'ChiseAI Dashboards'
    orgId: 1
    folder: 'ChiseAI'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: true
```

## Verification Steps

### 1. Verify Datasource Configuration

After `terraform apply` completes:

1. Open Grafana UI at `http://localhost:3001`
2. Navigate to **Configuration → Data Sources**
3. Look for **"ChiseAI InfluxDB"** in the list
4. Click on it to view details
5. Click **"Save & Test"** to verify the connection

**Expected Result:** Green checkmark with "Data source is working" message.

### 2. Verify Dashboard Data

1. Navigate to **Dashboards → Browse**
2. Open the **ChiseAI** folder
3. Select a dashboard (e.g., "Data Freshness")
4. Check that panels show data instead of "No data" or error messages

**Expected Result:** Panels display time-series data from InfluxDB.

### 3. API Health Check

You can also verify the datasource via Grafana API:

```bash
# Get datasource list
curl -u admin:${GRAFANA_ADMIN_PASSWORD} \
  http://localhost:3001/api/datasources

# Health check specific datasource
curl -u admin:${GRAFANA_ADMIN_PASSWORD} \
  http://localhost:3001/api/datasources/uid/chiseai-influxdb/health
```

**Expected Result:** HTTP 200 with health status.

## Troubleshooting

### Issue: "No data" in dashboard panels

**Possible Causes:**
1. InfluxDB token not set or incorrect
2. InfluxDB container not running
3. No data in InfluxDB bucket

**Resolution:**
1. Check Grafana container logs: `docker logs chiseai-grafana`
2. Verify InfluxDB is healthy: `docker ps | grep influxdb`
3. Check data exists: `docker exec chiseai-influxdb influx query 'from(bucket:"chiseai") |> range(start:-1h)'`

### Issue: "401 Unauthorized" in datasource test

**Possible Causes:**
1. `TF_VAR_influxdb_token` not set during `terraform apply`
2. Token value is incorrect

**Resolution:**
1. Verify token is set: `echo $TF_VAR_influxdb_token`
2. Re-run terraform apply with token: `TF_VAR_influxdb_token=<token> terraform apply`

### Issue: Provisioning files not loaded

**Possible Causes:**
1. Volume mount not configured correctly
2. Provisioning files missing or malformed

**Resolution:**
1. Check container has provisioning mounted:
   ```bash
   docker exec chiseai-grafana ls -la /etc/grafana/provisioning/
   ```
2. Verify datasource.yaml syntax is valid YAML
3. Check Grafana logs for provisioning errors

## Terraform Configuration Reference

The Grafana container is configured in `infrastructure/terraform/main.tf`:

```hcl
resource "docker_container" "grafana" {
  # ... other config ...
  
  env = [
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_admin_password}",
    "GF_SERVER_HTTP_PORT=3001",
    "INFLUXDB_TOKEN=${var.influxdb_token}",
    "INFLUXDB_ORG=${var.influxdb_org}",
    "INFLUXDB_BUCKET=${var.influxdb_bucket}",
  ]
  
  mounts {
    target = "/etc/grafana/provisioning"
    source = abspath("${path.module}/../grafana/provisioning")
    type   = "bind"
    read_only = true
  }
}
```

## Related Documentation

- [Grafana Provisioning Documentation](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [InfluxDB Flux Query Language](https://docs.influxdata.com/influxdb/v2.0/query-data/get-started/)
- ChiseAI Infrastructure: `infrastructure/terraform/`
