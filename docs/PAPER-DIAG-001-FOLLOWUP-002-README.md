# Paper Trading Log Rotation and Webhook Validation

This document describes the log rotation and webhook validation implementation for PAPER-DIAG-001-FOLLOWUP-002.

## Overview

This implementation provides:

1. **Log Rotation for Paper Trading Logs**
   - Daily rotation at midnight
   - Size-based rotation (100MB limit)
   - Gzip compression of archived logs
   - 7-day retention policy

2. **Startup Discord Webhook Validation**
   - Deterministic validation of webhook configuration
   - URL format validation
   - HTTP connectivity checks
   - Rate limit awareness
   - Structured exit codes for automation

## Files Created

### Log Rotation

- `scripts/logging/paper_log_rotation.py` - Core log rotation implementation
- `scripts/logging/__init__.py` - Package initialization
- `scripts/logging/test_log_rotation.py` - Test suite
- `scripts/logging/integration.py` - Integration with paper checkpoint system

### Webhook Validation

- `scripts/discord/startup_webhook_check.py` - Startup validation script
- `scripts/discord/test_webhook_validation.py` - Test suite

## Log Rotation Configuration

### Features

- **Daily Rotation**: Logs rotate automatically at midnight
- **Size Limit**: 100MB maximum per log file
- **Compression**: Rotated files are compressed with gzip
- **Retention**: Files older than 7 days are automatically deleted
- **Location**: `logs/paper_trading/` (configurable)

### Usage

```python
from scripts.logging.paper_log_rotation import get_paper_trading_logger

# Get a configured logger
logger = get_paper_trading_logger("my_component")
logger.info("Paper trading log message")
```

### Manual Testing

Run the test suite:

```bash
python scripts/logging/test_log_rotation.py --verbose
```

Run the simulation:

```python
from scripts.logging.paper_log_rotation import simulate_log_rotation

results = simulate_log_rotation(num_files=5, file_size_mb=1)
print(f"Created {len(results['files_created'])} files")
```

## Webhook Validation

### Features

- **URL Validation**: Validates Discord webhook URL format
- **Connectivity Check**: Sends test HTTP POST to webhook
- **Timeout Support**: Configurable timeout (default 5 seconds)
- **Rate Limit Awareness**: Respects Discord rate limit headers
- **Multiple Webhooks**: Supports multiple webhook configurations
- **Exit Codes**: Clear exit codes for automation

### Usage

Check all configured webhooks:

```bash
python scripts/discord/startup_webhook_check.py
```

Check specific webhook:

```bash
python scripts/discord/startup_webhook_check.py --webhook-url URL
```

JSON output for automation:

```bash
python scripts/discord/startup_webhook_check.py --json
```

Quiet mode (exit code only):

```bash
python scripts/discord/startup_webhook_check.py --quiet
echo "Exit code: $?"
```

### Environment Variables

- `DISCORD_WEBHOOK_URL` - Primary webhook URL
- `DISCORD_STANDUP_WEBHOOK` - Standup webhook URL
- `DISCORD_ALERTS_WEBHOOK` - Alerts webhook URL
- `WEBHOOK_TIMEOUT_SECONDS` - Default timeout (default: 5)

### Exit Codes

- `0` - All validations passed
- `1` - Webhook validation failed
- `2` - Invalid arguments or usage error
- `3` - Rate limited
- `4` - Network timeout

## Integration with Paper Checkpoint

The `scripts/logging/integration.py` module provides integration with the paper trading checkpoint system:

```python
from scripts.logging.integration import validate_startup_requirements

result = validate_startup_requirements()
if not result.success:
    print("Startup validation failed:")
    for error in result.errors:
        print(f"  - {error}")
    sys.exit(1)
```

Run the integration check:

```bash
python scripts/logging/integration.py
```

## Testing

### Log Rotation Tests

```bash
# Run all tests
python scripts/logging/test_log_rotation.py

# Quick mode (smaller files)
python scripts/logging/test_log_rotation.py --quick

# Verbose output
python scripts/logging/test_log_rotation.py --verbose
```

### Webhook Validation Tests

```bash
# Run all tests
python scripts/discord/test_webhook_validation.py

# Verbose output
python scripts/discord/test_webhook_validation.py --verbose
```

## Acceptance Criteria Verification

- [x] Log rotation config/script created and tested
- [x] Rotation simulation passes (create test logs, verify rotation)
- [x] Startup webhook validation script created
- [x] Validation passes against test webhook (or mock)
- [x] Integration with paper_checkpoint.py provided

## Implementation Notes

### Log Rotation Strategy

The implementation uses a hybrid approach:
- `CompressedTimedRotatingFileHandler`: Handles daily rotation with compression
- `SizeAndTimeRotatingHandler`: Combines size and time checks

This ensures logs rotate both when they reach 100MB and at midnight daily.

### Webhook Validation Design

The validation is deterministic and idempotent:
1. URL format validation (regex pattern matching)
2. HTTP POST with timeout
3. Response status code check (200/204 = success)
4. Rate limit header inspection
5. Response time measurement

### Error Handling

Both systems include comprehensive error handling:
- Graceful degradation when services are unavailable
- Clear error messages for debugging
- Proper resource cleanup (file handles, connections)
- No unhandled exceptions

## Maintenance

### Monitoring

To monitor the health of these systems:

```bash
# Check log rotation
cd logs/paper_trading && ls -lah

# Check webhook connectivity
python scripts/discord/startup_webhook_check.py --json
```

### Troubleshooting

**Log rotation not working:**
- Check directory permissions: `ls -ld logs/paper_trading`
- Verify disk space: `df -h`
- Run test suite: `python scripts/logging/test_log_rotation.py --verbose`

**Webhook validation failing:**
- Check environment variables: `env | grep DISCORD`
- Test connectivity: `python scripts/discord/startup_webhook_check.py`
- Verify URL format: Must match `https://discord.com/api/webhooks/{id}/{token}`

## Future Enhancements

Potential improvements:
- Alert when disk space is low for logs
- Integration with metrics system for webhook latency tracking
- Support for additional log backends (e.g., centralized logging)
- Webhook health monitoring dashboard
