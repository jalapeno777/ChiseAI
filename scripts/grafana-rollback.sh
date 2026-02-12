#!/bin/bash
#
# Grafana Dashboard Rollback Script
#
# Restores Grafana dashboards from a previous backup.
#
# Usage:
#     ./scripts/grafana-rollback.sh [OPTIONS] <target>
#
# Arguments:
#     target              Tag name (e.g., dashboard-backup-2024-01-15) or commit hash
#
# Options:
#     --grafana-url URL   Grafana URL (default: http://host.docker.internal:3001)
#     --grafana-api-key KEY Grafana API key (optional, uses basic auth if not set)
#     --grafana-user USER Grafana admin user (default: admin)
#     --grafana-pass PASS Grafana admin password (default: admin)
#     --provisioning-dir DIR Path to provisioning dashboards directory
#                          (default: infrastructure/grafana/provisioning/dashboards)
#     --backup-dir DIR    Backup directory (default: infrastructure/grafana/backups)
#     --dry-run           Show what would be done without making changes
#     --list              List available backups
#     --latest            Restore from the latest backup
#     --help              Show this help message
#
# Examples:
#     # List all available backups
#     ./scripts/grafana-rollback.sh --list
#
#     # Restore to a specific date
#     ./scripts/grafana-rollback.sh dashboard-backup-2024-01-15
#
#     # Restore to a specific commit
#     ./scripts/grafana-rollback.sh a1b2c3d4e5f6
#
#     # Restore to latest backup
#     ./scripts/grafana-rollback.sh --latest
#
#     # Dry run to see what would happen
#     ./scripts/grafana-rollback.sh --dry-run dashboard-backup-2024-01-15
#

set -euo pipefail

# Configuration
GRAFANA_URL="${GRAFANA_URL:-http://host.docker.internal:3001}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
PROVISIONING_DIR="${PROVISIONING_DIR:-infrastructure/grafana/provisioning/dashboards}"
BACKUP_DIR="${BACKUP_DIR:-infrastructure/grafana/backups}"
DRY_RUN=0
LIST_MODE=0
LATEST_MODE=0

TARGET=""

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --*=*)
            # Handle --option=value format
            option="${1%%=*}"
            value="${1#*=}"
            case $option in
                --grafana-url) GRAFANA_URL="$value" ;;
                --grafana-api-key) GRAFANA_API_KEY="$value" ;;
                --grafana-user) GRAFANA_USER="$value" ;;
                --grafana-pass) GRAFANA_PASSWORD="$value" ;;
                --provisioning-dir) PROVISIONING_DIR="$value" ;;
                --backup-dir) BACKUP_DIR="$value" ;;
                *)
                    echo "Unknown option: $1"
                    echo "Use --help for usage"
                    exit 1
                    ;;
            esac
            shift
            ;;
        --grafana-url)
            GRAFANA_URL="$2"
            shift 2
            ;;
        --grafana-api-key)
            GRAFANA_API_KEY="$2"
            shift 2
            ;;
        --grafana-user)
            GRAFANA_USER="$2"
            shift 2
            ;;
        --grafana-pass)
            GRAFANA_PASSWORD="$2"
            shift 2
            ;;
        --provisioning-dir)
            PROVISIONING_DIR="$2"
            shift 2
            ;;
        --backup-dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --list)
            LIST_MODE=1
            shift
            ;;
        --latest)
            LATEST_MODE=1
            shift
            ;;
        --help)
            grep -A 60 "# Usage:" "$0" | tail -n +2
            exit 0
            ;;
        -*)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
        *)
            TARGET="$1"
            shift
            ;;
    esac
done

# Validate prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    # Check jq is available
    if ! command -v jq &> /dev/null; then
        error "jq is required but not installed"
        exit 1
    fi

    # Check git is available
    if ! command -v git &> /dev/null; then
        error "git is required but not installed"
        exit 1
    fi

    # Check if we're in a git repo
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        error "Not in a git repository"
        exit 1
    fi

    # Check provisioning directory exists
    if [[ ! -d "$PROVISIONING_DIR" ]]; then
        error "Provisioning directory does not exist: $PROVISIONING_DIR"
        exit 1
    fi

    # Check backup directory exists
    if [[ ! -d "$BACKUP_DIR" ]]; then
        error "Backup directory does not exist: $BACKUP_DIR"
        exit 1
    fi

    log "Prerequisites check passed"
}

