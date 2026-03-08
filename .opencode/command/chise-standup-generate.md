---
name: "chise-standup-generate"
description: "ChiseAI: Generate daily standup report from workflow status, Redis iterlogs, and incidents"
disable-model-invocation: true
---

Generate a comprehensive daily standup snapshot report aggregating workflow status, active stories, and blockers.

## Execution

### Interactive Mode
```bash
python3 scripts/standup/generate_standup.py
```

### With Parameters
```bash
python3 scripts/standup/generate_standup.py \
    --date="2026-03-08" \
    --post-discord \
    --channel-id="1234567890"
```

### Standalone (No Script)
```bash
# Quick standalone execution
cat docs/bmm-workflow-status.yaml | python3 -c "
import sys, yaml, json
data = yaml.safe_load(sys.stdin)
print(f'Active stories: {len(data.get(\"backlog\", []))}')
print(f'Completed: {len(data.get(\"completed\", []))}')
"
```

## Required Steps

### Step 1: Read Workflow Status
```bash
# Load current workflow status from canonical source
WORKFLOW_STATUS=$(cat docs/bmm-workflow-status.yaml)

# Extract key metrics:
# - Current phase
# - Active epics
# - Backlog items
# - Recently completed stories
```

**Fields to Extract:**
- `current_phase` - Current operational phase
- `epics` - All epics with status (completed/in_progress/planned)
- `backlog` - Stories with status: in_progress, planned, blocked
- `completed` - Stories completed in last 7 days

### Step 2: Query Redis for Active Stories
```bash
# Find all active story iterlogs
redis-cli KEYS "bmad:chiseai:iterlog:story:*" | while read key; do
    redis-cli HGETALL "$key"
done

# Filter by:
# - status: in_progress
# - started_at: within last 7 days
# - last_updated: within last 24 hours
```

**Redis Key Patterns:**
- `bmad:chiseai:iterlog:story:<story_id>` - Story iteration log (hash)
- `bmad:chiseai:iterlog:story:<story_id>:incidents` - Incident list
- `bmad:chiseai:ownership` - Current scope ownership

### Step 3: Gather Yesterday's Completed Work
```bash
# From workflow status - completed stories with recent merge_date
# From Redis iterlogs - stories with status=completed and updated yesterday

# Filter criteria:
# - merge_date or completion_date within last 24-48 hours
# - status: merged, completed, validated
```

**Data Sources:**
1. `docs/bmm-workflow-status.yaml` → `completed` section
2. Redis: `bmad:chiseai:iterlog:story:*` with `status=completed`
3. Git log: `git log --since="yesterday" --oneline --merges`

### Step 4: Identify Today's Planned Work
```bash
# From workflow status - backlog items with:
# - status: in_progress, planned
# - priority: P0, P1 (focus on high priority)
# - owner: assigned agent

# From Redis iterlogs - stories with:
# - status: in_progress
# - phase: implementation, testing
```

**Filter Criteria:**
- Status: `in_progress`, `planned`
- Recent activity: `updated_at` within last 7 days
- Priority: `P0`, `P1` first, then `P2`, `P3`
- Assigned: has `owner` field

### Step 5: List Current Blockers
```bash
# From workflow status:
# - status: blocked
# - incidents: any story with incident records

# From Redis:
# - bmad:chiseai:iterlog:story:*:incidents (non-empty lists)
# - Any story with dependency issues

# From incidents directory:
# - docs/postmortems/*.md (recent incidents)
```

**Blocker Categories:**
1. **Technical Blockers**: CI failures, merge conflicts, test failures
2. **Dependency Blockers**: Waiting on other stories/tasks
3. **Resource Blockers**: Missing credentials, infrastructure issues
4. **Decision Blockers**: Awaiting human approval or design decisions

### Step 6: Identify Risks
```bash
# Scan for risk indicators:
# - Stories past due date (target_date < today)
# - Stories with no activity in 3+ days
# - Stories with multiple incidents
# - Epics with <50% completion near deadline
# - CI failure patterns (docs/tempmemories/ci-failures-*.json)
```

**Risk Signals:**
- `target_date` passed with `status != completed`
- No `updated_at` in 72+ hours for `in_progress` stories
- Incident count > 2 for single story
- Epic completion < 50% with deadline < 14 days away

