# Woodpecker Database Setup Resource
# This file contains the null_resource for initializing the woodpecker database
# Add the contents of this file to infrastructure/terraform/main.tf after the postgres container resource

# ============================================================================
# WOODPECKER DATABASE INITIALIZATION
# ============================================================================
# This resource creates the woodpecker database and user after PostgreSQL is ready.
# It runs SQL commands to:
#   1. Create the 'woodpecker' database if it doesn't exist
#   2. Create the 'woodpecker' user with password from variables
#   3. Grant appropriate permissions (least privilege principle)
#
# The triggers ensure this re-runs if:
#   - The postgres container is recreated
#   - The woodpecker_db_password variable changes
# ============================================================================

resource "null_resource" "postgres_init_woodpecker" {
  depends_on = [docker_container.postgres]

  triggers = {
    postgres_id         = docker_container.postgres.id
    woodpecker_password = var.woodpecker_db_password
  }

  provisioner "local-exec" {
    command = <<-EOT
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Woodpecker database initialization..."
      
      # Wait for PostgreSQL to be ready (max 60 seconds)
      echo "Waiting for PostgreSQL to be ready..."
      for i in {1..30}; do
        if docker exec chiseai-postgres pg_isready -p 5434 -U chiseai > /dev/null 2>&1; then
          echo "[$(date '+%Y-%m-%d %H:%M:%S')] PostgreSQL is ready"
          break
        fi
        if [ $i -eq 30 ]; then
          echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: PostgreSQL failed to become ready after 60 seconds"
          exit 1
        fi
        echo "Waiting for PostgreSQL... ($i/30)"
        sleep 2
      done

      # Create woodpecker database and user
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating woodpecker database and user..."
      docker exec -i chiseai-postgres psql -p 5434 -U chiseai -v ON_ERROR_STOP=1 <<'SQL'
        -- Create woodpecker database if not exists
        SELECT 'CREATE DATABASE woodpecker'
        WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'woodpecker')\gexec

        -- Create woodpecker user if not exists, or update password if exists
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'woodpecker') THEN
            CREATE USER woodpecker WITH PASSWORD '${var.woodpecker_db_password}';
            RAISE NOTICE 'Created woodpecker user';
          ELSE
            ALTER USER woodpecker WITH PASSWORD '${var.woodpecker_db_password}';
            RAISE NOTICE 'Updated woodpecker user password';
          END IF;
        END $$;

        -- Grant connection permission on woodpecker database
        GRANT CONNECT ON DATABASE woodpecker TO woodpecker;
SQL

      if [ $? -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Failed to create database/user"
        exit 1
      fi

      # Set up schema permissions in woodpecker database
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting up schema permissions..."
      docker exec -i chiseai-postgres psql -p 5434 -U chiseai -d woodpecker -v ON_ERROR_STOP=1 <<'SQL'
        -- Grant schema usage and create permissions
        GRANT USAGE, CREATE ON SCHEMA public TO woodpecker;

        -- Set default privileges for future tables/sequences
        ALTER DEFAULT PRIVILEGES IN SCHEMA public 
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO woodpecker;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public 
          GRANT USAGE, SELECT ON SEQUENCES TO woodpecker;

        -- Grant permissions on existing objects (if any)
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO woodpecker;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO woodpecker;
        GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO woodpecker;
SQL

      if [ $? -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Failed to set up schema permissions"
        exit 1
      fi

      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Woodpecker database initialization complete!"
    EOT
  }
}
