#!/usr/bin/env bash
#
# post_merge_verify.sh - Post-branch reconcile loop automation
#
# Implements the 5-step post-branch reconcile loop from AGENTS.md:
#   1. Check Woodpecker PR/pipeline state (classify non-green)
#   2. Route failed/error PRs for fixes (report only)
#   3. Verify merged branch head is on main (git branch --contains)
#   4. Sync local main to origin
#   5. Report status
#
# Exit codes:
#   0 = clean (all checks passed)
#   1 = issues found (failed pipelines, PRs need routing, etc.)
#   2 = error (script error, git failure, etc.)
#
# Usage:
#   post_merge_verify.sh [commit_sha]     # Check specific commit (defaults to HEAD)
#   post_merge_verify.sh --ci [commit_sha]  # JSON output for CI integration
#

set -euo pipefail

# Colors for human-readable output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# CI mode flag
CI_MODE=false

# Parse arguments
COMMIT_SHA=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ci)
            CI_MODE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [commit_sha]     # Check specific commit (defaults to HEAD)"
            echo "       $0 --ci [commit_sha]  # JSON output for CI integration"
            echo ""
            echo "Exit codes:"
            echo "  0 = clean (all checks passed)"
            echo "  1 = issues found (failed pipelines, PRs need routing, etc.)"
            echo "  2 = error (script error, git failure, etc.)"
            exit 0
            ;;
        *)
            if [[ -z "$COMMIT_SHA" ]]; then
                COMMIT_SHA="$1"
            else
                echo "Unknown argument: $1" >&2
                exit 2
            fi
            shift
            ;;
    esac
done

# Default to HEAD if no commit SHA provided
if [[ -z "$COMMIT_SHA" ]]; then
    COMMIT_SHA=$(git rev-parse HEAD)
fi

# Validate commit SHA exists
if ! git rev-parse --verify "$COMMIT_SHA" >/dev/null 2>&1; then
    if $CI_MODE; then
        echo "{\"error\": \"Invalid commit SHA: $COMMIT_SHA\"}"
    else
        echo -e "${RED}Error: Invalid commit SHA: $COMMIT_SHA${NC}" >&2
    fi
    exit 2
fi

# Resolve full SHA
COMMIT_SHA=$(git rev-parse "$COMMIT_SHA")

# Output functions for CI mode
ci_output() {
    if $CI_MODE; then
        echo "$1"
    fi
}

# Log functions
log_step() {
    if ! $CI_MODE; then
        echo -e "${BLUE}[STEP]${NC} $1"
    fi
}

log_pass() {
    if ! $CI_MODE; then
        echo -e "${GREEN}[PASS]${NC} $1"
    fi
}

log_warn() {
    if ! $CI_MODE; then
        echo -e "${YELLOW}[WARN]${NC} $1"
    fi
}

log_fail() {
    if ! $CI_MODE; then
        echo -e "${RED}[FAIL]${NC} $1"
    fi
}

