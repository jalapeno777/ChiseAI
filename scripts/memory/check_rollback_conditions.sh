#!/bin/bash
# Daily cron check for rollback conditions
# Exit 0: success (rollback triggered OR no rollback needed)
# Exit 1: failure (error occurred)

set -e

# Direct path to worktree root - the script is at scripts/memory/check_rollback_conditions.sh
# so parent of parent of dirname is the worktree root
SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
WORKTREE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$WORKTREE_ROOT"

export PYTHONPATH="$WORKTREE_ROOT:$PYTHONPATH"

python3 -c "
from src.governance.memory.rollback_manager import check_rollback_conditions

try:
    should_rollback, breached = check_rollback_conditions()
    
    if should_rollback:
        print(f'Rollback triggered for metrics: {breached}')
        print('MEMORY_HYBRID_ENABLED has been set to False')
        exit(0)  # Success - rollback was triggered and flag disabled
    else:
        print('No rollback needed - all metrics within acceptable range')
        exit(0)  # Success - no rollback needed
        
except Exception as e:
    print(f'Error checking rollback conditions: {e}')
    exit(1)  # Failure - error occurred
"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo "Cron check completed successfully"
else
    echo "Cron check failed with exit code $exit_code"
fi

exit $exit_code