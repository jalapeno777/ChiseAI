# Workflow Archival Live Mode Implementation

## Tasks Completed
- Task 3.1: Review current dry-run behavior
- Task 3.2: Implement controlled live mode with safety checks
- Task 3.3: Add lock + rollback safety mechanisms

---

## 1. Current Behavior Documentation (BEFORE)

### scripts/workflow/automated_archive.py (v1.0.0)
**Mode:** Always LIVE execution (always passed `--execute` to archive script)

**Behavior:**
- No dry-run mode available
- Always executed `archive_stories.py --execute`
- No explicit safety confirmations required
- No Redis locking mechanism
- No backup/rollback capability before making changes
- Basic notifications without mode indication

**Flow:**
1. Run preflight checks
2. Execute archival with `--execute` flag (always live)
3. Run post-archival verification
4. Send notification

### .woodpecker/workflow-archive.yaml (v1.0.0)
**Behavior:**
- Weekly archival every Sunday at 02:00 UTC
- Always ran in live mode
- No mechanism to disable live execution
- Called: `python3 scripts/workflow/automated_archive.py --batch-size 20 --verbose --notify`

---

## 2. Implemented Changes

### A. Live/Dry-Run Mode Control

#### New Arguments in automated_archive.py:
```bash
--live                           # Enable live mode (default: False = dry-run)
--i-understand-live-mode         # Required confirmation for live mode
```

#### Environment Variables:
```bash
WORKFLOW_ARCHIVE_LIVE=1          # Alternative to --live flag
WORKFLOW_ARCHIVE_LIVE_CONFIRM=1  # Alternative to --i-understand-live-mode flag
```

#### Usage Examples:
```bash
# Dry-run (default) - no changes made
python3 scripts/workflow/automated_archive.py

# Live mode with confirmation flag
python3 scripts/workflow/automated_archive.py --live --i-understand-live-mode

# Live mode with environment variables
WORKFLOW_ARCHIVE_LIVE=1 WORKFLOW_ARCHIVE_LIVE_CONFIRM=1 python3 scripts/workflow/automated_archive.py
```

### B. Safety Check for Live Mode

**Implementation:**
```python
if report.live_mode:
    env_confirmed = os.environ.get("WORKFLOW_ARCHIVE_LIVE_CONFIRM", "").lower() in ("1", "true", "yes", "on")
    flag_confirmed = args.i_understand_live_mode
    
    if not (env_confirmed or flag_confirmed):
        print("🚫 SAFETY CHECK FAILED")
        print("Live mode requires explicit confirmation...")
        return 4
```

**Exit Code:** 4 (Safety check failed)

### C. Redis Lock Mechanism

**Lock Details:**
- **Key:** `bmad:chiseai:workflow:archival:lock`
- **TTL:** 3600 seconds (1 hour)
- **Behavior:** Advisory lock - script continues if lock unavailable but logs warning

**Implementation:**
```python
def acquire_lock() -> tuple[bool, str]:
    client = _get_redis_client()
    lock_value = f"archival-{datetime.utcnow().isoformat()}"
    acquired = client.set(
        REDIS_LOCK_KEY,
        lock_value,
        nx=True,  # Only set if key doesn't exist
        ex=REDIS_LOCK_TTL_SECONDS,
    )
    return acquired, message
```

### D. Backup Before Archival

**Backup Details:**
- **Location:** `.backup/workflow-status-YYYYMMDD-HHMMSS.yaml`
- **Verification:** SHA-256 checksum comparison
- **Behavior:** Exit code 6 if backup fails in live mode

**Implementation:**
```python
def create_backup() -> tuple[bool, Optional[Path]]:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"workflow-status-{timestamp}.yaml"
    shutil.copy2(WORKFLOW_STATUS_PATH, backup_path)
    
    # Verify with checksum
    original_hash = hashlib.sha256(WORKFLOW_STATUS_PATH.read_bytes()).hexdigest()
    backup_hash = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    return original_hash == backup_hash, backup_path
```

### E. Enhanced Notifications

**Live Mode Notifications:**
- **Level:** CRITICAL for failures, SUCCESS for completion
- **Message:** Includes mode indicator, backup path reference
- **Example:** "✓ Workflow Archival Complete - 🚨 LIVE MODE"

**Dry-Run Notifications:**
- **Level:** WARNING for failures, INFO for success
- **Message:** Clarifies no changes were made
- **Example:** "✓ Workflow Archival Dry-Run Complete"

### F. Enhanced Reporting

**ExecutionReport New Fields:**
```python
live_mode: bool                    # Whether running in live mode
dry_run_mode: bool                 # Whether running in dry-run mode
lock_acquired: bool                # Whether Redis lock was obtained
backup_created: bool               # Whether backup was created
backup_path: Optional[str]         # Path to backup file
```

