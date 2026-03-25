# InfluxDB Retention Policy Runbook

## Overview

This runbook documents the retention policy configuration for the InfluxDB instance used by ChiseAI. Data older than the retention period is automatically deleted by InfluxDB's built-in compaction engine.

## InfluxDB Instance Details

| Property         | Value                                 |
| ---------------- | ------------------------------------- |
| **Version**      | InfluxDB v2 (OSS)                     |
| **Container**    | `chiseai-influxdb`                    |
| **Image**        | `influxdb:2`                          |
| **Port**         | `18087` (host) → `18087` (container)  |
| **Organization** | (default org, ID: `a05570ccb051076f`) |

## Retention Policies

### `chiseai` Bucket

| Property                 | Value              |
| ------------------------ | ------------------ |
| **Bucket Name**          | `chiseai`          |
| **Bucket ID**            | `5363c8bf37453dfb` |
| **Retention Period**     | 60 days (1440h)    |
| **Shard Group Duration** | 7 days (168h)      |
| **Schema Type**          | implicit           |

### Other System Buckets

| Bucket        | Retention     | Purpose                      |
| ------------- | ------------- | ---------------------------- |
| `_monitoring` | 7 days (168h) | InfluxDB internal monitoring |
| `_tasks`      | 3 days (72h)  | InfluxDB task system logs    |
| `governance`  | 7 days (168h) | Governance metrics           |

## Important: Forward-Only Behavior

The retention policy is **forward-only**. It does NOT retroactively delete existing data. Data already stored in the bucket will only be deleted once it ages past the 60-day retention window naturally. When the retention period was changed from 90 days to 60 days (via bucket update), existing data between 60-90 days old was preserved and will only be removed once it exceeds 60 days from the time of the update.

## Verification

### Check Current Retention

```bash
# List all buckets with retention info
docker exec chiseai-influxdb influx bucket list

# Check specific bucket
docker exec chiseai-influxdb influx bucket list --name chiseai
```

Expected output for `chiseai` bucket:

```
ID              Name      Retention    Shard group duration  Organization ID        Schema Type
5363c8bf...     chiseai   1440h0m0s    168h0m0s             a05570ccb051076f        implicit
```

### Check Via HTTP API (v1 Compatibility)

```bash
curl -s "http://localhost:18087/query?q=SHOW+RETENTION+POLICIES+ON+chiseai" | python3 -m json.tool
```

## DDL Reference

### Change Retention Period

To modify the retention period for the `chiseai` bucket:

```bash
# Set to N days (replace 1440h with desired duration)
docker exec chiseai-influxdb influx bucket update \
  --id 5363c8bf37453dfb \
  --retention 1440h \
  --name chiseai
```

Common durations:

- 30 days: `720h`
- 60 days: `1440h`
- 90 days: `2160h`
- Infinite: `0s` (never delete)

### Create a New Bucket with Retention

```bash
docker exec chiseai-influxdb influx bucket create \
  --name <bucket-name> \
  --retention 1440h \
  --org <org-id>
```

## History

| Date       | Change                                                     | Actor                 |
| ---------- | ---------------------------------------------------------- | --------------------- |
| 2026-03-25 | Initial retention policy documented (60 days, was 90 days) | quickdev (Story I-04) |