### Step 7: Generate Report

Generate markdown report with the following structure:

```markdown
# Daily Standup - [YYYY-MM-DD]

**Generated**: [timestamp]
**Phase**: [current_phase]

---

## Yesterday

### Completed
- [Story ID] Title (owner)
  - Key deliverable
  - Merge commit/PR

### In Progress
- [Story ID] Title (owner) - [phase]
  - Current status
  - Next steps

---

## Today

### Planned Work

#### P0 - Critical
- [Story ID] Title (owner)
  - Scope: [brief description]
  - Target: [completion target]

#### P1 - High Priority
- [Story ID] Title (owner)
  - Scope: [brief description]
  - Target: [completion target]

#### P2 - Medium Priority
- [Story ID] Title (owner)
  - Scope: [brief description]

---

## Blockers

### Technical
- [Story ID] [blocker description]
  - Impact: [what's blocked]
  - Owner: [who can resolve]
  - ETA: [resolution estimate]

### Dependencies
- [Story ID] waiting on [dependency story ID]
  - Reason: [why blocked]
  - Escalation: [if needed]

### Resources
- [Story ID] [resource issue]
  - Missing: [what's needed]
  - Requested: [when requested]

---

## Risks

### Schedule Risks
- [Story ID] - [risk description]
  - Due: [original target]
  - Impact: [consequence]
  - Mitigation: [proposed action]

### Quality Risks
- [Epic ID] - [quality concern]
  - Signal: [what indicators]
  - Action: [recommended response]

---

## Metrics

- **Active Stories**: [count]
- **In Progress**: [count]
- **Blocked**: [count]
- **Completed This Week**: [count]
- **Incidents (24h)**: [count]

---

## Notes

- [Any additional context, announcements, or reminders]

---

*Generated by chise-standup-generate*
*Next standup: [tomorrow's date]*
```

### Step 8: Save Report

```bash
# Save to tempmemories with datestamp
REPORT_DATE=$(date +%Y-%m-%d)
REPORT_PATH="docs/tempmemories/standup-${REPORT_DATE}.md"

# Write report
cat > "$REPORT_PATH" << 'EOF'
[Generated report content]
EOF

# Log to Redis for tracking
redis-cli HSET "bmad:chiseai:standup:${REPORT_DATE}" \
    generated_at "$(date -Iseconds)" \
    report_path "$REPORT_PATH" \
    active_stories [count] \
    blockers [count]

redis-cli EXPIRE "bmad:chiseai:standup:${REPORT_DATE}" 604800  # 7 days
```

### Step 9: Discord Integration (Optional)

If Discord posting is enabled:

```bash
# Check Discord configuration
if [ -n "$DISCORD_STANDUP_CHANNEL" ]; then
    # Format for Discord (shorter version)
    DISCORD_MSG="**Daily Standup - ${REPORT_DATE}**\n\n"
    DISCORD_MSG+="**Completed Yesterday**: [count]\n"
    DISCORD_MSG+="**In Progress**: [count]\n"
    DISCORD_MSG+="**Blockers**: [count]\n\n"
    DISCORD_MSG+="Full report: ${REPORT_PATH}"
    
    # Post via webhook or bot
    python3 scripts/discord/post_message.py \
        --channel "$DISCORD_STANDUP_CHANNEL" \
        --message "$DISCORD_MSG"
fi
```

**Discord Format (Compact):**
```
📊 **Daily Standup - 2026-03-08**

✅ **Yesterday**: 3 completed
🔄 **Today**: 5 in progress
🚫 **Blockers**: 2 active
⚠️ **Risks**: 1 flagged

Full report: docs/tempmemories/standup-2026-03-08.md
```

## Configuration

### Environment Variables

```bash
# Discord integration (optional)
export DISCORD_STANDUP_CHANNEL="1234567890"  # Channel ID for standup posts
export DISCORD_STANDUP_WEBHOOK="https://discord.com/api/webhooks/..."  # Webhook URL

# Redis connection (uses defaults if not set)
export REDIS_HOST="localhost"
export REDIS_PORT="6380"
export REDIS_DB="0"

# Report retention
export STANDUP_REPORT_TTL="604800"  # 7 days in seconds
```

