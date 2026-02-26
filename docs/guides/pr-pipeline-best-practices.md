# PR Pipeline Best Practices

Guidelines for effective and safe collaboration in the autonomous PR pipeline.

## Scope Ownership

### Principles

1. **Always claim before editing**
2. **Release when done**
3. **Check before starting**
4. **Respect existing claims**

### Claiming Scope

```bash
# Claim via CLI (preferred)
python3 scripts/pr_lifecycle/agent_cli.py reserve-scope \
    --story-id=ST-XXX \
    --scope="src/module/"

# Or manually via Redis
redis-cli -h host.docker.internal -p 6380 \
    HSET bmad:chiseai:ownership src:module "ST-XXX/agent/2026-02-25T10:00:00Z"
```

### Checking Ownership

```bash
# Check specific scope
redis-cli -h host.docker.internal -p 6380 \
    HGET bmad:chiseai:ownership src:module

# Check all ownerships
redis-cli -h host.docker.internal -p 6380 \
    HGETALL bmad:chiseai:ownership
```

### Releasing Scope

```bash
# Release when done
redis-cli -h host.docker.internal -p 6380 \
    HDEL bmad:chiseai:ownership src:module
```

### Scope Granularity

**Good scope examples:**
- `src/strategy/dsl/` - DSL module
- `docs/guides/` - Documentation
- `tests/unit/strategy/` - Unit tests
- `scripts/pr_lifecycle/` - PR lifecycle scripts

**Bad scope examples:**
- `src/` - Too broad
- `src/strategy/dsl/grammar.py` - Too specific (file-level)
- `.` - Entire repo

### Conflict Resolution

If you encounter an ownership conflict:

1. **STOP** - Do not proceed
2. **Check details** - Who owns it? For what story?
3. **Evaluate options:**
   - Wait for completion
   - Request re-scope
   - Escalate to Jarvis
4. **Document** - Log the conflict

## Parallel Work Patterns

### When Parallel is Safe

✓ **Safe for parallel:**
- Disjoint scopes (no shared files)
- Different modules
- Tests for different features
- Documentation in different areas

✗ **Not safe for parallel:**
- Shared files
- Global-lock areas (CI config, pyproject.toml)
- Database migrations
- API contract changes

### Parallel Workflow

```
Jarvis Plans Batch
       │
       ▼
┌─────────────┐
│ Pre-Flight  │
│   Check     │
└─────────────┘
       │
       ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Worker    │    │   Worker    │    │   Worker    │
│      A      │    │      B      │    │      C      │
│  (Scope 1)  │    │  (Scope 2)  │    │  (Scope 3)  │
└─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ▼
                   ┌─────────────┐
                   │ Integration │
                   │    Test     │
                   └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │    Merge    │
                   └─────────────┘
```

### Coordination via Redis

```bash
# Worker A claims scope
redis-cli HSET bmad:chiseai:ownership src:module:a "ST-A001/agent/2026-02-25T10:00:00Z"

# Worker B checks before starting
redis-cli HGET bmad:chiseai:ownership src:module:b
# (nil) - Available, safe to proceed

# Worker C tries to claim A's scope
redis-cli HSET bmad:chiseai:ownership src:module:a "ST-C001/agent/2026-02-25T11:00:00Z"
# Conflict detected - STOP
```

## Testing Requirements

### Test Coverage

| Change Type | Minimum Coverage | Required Tests |
|-------------|------------------|----------------|
| Bug fix | 80% | Regression test |
| New feature | 90% | Unit + integration |
| Refactoring | Maintain | All existing |
| Documentation | N/A | N/A |

### Test Organization

```
tests/
├── unit/              # Unit tests (fast, isolated)
│   ├── strategy/
│   ├── execution/
│   └── governance/
├── integration/       # Integration tests
│   ├── api/
│   └── database/
└── e2e/              # End-to-end tests
    └── workflows/
```

### Running Tests

```bash
# All tests
pytest tests/

# Unit tests only
pytest tests/unit/ -v

# Specific module
pytest tests/unit/strategy/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing

# Fail fast
pytest tests/ -x

# Parallel execution
pytest tests/ -n auto
```

### Test Quality

**Good test characteristics:**
- Fast (<100ms per test)
- Isolated (no dependencies)
- Deterministic (same result every time)
- Readable (clear intent)
- Maintainable (easy to update)

## Documentation Standards

### Code Documentation

```python
def function_name(param: str) -> bool:
    """Short description of what function does.

    Longer description if needed. Explain the purpose,
    any important details, and edge cases.

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Raises:
        ValueError: When invalid input provided

    Example:
        >>> function_name("test")
        True
    """
    pass
```

### Module Documentation

```python
"""Module purpose and overview.

This module provides functionality for X. It is used by
Y to accomplish Z.

Key classes:
    - ClassA: Does something
    - ClassB: Does something else

Usage:
    from module import ClassA
    instance = ClassA()
    result = instance.method()
"""
```

### README Updates

Update README.md when:
- Adding new commands
- Changing existing behavior
- Adding dependencies
- Updating installation steps

### Changelog

