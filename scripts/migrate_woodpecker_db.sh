#!/bin/bash
# Woodpecker Database Migration Script
# Performs zero-downtime migration to set up Woodpecker database
#
# Usage: ./migrate_woodpecker_db.sh [OPTIONS]
# Options:
#   --dry-run    Show what would be done without making changes
#   --backup     Create backup before migration (recommended)
#   --force      Skip confirmation prompts

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
DRY_RUN=false
BACKUP=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --backup)
            BACKUP=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be done without making changes"
            echo "  --backup     Create backup before migration (recommended)"
            echo "  --force      Skip confirmation prompts"
            echo "  --help       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Header
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Woodpecker Database Migration${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}DRY RUN MODE: No changes will be made${NC}"
    echo ""
fi

# Pre-flight checks
echo -e "${BLUE}Pre-flight checks...${NC}"

# Check if running from terraform directory
if [ ! -f "main.tf" ] || [ ! -f "variables.tf" ]; then
    echo -e "${RED}ERROR: Must run from infrastructure/terraform directory${NC}"
    exit 1
fi

# Check if PostgreSQL is running
if ! docker ps --filter name=chiseai-postgres --format "{{.Names}}" | grep -q "chiseai-postgres"; then
    echo -e "${RED}ERROR: PostgreSQL container is not running${NC}"
    echo "Start it first: terraform apply -target=docker_container.postgres"
    exit 1
fi

# Check if terraform is initialized
if [ ! -d ".terraform" ]; then
    echo -e "${YELLOW}WARNING: Terraform not initialized. Running init...${NC}"
    if [ "$DRY_RUN" = false ]; then
        terraform init
    fi
fi

echo -e "${GREEN}✓ Pre-flight checks passed${NC}"
echo ""

# Backup phase
if [ "$BACKUP" = true ]; then
    echo -e "${BLUE}Creating backup...${NC}"
    BACKUP_FILE="/tmp/postgres_backup_$(date +%Y%m%d_%H%M%S).sql"
    
    if [ "$DRY_RUN" = true ]; then
        echo "Would create backup at: $BACKUP_FILE"
    else
        echo "Creating backup at: $BACKUP_FILE"
        docker exec chiseai-postgres pg_dumpall -p 5434 -U chiseai > "$BACKUP_FILE"
        echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
    fi
    echo ""
fi

# Show migration plan
echo -e "${BLUE}Migration Plan:${NC}"
echo "1. Apply null_resource.postgres_init_woodpecker"
echo "   - Create 'woodpecker' database (if not exists)"
echo "   - Create 'woodpecker' database user"
echo "   - Grant appropriate permissions"
echo ""
echo "2. Recreate woodpecker-server container"
echo "   - Apply depends_on constraint"
echo "   - Restart with database connection"
echo ""

if [ "$FORCE" = false ] && [ "$DRY_RUN" = false ]; then
    echo -n "Continue with migration? [y/N] "
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Migration cancelled."
        exit 0
    fi
fi

# Phase 1: Create database and user
echo ""
echo -e "${BLUE}Phase 1: Creating Woodpecker database and user...${NC}"

if [ "$DRY_RUN" = true ]; then
    echo "Would run: terraform plan -target=null_resource.postgres_init_woodpecker"
    echo "Would run: terraform apply -target=null_resource.postgres_init_woodpecker"
else
    echo "Running terraform apply for database initialization..."
    terraform apply -target=null_resource.postgres_init_woodpecker
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Database initialization failed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Database and user created${NC}"
fi

# Phase 2: Restart Woodpecker server
echo ""
echo -e "${BLUE}Phase 2: Restarting Woodpecker server...${NC}"

if [ "$DRY_RUN" = true ]; then
    echo "Would run: terraform apply -target=docker_container.woodpecker_server"
else
    echo "Running terraform apply for woodpecker-server..."
    terraform apply -target=docker_container.woodpecker_server
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Woodpecker server restart failed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Woodpecker server restarted${NC}"
fi

# Verification
echo ""
echo -e "${BLUE}Phase 3: Verification...${NC}"

if [ "$DRY_RUN" = true ]; then
    echo "Would run test script to verify setup"
else
    echo "Running verification tests..."
    sleep 5  # Give Woodpecker time to start
    
    if ../../scripts/test_woodpecker_db.sh; then
        echo ""
        echo -e "${GREEN}================================================${NC}"
        echo -e "${GREEN}   Migration completed successfully! ✓${NC}"
        echo -e "${GREEN}================================================${NC}"
        echo ""
        echo "Woodpecker is now configured with dedicated database credentials."
        echo ""
        echo "Access Woodpecker at: http://localhost:8012"
        echo ""
        echo "To verify logs:"
        echo "  docker logs woodpecker-server --tail 50"
        echo ""
        exit 0
    else
        echo ""
        echo -e "${RED}================================================${NC}"
        echo -e "${RED}   Migration completed with warnings!${NC}"
        echo -e "${RED}================================================${NC}"
        echo ""
        echo "The database was set up, but verification tests failed."
        echo "Check the logs above for details."
        echo ""
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Dry run completed${NC}"
echo -e "${BLUE}================================================${NC}"
