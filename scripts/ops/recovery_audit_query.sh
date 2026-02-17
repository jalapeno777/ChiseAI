#!/bin/bash
#
# Recovery Audit Query Script
# Query and analyze recovery audit logs
#
# Usage:
#   ./recovery_audit_query.sh [options]
#   ./recovery_audit_query.sh --time-range="24h"
#   ./recovery_audit_query.sh --source=redis --status=failed
#
# For PAPER-003-004: Event-Driven Self-Healing Automation
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
RECOVERY_LOG_DIR="${PROJECT_ROOT}/logs/recovery"
DEPLOYMENT_LOG_DIR="${PROJECT_ROOT}/logs/deployments"

# Default values
TIME_RANGE="24h"
SOURCE=""
STATUS=""
RECOVERY_TYPE=""
FORMAT="table"  # table, json, csv
LIMIT=100

# Usage
usage() {
    cat << EOF
Recovery Audit Query Script

Usage:
    $0 [options]

Options:
    --time-range=<range>    Time range: 1h, 24h, 7d, 30d (default: 24h)
    --source=<source>      Filter by source (e.g., redis, bybit, api)
    --status=<status>      Filter by status: succeeded, failed, pending
    --type=<type>          Filter by recovery type
    --format=<format>     Output format: table, json, csv (default: table)
    --limit=<n>            Limit results (default: 100)
    --stats                 Show statistics only
    --success-rate          Calculate success rate
    --trends                Show recovery trends over time
    --export=<file>        Export to file

Examples:
    $0 --time-range=24h --status=failed
    $0 --source=redis --format=json
    $0 --stats
    $0 --trends --time-range=7d

EOF
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --time-range=*)
                TIME_RANGE="${1#*=}"
                ;;
            --source=*)
                SOURCE="${1#*=}"
                ;;
            --status=*)
                STATUS="${1#*=}"
                ;;
            --type=*)
                RECOVERY_TYPE="${1#*=}"
                ;;
            --format=*)
                FORMAT="${1#*=}"
                ;;
            --limit=*)
                LIMIT="${1#*=}"
                ;;
            --stats)
                SHOW_STATS=1
                ;;
            --success-rate)
                SHOW_SUCCESS_RATE=1
                ;;
            --trends)
                SHOW_TRENDS=1
                ;;
            --export=*)
                EXPORT_FILE="${1#*=}"
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1" >&2
                usage
                exit 1
                ;;
        esac
        shift
    done
}

# Calculate time threshold
calculate_threshold() {
    local range="$1"
    local now
    now=$(date +%s)
    local threshold
    
    case "$range" in
        *h)
            local hours="${range%h}"
            threshold=$((now - hours * 3600))
            ;;
        *d)
            local days="${range%d}"
            threshold=$((now - days * 86400))
            ;;
        *)
            threshold=$((now - 86400))  # Default 24h
            ;;
    esac
    
    echo "$threshold"
}

# Query recovery attempts
query_attempts() {
    local threshold
    threshold=$(calculate_threshold "$TIME_RANGE")
    
    # Build filter
    local filter="true"
    
    # Filter by time
    filter="\$data.timestamp >= $threshold"
    
    # Filter by source
    if [[ -n "$SOURCE" ]]; then
        filter="$filter and \$data.source == \"$SOURCE\""
    fi
    
    # Filter by status
    if [[ -n "$STATUS" ]]; then
        filter="$filter and \$data.state == \"$STATUS\""
    fi
    
    # Filter by type
    if [[ -n "$RECOVERY_TYPE" ]]; then
        filter="$filter and \$data.recovery_type == \"$RECOVERY_TYPE\""
    fi
    
    # Find and filter attempt files
    find "$RECOVERY_LOG_DIR" -name "attempt_*.json" -type f -print0 2>/dev/null | \
    while IFS= read -r -d '' file; do
        python3 << PYEOF
import json
import sys
from datetime import datetime

try:
    with open('$file') as f:
        data = json.load(f)
    
    # Parse timestamp
    ts_str = data.get('started_at', data.get('timestamp', ''))
    if ts_str:
        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        data['_timestamp'] = ts.timestamp()
    else:
        data['_timestamp'] = 0
    
    # Apply filters
    if $filter:
        print(json.dumps(data))
except Exception as e:
    pass
PYEOF
    done | sort -t"_timestamp" -k2 -nr | head -"$LIMIT"
}

