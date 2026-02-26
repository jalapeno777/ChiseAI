# Workflow Paths Documentation

## Overview

The ChiseAI Agent Swarm uses a **tiered automation pipeline** with three distinct workflow paths. Each path is designed to balance development velocity with safety, ensuring that low-risk changes move quickly while high-risk changes receive appropriate scrutiny.

## The Three Workflow Paths

### 1. SAFE Path: Auto-Approve

**Purpose**: Enable rapid iteration on low-risk changes

**Criteria for SAFE Path**:
- Changes to documentation, comments, or docstrings
- Test-only changes (adding tests, not modifying test infrastructure)
- Configuration changes with no security impact
- ≤5 files changed
- ≤200 lines of code changed
- No changes to CI/CD configuration
- No changes to infrastructure code
- No changes to security-critical code

**Process Flow**:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Commit    │────▶│  CI Pipeline │────▶│  All Green? │────▶│ Auto-Merge   │
│   Pushed    │     │    Runs      │     │             │     │ <5 minutes  │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
                                                │
                                                ▼
                                         ┌─────────────┐
                                         │  Any Red?   │────▶│ STANDARD Path │
                                         └─────────────┘     │   Escalation  │
                                                              └───────────────┘
```

**Auto-Approve Requirements**:
1. All CI checks pass (Black, Ruff, Bandit, Pytest, Coverage)
2. No merge conflicts
3. Branch is up-to-date with main
4. PR title contains valid story ID token (ST-*, CH-*, FT-*, etc.)
5. Changes are within SAFE path criteria (verified by path classifier)

**Examples of SAFE Path Changes**:

```markdown
✅ SAFE Path Examples:
- Adding docstrings to existing functions
- Fixing typos in documentation
- Adding unit tests for existing code
- Updating README files
- Adding inline comments explaining complex logic

❌ NOT SAFE Path:
- Modifying .woodpecker.yml (CI config)
- Changing pyproject.toml (dependencies)
- Modifying infrastructure/terraform/
- Changes to src/execution/ (trading code)
- Changes to secrets or credentials
```

### 2. STANDARD Path: GitReviewBot Review

**Purpose**: Automated review for medium-risk changes

**Criteria for STANDARD Path**:
- Feature additions and modifications
- Bug fixes with limited scope
- Refactoring within a single module
- 6-15 files changed
- 200-500 lines of code changed
- Changes to non-critical configuration
- Test infrastructure modifications

**Process Flow**:

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Commit    │────▶│  CI Pipeline │────▶│ GitReviewBot │────▶│  Bot Review  │
│   Pushed    │     │    Runs      │     │  Triggered   │     │  <12 min    │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                       │
                    ┌──────────────────────────────────────────────────┘
                    ▼
         ┌─────────────────────┐
         │   Review Results    │
         └─────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐
   │ APPROVE │ │ COMMENT │ │ REQUEST  │
   │  ─────▶ │ │  ─────▶ │ │ CHANGES  │
   │  Merge  │ │  Human  │ │  ─────▶  │
   │         │ │ Review  │ │  Revise  │
   └─────────┘ └─────────┘ └──────────┘
```

**GitReviewBot Review Criteria**:

1. **Code Quality Checks**:
   - Complexity analysis (cyclomatic complexity <10)
   - Function length (<50 lines)
   - Test coverage for new code (>80%)
   - Documentation coverage for public APIs

2. **Security Checks**:
   - No hardcoded secrets
   - No SQL injection vulnerabilities
   - No unsafe deserialization
   - Input validation present

3. **Style Consistency**:
   - Follows project conventions
   - Consistent naming patterns
   - Proper error handling

4. **Test Validation**:
   - New tests pass
   - No flaky tests introduced
   - Edge cases covered

**Review Outcomes**:

| Outcome | Action | Timeline |
|---------|--------|----------|
| **APPROVE** | Auto-merge proceeds | <12 minutes total |
| **COMMENT** | Human review required | Escalated to human |
| **REQUEST_CHANGES** | Author must revise | Back to author |

**Examples of STANDARD Path Changes**:

```markdown
✅ STANDARD Path Examples:
- Implementing a new feature in src/strategy/
- Adding a new API endpoint
- Refactoring a module for better organization
- Adding integration tests
- Performance optimizations

❌ NOT STANDARD Path:
- Changes to execution engine
- Infrastructure modifications
- Security policy changes
- Database schema migrations
```

### 3. COMPLEX Path: Human Escalation

**Purpose**: Ensure human oversight for high-risk changes

