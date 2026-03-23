#!/usr/bin/env bash
# detect_orphan_worktrees.sh — Find git worktrees without active Redis leases
#
# Usage: bash scripts/cleanup/detect_orphan_worktrees.sh
#
# A worktree is considered "orphaned" when it has no matching active lease
# under the Redis key pattern  bmad:chiseai:worktree-lease:*
#
# Environment variables:
#   CHISE_REDIS_HOST / REDIS_HOST   Redis host  (default: host.docker.internal)
#   CHISE_REDIS_PORT / REDIS_PORT   Redis port  (default: 6380)
#   CHISE_REDIS_DB   / REDIS_DB     Redis DB    (default: 0)

set -euo pipefail

# ── Redis config ──────────────────────────────────────────────────────────
REDIS_HOST="${CHISE_REDIS_HOST:-${REDIS_HOST:-host.docker.internal}}"
REDIS_PORT="${CHISE_REDIS_PORT:-${REDIS_PORT:-6380}}"
REDIS_DB="${CHISE_REDIS_DB:-${REDIS_DB:-0}}"

# ── Helpers ───────────────────────────────────────────────────────────────
redis_available() {
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" ping 2>/dev/null | grep -q PONG
}

get_active_lease_slugs() {
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" \
        --scan --pattern "bmad:chiseai:worktree-lease:*" 2>/dev/null \
        | sed 's|^bmad:chiseai:worktree-lease:||' \
        || true
}

# Convert a worktree path to the Redis lease key suffix format.
# Lease keys strip the leading "/" and replace path separators with ":".
#   /tmp/worktrees/ST-GIT-012-quickdev  →  tmp:worktrees:ST-GIT-012-quickdev
#   /home/tacopants/projects/ChiseAI    →  home:tacopants:projects:ChiseAI
slug_from_path() {
    echo "$1" | sed 's|^/||; s|/|:|g'
}

# ── Main ──────────────────────────────────────────────────────────────────
echo "=== Git Worktree Orphan Detection ==="
echo ""

# 1. Gather worktrees (porcelain output: "worktree <path>" lines)
mapfile -t WORKTREE_LINES < <(
    git worktree list --porcelain 2>/dev/null \
        | grep '^worktree ' \
        | sed 's/^worktree //'
) || true

if [ ${#WORKTREE_LINES[@]} -eq 0 ]; then
    echo "No worktrees found."
    exit 0
fi

# 2. Gather active leases from Redis
if redis_available; then
    mapfile -t ACTIVE_LEASES < <(get_active_lease_slugs)
else
    echo "WARNING: Redis unavailable at ${REDIS_HOST}:${REDIS_PORT} — cannot verify leases."
    echo "         All worktrees will be reported as ORPHANED."
    ACTIVE_LEASES=()
fi

echo "Active worktree leases in Redis (${#ACTIVE_LEASES[@]}):"
if [ ${#ACTIVE_LEASES[@]} -eq 0 ]; then
    echo "  (none)"
else
    for lease in "${ACTIVE_LEASES[@]}"; do
        echo "  - $lease"
    done
fi
echo ""

# 3. Classify each worktree
ACTIVE_COUNT=0
ORPHAN_COUNT=0

echo "Worktree inventory:"
for wt_path in "${WORKTREE_LINES[@]}"; do
    wt_slug=$(slug_from_path "$wt_path")
    matched=false
    for lease in "${ACTIVE_LEASES[@]+"${ACTIVE_LEASES[@]}"}"; do
        if [[ "$lease" == "$wt_slug" ]]; then
            matched=true
            break
        fi
    done

    if $matched; then
        echo "  [ACTIVE]   $wt_path"
        ((ACTIVE_COUNT++)) || true
    else
        echo "  [ORPHANED] $wt_path  (no matching lease)"
        ((ORPHAN_COUNT++)) || true
    fi
done

echo ""
echo "--- Summary ---"
echo "  Total worktrees : ${#WORKTREE_LINES[@]}"
echo "  Active (leased) : $ACTIVE_COUNT"
echo "  Orphaned        : $ORPHAN_COUNT"

if [ "$ORPHAN_COUNT" -gt 0 ]; then
    echo ""
    echo "To remove an orphaned worktree:"
    echo "  git worktree remove <path>"
    echo ""
    echo "To prune stale worktree admin entries:"
    echo "  git worktree prune"
fi

exit 0