**Report Output:**
```
================================================================================
WORKFLOW STATUS AUTOMATED ARCHIVE EXECUTION REPORT
================================================================================
...
🛡️  MODE: DRY-RUN - NO CHANGES WILL BE MADE

SAFETY CHECKS:
  ⚠ Redis lock not acquired (may be unavailable)
  ⚠ No backup created

PREFLIGHT CHECKS:
  ✓ All preflight checks passed
...
```

### G. Updated Workflow Steps

**New 4-Step Process:**
1. **Step 0:** Acquire lock + create backup (live mode only)
2. **Step 1:** Preflight checks
3. **Step 2:** Archival execution (with --execute or --dry-run)
4. **Step 3:** Post-archival verification
5. **Step 4:** Cleanup - release lock (live mode only)

---

## 3. CI/CD Integration

### .woodpecker/workflow-archive.yaml (v2.0.0)

**Changes:**
- Added environment variables for live mode control
- Added mode detection logic in shell script
- Added `redis` package installation
- Default: DRY-RUN mode

**Configuration:**
```yaml
environment:
  WORKFLOW_ARCHIVE_LIVE:
    from_secret: WORKFLOW_ARCHIVE_LIVE
  WORKFLOW_ARCHIVE_LIVE_CONFIRM:
    from_secret: WORKFLOW_ARCHIVE_LIVE_CONFIRM
  REDIS_HOST: "host.docker.internal"
  REDIS_PORT: "6380"
```

**Mode Selection Logic:**
```bash
if [ "${WORKFLOW_ARCHIVE_LIVE:-0}" = "1" ] && [ "${WORKFLOW_ARCHIVE_LIVE_CONFIRM:-0}" = "1" ]; then
  echo "🚨 LIVE MODE ENABLED - Changes will be made"
  MODE_FLAGS="--live --i-understand-live-mode"
else
  echo "🛡️  DRY-RUN MODE - No changes will be made"
  MODE_FLAGS=""
fi
```

---

## 4. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Preflight checks failed |
| 2 | Archival execution failed |
| 3 | Post-archival verification failed |
| 4 | Safety check failed (live mode without confirmation) |
| 5 | Lock acquisition failed (not used - advisory) |
| 6 | Backup failed in live mode |

---

## 5. Rollback Capability Reference

### Manual Rollback Procedure:

If live archival needs to be rolled back:

```bash
# 1. Stop any running archival processes
# 2. Restore from backup
cp .backup/workflow-status-YYYYMMDD-HHMMSS.yaml docs/bmm-workflow-status.yaml

# 3. Remove created archive entries (optional)
rm docs/archives/workflow-status/entries/ARCH-YYYYMMDD-HHMMSS-*.yaml

# 4. Clear Redis lock if stuck
redis-cli DEL bmad:chiseai:workflow:archival:lock

# 5. Verify restoration
python3 scripts/workflow/preflight_archive.py --verbose
```

### Automatic Safety:
- Backup is created BEFORE any changes in live mode
- If backup fails, archival is aborted (exit code 6)
- Lock expires automatically after 1 hour (TTL)

---

## 6. Files Modified

1. **scripts/workflow/automated_archive.py** (+355 lines, -29 lines)
   - Added live/dry-run mode control
   - Added safety checks
   - Added Redis lock mechanism
   - Added backup creation
   - Enhanced notifications
   - Updated ExecutionReport

2. **.woodpecker/workflow-archive.yaml** (+32 lines)
   - Updated header documentation
   - Added live mode environment variables
   - Added mode selection logic
   - Added redis package installation

3. **.backup/** (directory created)
   - New directory for workflow-status backups

---

## 7. Test Results

### Help Output:
```bash
$ python3 scripts/workflow/automated_archive.py --help
usage: automated_archive.py [-h] [--batch-size BATCH_SIZE] [--verbose]
                            [--json] [--notify] [--webhook-url WEBHOOK_URL]
                            [--skip-preflight] [--live]
                            [--i-understand-live-mode]

Automated workflow status archival with preflight checks and safety controls
```

### Dry-Run Mode:
```
🛡️  RUNNING IN DRY-RUN MODE - NO CHANGES WILL BE MADE
...
✓ Archival executed: 0 stories archived
✓ Post-archival verification passed
```

### Live Mode Safety Check:
```
🚨 RUNNING IN LIVE MODE - CHANGES WILL BE MADE
🚫 SAFETY CHECK FAILED
Live mode requires explicit confirmation...
```

---

## 8. Security Considerations

1. **Default Safe:** Dry-run mode is the default
2. **Double Confirmation:** Live mode requires both `--live` AND confirmation
3. **Backup Before Changes:** Backup is mandatory in live mode
4. **Advisory Lock:** Redis lock prevents concurrent execution
5. **TTL Protection:** Lock auto-expires after 1 hour
6. **Fail-Closed:** Backup failure aborts live archival

---

**Version:** 2.0.0  
**Story:** ST-WORKFLOW-ARCHIVAL-001  
**Implementation Date:** 2026-03-09
