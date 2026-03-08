# Standup Report Generator

Daily standup automation for ChiseAI agent swarm operations.

## Overview

Generates comprehensive daily standup reports by aggregating:
- Workflow status from `docs/bmm-workflow-status.yaml`
- Active story iteration logs from Redis
- Recent git merges
- Incident records and blockers

## Quick Start

```bash
# Generate today's standup report
python3 scripts/standup/generate_standup.py

# Generate with verbose output
python3 scripts/standup/generate_standup.py --verbose

# Generate and post to Discord
python3 scripts/standup/generate_standup.py --post-discord --channel-id "1234567890"
```

## Output

Reports are saved to: `docs/tempmemories/standup-YYYY-MM-DD.md`

### Report Sections

1. **Yesterday** - Completed work from last 24-48 hours
2. **Today** - Planned work by priority (P0-P3)
3. **Blockers** - Technical, dependency, and resource blockers
4. **Risks** - Schedule and quality risks
5. **Metrics** - Summary statistics

## Command Line Options

```bash
python3 scripts/standup/generate_standup.py [OPTIONS]

Options:
  --date DATE                   Report date (YYYY-MM-DD)
  --post-discord                Post summary to Discord
  --channel-id CHANNEL_ID       Discord channel ID
  --include-completed N         Days of completed work (default: 7)
  --format {markdown,json}      Output format (default: markdown)
  --output PATH                 Custom output path
  --verbose                     Enable verbose logging
  --redis-host HOST             Redis host (default: localhost)
  --redis-port PORT             Redis port (default: 6380)
```

## Configuration

### Environment Variables

```bash
# Discord integration
export DISCORD_STANDUP_CHANNEL="1234567890"
export DISCORD_STANDUP_WEBHOOK="https://discord.com/api/webhooks/..."

# Redis connection
export REDIS_HOST="localhost"
export REDIS_PORT="6380"
export REDIS_DB="0"
```

## Automation

### Cron Job

```bash
# Run daily at 9 AM UTC
0 9 * * * cd /path/to/ChiseAI && python3 scripts/standup/generate_standup.py --post-discord
```

### Woodpecker CI

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

## Data Sources

### Primary Sources

1. **Workflow Status** (`docs/bmm-workflow-status.yaml`)
   - Epic progress and completion
   - Story backlog with priorities
   - Recently completed stories

2. **Redis Iterlogs** (`bmad:chiseai:iterlog:story:*`)
   - Active story status
   - Phase and progress tracking
   - Owner assignment

3. **Incident Records** (`bmad:chiseai:iterlog:story:*:incidents`)
   - Active incidents
   - Blocker identification
   - Impact assessment

### Fallback Behavior

If Redis is unavailable:
- Reads from workflow status YAML only
- Checks `docs/tempmemories/iterlog-*.md` for story logs
- Generates report with reduced fidelity
- Notes limitation in report

## Redis Key Reference

| Key Pattern | Type | Purpose | TTL |
|------------|------|---------|-----|
| `bmad:chiseai:standup:<date>` | Hash | Standup metadata | 7 days |
| `bmad:chiseai:iterlog:story:<id>` | Hash | Story iteration log | 5 days |
| `bmad:chiseai:iterlog:story:<id>:incidents` | List | Story incidents | 5 days |

## Examples

### Generate JSON Report

```bash
python3 scripts/standup/generate_standup.py --format json --output standup.json
```

### Generate for Specific Date

```bash
python3 scripts/standup/generate_standup.py --date 2026-03-01
```

### Custom Output Path

```bash
python3 scripts/standup/generate_standup.py --output /tmp/standup.md
```

## Troubleshooting

### No Stories Appear

1. Check Redis connection:
   ```bash
   redis-cli -p 6380 PING
   ```

2. Verify workflow status exists:
   ```bash
   test -f docs/bmm-workflow-status.yaml && echo "OK"
   ```

3. Check iterlog keys:
   ```bash
   redis-cli KEYS "bmad:chiseai:iterlog:story:*"
   ```

### Discord Post Fails

1. Verify channel ID format (numeric string)
2. Check webhook URL validity
3. Test with verbose flag: `--verbose`

### Report Missing Data

Run with `--verbose` for detailed logging:
```bash
python3 scripts/standup/generate_standup.py --verbose
```

## Related Documentation

- Command: `.opencode/command/chise-standup-generate.md`
- Skill: `.opencode/skills/chiseai-memory-ops/SKILL.md`
- Workflow: `.opencode/skills/chiseai-git-workflow/SKILL.md`

## Support

For issues or questions:
1. Check the command documentation: `.opencode/command/chise-standup-generate.md`
2. Review verbose output with `--verbose` flag
3. Consult Redis keys and workflow status directly