Follow [Keep a Changelog](https://keepachangelog.com/):

```markdown
## [Unreleased]

### Added
- New feature X

### Changed
- Behavior of Y

### Fixed
- Bug in Z

### Deprecated
- Old API method

### Removed
- Unused feature

### Security
- Fixed vulnerability
```

## Code Quality

### Linting

```bash
# Check all files
ruff check src/ scripts/

# Fix auto-fixable issues
ruff check --fix src/ scripts/

# Check specific file
ruff check src/module.py
```

### Formatting

```bash
# Check formatting
black --check src/ scripts/

# Apply formatting
black src/ scripts/
```

### Type Checking

```bash
# Run mypy
mypy src/ --ignore-missing-imports
```

### Pre-Commit Checklist

Before submitting:

- [ ] Code formatted with black
- [ ] Linting passes with ruff
- [ ] Tests pass with pytest
- [ ] Type checking passes (if applicable)
- [ ] Documentation updated
- [ ] No debug code left in
- [ ] No secrets committed
- [ ] Commit messages follow format

## Git Best Practices

### Commit Messages

```
type(scope): description (ST-XXX)

Body explaining what and why, not how.

Refs: ST-XXX
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Tests
- `chore`: Maintenance

**Scopes:**
- Module or component name
- Use lowercase
- Be consistent

### Branch Management

```bash
# Create feature branch
git checkout -b feature/ST-XXX-description

# Keep up to date
git fetch origin
git rebase origin/main

# Clean history
git rebase -i main

# Push
git push -u origin feature/ST-XXX-description
```

### Rebasing

```bash
# Interactive rebase
git rebase -i main

# Rebase onto latest main
git fetch origin
git rebase origin/main

# Abort if issues
git rebase --abort

# Continue after fixing
git add .
git rebase --continue
```

## PR Best Practices

### PR Size

**Optimal PR size:**
- <200 lines changed
- Single logical change
- Reviewable in 30 minutes
- Passes CI quickly

**Split large changes:**
```
Large Feature
├── PR 1: Foundation/interfaces
├── PR 2: Core implementation
├── PR 3: Additional features
└── PR 4: Tests and docs
```

### PR Description Template

```markdown
## Summary
Brief description of changes

## Changes
- Change 1
- Change 2

## Testing
- [ ] Unit tests added
- [ ] Integration tests pass
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guide
- [ ] Documentation updated
- [ ] Tests pass
- [ ] No breaking changes (or documented)

## Related
- Closes ST-XXX
- Depends on ST-YYY
```

### Review Response

When receiving feedback:

1. **Acknowledge** - Respond to each comment
2. **Clarify** - Ask if unclear
3. **Fix** - Make requested changes
4. **Test** - Verify fixes work
5. **Update** - Push changes
6. **Notify** - Let reviewers know

## Security Practices

### Sensitive Data

**Never commit:**
- Passwords
- API keys
- Private keys
- Tokens
- Personal data

**Use environment variables:**
```python
import os

api_key = os.getenv("API_KEY")
if not api_key:
    raise ValueError("API_KEY not set")
```

### Dependencies

```bash
# Check for vulnerabilities
pip-audit

# Update dependencies
pip-compile --upgrade

# Review changes
pip-review --local --interactive
```

## Performance Considerations

### Code Performance

- Profile before optimizing
- Optimize for readability first
- Use appropriate data structures
- Avoid premature optimization
- Measure impact

### Database Performance

- Use indexes appropriately
- Limit query results
- Avoid N+1 queries
- Use transactions for batches

### Test Performance

- Keep unit tests fast
- Mock external dependencies
- Use fixtures for setup
- Parallelize when possible

## Monitoring and Observability

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Good logging
logger.info("Processing order %s", order_id)
logger.warning("Rate limit approaching: %d%%", usage_percent)
logger.error("Failed to process order %s: %s", order_id, error)

# Bad logging
logger.info(f"Processing order {order_id}")  # f-string in logging
logger.info("Processing")  # Not enough context
```

### Metrics

```python
# Track important metrics
from prometheus_client import Counter, Histogram

requests_total = Counter('requests_total', 'Total requests')
request_duration = Histogram('request_duration_seconds', 'Request duration')

@request_duration.time()
def handle_request():
    requests_total.inc()
    # ... handle request
```

## Incident Prevention

### Common Issues and Prevention

| Issue | Prevention |
|-------|------------|
| Merge conflicts | Rebase frequently |
| CI failures | Run pre-commit gates |
| Scope conflicts | Always check ownership |
| Breaking changes | Comprehensive tests |
| Security issues | Regular audits |
| Performance regressions | Benchmark tests |

### Early Warning Signs

Watch for:
- Increasing CI failure rate
- Growing PR backlog
- Longer review times
- More merge conflicts
- Decreasing test coverage

### Proactive Measures

- Regular dependency updates
- Periodic refactoring
- Documentation reviews
- Test maintenance
- Performance monitoring

## Continuous Improvement

### Learning from Mistakes

When issues occur:
1. Document what happened
2. Analyze root cause
3. Identify prevention measures
4. Update processes
5. Share learnings

### Knowledge Sharing

- Document lessons learned
- Update guides and playbooks
- Mentor new agents
- Share useful patterns
- Contribute to skills

---

**Related Documents:**
- [Agent Onboarding Guide](agent-onboarding-guide.md)
- [PR Pipeline Quick Start](pr-pipeline-quickstart.md)
- [PR Pipeline Troubleshooting](pr-pipeline-troubleshooting.md)
- [PR Pipeline FAQ](pr-pipeline-faq.md)