**Criteria for COMPLEX Path** (any of the following):
- >15 files changed or >500 lines of code
- Changes to CI/CD configuration (.woodpecker.yml)
- Changes to infrastructure (terraform/, docker-compose.yml)
- Changes to security policies or secrets management
- Changes to execution/trading logic
- Database schema migrations
- Changes to core architecture
- Breaking API changes
- Changes with cross-cutting concerns

**Process Flow**:

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Commit    │────▶│  CI Pipeline │────▶│ GitReviewBot │────▶│  Pre-Review  │
│   Pushed    │     │    Runs      │     │  Pre-Review  │     │   <12 min   │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                       │
                    ┌──────────────────────────────────────────────────┘
                    ▼
         ┌─────────────────────┐
         │   Human Review      │
         │   Required          │
         └─────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐
   │ APPROVE │ │ COMMENT │ │ REQUEST  │
   │  ─────▶ │ │  ─────▶ │ │ CHANGES  │
   │  Merge  │ │ Discuss │ │  ─────▶  │
   │         │ │         │ │  Revise  │
   └─────────┘ └─────────┘ └──────────┘
```

**Human Review Requirements**:

1. **Required Reviewers**:
   - At least one senior engineer
   - Domain expert for affected area
   - Security review for security-related changes

2. **Review Checklist**:
   - Architecture alignment
   - Security implications
   - Performance impact
   - Testing adequacy
   - Documentation completeness
   - Rollback feasibility

3. **Promotion Packet** (for critical changes):
   - Evidence summary
   - Risk assessment
   - Rollback plan
   - Testing evidence
   - Performance benchmarks

**Examples of COMPLEX Path Changes**:

```markdown
✅ COMPLEX Path Examples:
- Modifying .woodpecker.yml CI configuration
- Terraform infrastructure changes
- Database schema migrations
- Changes to src/execution/ (live trading code)
- Security policy modifications
- Major refactoring across multiple modules
- Breaking API changes

❌ NOT COMPLEX Path (would be overkill):
- Simple bug fixes
- Adding a new utility function
- Documentation updates
- Test additions
```

## Decision Tree for Path Selection

Use this decision tree to determine the correct workflow path:

```
                    ┌─────────────────┐
                    │  Change Ready   │
                    │   for Review    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Touch CI/Infra │────YES────▶ COMPLEX Path
                    │   or Secrets?   │           (Human Required)
                    └────────┬────────┘
                             │ NO
                             ▼
                    ┌─────────────────┐
                    │  Touch Execution │───YES────▶ COMPLEX Path
                    │   or Trading?    │           (Human Required)
                    └────────┬─────────┘
                             │ NO
                             ▼
                    ┌─────────────────┐
                    │   >15 files or  │───YES────▶ COMPLEX Path
                    │   >500 lines?   │           (Human Required)
                    └────────┬────────┘
                             │ NO
                             ▼
                    ┌─────────────────┐
                    │    >5 files    │───YES────▶ STANDARD Path
                    │    or >200      │           (GitReviewBot)
                    │     lines?       │
                    └────────┬────────┘
                             │ NO
                             ▼
                    ┌─────────────────┐
                    │  Documentation  │───YES────▶ SAFE Path
                    │   Tests Only?   │           (Auto-Approve)
                    └────────┬────────┘
                             │ NO
                             ▼
                    ┌─────────────────┐
                    │   Feature Add   │───YES────▶ STANDARD Path
                    │   Bug Fix?      │           (GitReviewBot)
                    └────────┬────────┘
                             │ NO
                             ▼
                    ┌─────────────────┐
                    │   Default to    │
                    │  STANDARD Path  │
                    └─────────────────┘
```

## Path Classifier Algorithm

The system automatically classifies PRs using this algorithm:

```python
def classify_workflow_path(files_changed, lines_changed, file_types):
    """
    Classify PR into workflow path.
    
    Returns: 'SAFE' | 'STANDARD' | 'COMPLEX'
    """
    # COMPLEX path triggers
    if any(f in CRITICAL_PATHS for f in files_changed):
        return 'COMPLEX'
    
    if any(f in INFRASTRUCTURE_PATHS for f in files_changed):
        return 'COMPLEX'
    
    if any(f in SECURITY_PATHS for f in files_changed):
        return 'COMPLEX'
    
    if len(files_changed) > 15 or lines_changed > 500:
        return 'COMPLEX'
    
    # SAFE path criteria (must meet ALL)
    safe_criteria = [
        len(files_changed) <= 5,
        lines_changed <= 200,
        all(f in SAFE_FILE_TYPES for f in file_types),
        not any(f in NON_SAFE_PATHS for f in files_changed)
    ]
    
    if all(safe_criteria):
        return 'SAFE'
    
    # Default to STANDARD
    return 'STANDARD'

