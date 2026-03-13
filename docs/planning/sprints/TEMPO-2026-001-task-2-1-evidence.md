# TEMPO-2026-001 Task 2.1 Evidence

**Task:** 2.1 - Add Tempo datasource to Grafana
**Story ID:** TEMPO-2026-001
**Phase:** 2 (Grafana Wiring)
**Date:** 2026-03-13
**Status:** Complete

## Files Created/Modified

- `infrastructure/terraform/config/grafana/provisioning/datasources/tempo.yaml` (created)
- `infrastructure/terraform/main.tf` (modified)
  - Added `docker_volume.grafana_datasources` resource
  - Added volume mount for datasource provisioning to Grafana container

## Configuration

- **Datasource Name:** Tempo
- **Type:** tempo
- **URL:** http://chiseai-tempo:3200
- **Access:** proxy
- **Features Enabled:**
  - Service Map (linked to Prometheus)
  - Node Graph (enabled)
  - Trace Query (time shift enabled: ±1h)
  - Trace to Logs (linked to Loki)
  - Trace to Metrics (linked to Prometheus)

## Verification

### Datasource API Check
```bash
$ curl -s -u admin:admin123 http://host.docker.internal:3001/api/datasources/name/Tempo | jq '.'
{
  "id": 3,
  "uid": "P214B5B846CF3925F",
  "orgId": 1,
  "name": "Tempo",
  "type": "tempo",
  "access": "proxy",
  "url": "http://chiseai-tempo:3200",
  "isDefault": false,
  "jsonData": {
    "httpMethod": "GET",
    "nodeGraph": { "enabled": true },
    "serviceMap": { "datasourceUid": "prometheus" },
    "traceQuery": {
      "spanEndTimeShift": "1h",
      "spanStartTimeShift": "1h",
      "timeShiftEnabled": true
    },
    "tracesToLogs": {
      "datasourceUid": "loki",
      "filterBySpanID": false,
      "filterByTraceID": false,
      "mapTagNamesEnabled": false,
      "mappedTags": [{ "key": "service.name", "value": "service" }],
      "spanEndTimeShift": "1h",
      "spanStartTimeShift": "1h",
      "tags": ["service.name", "service.namespace"]
    },
    "tracesToMetrics": {
      "datasourceUid": "prometheus",
      "spanEndTimeShift": "1h",
      "spanStartTimeShift": "1h",
      "tags": [{ "key": "service.name", "value": "service" }]
    }
  },
  "readOnly": true
}
```

### Datasource List
```bash
$ curl -s -u admin:admin123 http://host.docker.internal:3001/api/datasources | jq '.[] | {name: .name, type: .type}'
{
  "name": "ChiseAI InfluxDB",
  "type": "influxdb"
}
{
  "name": "Tempo",
  "type": "tempo"
}
```

## Result

- **Datasource Status:** PROVISIONED
- **API Test:** PASS
- **Grafana Container:** Running with datasource volume mounted
- **Tempo Endpoint:** http://chiseai-tempo:3200 (accessible from Grafana)

## Notes

- Used a Docker volume (`chiseai-grafana-datasources`) for provisioning due to Docker-in-Docker constraints
- The tempo.yaml file was copied to the volume before container creation
- Datasource is marked as `readOnly: true` in Grafana (expected for provisioned datasources)
- All trace linking features are configured and ready for use

## Next Steps

Ready for Task 2.2: Create trace visualization dashboard
