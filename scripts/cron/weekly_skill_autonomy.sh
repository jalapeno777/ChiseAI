#!/bin/bash
# Weekly Skill Autonomy Cron Wrapper
# Runs weekly and generates:
# - skills autonomy weekly KPI report
# - backlog candidates for repeated missing-skill patterns

set -euo pipefail

REPO_ROOT="/home/tacopants/projects/ChiseAI"
LOG_DIR="$REPO_ROOT/logs/skill-autonomy"
DATE_STAMP=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/weekly_$DATE_STAMP.log"
DISCORD_WEBHOOK="${DISCORD_DEV_WEBHOOK_URL:-${DISCORD_WEBHOOK_URL:-}}"

# Optional automation controls (safe defaults: disabled)
SKILL_AUTONOMY_AUTO_COMMIT="${SKILL_AUTONOMY_AUTO_COMMIT:-0}"
SKILL_AUTONOMY_COMMIT_BRANCH="${SKILL_AUTONOMY_COMMIT_BRANCH:-}"
SKILL_AUTONOMY_COMMIT_MESSAGE="${SKILL_AUTONOMY_COMMIT_MESSAGE:-chore(skills): weekly autonomy backlog ingestion [skip ci]}"
SKILL_AUTONOMY_QUEUE_WARN_THRESHOLD="${SKILL_AUTONOMY_QUEUE_WARN_THRESHOLD:-25}"
SKILL_AUTONOMY_QUEUE_CRIT_THRESHOLD="${SKILL_AUTONOMY_QUEUE_CRIT_THRESHOLD:-100}"
SKILL_AUTONOMY_WEEKLY_RETENTION_DAYS="${SKILL_AUTONOMY_WEEKLY_RETENTION_DAYS:-60}"
SKILL_AUTONOMY_BACKLOG_RETENTION_DAYS="${SKILL_AUTONOMY_BACKLOG_RETENTION_DAYS:-120}"

mkdir -p "$LOG_DIR"

notify_discord() {
  local status="$1"
  local details="$2"
  if [ -z "$DISCORD_WEBHOOK" ]; then
    return 0
  fi

  local color="15158332" # orange
  if [ "$status" = "SUCCESS" ]; then
    color="3066993" # green
  elif [ "$status" = "FAILURE" ]; then
    color="15158332" # orange
  fi

  curl -s -X POST "$DISCORD_WEBHOOK" \
    -H "Content-Type: application/json" \
    -d "{
      \"embeds\": [{
        \"title\": \"Weekly Skill Autonomy - $status\",
        \"description\": \"$details\",
        \"color\": $color,
        \"fields\": [
          {\"name\": \"Script\", \"value\": \"scripts/cron/weekly_skill_autonomy.sh\", \"inline\": false},
          {\"name\": \"Log\", \"value\": \"logs/skill-autonomy/weekly_$DATE_STAMP.log\", \"inline\": false}
        ],
        \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
      }]
    }" > /dev/null || true
}

run_log_header() {
  echo "========================================"
  echo "Weekly Skill Autonomy Tick - $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "========================================"
}

maybe_autocommit() {
  cd "$REPO_ROOT"
  if [ "$SKILL_AUTONOMY_AUTO_COMMIT" != "1" ]; then
    echo "Auto-commit disabled (SKILL_AUTONOMY_AUTO_COMMIT=$SKILL_AUTONOMY_AUTO_COMMIT)"
    return 0
  fi

  if [ -z "$SKILL_AUTONOMY_COMMIT_BRANCH" ]; then
    echo "Auto-commit enabled but SKILL_AUTONOMY_COMMIT_BRANCH is not set; skipping commit."
    return 0
  fi

  local current_branch
  current_branch="$(git branch --show-current)"
  if [ "$current_branch" != "$SKILL_AUTONOMY_COMMIT_BRANCH" ]; then
    echo "Current branch '$current_branch' != target '$SKILL_AUTONOMY_COMMIT_BRANCH'; skipping auto-commit."
    return 0
  fi

  git add docs/bmm-workflow-status.yaml || true
  git add docs/backlog/skills-autonomy-candidates-*.md 2>/dev/null || true
  git add docs/tempmemories/skill-autonomy-weekly-*.md 2>/dev/null || true

  if git diff --cached --quiet; then
    echo "No skill-autonomy artifacts staged; skipping commit."
    return 0
  fi

  git commit -m "$SKILL_AUTONOMY_COMMIT_MESSAGE"
  echo "Auto-commit created on branch '$current_branch'."
}

{
  run_log_header
  cd "$REPO_ROOT"

  /usr/bin/python3 scripts/ops/skill_autonomy_tick.py --mode=weekly
  /usr/bin/python3 scripts/ops/ingest_skill_backlog_candidates.py
  /usr/bin/python3 scripts/monitoring/skill_autonomy_queue_depth.py \
    --warn-threshold="$SKILL_AUTONOMY_QUEUE_WARN_THRESHOLD" \
    --crit-threshold="$SKILL_AUTONOMY_QUEUE_CRIT_THRESHOLD"
  /usr/bin/python3 scripts/ops/cleanup_skill_autonomy_artifacts.py \
    --weekly-retention-days="$SKILL_AUTONOMY_WEEKLY_RETENTION_DAYS" \
    --backlog-retention-days="$SKILL_AUTONOMY_BACKLOG_RETENTION_DAYS"
  maybe_autocommit

  echo "✓ Weekly skill autonomy tick + backlog ingestion completed"
  echo
} >> "$LOG_FILE" 2>&1 || {
  notify_discord "FAILURE" "Weekly skill autonomy job failed. See log for details."
  exit 1
}

notify_discord "SUCCESS" "Weekly skill autonomy job completed."
