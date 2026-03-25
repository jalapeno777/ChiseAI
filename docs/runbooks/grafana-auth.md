# Grafana API Authentication Runbook

## Overview

This document describes the Grafana API authentication configuration for the ChiseAI local development environment.

## Grafana Instance Details

| Property           | Value                     |
| ------------------ | ------------------------- |
| **Container Name** | `chiseai-grafana`         |
| **Image**          | `grafana/grafana:10.4.2`  |
| **Network**        | `chiseai` (Docker bridge) |
| **Host Port**      | `3001`                    |
| **Container Port** | `3001`                    |
| **Container IP**   | `172.27.0.12`             |

## Authentication Method

**Anonymous Access** is enabled for the Grafana API.

This is appropriate for the local development environment because:

- No credentials are required for API access
- CI/CD pipelines can query Grafana API without credential management
- The instance is on a private Docker network

## Environment Variables

The following environment variables configure the authentication:

| Variable                      | Value                 | Purpose                   |
| ----------------------------- | --------------------- | ------------------------- |
| `GF_AUTH_ANONYMOUS_ENABLED`   | `true`                | Enable anonymous access   |
| `GF_AUTH_ANONYMOUS_ORG_ROLE`  | `Viewer`              | Role for anonymous users  |
| `GF_SECURITY_ADMIN_USER`      | `admin`               | Grafana admin username    |
| `GF_SECURITY_ADMIN_PASSWORD`  | `${GRAFANA_PASSWORD}` | Admin password (from env) |
| `GF_SERVER_HTTP_PORT`         | `3001`                | HTTP port                 |
| `GF_SECURITY_ALLOW_EMBEDDING` | `true`                | Allow iframe embedding    |

## How to Verify API Access

### From Inside the Container

```bash
docker exec chiseai-grafana curl -s http://localhost:3001/api/health
```

Expected response:

```json
{
  "commit": "701c851be7a930e04fbc6ebb1cd4254da80edd4c",
  "database": "ok",
  "version": "10.4.2"
}
```

### From Host (via Container IP)

```bash
curl -s http://172.27.0.12:3001/api/health
```

### From Host (via Host Port)

```bash
curl -s http://localhost:3001/api/health
```

### Dashboard API (No Auth Required)

```bash
curl -s -o /dev/null -w "%{http_code}" http://172.27.0.12:3001/api/dashboards
```

Expected response: `200` or `404` (if no dashboards exist)

- **200**: API accessible, authentication working
- **401**: Authentication failed (anonymous auth not enabled)
- **404**: API accessible but no dashboards found (authentication working)

## CI/CD Authentication

For CI pipelines running in the `chiseai` Docker network, use the container's internal IP:

```bash
GRAFANA_URL=http://172.27.0.12:3001
curl -s ${GRAFANA_URL}/api/health
```

## Troubleshooting

### API Returns 401 Unauthorized

1. Check if anonymous auth is enabled in the container:

   ```bash
   docker exec chiseai-grafana env | grep GF_AUTH_ANONYMOUS
   ```

2. If not set, the container needs to be restarted with the correct environment variables

### Connection Refused

1. Verify container is running:

   ```bash
   docker ps --filter "name=chiseai-grafana"
   ```

2. Check port mapping:

   ```bash
   docker port chiseai-grafana
   ```

3. Verify network connectivity:
   ```bash
   docker network inspect chiseai
   ```

### Health Check Works but Dashboard API Returns 401

Anonymous auth may not be fully propagated. Restart the container:

```bash
docker restart chiseai-grafana
```

## Security Notes

- **Development Only**: Anonymous access is appropriate for local development only
- **Private Network**: Grafana is on the private `chiseai` Docker network, not exposed publicly
- **No Credentials in Logs**: API calls do not require credentials, so no sensitive data is logged
- **Viewer Role**: Anonymous users have Viewer role, limiting write operations

## Docker Compose Configuration

The Grafana service is defined in `infrastructure/grafana/watchdog/docker-compose.yml`:

```yaml
grafana:
  image: grafana/grafana:10.4.0
  container_name: chiseai-grafana
  networks:
    - chiseai
  ports:
    - "3001:3001"
  environment:
    - GF_SERVER_HTTP_PORT=3001
    - GF_SECURITY_ADMIN_USER=${GRAFANA_USER:-admin}
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
    - GF_AUTH_ANONYMOUS_ENABLED=true
    - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
    - GF_SECURITY_ALLOW_EMBEDDING=true
    - GF_SECURITY_CSRF_ADDITIONAL_HEADERS=X-Forwarded-Host
```

## Revision History

| Date       | Change                                   |
| ---------- | ---------------------------------------- |
| 2026-03-25 | Initial runbook - Anonymous auth enabled |