# Display results as table
format_table() {
    printf "%-30s %-20s %-20s %-15s %-10s %-10s\n" \
        "Attempt ID" "Source" "Type" "State" "Duration" "Started"
    printf "%s\n" "$(printf '=%.0s' {1..110})"
    
    while read -r line; do
        if [[ -n "$line" ]]; then
            python3 << PYEOF
import json
import sys
from datetime import datetime

try:
    data = json.loads('$line')
    
    attempt_id = data.get('attempt_id', 'N/A')[:28]
    source = data.get('source', 'N/A')[:18]
    recovery_type = data.get('recovery_type', 'N/A')[:18]
    state = data.get('state', 'N/A')[:13]
    duration = f"{data.get('duration_seconds', 0):.1f}s"
    
    started = data.get('started_at', 'N/A')
    if started != 'N/A':
        started = started.split('T')[1][:8] if 'T' in started else started[:10]
    
    print(f"{attempt_id:<30} {source:<20} {recovery_type:<20} {state:<15} {duration:<10} {started:<10}")
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
PYEOF
        fi
    done
}

# Format as JSON
format_json() {
    echo "["
    local first=1
    while read -r line; do
        if [[ -n "$line" ]]; then
            if [[ $first -eq 0 ]]; then
                echo ","
            fi
            echo "$line"
            first=0
        fi
    done
    echo "]"
}

# Format as CSV
format_csv() {
    echo "attempt_id,source,recovery_type,state,started_at,completed_at,duration_seconds,error_message"
    
    while read -r line; do
        if [[ -n "$line" ]]; then
            python3 << PYEOF
import json
import csv
import sys

try:
    data = json.loads('$line')
    row = [
        data.get('attempt_id', ''),
        data.get('source', ''),
        data.get('recovery_type', ''),
        data.get('state', ''),
        data.get('started_at', ''),
        data.get('completed_at', ''),
        str(data.get('duration_seconds', '')),
        data.get('error_message', '').replace('"', '""'),
    ]
    print(','.join(f'"{c}"' for c in row))
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
PYEOF
        fi
    done
}