# List available backups
list_backups() {
    log "Available backups:"
    log ""
    log "Git tags:"
    git tag -l "dashboard-backup-*" --sort=-creatordate 2>/dev/null | while read -r tag; do
        local tag_date
        tag_date=$(echo "$tag" | sed 's/dashboard-backup-//')
        local commit_msg
        commit_msg=$(git log -1 --format="%s" "$tag" 2>/dev/null || echo "")
        log "  $tag"
        log "    Date: $tag_date"
        log "    Message: $commit_msg"
        log ""
    done

    log "Backup directories:"
    ls -la "$BACKUP_DIR" 2>/dev/null || echo "  No backup directories found"
}

# Get the backup directory for a given target
get_backup_dir() {
    local target="$1"

    # Check if it's a tag
    if git rev-parse --verify "refs/tags/$target" > /dev/null 2>&1; then
        # Extract date from tag name
        local backup_date
        backup_date=$(echo "$target" | sed 's/dashboard-backup-//')
        echo "$BACKUP_DIR/$backup_date"
        return 0
    fi

    # Check if it's a commit hash
    if git rev-parse --verify "$target" > /dev/null 2>&1; then
        # Find the backup directory from the commit
        local backup_path
        backup_path=$(git show "$target:infrastructure/grafana/backups/" 2>/dev/null | head -1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || echo "")

        if [[ -n "$backup_path" ]]; then
            echo "$BACKUP_DIR/$backup_path"
            return 0
        else
            error "Could not find backup directory for commit $target"
            return 1
        fi
    fi

    # Check if it's a date format
    if [[ -d "$BACKUP_DIR/$target" ]]; then
        echo "$BACKUP_DIR/$target"
        return 0
    fi

    error "Unknown target: $target"
    error "Please provide a valid tag name, commit hash, or date (YYYY-MM-DD)"
    return 1
}