### Command Line Parameters

```bash
python3 scripts/standup/generate_standup.py \
    --date "2026-03-08" \              # Specific date (default: today)
    --post-discord \                    # Post to Discord
    --channel-id "1234567890" \        # Discord channel override
    --include-completed 7 \            # Days of completed work to include
    --format "markdown" \              # Output format (markdown/json/text)
    --output "/path/to/report.md" \    # Custom output path
    --verbose                           # Detailed logging
```

## Output Examples

### Markdown Report (Full)
See Step 7 for complete structure.

### JSON Format (for automation)
```json
{
  "date": "2026-03-08",
  "generated_at": "2026-03-08T09:00:00Z",
  "phase": "phase_2_plus",
  "summary": {
    "active_stories": 12,
    "in_progress": 5,
    "blocked": 2,
    "completed_24h": 3
  },
  "yesterday": {
    "completed": [
      {
        "id": "ST-EXAMPLE-001",
        "title": "Example Story",
        "owner": "jarvis",
        "merge_commit": "abc123"
      }
    ],
    "in_progress": [...]
  },
  "today": {
    "planned": [...]
  },
  "blockers": [...],
  "risks": [...]
}
```

## Redis Key Reference

| Key Pattern | Type | Purpose | TTL |
|------------|------|---------|-----|
| `bmad:chiseai:standup:<date>` | Hash | Standup metadata | 7 days |
| `bmad:chiseai:iterlog:story:<id>` | Hash | Story iteration log | 5 days |
| `bmad:chiseai:iterlog:story:<id>:incidents` | List | Story incidents | 5 days |
| `bmad:chiseai:ownership` | Hash | Scope ownership | 24 hours |

## Fallback Behavior

### Redis Unavailable
1. Read from `docs/bmm-workflow-status.yaml` only
2. Check `docs/tempmemories/iterlog-*.md` for story logs
3. Create report with reduced fidelity
4. Note in report: "Redis unavailable - limited data"

### Workflow Status Missing
1. Error with clear message
2. Do not generate incomplete report
3. Suggest running from repository root

### Discord Post Failure
1. Log error to `docs/tempmemories/standup-<date>-error.log`
2. Report still saved locally
3. Retry logic: 3 attempts with exponential backoff

## Scheduling

### Cron Job (Recommended)
```bash
# Run daily at 9 AM UTC
0 9 * * * cd /path/to/ChiseAI && python3 scripts/standup/generate_standup.py --post-discord
```

### Woodpecker CI Cron
```yaml
# .woodpecker/standup.yml
when:
  - event: cron
    cron: daily-standup

steps:
  generate:
    image: python:3.11
    commands:
      - pip install pyyaml redis
      - python3 scripts/standup/generate_standup.py --post-discord
    environment:
      DISCORD_STANDUP_CHANNEL:
        from_secret: discord_standup_channel
```

## Related Commands

- `chise-iterloop-start` - Start story iteration
- `chise-iterloop-close` - Close story iteration
- `chise-incident-log` - Log incident
- `chise-branch-hygiene-check` - Check branch hygiene

## Related Skills

- `chiseai-memory-ops` - Redis/Qdrant operations
- `chiseai-git-workflow` - Git workflow patterns
- `chiseai-incident-response` - Incident handling

## Troubleshooting

### No Stories Appear
- Check Redis connection: `redis-cli -p 6380 PING`
- Verify workflow status exists: `test -f docs/bmm-workflow-status.yaml`
- Check iterlog keys: `redis-cli KEYS "bmad:chiseai:iterlog:story:*"`

### Discord Post Fails
- Verify channel ID format (numeric string)
- Check webhook URL validity
- Test with: `python3 scripts/discord/test_webhook.py`

### Report Missing Data
- Run with `--verbose` flag for detailed logging
- Check Redis keys exist for active stories
- Verify YAML parsing: `python3 -c "import yaml; yaml.safe_load(open('docs/bmm-workflow-status.yaml'))"`

---

**Implementation Note**: This command can be implemented as a standalone Python script at `scripts/standup/generate_standup.py` that follows these specifications. The script should be idempotent and safe to run multiple times per day.
