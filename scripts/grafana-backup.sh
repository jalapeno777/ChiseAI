#!/bin/bash
#
# Grafana Dashboard Backup Script
#
# Backs up all Grafana dashboards to the backups directory with git versioning.
#
# Usage:
#     ./scripts/grafana-backup.sh [OPTIONS]
#
# Options:
#     --grafana-url URL     Grafana URL (default: http://host.docker.internal:3001)
#     --grafana-api-key KEY Grafana API key (optional, uses basic auth if not set)
#     --grafana-user USER   Grafana admin user (default: admin)
#     --grafana-pass PASS   Grafana admin password (default: admin)
#     --backup-dir DIR      Backup directory (default: infrastructure/grafana/backups)
#     --retention-days DAYS Number of days to retain backups (default: 30)
#     --no-git              Skip git commit
#     --dry-run             Show what would be done without making changes
#     --help                Show this help message
#
# Environment Variables:
#     GRAFANA_URL
#     GRAFANA_API_KEY
#     GRAFANA_USER
#     GRAFANA_PASSWORD
#     BACKUP_DIR
#     RETENTION_DAYS
#     SKIP_GIT_COMMIT (if set, skips git commit)
#

set -euo pipefail

# Configuration
GRAFANA_URL="${GRAFANA_URL:-http://host.docker.internal:3001}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
BACKUP_DIR="${BACKUP_DIR:-infrastructure/grafana/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
SKIP_GIT_COMMIT="${SKIP_GIT_COMMIT:-}"
DRY_RUN=0

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
                --backup-dir) BACKUP_DIR="$value" ;;
                --retention-days) RETENTION_DAYS="$value" ;;
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
        --backup-dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --retention-days)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        --no-git)
            SKIP_GIT_COMMIT=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --help)
            grep -A 50 "# Usage:" "$0" | tail -n +2
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

get_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

get_date_folder() {
    date '+%Y-%m-%d'
}

get_tag_name() {
    date '+%Y-%m-%d-%H%M%S'
}

# Validate prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    # Check jq is available
    if ! command -v jq &> /dev/null; then
        error "jq is required but not installed"
        exit 1
    fi

    # Check curl is available
    if ! command -v curl &> /dev/null; then
        error "curl is required but not installed"
        exit 1
    fi

    # Check git is available
    if ! command -v git &> /dev/null; then
        error "git is required but not installed"
        exit 1
    fi

    # Check backup directory exists
    if [[ ! -d "$BACKUP_DIR" ]]; then
        if [[ $DRY_RUN -eq 0 ]]; then
            mkdir -p "$BACKUP_DIR"
            log "Created backup directory: $BACKUP_DIR"
        else
            log "Would create backup directory: $BACKUP_DIR"
        fi
    fi

    log "Prerequisites check passed"
}

# Query Grafana for all dashboards
fetch_dashboards() {
    log "Fetching dashboards from Grafana at $GRAFANA_URL..."

    local auth_header=""
    if [[ -n "$GRAFANA_API_KEY" ]]; then
        auth_header="Authorization: Bearer $GRAFANA_API_KEY"
    else
        auth_header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)"
    fi

    local response
    response=$(curl -s -H "$auth_header" \
        -H "Content-Type: application/json" \
        "$GRAFANA_URL/api/search" \
        -d '{"type":"dash-db"}' || echo "[]")

    if [[ -z "$response" ]] || [[ "$response" == "null" ]]; then
        error "Failed to fetch dashboards from Grafana"
        exit 1
    fi

    echo "$response"
}

# Get dashboard JSON content
get_dashboard_json() {
    local uid="$1"
    local auth_header=""

    if [[ -n "$GRAFANA_API_KEY" ]]; then
        auth_header="Authorization: Bearer $GRAFANA_API_KEY"
    else
        auth_header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)"
    fi

    curl -s -H "$auth_header" \
        "$GRAFANA_URL/api/dashboards/uid/$uid" | jq '.dashboard'
}

# Export all dashboards
export_dashboards() {
    local dashboards_json="$1"
    local backup_date="$2"
    local backup_path="$BACKUP_DIR/$backup_date"

    if [[ $DRY_RUN -eq 0 ]]; then
        mkdir -p "$backup_path"
    fi

    log "Exporting dashboards to $backup_path..."

    local total_dashboards
    total_dashboards=$(echo "$dashboards_json" | jq 'length')
    local exported=0
    local errors=0

    # Get list of dashboard UIDs
    local uids
    uids=$(echo "$dashboards_json" | jq -r '.[].uid')

    for uid in $uids; do
        local title
        title=$(echo "$dashboards_json" | jq -r ".[] | select(.uid == \"$uid\") | .title")

        # Sanitize title for filename
        local filename
        filename=$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-')

        if [[ -z "$filename" ]]; then
            filename="dashboard-$uid"
        fi

        local filepath="$backup_path/${filename}.json"

        if [[ $DRY_RUN -eq 1 ]]; then
            log "  Would export: $title -> $filepath"
        else
            log "  Exporting: $title -> $filepath"

            local dashboard_json
            dashboard_json=$(get_dashboard_json "$uid")

            if [[ -n "$dashboard_json" ]] && [[ "$dashboard_json" != "null" ]]; then
                # Create JSON with metadata
                local export_time
                export_time=$(get_timestamp)
                local full_json
                full_json=$(jq -n \
                    --argjson dashboard "$dashboard_json" \
                    --arg title "$title" \
                    --arg uid "$uid" \
                    --arg exported_at "$export_time" \
                    '{
                        meta: {
                            title: $title,
                            uid: $uid,
                            exported_at: $exported_at,
                            source: "grafana-api"
                        },
                        dashboard: $dashboard
                    }')

                echo "$full_json" > "$filepath"
                ((exported++))
                log "    Exported: $filepath"
            else
                ((errors++))
                error "  Failed to export dashboard: $title (uid: $uid)"
            fi
        fi
    done

    log "Exported $exported dashboards ($errors errors)"

    if [[ $errors -gt 0 ]]; then
        error "Some dashboards failed to export"
    fi

    # Return export status
    echo "$exported:$errors"
}

