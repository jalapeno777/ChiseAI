# Merlin Authority Enforcement Module

ST-AUTO-CONTROL-001: Merlin-only authority enforcement for EP-AUTO-GIT mutations.

## Files Created

1. **scripts/governance/merlin_authority.py** (666 lines)
   - Core authority enforcement module
   - CLI interface for checking authority
   - Redis integration for authority settings

2. **tests/test_governance/test_merlin_authority.py** (527 lines)
   - 37 comprehensive tests
   - Tests for all major functionality
   - Mock-based testing for Redis interactions

## Features

### Authority Verification Functions

- `is_merlin()` - Check if current process is running as Merlin agent
- `check_ep_auto_git_authority(action)` - Check if action is authorized
- `check_epic_authority(epic_id, action)` - Check authority for specific epic
- `enforce_merlin_only(epic_id, action)` - Enforce Merlin-only authority (raises on violation)

### Exception Classes

- `AuthorityViolation` - Raised when non-Merlin attempts Merlin-only action
- `EpicNotProtected` - Raised when checking authority for unprotected epic
- `AuthorityCheckError` - Raised when authority check fails technically

### Decorator

- `@require_merlin` - Decorator to require Merlin authority for a function

### CLI Interface

```bash
# Check if current process is Merlin
python3 scripts/governance/merlin_authority.py check

# Verify authority for an action
python3 scripts/governance/merlin_authority.py verify --action status_write --epic EP-AUTO-GIT-001

# Enforce authority (fails if not Merlin)
python3 scripts/governance/merlin_authority.py enforce --action merge --epic EP-AUTO-GIT-001

# Exit codes: 0=authorized, 1=not authorized, 2=error
```

## Integration with status_write_gate.py

```python
from scripts.governance.merlin_authority import enforce_merlin_only, AuthorityViolation

def write_status_update():
    try:
        # Enforce Merlin-only authority before writing
        enforce_merlin_only(epic_id="EP-AUTO-GIT-001", action="status_write")
        
        # Proceed with status write
        ...
        
    except AuthorityViolation as e:
        logger.error(f"Status write blocked: {e.message}")
        raise
```

## Redis Schema

Authority settings are stored in Redis hash at key: `bmad:chiseai:ep:auto-git`

Fields:
- `merge_authority`: Authority required for merge (e.g., "merlin-only")
- `pr_authority`: Authority required for PR operations (e.g., "merlin-only")
- `status_authority`: Authority required for status writes (e.g., "merlin-only")
- `lock_timestamp`: ISO timestamp when settings were locked

## Testing

All tests pass:
```bash
python3 -m pytest tests/test_governance/test_merlin_authority.py -v
```

Test coverage:
- Agent detection (environment variable, process detection)
- Authority settings parsing from Redis
- Authority checks for different actions
- Exception handling
- Redis failure handling (fail-secure)
- Cache functionality
- Decorator functionality
- Integration scenarios

## Quality Checks

- ✅ Python syntax validation passed
- ✅ Black formatting check passed
- ✅ Ruff linting passed (all issues auto-fixed)
- ✅ All 37 tests passed

## Memory Applied

From MEMORY_CONTEXT:
1. **Redis authority locks exist**: The module reads from `bmad:chiseai:ep:auto-git` hash which already has `merge_authority`, `pr_authority`, and `status_authority` all set to "merlin-only".

2. **Fail-secure design**: When Redis is unavailable, the module denies access by default (returns False from check functions, raises exceptions from enforce functions).

3. **Caching for performance**: Authority settings are cached for 60 seconds to avoid repeated Redis queries.

## Example Usage

See `/tmp/example_usage.py` for complete examples of:
- Status write gate integration
- Decorator usage
- Authority checking without raising exceptions

## Notes

- The module detects agent identity via `CHISE_AGENT` environment variable
- Redis integration uses graceful fallback when tools are unavailable
- The module is designed to work both as a library and CLI tool
- All functions include comprehensive docstrings and type hints
