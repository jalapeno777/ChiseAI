#!/usr/bin/env bash
# Stash Lifecycle Management
# Lists and optionally removes old git stashes
#
# Usage:
#   stash_cleanup.sh [--days N] [--prune]
#
# Without --prune, runs in dry-run mode (report only).
# With --prune, deletes stashes that are older than N days.

set -euo pipefail

DAYS=30
PRUNE=false

usage() {
    cat <<EOF
Usage: $0 [--days N] [--prune]

Options:
  --days N   Consider stashes older than N days (default: 30)
  --prune    Actually delete old stashes (without this, only reports)
  --help|-h  Show this help message

Examples:
  $0                      # List stashes older than 30 days
  $0 --days 14            # List stashes older than 14 days
  $0 --prune --days 14    # Delete stashes older than 14 days
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --days)
            if [[ -z "${2:-}" || ! "$2" =~ ^[0-9]+$ ]]; then
                echo "Error: --days requires a positive integer argument" >&2
                usage
                exit 1
            fi
            DAYS="$2"
            shift 2
            ;;
        --prune)
            PRUNE=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Error: Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# Compute cutoff timestamp in seconds since epoch.
# Supports GNU date (Linux) and BSD date (macOS).
CUTOFF_DATE=$(date -d "$DAYS days ago" +%s 2>/dev/null || date -v-"${DAYS}d" +%s)

echo "=== Git Stash Lifecycle Report ==="
echo "Cutoff: stashes older than $DAYS days ($(date -d "@$CUTOFF_DATE" 2>/dev/null || date -r "$CUTOFF_DATE" 2>/dev/null))"
echo ""

STASHES=$(git stash list 2>/dev/null || true)
if [[ -z "$STASHES" ]]; then
    echo "No stashes found."
    exit 0
fi

# Collect stashes that are older than the cutoff.
# git stash list entries look like: stash@{0}: On branch: message
# We extract the index and use git log to get the actual commit date.
OLD_STASHES=()
SAFE_TO_DELETE=true

while IFS= read -r line; do
    if [[ "$line" =~ ^stash@\{([0-9]+)\}:\ (.*) ]]; then
        INDEX="${BASH_REMATCH[1]}"
        MESSAGE="${BASH_REMATCH[2]}"

        # Get the commit date of the stash (the stash commit itself).
        STASH_DATE=$(git log -1 --format='%ct' "stash@{$INDEX}" 2>/dev/null || echo "0")

        if [[ "$STASH_DATE" -lt "$CUTOFF_DATE" ]]; then
            HUMAN_DATE=$(date -d "@$STASH_DATE" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "$STASH_DATE" '+%Y-%m-%d %H:%M:%S' 2>/dev/null)
            OLD_STASHES+=("$INDEX:$MESSAGE:$HUMAN_DATE")
        fi
    fi
done <<< "$STASHES"

if [[ ${#OLD_STASHES[@]} -eq 0 ]]; then
    echo "No stashes older than $DAYS days found."
    echo "Total stashes: $(echo "$STASHES" | wc -l | tr -d ' ')"
    exit 0
fi

echo "Found ${#OLD_STASHES[@]} stash(es) older than $DAYS days:"
echo ""
printf "  %-12s %-20s %s\n" "INDEX" "DATE" "MESSAGE"
printf "  %-12s %-20s %s\n" "-----" "----" "-------"
for entry in "${OLD_STASHES[@]}"; do
    IFS=':' read -r INDEX MESSAGE HUMAN_DATE <<< "$entry"
    printf "  stash@{%-5s} %-20s %s\n" "$INDEX" "$HUMAN_DATE" "$MESSAGE"
done
echo ""

if [[ "$PRUNE" == true ]]; then
    echo "Deleting old stashes..."
    echo ""
    DROPPED=0
    FAILED=0

    # Delete in reverse index order to avoid renumbering issues.
    for entry in $(printf '%s\n' "${OLD_STASHES[@]}" | sort -t: -k1 -rn); do
        IFS=':' read -r INDEX MESSAGE HUMAN_DATE <<< "$entry"

        if git stash drop "stash@{$INDEX}" 2>/dev/null; then
            echo "  [OK] Dropped stash@{$INDEX}: $MESSAGE"
            ((DROPPED++)) || true
        else
            echo "  [FAIL] Could not drop stash@{$INDEX}: $MESSAGE"
            ((FAILED++)) || true
            SAFE_TO_DELETE=false
        fi
    done

    echo ""
    echo "Summary: $DROPPED dropped, $FAILED failed."

    if [[ "$SAFE_TO_DELETE" == false ]]; then
        echo "WARNING: Some stashes could not be dropped. Index may have shifted."
        echo "Run again to catch any remaining old stashes."
        exit 1
    fi
else
    echo "Dry-run mode: no stashes were deleted."
    echo "To actually delete, re-run with: $0 --days $DAYS --prune"
fi