# Create git commit
create_git_commit() {
    local backup_date="$1"
    local backup_path="$BACKUP_DIR/$backup_date"
    local export_count="$2"

    if [[ -n "$SKIP_GIT_COMMIT" ]]; then
        log "Skipping git commit (SKIP_GIT_COMMIT is set)"
        return 0
    fi

    if [[ $DRY_RUN -eq 1 ]]; then
        log "Would create git commit for backup $backup_date"
        return 0
    fi

    log "Creating git commit for backup..."

    # Check if we're in a git repo
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        error "Not in a git repository"
        return 1
    fi

    # Stage the backup files
    git add "$backup_path"

    # Check if there are changes to commit
    if ! git diff --cached --quiet; then
        # Create commit with timestamp format
        local timestamp
        timestamp=$(get_timestamp)
        local commit_msg="Dashboard backup $timestamp - $export_count dashboards"

        git commit -m "$commit_msg"

        # Create tag for this backup
        local tag_name="dashboard-backup-$backup_date"
        local tag_msg="Dashboard backup from $timestamp

Automated backup of $export_count dashboards.

Backup location: $backup_path"

        # Check if tag already exists
        if git rev-parse "$tag_name" > /dev/null 2>&1; then
            # Delete existing tag and create new one
            git tag -d "$tag_name" > /dev/null 2>&1 || true
        fi

        git tag -a "$tag_name" -m "$tag_msg"

        log "Created git commit and tag: $tag_name"
    else
        log "No changes to commit (dashboards unchanged)"
    fi
}

# Cleanup old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."

    if [[ $DRY_RUN -eq 1 ]]; then
        log "Would remove backups older than $RETENTION_DAYS days"
        return 0
    fi

    # Find and remove old backup directories
    local deleted_count=0
    while IFS= read -r backup_dir; do
        if [[ -d "$backup_dir" ]]; then
            log "Removing old backup: $backup_dir"
            rm -rf "$backup_dir"

            # Also remove git tag if it exists
            local backup_date
            backup_date=$(basename "$backup_dir")
            local tag_name="dashboard-backup-$backup_date"
            if git rev-parse "$tag_name" > /dev/null 2>&1; then
                git tag -d "$tag_name" > /dev/null 2>&1 || true
                log "  Removed git tag: $tag_name"
            fi

            ((deleted_count++))
        fi
    done < <(find "$BACKUP_DIR" -maxdepth 1 -type d -name "????-??-??" -mtime +"$RETENTION_DAYS" 2>/dev/null)

    if [[ $deleted_count -gt 0 ]]; then
        log "Cleaned up $deleted_count old backup(s)"
    else
        log "No old backups to clean up"
    fi
}

# Print backup summary
print_summary() {
    local backup_date="$1"
    local backup_path="$BACKUP_DIR/$backup_date"

    log "========================================="
    log "Backup Summary"
    log "========================================="
    log "Backup Date:    $backup_date"
    log "Backup Path:    $backup_path"
    log "Grafana URL:    $GRAFANA_URL"
    log "Retention:      $RETENTION_DAYS days"
    log "========================================="
}

# Main execution
main() {
    log "Starting Grafana dashboard backup..."

    # Check prerequisites
    check_prerequisites

    # Get timestamp and folder name
    local backup_date
    backup_date=$(get_date_folder)
    local timestamp
    timestamp=$(get_timestamp)

    # Fetch dashboards from Grafana
    local dashboards_json
    dashboards_json=$(fetch_dashboards)

    # Export dashboards
    local export_result
    export_result=$(export_dashboards "$dashboards_json" "$backup_date")
    local export_count
    export_count=$(echo "$export_result" | cut -d':' -f1)

    if [[ "$export_count" == "0" ]] && [[ -n "$export_result" ]]; then
        error "No dashboards were exported"
        exit 1
    fi

    # Create git commit
    create_git_commit "$backup_date" "$export_count"

    # Cleanup old backups
    cleanup_old_backups

    # Print summary
    print_summary "$backup_date"

    log "Backup completed successfully!"

    # Return the backup path for potential integration
    echo "$BACKUP_DIR/$backup_date"
}

# Run main
main
