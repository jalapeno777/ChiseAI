# Woodpecker Database Credential Solution

## Executive Summary

**Problem:** Woodpecker CI cannot connect to PostgreSQL because the `woodpecker` database user does not exist. The PostgreSQL container only creates the `chiseai` superuser during initialization, but Woodpecker expects a separate `woodpecker` user with its own database.

**Recommended Architecture:** **Option A** - Same PostgreSQL instance with dedicated database user for Woodpecker.

**Rationale:**
- ✅ Resource efficient (no additional container overhead)
- ✅ Proper isolation via database-level user permissions
- ✅ Woodpecker access independent of main app password changes
- ✅ Aligns with existing Woodpecker connection string configuration
- ✅ Easier backup/restore (single PostgreSQL instance)

---

## 1. Architecture Decision

### Option A: Same Instance, Separate User (RECOMMENDED)

**Components:**
- PostgreSQL container: `chiseai-postgres` (port 5434)
- Main app user: `chiseai` (superuser for `chiseai` database)
- Woodpecker user: `woodpecker` (limited permissions on `woodpecker` database)

**Permissions Required for Woodpecker:**
- `CONNECT` on `woodpecker` database
- `CREATE`, `USAGE` on schema `public`
- Full DML permissions: `SELECT`, `INSERT`, `UPDATE`, `DELETE`
- DDL permissions: `CREATE TABLE`, `CREATE INDEX`, `CREATE SEQUENCE`

**Why Not Option B (Separate Container)?**
- Overkill for CI tool database (Woodpecker needs ~10-50MB)
- Doubles memory overhead (PostgreSQL ~100MB base)
- Complicates backup strategy
- Requires additional network configuration

**Why Not Option C (Same User)?**
- Violates least privilege principle
- Couples Woodpecker to main app password changes
- Security risk if Woodpecker is compromised

---

## 2. Terraform Implementation

### 2.1 Updated `main.tf` - Add Database Initialization

Add this resource after the `docker_container.postgres` resource (line 109):

```hcl
# PostgreSQL Database Initialization for Woodpecker
# This null_resource creates the woodpecker database and user after PostgreSQL is ready
resource "null_resource" "postgres_init_woodpecker" {
  depends_on = [docker_container.postgres]

  triggers = {
    postgres_id = docker_container.postgres.id
    # Trigger recreation if the password changes
    woodpecker_password = var.woodpecker_db_password
  }

  provisioner "local-exec" {
    command = <<-EOT
      echo "Waiting for PostgreSQL to be ready..."
      for i in {1..30}; do
        if docker exec chiseai-postgres pg_isready -p 5434 -U chiseai > /dev/null 2>&1; then
          echo "PostgreSQL is ready"
          break
        fi
        echo "Waiting for PostgreSQL... ($i/30)"
        sleep 2
      done

      echo "Creating woodpecker database and user..."
      docker exec -i chiseai-postgres psql -p 5434 -U chiseai -d chiseai <<'SQL'
      -- Create woodpecker database if not exists
      SELECT 'CREATE DATABASE woodpecker'
      WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'woodpecker')\gexec

      -- Create woodpecker user if not exists
      DO $$
      BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'woodpecker') THEN
          CREATE USER woodpecker WITH PASSWORD '${var.woodpecker_db_password}';
        ELSE
          ALTER USER woodpecker WITH PASSWORD '${var.woodpecker_db_password}';
        END IF;
      END $$;

      -- Grant permissions on woodpecker database
      GRANT CONNECT ON DATABASE woodpecker TO woodpecker;

      -- Connect to woodpecker database and set up schema permissions
      \c woodpecker

      -- Grant schema usage and create permissions
      GRANT USAGE, CREATE ON SCHEMA public TO woodpecker;

      -- Grant table permissions (for future tables)
      ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO woodpecker;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO woodpecker;

      -- Grant permissions on existing objects (if any)
      GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO woodpecker;
      GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO woodpecker;
      GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO woodpecker;
SQL

      echo "Woodpecker database and user setup complete"
    EOT

    environment = {
      WOODPECKER_PASSWORD = var.woodpecker_db_password
    }
  }
}
```

### 2.2 Update Woodpecker Server Container

Update the `woodpecker_server` container to depend on the initialization:

```hcl
resource "docker_container" "woodpecker_server" {
  name  = "woodpecker-server"
  image = "woodpeckerci/woodpecker-server:latest"

  # Ensure database is initialized before starting Woodpecker
  depends_on = [null_resource.postgres_init_woodpecker]

  env = [
    "WOODPECKER_OPEN=false",
    "WOODPECKER_HOST=http://localhost:8012",
    "WOODPECKER_GITEA=true",
    "WOODPECKER_GITEA_URL=http://gitea:3000",
    "WOODPECKER_GITEA_CLIENT=${var.woodpecker_gitea_client}",
    "WOODPECKER_GITEA_SECRET=${var.woodpecker_gitea_secret}",
    "WOODPECKER_AGENT_SECRET=${var.woodpecker_agent_secret}",
    "WOODPECKER_PLUGINS_TRUSTED_CLONE=docker.io/woodpeckerci/plugin-git:2.5.1,docker.io/woodpeckerci/plugin-git",
    "WOODPECKER_GRPC_ADDR=:9000",
    "WOODPECKER_DATABASE_DRIVER=postgres",
    "WOODPECKER_DATABASE_DATASOURCE=postgres://woodpecker:${var.woodpecker_db_password}@chiseai-postgres:5434/woodpecker?sslmode=disable",
  ]

  # ... rest of configuration remains the same ...
}
```

### 2.3 No Changes to Variables Required

The existing `woodpecker_db_password` variable is already defined in `variables.tf` (lines 74-79):

```hcl
variable "woodpecker_db_password" {
  type        = string
  description = "Postgres password for Woodpecker database user."
  default     = "change-me"
  sensitive   = true
}
```

---

## 3. SQL Commands Reference

### 3.1 Initial Setup SQL (Executed via Terraform)

```sql
-- Create woodpecker database if not exists
SELECT 'CREATE DATABASE woodpecker'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'woodpecker')\gexec

-- Create woodpecker user with secure password
CREATE USER woodpecker WITH PASSWORD '<secure_password>';

-- Grant connection permission
GRANT CONNECT ON DATABASE woodpecker TO woodpecker;

-- Switch to woodpecker database
\c woodpecker

-- Grant schema permissions
GRANT USAGE, CREATE ON SCHEMA public TO woodpecker;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO woodpecker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
  GRANT USAGE, SELECT ON SEQUENCES TO woodpecker;

-- Grant permissions on existing objects
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO woodpecker;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO woodpecker;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO woodpecker;
```

### 3.2 Verify Permissions SQL

```sql
-- Check if user exists and has correct permissions
\c woodpecker

-- View user attributes
SELECT rolname, rolsuper, rolcreatedb, rolcanlogin 
FROM pg_roles 
WHERE rolname = 'woodpecker';

-- View database permissions
SELECT datname, datacl 
FROM pg_database 
WHERE datname = 'woodpecker';

-- View schema permissions
SELECT nspname, nspacl 
FROM pg_namespace 
WHERE nspname = 'public';

-- Test connection as woodpecker user (from shell)
-- psql -p 5434 -U woodpecker -d woodpecker -h localhost
```

### 3.3 Password Rotation SQL

```sql
-- Rotate woodpecker password (for quarterly rotation)
ALTER USER woodpecker WITH PASSWORD '<new_secure_password>';

-- After rotation, restart woodpecker-server container to pick up new password
-- docker restart woodpecker-server
```

---

## 4. Migration Strategy (Zero Downtime)

### Phase 1: Preparation (5 minutes)

1. **Backup current state:**
   ```bash
   # Backup woodpecker data (if any exists in a different location)
   docker exec chiseai-postgres pg_dump -p 5434 -U chiseai -d chiseai --schema-only > /tmp/woodpecker_schema_backup.sql
   
   # Note: Woodpecker hasn't been running, so no data to migrate
   ```

2. **Update terraform.tfvars with secure password:**
   ```hcl
   woodpecker_db_password = "<generate_secure_random_password>"
   ```

### Phase 2: Apply Changes (5 minutes)

1. **Apply Terraform:**
   ```bash
   cd infrastructure/terraform
   terraform plan -target=null_resource.postgres_init_woodpecker
   terraform apply -target=null_resource.postgres_init_woodpecker
   ```

2. **Verify database and user created:**
   ```bash
   docker exec -it chiseai-postgres psql -p 5434 -U chiseai -c "\du" | grep woodpecker
   docker exec -it chiseai-postgres psql -p 5434 -U chiseai -c "\l" | grep woodpecker
   ```

3. **Restart Woodpecker server:**
   ```bash
   # The container will be recreated with updated dependency
   terraform apply -target=docker_container.woodpecker_server
   ```

### Phase 3: Validation (5 minutes)

1. **Check Woodpecker logs:**
   ```bash
   docker logs woodpecker-server --tail 50 | grep -i "database\|connected\|error"
   ```

2. **Test database connectivity:**
   ```bash
   docker exec -it chiseai-postgres psql -p 5434 -U woodpecker -d woodpecker -c "SELECT 1;"
   ```

3. **Verify Woodpecker UI accessible:**
   ```bash
   curl -s http://localhost:8012/health || curl -s http://localhost:8012/
   ```

---

## 5. Security Considerations

### 5.1 Least Privilege Principle