# Restore dashboards from backup
restore_dashboards() {
    local backup_path="$1"

    if [[ ! -d "$backup_path" ]]; then
        error "Backup directory does not exist: $backup_path"
        return 1
    fi

    log "Restoring dashboards from: $backup_path"
    log "Target directory: $PROVISIONING_DIR"

    # Count dashboards to restore
    local dashboard_count
    dashboard_count=$(find "$backup_path" -name "*.json" -type f | wc -l)

    if [[ "$dashboard_count" -eq 0 ]]; then
        error "No dashboard files found in backup: $backup_path"
        return 1
    fi

    log "Found $dashboard_count dashboard(s) to restore"

    if [[ $DRY_RUN -eq 1 ]]; then
        log "Would restore the following dashboards:"
        find "$backup_path" -name "*.json" -type f | while read -r f; do
            log "  $f -> $PROVISIONING_DIR/$(basename "$f")"
        done
        return 0
    fi

    # Create backup of current state before restoring
    local current_backup_dir="$BACKUP_DIR/rollback-pre-$(date '+%Y-%m-%d-%H%M%S')"
    log "Creating pre-rollback backup: $current_backup_dir"
    mkdir -p "$current_backup_dir"
    cp -r "$PROVISIONING_DIR"/* "$current_backup_dir/" 2>/dev/null || true

    # Restore dashboards
    local restored=0
    local errors=0

    for dashboard_file in "$backup_path"/*.json; do
        if [[ -f "$dashboard_file" ]]; then
            local filename
            filename=$(basename "$dashboard_file")
            local target_file="$PROVISIONING_DIR/$filename"

            # Validate JSON
            if ! jq empty "$dashboard_file" 2>/dev/null; then
                ((errors++))
                error "Invalid JSON in $dashboard_file"
                continue
            fi

            # Copy the dashboard
            cp "$dashboard_file" "$target_file"
            ((restored++))

            log "  Restored: $filename"

            # Verify the restore
            if [[ -f "$target_file" ]]; then
                log "    Verified: $target_file"
            else
                ((errors++))
                error "    Failed to verify: $target_file"
            fi
        fi
    done

    log "Restored $restored dashboard(s) ($errors errors)"

    if [[ $errors -gt 0 ]]; then
        error "Some dashboards failed to restore"
        return 1
    fi

    return 0
}

# Trigger Grafana reload
trigger_grafana_reload() {
    log "Triggering Grafana dashboard reload..."

    if [[ $DRY_RUN -eq 1 ]]; then
        log "Would trigger Grafana reload at $GRAFANA_URL"
        return 0
    fi

    local auth_header=""
    if [[ -n "$GRAFANA_API_KEY" ]]; then
        auth_header="Authorization: Bearer $GRAFANA_API_KEY"
    else
        auth_header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)"
    fi

    # Try the provisioning reload endpoint
    local response
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "$auth_header" \
        "$GRAFANA_URL/api/admin/provisioning/dashboards/reload" 2>/dev/null || echo "000")

    if [[ "$response" == "200" ]]; then
        log "Grafana dashboard reload successful"
        return 0
    elif [[ "$response" == "404" ]]; then
        log "Grafana provisioning reload API not available (404)"
        log "Manual reload may be required"
        return 0
    elif [[ "$response" == "401" ]]; then
        error "Grafana API authentication failed (401)"
        return 1
    else
        error "Grafana reload returned status $response"
        return 1
    fi
}

# Create rollback git commit
create_rollback_commit() {
    local target="$1"

    if [[ $DRY_RUN -eq 1 ]]; then
        log "Would create git commit for rollback to $target"
        return 0
    fi

    log "Creating git commit for rollback..."

    # Stage the restored files
    git add "$PROVISIONING_DIR"

    # Check if there are changes to commit
    if ! git diff --cached --quiet; then
        local timestamp
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        local commit_msg="Dashboard rollback $timestamp - Restored from $target"

        git commit -m "$commit_msg"
        log "Created git commit: $commit_msg"
    else
        log "No changes to commit (dashboards unchanged)"
    fi
}

# Get the latest backup tag
get_latest_backup_tag() {
    local latest_tag
    latest_tag=$(git tag -l "dashboard-backup-*" --sort=-creatordate 2>/dev/null | head -1)

    if [[ -n "$latest_tag" ]]; then
        echo "$latest_tag"
        return 0
    else
        error "No backup tags found"
        return 1
    fi
}

# Print rollback summary
print_summary() {
    local target="$1"
    local backup_path="$2"

    log "========================================="
    log "Rollback Summary"
    log "========================================="
    log "Target:         $target"
    log "Backup Path:    $backup_path"
    log "Provisioning:  $PROVISIONING_DIR"
    log "Grafana URL:   $GRAFANA_URL"
    log "========================================="
}

# Main execution
main() {
    local target=""
    local backup_path=""

    # Check prerequisites first
    check_prerequisites

    # Handle list mode
    if [[ $LIST_MODE -eq 1 ]]; then
        list_backups
        exit 0
    fi

    # Handle latest mode
    if [[ $LATEST_MODE -eq 1 ]]; then
        target=$(get_latest_backup_tag)
        if [[ $? -ne 0 ]] || [[ -z "$target" ]]; then
            error "Could not find latest backup"
            exit 1
        fi
        log "Using latest backup: $target"
    else
        # Get target from argument
        if [[ -z "${TARGET:-}" ]]; then
            error "No target specified"
            echo "Use --help for usage"
            exit 1
        fi
        target="$TARGET"
    fi

    log "Starting Grafana dashboard rollback to: $target"

    # Get backup directory
    backup_path=$(get_backup_dir "$target")
    if [[ $? -ne 0 ]] || [[ -z "$backup_path" ]]; then
        error "Failed to find backup for: $target"
        exit 1
    fi

    log "Backup path: $backup_path"

    # Verify backup exists
    if [[ ! -d "$backup_path" ]]; then
        error "Backup directory does not exist: $backup_path"
        exit 1
    fi

    # Restore dashboards
    restore_dashboards "$backup_path"
    if [[ $? -ne 0 ]]; then
        error "Dashboard restoration failed"
        exit 1
    fi

    # Trigger Grafana reload
    trigger_grafana_reload
    if [[ $? -ne 0 ]]; then
        error "Grafana reload failed"
        exit 1
    fi

    # Create git commit
    create_rollback_commit "$target"

    # Print summary
    print_summary "$target" "$backup_path"

    log "Rollback completed successfully!"
    log ""
    log "IMPORTANT: Verify dashboard changes in Grafana UI"
    log "If issues occur, you can rollback again to a previous version"
}

# Run main
main