# Path definitions
CRITICAL_PATHS = [
    '.woodpecker.yml',
    'infrastructure/terraform/',
    'src/execution/',
    'secrets/',
    'credentials/'
]

INFRASTRUCTURE_PATHS = [
    'docker-compose.yml',
    'Dockerfile',
    'infrastructure/',
    'scripts/ci/'
]

SECURITY_PATHS = [
    'src/security/',
    'src/auth/',
    'policies/'
]

SAFE_FILE_TYPES = [
    '.md',      # Documentation
    '.txt',     # Text files
    '.rst',     # Documentation
    '.py'       # Python (for docstrings/comments only)
]

NON_SAFE_PATHS = [
    'pyproject.toml',
    'poetry.lock',
    'requirements.txt'
]
```

## Examples by Path

### SAFE Path Example

**PR Title**: `docs(strategy): add docstrings to position sizing module (ST-NS-012A)`

**Files Changed**:
- `src/strategy/position_sizing/kelly.py` (+45 lines of docstrings)
- `src/strategy/position_sizing/fixed_fractional.py` (+38 lines of docstrings)
- `tests/test_position_sizing.py` (+25 lines of test documentation)

**Classification**: SAFE (3 files, 108 lines, documentation only)

**Timeline**: Auto-merged in 3 minutes after CI passed

### STANDARD Path Example

**PR Title**: `feat(dsl): implement trailing stop syntax (ST-DSL-042)`

**Files Changed**:
- `src/strategy/dsl/grammar.py` (+120 lines)
- `src/strategy/dsl/trailing_stop.py` (+85 lines, new file)
- `src/strategy/dsl/parser.py` (+45 lines)
- `tests/unit/strategy/test_trailing_stop.py` (+95 lines, new file)
- `tests/unit/strategy/test_grammar.py` (+35 lines)

**Classification**: STANDARD (5 files, 380 lines, feature addition)

**Timeline**: GitReviewBot approved in 8 minutes, auto-merged

### COMPLEX Path Example

**PR Title**: `feat(infra): add Redis cluster support with failover (ST-INFRA-015)`

**Files Changed**:
- `infrastructure/terraform/redis.tf` (+150 lines)
- `infrastructure/terraform/network.tf` (+85 lines)
- `src/cache/redis_client.py` (+120 lines)
- `src/cache/failover.py` (+95 lines, new file)
- `docker-compose.yml` (+45 lines)
- `pyproject.toml` (+15 lines - new dependency)
- `.woodpecker.yml` (+30 lines - new CI step)
- `tests/test_cache/test_failover.py` (+110 lines)
- `docs/runbooks/redis-failover.md` (+85 lines)

**Classification**: COMPLEX (9 files, 735 lines, infrastructure changes)

**Timeline**: GitReviewBot pre-review (10 min) → Human review (2 hours) → Approved → Merged

## Emergency Stop Mechanism

All paths respect the emergency stop mechanism:

```python
# Check emergency stop
emergency_stop = redis_state_hget(
    name="bmad:chiseai:system",
    key="emergency_stop"
)

if emergency_stop == "enabled":
    # Disable all auto-merges
    # Escalate all PRs to human review
    log_incident("Emergency stop active - auto-merge disabled")
```

To activate emergency stop:

```bash
redis-cli -p 6380 HSET bmad:chiseai:system emergency_stop enabled
```

This immediately:
1. Disables all SAFE path auto-merges
2. Escalates all in-flight STANDARD path PRs to human review
3. Blocks new auto-approvals until emergency stop is cleared

## Metrics and Monitoring

Track path distribution and performance:

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| SAFE path % | 30-40% | <20% or >50% |
| STANDARD path % | 50-60% | <40% or >70% |
| COMPLEX path % | 10-20% | >30% |
| SAFE path time | <5 min | >10 min |
| STANDARD path time | <12 min | >20 min |
| GitReviewBot accuracy | >90% | <85% |

## Best Practices

1. **Aim for STANDARD Path**: Most changes should fit here
2. **Don't Game the System**: Splitting PRs to avoid COMPLEX path creates risk
3. **Document COMPLEX Changes**: Include detailed descriptions and rollback plans
4. **Respect Emergency Stop**: Never bypass when active
5. **Monitor Your Stats**: Track your path distribution to improve efficiency

## See Also

- `quickstart.md` - Getting started guide
- `best-practices.md` - Scope ownership and conflict avoidance
- `troubleshooting.md` - Common issues and resolutions
- `../runbooks/agent-autonomous-workflow.md` - Operational procedures