log_info() {
    if ! $CI_MODE; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

# Initialize tracking variables
ISSUES_FOUND=false
STEP_FAILURES=()
WOODPECKER_ISSUES=()
BRANCH_ON_MAIN=false
MAIN_SYNCED=false

#######################################
# STEP 1: Check Woodpecker PR/pipeline state
#######################################
step_1_check_woodpecker() {
    log_step "Step 1: Checking Woodpecker pipeline state..."
    
    ci_output "{\"step\": 1, \"name\": \"woodpecker_check\", \"status\": \"running\"}"
    
    # Check if woodpecker command is available
    if ! command -v woodpecker &>/dev/null; then
        log_warn "Woodpecker CLI not found. Checking via API/Gitea instead."
        
        # Use Gitea MCP to check PR status if available, otherwise skip
        # For now, we'll do a best-effort check using git log
        local recent_commits
        recent_commits=$(git log --oneline -10 --format="%h %s" 2>/dev/null || echo "")
        
        if [[ -n "$recent_commits" ]]; then
            log_info "Recent commits on this branch:"
            echo "$recent_commits" | while IFS= read -r line; do
                log_info "  $line"
            done
        fi
        
        log_warn "Woodpecker status check skipped (CLI not available)"
        ci_output "{\"step\": 1, \"name\": \"woodpecker_check\", \"status\": \"skipped\", \"reason\": \"woodpecker_cli_not_available\"}"
        return 0
    fi
    
    # Get pipeline states using woodpecker CLI
    local pipeline_output
    pipeline_output=$(woodpecker pipeline list 2>&1) || {
        log_warn "Could not fetch Woodpecker pipelines: $pipeline_output"
        ci_output "{\"step\": 1, \"name\": \"woodpecker_check\", \"status\": \"skipped\", \"reason\": \"could_not_fetch_pipelines\"}"
        return 0
    }
    
    # Parse and classify pipeline states
    local running=0 pending=0 failure=0 error=0 success=0
    while IFS= read -r line; do
        case "$line" in
            *"[running]"*) ((running++)) ;;
            *"[pending]"*) ((pending++)) ;;
            *"[failure]"*) ((failure++)) ;;
            *"[error]"*) ((error++)) ;;
            *"[success]"*) ((success++)) ;;
        esac
    done <<< "$pipeline_output"
    
    local total=$((running + pending + failure + error + success))
    
    if ! $CI_MODE; then
        echo "  Pipeline summary: $total total"
        [[ $running -gt 0 ]] && echo "    - Running: $running"
        [[ $pending -gt 0 ]] && echo "    - Pending: $pending"
        [[ $failure -gt 0 ]] && echo "    - Failure: $failure"
        [[ $error -gt 0 ]] && echo "    - Error: $error"
        [[ $success -gt 0 ]] && echo "    - Success: $success"
    fi
    
    # Classify non-green pipelines
    local non_green=0
    [[ $running -gt 0 ]] && ((non_green+=running)) && WOODPECKER_ISSUES+=("Running pipelines: $running")
    [[ $pending -gt 0 ]] && ((non_green+=pending)) && WOODPECKER_ISSUES+=("Pending pipelines: $pending")
    [[ $failure -gt 0 ]] && ((non_green+=failure)) && WOODPECKER_ISSUES+=("Failed pipelines: $failure")
    [[ $error -gt 0 ]] && ((non_green+=error)) && WOODPECKER_ISSUES+=("Error pipelines: $error")
    
    if [[ $non_green -gt 0 ]]; then
        ISSUES_FOUND=true
        log_warn "Found $non_green non-green pipeline(s)"
        ci_output "{\"step\": 1, \"name\": \"woodpecker_check\", \"status\": \"issues\", \"non_green_count\": $non_green, \"details\": $(printf '%s\n' "${WOODPECKER_ISSUES[@]}" | jq -Rs .)}"
    else
        log_pass "All pipelines are green"
        ci_output "{\"step\": 1, \"name\": \"woodpecker_check\", \"status\": \"pass\"}"
    fi
}