# Show statistics
show_stats() {
    local attempts
    attempts=$(query_attempts)
    
    echo "Recovery Statistics (last $TIME_RANGE)"
    echo "======================================"
    
    # Calculate stats using Python
    echo "$attempts" | python3 << 'PYEOF'
import json
import sys
from collections import defaultdict

attempts = []
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            attempts.append(json.loads(line))
        except:
            pass

total = len(attempts)
if total == 0:
    print("No recovery attempts found")
    sys.exit(0)

succeeded = sum(1 for a in attempts if a.get('state') == 'succeeded')
failed = sum(1 for a in attempts if a.get('state') == 'failed')
pending = sum(1 for a in attempts if a.get('state') == 'pending')

# By source
by_source = defaultdict(lambda: {'total': 0, 'succeeded': 0, 'failed': 0})
for a in attempts:
    src = a.get('source', 'unknown')
    by_source[src]['total'] += 1
    if a.get('state') == 'succeeded':
        by_source[src]['succeeded'] += 1
    elif a.get('state') == 'failed':
        by_source[src]['failed'] += 1

# By type
by_type = defaultdict(lambda: {'total': 0, 'succeeded': 0, 'failed': 0})
for a in attempts:
    rt = a.get('recovery_type', 'unknown')
    by_type[rt]['total'] += 1
    if a.get('state') == 'succeeded':
        by_type[rt]['succeeded'] += 1
    elif a.get('state') == 'failed':
        by_type[rt]['failed'] += 1

print(f"\nOverall:")
print(f"  Total attempts:     {total}")
print(f"  Succeeded:          {succeeded} ({succeeded/total*100:.1f}%)")
print(f"  Failed:             {failed} ({failed/total*100:.1f}%)")
print(f"  Pending:            {pending}")

print(f"\nBy Source:")
for src, stats in sorted(by_source.items()):
    success_rate = stats['succeeded'] / stats['total'] * 100 if stats['total'] > 0 else 0
    print(f"  {src:<20} {stats['total']:>3} total, {success_rate:>5.1f}% success")

print(f"\nBy Recovery Type:")
for rt, stats in sorted(by_type.items()):
    success_rate = stats['succeeded'] / stats['total'] * 100 if stats['total'] > 0 else 0
    print(f"  {rt:<20} {stats['total']:>3} total, {success_rate:>5.1f}% success")
PYEOF
'}

# Show trends
show_trends() {
    local attempts
    attempts=$(query_attempts)
    
    echo "Recovery Trends (last $TIME_RANGE)"
    echo "=================================="
    
    echo "$attempts" | python3 << 'PYEOF'
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta

attempts = []
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            attempts.append(json.loads(line))
        except:
            pass

if not attempts:
    print("No recovery attempts found")
    sys.exit(0)

# Group by hour
time_buckets = defaultdict(lambda: {'total': 0, 'succeeded': 0, 'failed': 0})

for a in attempts:
    ts_str = a.get('started_at', '')
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            bucket = ts.replace(minute=0, second=0, microsecond=0)
            bucket_key = bucket.strftime('%Y-%m-%d %H:00')
            
            time_buckets[bucket_key]['total'] += 1
            if a.get('state') == 'succeeded':
                time_buckets[bucket_key]['succeeded'] += 1
            elif a.get('state') == 'failed':
                time_buckets[bucket_key]['failed'] += 1
        except:
            pass

print(f"\n{'Hour':<20} {'Total':>6} {'Success':>8} {'Failed':>8} {'Rate':>8}")
print("-" * 60)

for bucket in sorted(time_buckets.keys()):
    stats = time_buckets[bucket]
    success_rate = stats['succeeded'] / stats['total'] * 100 if stats['total'] > 0 else 0
    print(f"{bucket:<20} {stats['total']:>6} {stats['succeeded']:>8} {stats['failed']:>8} {success_rate:>7.1f}%")
PYEOF
'}

# Main
main() {
    parse_args "$@"
    
    # Check if we have any logs
    if [[ ! -d "$RECOVERY_LOG_DIR" ]] || [[ -z "$(ls -A "$RECOVERY_LOG_DIR" 2>/dev/null)" ]]; then
        echo "No recovery logs found in $RECOVERY_LOG_DIR"
        exit 0
    fi
    
    # Show stats if requested
    if [[ "${SHOW_STATS:-0}" == "1" ]]; then
        show_stats
        exit 0
    fi
    
    # Show trends if requested
    if [[ "${SHOW_TRENDS:-0}" == "1" ]]; then
        show_trends
        exit 0
    fi
    
    # Query attempts
    local results
    results=$(query_attempts)
    
    # Check if we have results
    if [[ -z "$results" ]]; then
        echo "No recovery attempts found matching the criteria"
        exit 0
    fi
    
    # Format output
    case "$FORMAT" in
        table)
            echo "$results" | format_table
            ;;
        json)
            echo "$results" | format_json
            ;;
        csv)
            echo "$results" | format_csv
            ;;
        *)
            echo "Unknown format: $FORMAT"
            exit 1
            ;;
    esac
    
    # Export if requested
    if [[ -n "${EXPORT_FILE:-}" ]]; then
        echo "$results" > "$EXPORT_FILE"
        echo -e "\n${GREEN}Results exported to: $EXPORT_FILE${NC}"
    fi
}

main "$@"
