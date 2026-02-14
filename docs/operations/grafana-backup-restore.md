# Grafana Backup and Restore Runbook

## Overview

This runbook documents how to backup and restore Grafana data, including users, dashboards, and configuration.

## Architecture

- **Data Storage**: Grafana uses SQLite by default, stored in `/var/lib/grafana/grafana.db`
- **Persistence**: Docker volume `chiseai-grafana-data` persists data across container recreations
- **Bootstrap**: Container entrypoint runs `bootstrap_admin.sh` to ensure `craig-admin` user exists

## Quick Reference

### Check Grafana Status

```bash
# Check if Grafana container is running
docker ps --filter name=chiseai-grafana

# Check Grafana health
curl -u admin:admin http://localhost:3001/api/health

# List all users
curl -u admin:admin http://localhost:3001/api/users
```

## Backup Procedures

### Method 1: Backup Docker Volume (Recommended)

```bash
# Create backup directory
mkdir -p backups/grafana/$(date +%Y%m%d)

# Backup the entire Grafana volume
docker run --rm \
  -v chiseai-grafana-data:/source:ro \
  -v $(pwd)/backups/grafana/$(date +%Y%m%d):/backup \
  alpine tar czf /backup/grafana-data-$(date +%Y%m%d-%H%M%S).tar.gz -C /source .

echo "Backup created: backups/grafana/$(date +%Y%m%d)/grafana-data-*.tar.gz"
```

### Method 2: Export Dashboards via API

```bash
# Export all dashboards
GRAFANA_URL="http://localhost:3001"
GRAFANA_USER="admin"
GRAFANA_PASS="admin"

# Get list of all dashboards
curl -s -u ${GRAFANA_USER}:${GRAFANA_PASS} \
  "${GRAFANA_URL}/api/search?query=" | jq -r '.[] | select(.type=="dash-db") | .uid'

# Export each dashboard (example for one dashboard)
curl -s -u ${GRAFANA_USER}:${GRAFANA_PASS} \
  "${GRAFANA_URL}/api/dashboards/uid/chiseai-data-freshness" | jq . > dashboard-backup.json
```

### Method 3: Database File Copy

```bash
# Copy database file directly from running container
docker cp chiseai-grafana:/var/lib/grafana/grafana.db \
  backups/grafana/grafana-$(date +%Y%m%d-%H%M%S).db

# Copy provisioning configuration
cp -r infrastructure/grafana/provisioning backups/grafana/
```

## Restore Procedures

### Method 1: Restore from Docker Volume Backup

```bash
# Stop Grafana container
docker stop chiseai-grafana

# Remove existing volume (WARNING: destroys current data)
docker volume rm chiseai-grafana-data

# Create new volume and restore from backup
docker volume create chiseai-grafana-data

# Restore backup
docker run --rm \
  -v chiseai-grafana-data:/target \
  -v $(pwd)/backups/grafana/20240214/grafana-data-20240214-120000.tar.gz:/backup.tar.gz:ro \
  alpine tar xzf /backup.tar.gz -C /target

# Restart Grafana
docker start chiseai-grafana
```

### Method 2: Restore Database File

```bash
# Stop Grafana
docker stop chiseai-grafana

# Copy database file into volume
docker run --rm \
  -v chiseai-grafana-data:/target \
  -v $(pwd)/backups/grafana/grafana-20240214-120000.db:/source.db:ro \
  alpine cp /source.db /target/grafana.db

# Fix permissions (Grafana runs as user 472)
docker run --rm \
  -v chiseai-grafana-data:/target \
  alpine chown -R 472:472 /target

# Start Grafana
docker start chiseai-grafana
```

### Method 3: Recreate with Terraform (Clean State)

```bash
# WARNING: This will destroy and recreate the container
# Data is preserved in the volume if you don't delete it

# In infrastructure/terraform directory
cd infrastructure/terraform

# Plan changes
terraform plan

# Apply (recreates container, preserves volume data)
terraform apply

# Bootstrap script will recreate craig-admin user automatically
```

## User Recovery

### Reset Admin Password

```bash
# Use grafana-cli inside the container
docker exec -it chiseai-grafana grafana-cli admin reset-admin-password newpassword

# Or via API if you have another admin user
curl -X PUT \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{"password":"newpassword"}' \
  http://localhost:3001/api/admin/users/1/password
```

### Recreate craig-admin User

The bootstrap script runs automatically on container start. To manually trigger it:

```bash
# Exec into container and run bootstrap
docker exec -it chiseai-grafana /usr/local/bin/bootstrap_admin.sh
```

Or recreate the container (data persists in volume):

```bash
docker restart chiseai-grafana
```

## Verification

### After Backup

```bash
# Verify backup file exists and has content
ls -lh backups/grafana/*/grafana-data-*.tar.gz

# Test backup integrity
docker run --rm -v $(pwd)/backups/grafana/20240214:/backup alpine \
  tar tzf /backup/grafana-data-20240214-120000.tar.gz | head -20
```

### After Restore

```bash
# Check Grafana is running
docker ps --filter name=chiseai-grafana

# Check health
curl -u admin:admin http://localhost:3001/api/health

# Verify users exist
curl -u admin:admin http://localhost:3001/api/users | jq '.[] | {login: .login, role: .role}'

# Verify craig-admin specifically
curl -u admin:admin "http://localhost:3001/api/users/search?query=craig-admin" | jq .

# Test login as craig-admin
curl -u craig-admin:admin http://localhost:3001/api/user
```

## Troubleshooting

### Issue: Users Lost After Container Recreation

**Cause**: Volume not properly mounted or was deleted.

**Solution**:
1. Check volume exists: `docker volume ls | grep grafana`
2. Check volume is mounted: `docker inspect chiseai-grafana | jq '.[0].Mounts'`
3. Restore from backup if volume was deleted

### Issue: Bootstrap Script Fails

**Check logs**:
```bash
docker logs chiseai-grafana | grep bootstrap
```

**Common causes**:
- Grafana not ready (script waits 30s max)
- Wrong admin credentials
- Network issues

**Manual fix**:
```bash
# Create user manually
curl -X POST \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Craig Admin",
    "email": "craig@chiseai.local",
    "login": "craig-admin",
    "password": "admin"
  }' \
  http://localhost:3001/api/admin/users
```

### Issue: Permission Denied on Database

**Fix permissions**:
```bash
docker exec chiseai-grafana chown -R 472:472 /var/lib/grafana
```

## Automation

### Scheduled Backups (Cron)

Add to crontab for daily backups:

```bash
# /etc/cron.d/grafana-backup
0 2 * * * root /path/to/scripts/grafana-backup.sh
```

Create `/path/to/scripts/grafana-backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backups/grafana/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

docker run --rm \
  -v chiseai-grafana-data:/source:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/grafana-data-$(date +%Y%m%d-%H%M%S).tar.gz" -C /source .

# Keep only last 30 days
find /backups/grafana -name "*.tar.gz" -mtime +30 -delete
```

## Related Documentation

- [Grafana HTTP API](https://grafana.com/docs/grafana/latest/developers/http_api/)
- [Grafana Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Docker Volumes](https://docs.docker.com/storage/volumes/)