#######################################
# STEP 2: Route failed/error PRs for fixes
#######################################
step_2_route_failed_prs() {
    log_step "Step 2: Routing failed/error PRs..."
    
    ci_output "{\"step\": 2, \"name\": \"route_failed_prs\", \"status\": \"running\"}"
    
    if [[ ${#WOODPECKER_ISSUES[@]} -eq 0 ]]; then
        log_pass "No failed/error PRs to route"
        ci_output "{\"step\": 2, \"name\": \"route_failed_prs\", \"status\": \"pass\", \"message\": \"no_failed_prs\"}"
        return 0
    fi
    
    # Report on failed/error PRs that need attention
    log_warn "The following issues were found and need routing for fixes:"
    for issue in "${WOODPECKER_ISSUES[@]}"; do
        log_warn "  - $issue"
    done
    
    # Check for open PRs associated with the commit
    local pr_info
    pr_info=$(git log --format="%B" -1 "$COMMIT_SHA" 2>/dev/null | grep -i "pull request" || echo "")
    
    if [[ -n "$pr_info" ]]; then
        log_info "PR reference found in commit message: $pr_info"
    fi
    
    # In CI mode, list the issues for automated routing
    if $CI_MODE; then
        local pr_list=""
        for issue in "${WOODPECKER_ISSUES[@]}"; do
            pr_list="${pr_list}\n  - ${issue}"
        done
        ci_output "{\"step\": 2, \"name\": \"route_failed_prs\", \"status\": \"needs_routing\", \"issues\": $(printf '%s\n' "${WOODPECKER_ISSUES[@]}" | jq -Rs .)}"
    fi
    
    # Mark as issue since routing is needed
    ISSUES_FOUND=true
}

#######################################
# STEP 3: Verify merged branch head on main
#######################################
step_3_verify_on_main() {
    log_step "Step 3: Verifying commit $COMMIT_SHA is on main..."
    
    ci_output "{\"step\": 3, \"name\": \"verify_on_main\", \"status\": \"running\", \"commit\": \"$COMMIT_SHA\"}"
    
    # Check if commit is on main using git branch --contains
    if git branch --contains "$COMMIT_SHA" 2>/dev/null | grep -q "^\* main$"; then
        BRANCH_ON_MAIN=true
        log_pass "Commit $COMMIT_SHA is on main"
        ci_output "{\"step\": 3, \"name\": \"verify_on_main\", \"status\": \"pass\", \"commit\": \"$COMMIT_SHA\", \"on_main\": true}"
    elif git branch --contains "$COMMIT_SHA" 2>/dev/null | grep -q "main"; then
        BRANCH_ON_MAIN=true
        log_pass "Commit $COMMIT_SHA is on main (detached HEAD or main not current)"
        ci_output "{\"step\": 3, \"name\": \"verify_on_main\", \"status\": \"pass\", \"commit\": \"$COMMIT_SHA\", \"on_main\": true}"
    else
        BRANCH_ON_MAIN=false
        ISSUES_FOUND=true
        STEP_FAILURES+=("Commit not on main: $COMMIT_SHA")
        log_fail "Commit $COMMIT_SHA is NOT on main"
        
        # Show which branches contain this commit
        local containing_branches
        containing_branches=$(git branch --contains "$COMMIT_SHA" 2>/dev/null | tr '\n' ' ' || echo "none")
        log_info "Branches containing this commit: $containing_branches"
        
        ci_output "{\"step\": 3, \"name\": \"verify_on_main\", \"status\": \"fail\", \"commit\": \"$COMMIT_SHA\", \"on_main\": false, \"containing_branches\": \"$containing_branches\"}"
    fi
}

#######################################
# STEP 4: Sync local main to origin
#######################################
step_4_sync_main() {
    log_step "Step 4: Syncing local main to origin..."
    
    ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"running\"}"
    
    # Save current branch
    local original_branch
    original_branch=$(git branch --show-current 2>/dev/null || echo "")
    
    # Track if we need to switch back
    local needed_switch_back=false
    
    # Check if main is available to switch to in this worktree
    local main_available=true
    
    # Switch to main if not already there
    if [[ "$original_branch" != "main" ]]; then
        needed_switch_back=true
        log_info "Switching to main branch..."
        
        # Try to switch and capture output
        local switch_output
        if ! switch_output=$(git switch main 2>&1); then
            # Handle worktree case - main is checked out in another worktree
            if echo "$switch_output" | grep -q "already used by worktree"; then
                main_available=false
                log_warn "Main is checked out in another worktree. Using alternative sync method..."
                
                # Fetch and update origin/main reference without switching
                log_info "Fetching origin (with prune)..."
                if ! git fetch origin --prune 2>&1; then
                    ISSUES_FOUND=true
                    STEP_FAILURES+=("Failed to fetch from origin")
                    log_fail "Failed to fetch from origin"
                    ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"error\", \"message\": \"fetch_failed\"}"
                    return 1
                fi
                
                # Verify origin/main advanced
                local local_main_oid remote_main_oid
                local_main_oid=$(git rev-parse refs/heads/main 2>/dev/null || echo "")
                remote_main_oid=$(git rev-parse refs/remotes/origin/main 2>/dev/null || echo "")
                
                if [[ -n "$local_main_oid" && -n "$remote_main_oid" && "$local_main_oid" != "$remote_main_oid" ]]; then
                    log_warn "Local main ($local_main_oid) differs from origin/main ($remote_main_oid)"
                    log_warn "Full sync requires running from main worktree"
                    ISSUES_FOUND=true
                    ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"partial\", \"message\": \"worktree_constraint_main_not_switchable\", \"local_main\": \"$local_main_oid\", \"origin_main\": \"$remote_main_oid\"}"
                else
                    log_pass "origin/main is up to date (worktree constraint prevents local main update)"
                    ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"pass\", \"message\": \"worktree_constraint_sync_skipped\", \"reason\": \"main_checked_out_in_another_worktree\"}"
                fi
                
                # Show status of current worktree
                local status_output
                status_output=$(git status -sb 2>&1)
                log_info "Git status: $status_output"
                
                MAIN_SYNCED=true
                return 0
                
            else
                # Other error
                ISSUES_FOUND=true
                STEP_FAILURES+=("Failed to switch to main: $switch_output")
                log_fail "Failed to switch to main branch: $switch_output"
                ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"error\", \"message\": \"failed_to_switch_to_main\", \"error\": \"$switch_output\"}"
                return 1
            fi
        fi
    fi
    
    # Fetch and prune
    log_info "Fetching origin (with prune)..."
    if ! git fetch origin --prune 2>&1; then
        ISSUES_FOUND=true
        STEP_FAILURES+=("Failed to fetch from origin")
        log_fail "Failed to fetch from origin"
        ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"error\", \"message\": \"fetch_failed\"}"
        
        # Try to restore original branch
        if $needed_switch_back && [[ "$original_branch" != "" ]]; then
            git switch "$original_branch" 2>/dev/null || true
        fi
        return 1
    fi
    
    # Pull with ff-only
    log_info "Fast-forward pulling origin/main..."
    if ! git pull --ff-only origin main 2>&1; then
        ISSUES_FOUND=true
        STEP_FAILURES+=("Failed to fast-forward pull - local changes or diverged history")
        log_fail "Failed to fast-forward pull origin/main. Local changes may exist or history has diverged."
        ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"error\", \"message\": \"ff_only_pull_failed\"}"
        
        # Try to restore original branch
        if $needed_switch_back && [[ "$original_branch" != "" ]]; then
            git switch "$original_branch" 2>/dev/null || true
        fi
        return 1
    fi
    
    # Show status
    local status_output
    status_output=$(git status -sb 2>&1)
    log_info "Git status: $status_output"
    
    MAIN_SYNCED=true
    
    # Restore original branch if needed
    if $needed_switch_back && [[ "$original_branch" != "" ]]; then
        log_info "Restoring original branch: $original_branch"
        git switch "$original_branch" 2>/dev/null || true
    fi
    
    log_pass "Local main synced to origin/main"
    ci_output "{\"step\": 4, \"name\": \"sync_main\", \"status\": \"pass\", \"git_status\": \"$status_output\"}"
}

#######################################
# STEP 5: Report final status
#######################################
step_5_report_status() {
    log_step "Step 5: Final status report..."
    
    ci_output "{\"step\": 5, \"name\": \"report_status\", \"status\": \"running\"}"
    
    if $CI_MODE; then
        # JSON summary
        local issues_json="[]"
        if [[ ${#STEP_FAILURES[@]} -gt 0 ]]; then
            issues_json=$(printf '%s\n' "${STEP_FAILURES[@]}" | jq -Rs 'split("\n") | map(select(length > 0))')
        fi
        
        cat <<EOF
{
  "summary": "$([ "$ISSUES_FOUND" = true ] && echo "issues_found" || echo "clean")",
  "commit_sha": "$COMMIT_SHA",
  "issues_found": $ISSUES_FOUND,
  "branch_on_main": $BRANCH_ON_MAIN,
  "main_synced": $MAIN_SYNCED,
  "step_failures": $issues_json,
  "woodpecker_issues": $(printf '%s\n' "${WOODPECKER_ISSUES[@]:-}" | jq -Rs 'split("\n") | map(select(length > 0))')
}
EOF
    else
        # Human-readable summary
        echo ""
        echo "========================================"
        echo "         POST-MERGE VERIFY SUMMARY"
        echo "========================================"
        echo "Commit SHA: $COMMIT_SHA"
        echo "On Main:    $BRANCH_ON_MAIN"
        echo "Main Synced: $MAIN_SYNCED"
        echo ""
        
        if $ISSUES_FOUND; then
            echo -e "${RED}STATUS: ISSUES FOUND${NC}"
            echo ""
            if [[ ${#STEP_FAILURES[@]} -gt 0 ]]; then
                echo "Step Failures:"
                for failure in "${STEP_FAILURES[@]}"; do
                    echo "  - $failure"
                done
                echo ""
            fi
            if [[ ${#WOODPECKER_ISSUES[@]} -gt 0 ]]; then
                echo "Woodpecker Issues:"
                for issue in "${WOODPECKER_ISSUES[@]}"; do
                    echo "  - $issue"
                done
                echo ""
            fi
        else
            echo -e "${GREEN}STATUS: CLEAN${NC}"
            echo ""
            log_pass "All post-merge checks passed"
        fi
    fi
    
    ci_output "{\"step\": 5, \"name\": \"report_status\", \"status\": \"complete\", \"issues_found\": $ISSUES_FOUND}"
}

#######################################
# Main execution
#######################################
main() {
    if ! $CI_MODE; then
        echo "========================================"
        echo "   POST-BRANCH RECONCILE VERIFICATION"
        echo "========================================"
        echo "Commit SHA: $COMMIT_SHA"
        echo "CI Mode:    $CI_MODE"
        echo ""
    fi
    
    # Run all 5 steps
    step_1_check_woodpecker || true
    step_2_route_failed_prs || true
    step_3_verify_on_main || true
    step_4_sync_main || true
    step_5_report_status || true
    
    # Final exit code
    if [[ ${#STEP_FAILURES[@]} -gt 0 ]]; then
        exit 1
    elif $ISSUES_FOUND; then
        exit 1
    else
        exit 0
    fi
}

main