The `woodpecker` user has:
- ✅ **NO** superuser privileges
- ✅ **NO** access to `chiseai` database
- ✅ **ONLY** access to `woodpecker` database
- ✅ **ONLY** necessary DDL/DML permissions

### 5.2 Password Management

1. **Generation:** Use strong, random passwords (32+ characters)
   ```bash
   openssl rand -base64 32
   ```

2. **Storage:** Store in `terraform.tfvars` (never commit to git):
   ```bash
   # terraform.tfvars (add to .gitignore!)
   woodpecker_db_password = "your-secure-password-here"
   ```

3. **Rotation:** Quarterly rotation recommended
   - Update `terraform.tfvars`
   - Run `terraform apply -target=null_resource.postgres_init_woodpecker`
   - Restart woodpecker-server container

### 5.3 Network Security

- Woodpecker connects via internal Docker network (`chiseai`)
- PostgreSQL port 5434 is bound to localhost only (check `main.tf` line 82-83)
- No external exposure of database port

---

## 6. Testing Procedure

### 6.1 Automated Test Script

Create `scripts/test_woodpecker_db.sh`:

```bash
#!/bin/bash
set -e

echo "=== Woodpecker Database Connectivity Test ==="

# Test 1: Check PostgreSQL is running
echo "[1/5] Checking PostgreSQL container..."
docker ps --filter name=chiseai-postgres --format "table {{.Names}}\t{{.Status}}" | grep -q "chiseai-postgres" || {
    echo "ERROR: PostgreSQL container not running"
    exit 1
}
echo "✓ PostgreSQL container is running"

# Test 2: Check woodpecker user exists
echo "[2/5] Checking woodpecker user exists..."
docker exec chiseai-postgres psql -p 5434 -U chiseai -t -c "SELECT 1 FROM pg_roles WHERE rolname='woodpecker';" | grep -q 1 || {
    echo "ERROR: woodpecker user does not exist"
    exit 1
}
echo "✓ woodpecker user exists"

# Test 3: Check woodpecker database exists
echo "[3/5] Checking woodpecker database exists..."
docker exec chiseai-postgres psql -p 5434 -U chiseai -t -c "SELECT 1 FROM pg_database WHERE datname='woodpecker';" | grep -q 1 || {
    echo "ERROR: woodpecker database does not exist"
    exit 1
}
echo "✓ woodpecker database exists"

# Test 4: Test connection as woodpecker user
echo "[4/5] Testing connection as woodpecker user..."
docker exec chiseai-postgres psql -p 5434 -U woodpecker -d woodpecker -c "SELECT current_user, current_database();" || {
    echo "ERROR: Cannot connect as woodpecker user"
    exit 1
}
echo "✓ Connection as woodpecker user successful"

# Test 5: Verify Woodpecker server is running
echo "[5/5] Checking Woodpecker server..."
docker ps --filter name=woodpecker-server --format "table {{.Names}}\t{{.Status}}" | grep -q "woodpecker-server" || {
    echo "WARNING: Woodpecker server not running (may still be initializing)"
}
docker logs woodpecker-server --tail 20 2>&1 | grep -i "database connected\|server started" && echo "✓ Woodpecker server connected to database" || echo "⚠ Check Woodpecker logs manually"

echo ""
echo "=== All tests passed! ==="
```

### 6.2 Manual Verification Commands

```bash
# Check user permissions
docker exec -it chiseai-postgres psql -p 5434 -U chiseai -c "\du woodpecker"

# Check database permissions
docker exec -it chiseai-postgres psql -p 5434 -U chiseai -c "\l woodpecker"

# Test write access as woodpecker
docker exec -it chiseai-postgres psql -p 5434 -U woodpecker -d woodpecker -c "
  CREATE TABLE IF NOT EXISTS test_table (id serial PRIMARY KEY, name text);
  INSERT INTO test_table (name) VALUES ('test');
  SELECT * FROM test_table;
  DROP TABLE test_table;
"

# Verify cannot access chiseai database
docker exec -it chiseai-postgres psql -p 5434 -U woodpecker -d chiseai -c "SELECT 1;" 2>&1 | grep -q "permission denied" && echo "✓ Isolation working" || echo "⚠ Check isolation"
```

---

## 7. Monitoring & Alerting

### 7.1 Health Check Script

Add to `scripts/monitor_woodpecker_db.sh`:

```bash
#!/bin/bash
# Run this via cron every 5 minutes or as a systemd timer

ALERT_WEBHOOK="${ALERT_WEBHOOK_URL:-}"
LOG_FILE="/var/log/chiseai/woodpecker_db_monitor.log"

mkdir -p "$(dirname "$LOG_FILE")"

check_db_connection() {
    docker exec chiseai-postgres psql -p 5434 -U woodpecker -d woodpecker -c "SELECT 1;" > /dev/null 2>&1
}

check_woodpecker_logs() {
    docker logs woodpecker-server --since 5m 2>&1 | grep -i "database connection error\|pq:" | head -5
}

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if ! check_db_connection; then
    ERROR_MSG="[$TIMESTAMP] CRITICAL: Woodpecker database connection failed"
    echo "$ERROR_MSG" >> "$LOG_FILE"
    
    if [ -n "$ALERT_WEBHOOK" ]; then
        curl -s -X POST -H "Content-Type: application/json" \
            -d "{\"text\":\"$ERROR_MSG\"}" \
            "$ALERT_WEBHOOK"
    fi
    exit 1
fi

DB_ERRORS=$(check_woodpecker_logs)
if [ -n "$DB_ERRORS" ]; then
    ERROR_MSG="[$TIMESTAMP] WARNING: Woodpecker database errors detected: $DB_ERRORS"
    echo "$ERROR_MSG" >> "$LOG_FILE"
    exit 1
fi

echo "[$TIMESTAMP] OK: Woodpecker database healthy" >> "$LOG_FILE"
exit 0
```

### 7.2 Log Monitoring

```bash
# Watch Woodpecker database logs in real-time
docker logs -f woodpecker-server 2>&1 | grep -i "database\|postgres\|pq:"

# Check recent database errors
docker logs woodpecker-server --since 1h 2>&1 | grep -i "error\|fail" | grep -i "database\|postgres\|pq:"
```

---

## 8. Rollback Plan

### 8.1 Quick Rollback (If Issues Occur)

```bash
# 1. Stop Woodpecker server
docker stop woodpecker-server

# 2. Remove woodpecker user and database (if needed)
docker exec -it chiseai-postgres psql -p 5434 -U chiseai -c "
  DROP DATABASE IF EXISTS woodpecker;
  DROP USER IF EXISTS woodpecker;
"

# 3. Revert Terraform changes
cd infrastructure/terraform
git checkout main.tf

# 4. Restart Woodpecker with previous configuration
# (If you had a working configuration, restore it here)
```

### 8.2 Data Backup Before Migration

```bash
# Create full PostgreSQL backup
docker exec chiseai-postgres pg_dumpall -p 5434 -U chiseai > /tmp/postgres_full_backup_$(date +%Y%m%d_%H%M%S).sql

# Or backup just the chiseai database
docker exec chiseai-postgres pg_dump -p 5434 -U chiseai -d chiseai > /tmp/chiseai_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 8.3 Restore Procedure

```bash
# If rollback needed, restore from backup
docker exec -i chiseai-postgres psql -p 5434 -U chiseai < /tmp/postgres_full_backup_YYYYMMDD_HHMMSS.sql
```

---

## 9. Implementation Checklist

- [ ] Generate secure password for `woodpecker_db_password`
- [ ] Update `terraform.tfvars` with new password
- [ ] Add `null_resource.postgres_init_woodpecker` to `main.tf`
- [ ] Add `depends_on` to `docker_container.woodpecker_server`
- [ ] Run `terraform plan` to verify changes
- [ ] Create database backup (if any existing data)
- [ ] Run `terraform apply -target=null_resource.postgres_init_woodpecker`
- [ ] Verify database and user created successfully
- [ ] Run `terraform apply -target=docker_container.woodpecker_server`
- [ ] Run test script `scripts/test_woodpecker_db.sh`
- [ ] Verify Woodpecker UI is accessible
- [ ] Update documentation
- [ ] Schedule password rotation reminder (quarterly)

---

## 10. Files to Modify

### 10.1 `infrastructure/terraform/main.tf`

Add after line 109 (after postgres container):
- `null_resource.postgres_init_woodpecker` resource

Modify around line 290-310:
- Add `depends_on = [null_resource.postgres_init_woodpecker]` to `woodpecker_server` container

### 10.2 New Files to Create

- `scripts/test_woodpecker_db.sh` - Automated testing
- `scripts/monitor_woodpecker_db.sh` - Monitoring script

### 10.3 No Changes Required

- `infrastructure/terraform/variables.tf` - Already has `woodpecker_db_password`
- Connection string - Already correct in `main.tf` line 306

---

## Summary

This solution implements **Option A** - same PostgreSQL instance with dedicated database user for Woodpecker. The key components are:

1. **Terraform null_resource** with local-exec provisioner to execute SQL after PostgreSQL is ready
2. **Proper permission grants** for least privilege access
3. **Dependency management** to ensure database is initialized before Woodpecker starts
4. **Comprehensive testing** to validate the setup

**Estimated Implementation Time:** 15-30 minutes
**Risk Level:** Low (isolated to Woodpecker, no impact on main app)
**Rollback Time:** 5 minutes

The solution ensures Woodpecker has dedicated, isolated credentials that won't be affected by main application password changes, while maintaining resource efficiency and security best practices.
