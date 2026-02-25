# Soul-Guided Compass Framework Operations Runbook

> **Story:** ST-SOUL-001  
> **Last Updated:** 2026-02-25  
> **Owner:** Platform Team / Merlin  
> **Status:** READY FOR USE

---

## 1. Overview

### 1.1 Purpose

The **Soul-Guided Compass Framework** is a constitutional governance layer that provides automated safety checks and human oversight for changes to critical system components. It ensures that modifications to execution, risk, infrastructure, secrets, and financial invariants receive appropriate scrutiny before deployment.

### 1.2 Key Principles

| Principle | Description |
|-----------|-------------|
| **Veto Authority** | Changes to veto paths automatically trigger COMPASS-VETO label |
| **Human Oversight** | COMPASS-VETO changes require HUMAN-APPROVED label to pass CI |
| **Auto-Detection** | compass_apply.py automatically detects and labels sensitive changes |
| **CI Blocking** | compass_gate.py blocks CI until proper approval is obtained |
| **Transparency** | All veto decisions are logged and auditable |

### 1.3 Authority

| Role | Can Approve COMPASS-VETO | Notes |
|------|-------------------------|-------|
| Captain Craig | ✅ Yes | Final authority; can override any decision |
| Merlin | ✅ Yes | Must document rationale for approval |
| SeniorDev | ❌ No | Can review but cannot add HUMAN-APPROVED label |
| On-Call Engineer | ❌ No | Can escalate but cannot approve |

---

## 2. Components

### 2.1 Configuration Files

| File | Purpose | Location |
|------|---------|----------|
| `compass.yaml` | Main policy configuration defining veto paths and principles | `docs/policy/compass.yaml` |
| `human_approval.yaml` | Human approval workflow and sensitive path definitions | `docs/policy/human_approval.yaml` |

### 2.2 Scripts

| Script | Purpose | Location |
|--------|---------|----------|
| `compass_apply.py` | Auto-applies COMPASS-VETO label based on file changes | `scripts/ops/compass_apply.py` |
| `compass_gate.py` | CI gate that blocks builds without proper approval | `scripts/ci/compass_gate.py` |

### 2.3 Tests

| Test File | Purpose | Location |
|-----------|---------|----------|
| `test_compass.py` | Unit tests for compass gate and apply functionality | `tests/unit/governance/test_compass.py` |

### 2.4 Component Relationships

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   PR Created    │────▶│ compass_apply.py │────▶│ COMPASS-VETO    │
│   Files Changed │     │ (Auto-labeling)  │     │ Label Applied   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   CI Passes     │◀────│ compass_gate.py  │◀────│ CI Pipeline     │
│   (Approved)    │     │ (Gate Check)     │     │ Blocked         │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌──────────────────┐
                        │ Human Reviewer   │
                        │ Adds HUMAN-      │
                        │ APPROVED Label   │
                        └──────────────────┘
```

---

## 3. Veto Path Categories

### 3.1 Execution Paths

**Patterns:**
- `src/execution/**/*.py`
- `src/trading/**/*.py`
- `src/position/**/*.py`

**Rationale:** Code that executes live trades, manages positions, or handles order flow.

**Examples:**
```
src/execution/order_manager.py
src/execution/position_manager.py
src/trading/strategy_runner.py
```

### 3.2 Risk Paths

**Patterns:**
- `src/risk/**/*.py`
- `src/portfolio/**/*.py`
- `**/kill_switch*`
- `**/position_sizing*`

**Rationale:** Risk management, position sizing, kill switches, and drawdown protection.

**Examples:**
```
src/risk/risk_engine.py
src/risk/drawdown_monitor.py
config/kill_switch.yaml
```

### 3.3 Infrastructure Paths

**Patterns:**
- `infrastructure/terraform/**/*.tf`
- `infrastructure/terraform/**/*.tfvars`
- `.woodpecker.yml`
- `.github/workflows/*`

**Rationale:** Infrastructure as Code, CI/CD pipelines, and deployment configurations.

**Examples:**
```
infrastructure/terraform/main.tf
infrastructure/terraform/variables.tfvars
.woodpecker.yml
```

### 3.4 Secrets Paths

**Patterns:**
- `**/*secret*`
- `**/*.env*`
- `**/credentials*`
- `infrastructure/secrets/**/*`

**Rationale:** Secrets, credentials, API keys, and sensitive configuration.

**Examples:**
```
infrastructure/secrets/api_keys.yaml
config/production.env
src/utils/credentials_manager.py
```

### 3.5 Invariants Paths

**Patterns:**
- `docs/invariants/**/*`
- `**/invariant*`

**Rationale:** Financial invariants that protect capital and system integrity.

**Examples:**
```
docs/invariants/capital_protection.md
src/validation/invariant_checker.py
```

### 3.6 Veto Path Reference Table

| Category | Risk Level | Auto-Label | Requires Approval |
|----------|-----------|------------|-------------------|
| execution | CRITICAL | COMPASS-VETO | HUMAN-APPROVED |
| risk | CRITICAL | COMPASS-VETO | HUMAN-APPROVED |
| infrastructure | HIGH | COMPASS-VETO | HUMAN-APPROVED |
| secrets | CRITICAL | COMPASS-VETO | HUMAN-APPROVED |
| invariants | HIGH | COMPASS-VETO | HUMAN-APPROVED |

---

## 4. CI Pipeline Integration

### 4.1 Pipeline Stage Configuration

The compass gate runs as a dedicated stage in the CI pipeline:

```yaml
# .woodpecker.yml (relevant section)
pipeline:
  compass-apply:
    image: python:3.11
    commands:
      - git diff --name-only HEAD~1 | python3 scripts/ops/compass_apply.py --pr=$CI_COMMIT_PULL_REQUEST
    when:
      event: pull_request

  compass-gate:
    image: python:3.11
    commands:
      - pip install pyyaml
      - git diff --name-only HEAD~1 | python3 scripts/ci/compass_gate.py --pr=$CI_COMMIT_PULL_REQUEST
    when:
      event: pull_request
```

### 4.2 compass_apply.py Usage

**Auto-apply labels on PR:**
```bash
# In CI pipeline - auto-applies COMPASS-VETO based on changed files
git diff --name-only HEAD~1 | python3 scripts/ops/compass_apply.py --pr=123
```

**Dry run (testing):**
```bash
# Preview what would happen without making changes
git diff --name-only HEAD~1 | python3 scripts/ops/compass_apply.py --dry-run --pr=123
```

**Check specific files:**
```bash
# Check specific files without PR context
python3 scripts/ops/compass_apply.py --files src/execution/order.py src/risk/manager.py
```

**Remove label:**
```bash
# Remove COMPASS-VETO label (use with caution)
python3 scripts/ops/compass_apply.py --pr=123 --remove
```

### 4.3 compass_gate.py Usage

**Gate check in CI:**
```bash
# Standard CI gate check
git diff --name-only HEAD~1 | python3 scripts/ci/compass_gate.py --pr=123
```

**Dry run (testing):**
```bash
# Preview gate results without failing
git diff --name-only HEAD~1 | python3 scripts/ci/compass_gate.py --dry-run --pr=123
```

**Check specific files:**
```bash
# Check specific files
python3 scripts/ci/compass_gate.py --check src/execution/order.py docs/readme.md
```

**Expected Output (Pass):**
```
============================================================
SOUL-GUIDED COMPASS GATE
============================================================

Files changed: 2
  - docs/readme.md
  - src/utils/helper.py

✓ No sensitive paths detected

Label Status:
  COMPASS-VETO: ✗ Not present
  HUMAN-APPROVED: ✗ Not present

============================================================
✅ COMPASS GATE PASSED
============================================================
```

**Expected Output (Fail - Veto without Approval):**
```
============================================================
SOUL-GUIDED COMPASS GATE
============================================================

Files changed: 2
  - src/execution/order_manager.py
  - docs/readme.md

⚠️  VETO PATH MATCHES (1):
  ⚡ src/execution/order_manager.py

Label Status:
  COMPASS-VETO: ✓ Present
  HUMAN-APPROVED: ✗ Not present

============================================================
❌ COMPASS GATE FAILED

Failures:
  - COMPASS-VETO label present without HUMAN-APPROVED
============================================================
```

---

## 5. Label Workflow

### 5.1 COMPASS-VETO Label

**Applied By:** `compass_apply.py` (automatic)

**When Applied:**
- Any changed file matches a veto path pattern
- PR touches execution, risk, infrastructure, secrets, or invariants

**Purpose:** Flags the PR as requiring human oversight

**Removal:** Only after HUMAN-APPROVED is added and PR is merged

### 5.2 HUMAN-APPROVED Label

**Applied By:** Human reviewer (manual)

**Who Can Apply:**
- Captain Craig (final authority)
- Merlin (with documented rationale)

**When Applied:**
- After reviewing the changes
- Risk assessment completed
- Rationale documented in PR comments

**Purpose:** Indicates human oversight has been provided

### 5.3 Label State Machine

```
┌─────────────┐    File matches    ┌─────────────┐
│   No Label  │───veto pattern───▶│ COMPASS-VETO│
└─────────────┘                   └─────────────┘
                                        │
                                        │ Human
                                        │ reviews
                                        ▼
                               ┌─────────────┐
                               │HUMAN-APPROVED│
                               │  + COMPASS  │
                               │   -VETO     │
                               └─────────────┘
                                        │
                                        │ CI Gate
                                        │ Passes
                                        ▼
                               ┌─────────────┐
                               │   Merged    │
                               └─────────────┘
```

### 5.4 Label Application Commands

**Via Gitea UI:**
1. Open PR in Gitea
2. Click "Labels" on the right sidebar
3. Select appropriate label

**Via API (for automation):**
```bash
# Add label
curl -X POST "https://gitea.chiseai.com/api/v1/repos/chiseai/chiseai/issues/123/labels" \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '["HUMAN-APPROVED"]'

# Remove label
curl -X DELETE "https://gitea.chiseai.com/api/v1/repos/chiseai/chiseai/issues/123/labels/COMPASS-VETO" \
  -H "Authorization: token $GITEA_TOKEN"
```

---

## 6. Approval Process

### 6.1 Approval Workflow

```
Step 1: PR Created
    ↓
Step 2: compass_apply.py detects sensitive paths
    ↓
Step 3: COMPASS-VETO label auto-applied
    ↓
Step 4: compass_gate.py blocks CI
    ↓
Step 5: Human reviewer assesses changes
    ↓
Step 6: If approved, HUMAN-APPROVED label added
    ↓
Step 7: compass_gate.py passes, CI continues
    ↓
Step 8: PR can be merged
```

### 6.2 Reviewer Checklist

Before adding HUMAN-APPROVED label, verify:

- [ ] **Code Quality:** Changes follow coding standards
- [ ] **Risk Assessment:** Potential risks identified and mitigated
- [ ] **Testing:** Appropriate tests added/updated
- [ ] **Documentation:** Changes documented if needed
- [ ] **Scope:** Changes are minimal and focused
- [ ] **Rollback Plan:** Rollback procedure understood

### 6.3 Approval Documentation

**Required in PR Comments:**

```markdown
## COMPASS-VETO Approval

**Approved by:** [Name]
**Date:** [YYYY-MM-DD]

### Risk Assessment
- **Category:** [execution/risk/infrastructure/secrets/invariants]
- **Risk Level:** [LOW/MEDIUM/HIGH/CRITICAL]
- **Mitigations:** [Description of risk mitigations]

### Rationale
[Why this change is safe to approve]

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

### Rollback Plan
[How to revert if issues arise]
```

### 6.4 Escalation Path

```
Reviewer Uncertain
        ↓
    Consult SeniorDev
        ↓
    Still Uncertain
        ↓
    Escalate to Merlin
        ↓
    Policy Question
        ↓
    Escalate to Captain Craig
```

---

## 7. Rollback Procedures

### 7.1 Emergency Bypass

In emergency situations, the compass gate can be bypassed:

**⚠️ WARNING:** Only use in true emergencies. All bypasses are logged and audited.

**Authorized Personnel:**
- Captain Craig
- Merlin (with post-hoc approval from Captain Craig)

**Bypass Methods:**

**Method 1: Add HUMAN-APPROVED with Emergency Rationale**
```markdown
## EMERGENCY APPROVAL

**Approved by:** [Name]
**Date:** [YYYY-MM-DD]
**Emergency:** [Brief description of emergency]

### Justification
[Why normal approval process was bypassed]

### Risk Acceptance
[Risks accepted by this emergency approval]

### Follow-up Required
- [ ] Post-incident review scheduled
- [ ] Process improvement identified
- [ ] Documentation updated
```

**Method 2: CI Pipeline Override (Last Resort)**
```bash
# Force merge (requires admin privileges)
# This should ONLY be used when:
# 1. System is down
# 2. Critical security fix needed
# 3. All other methods exhausted

# Document the override immediately in incident log
echo "Compass gate bypassed by [NAME] at [TIME] for [REASON]" >> docs/incidents/INCIDENT-XXX.md
```

### 7.2 Post-Bypass Procedures

Within 1 hour of bypass:
1. **Log the incident** in incident management system
2. **Notify stakeholders:** #incidents channel, Merlin, Captain Craig
3. **Schedule post-mortem** within 24 hours
4. **Document rationale** in PR comments

### 7.3 Reverting Changes

If a COMPASS-VETO change causes issues after merge:

**Immediate Rollback:**
```bash
# Revert the PR
git revert -m 1 <merge-commit-hash>
git push origin main

# Or create revert PR
git checkout -b revert/PR-123
git revert -m 1 <merge-commit-hash>
git push origin revert/PR-123
# Create PR with REVERT prefix
```

**Document the Rollback:**
```markdown
## Rollback: PR-123

**Rolled back by:** [Name]
**Date:** [YYYY-MM-DD]
**Reason:** [Why the change was reverted]

### Impact
[What systems were affected]

### Lessons Learned
[What we learned from this incident]
```

---

## 8. Troubleshooting

### 8.1 Common Issues

#### Issue: COMPASS-VETO not auto-applied

**Symptoms:**
- Changed sensitive files but no COMPASS-VETO label

**Diagnosis:**
```bash
# Check if auto-labeling is enabled
python3 -c "import yaml; print(yaml.safe_load(open('docs/policy/compass.yaml'))['auto_label']['enabled'])"

# Check if files match patterns
python3 scripts/ops/compass_apply.py --files src/execution/order.py --dry-run
```

**Resolution:**
1. Verify `compass.yaml` has `auto_label.enabled: true`
2. Check file path matches veto pattern exactly
3. Manually add COMPASS-VETO label if needed

#### Issue: CI Gate fails unexpectedly

**Symptoms:**
- Gate fails even with HUMAN-APPROVED label

**Diagnosis:**
```bash
# Check environment variable
env | grep CI_PR_LABELS

# Run gate locally with debug
git diff --name-only HEAD~1 | python3 scripts/ci/compass_gate.py --pr=123
```

**Resolution:**
1. Verify HUMAN-APPROVED label is spelled correctly
2. Check CI environment has access to labels
3. Re-run CI pipeline

#### Issue: False positive veto detection

**Symptoms:**
- Non-sensitive file triggers COMPASS-VETO

**Diagnosis:**
```bash
# Check which pattern matched
python3 scripts/ops/compass_apply.py --files path/to/file.py --dry-run
```

**Resolution:**
1. Review `compass.yaml` veto_paths patterns
2. Consider making pattern more specific
3. Document exception if pattern is correct

#### Issue: Pattern not matching expected files

**Symptoms:**
- Sensitive file changes don't trigger veto

**Diagnosis:**
```bash
# Test pattern matching
python3 -c "
import fnmatch
patterns = ['src/execution/**/*.py']
file = 'src/execution/nested/order.py'
print(fnmatch.fnmatch(file, patterns[0]))
"
```

**Resolution:**
1. Update pattern in `compass.yaml` to use `**` for recursion
2. Example: `src/execution/**/*.py` matches nested files

### 8.2 Debug Commands

**Test pattern matching:**
```bash
# Test if a file matches veto patterns
python3 << 'EOF'
import sys
sys.path.insert(0, 'scripts/ci')
import compass_gate

config = compass_gate.load_compass_config()
patterns = compass_gate.get_veto_patterns(config)

test_files = [
    "src/execution/order.py",
    "src/risk/manager.py",
    "docs/readme.md"
]

for f in test_files:
    matches = compass_gate.match_glob_patterns(f, patterns)
    print(f"{f}: {'MATCH' if matches else 'no match'}")
EOF
```

**Check current labels:**
```bash
# Via API
curl -s "https://gitea.chiseai.com/api/v1/repos/chiseai/chiseai/pulls/123" \
  -H "Authorization: token $GITEA_TOKEN" | jq '.labels'
```

**Validate config files:**
```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('docs/policy/compass.yaml'))"
python3 -c "import yaml; yaml.safe_load(open('docs/policy/human_approval.yaml'))"
```

### 8.3 Contact Information

| Issue Type | Contact | Response SLA |
|-----------|---------|--------------|
| Config issues | Merlin | < 4 hours |
| CI pipeline failures | Platform Team | < 2 hours |
| False positives/negatives | Merlin | < 1 business day |
| Policy questions | Captain Craig | < 1 business day |

---

## 9. Testing

### 9.1 Running Compass Tests

**All compass tests:**
```bash
# Run all compass-related tests
pytest tests/unit/governance/test_compass.py -v
```

**Specific test classes:**
```bash
# Test compass gate only
pytest tests/unit/governance/test_compass.py::TestCompassGate -v

# Test compass apply only
pytest tests/unit/governance/test_compass.py::TestCompassApply -v

# Test integration scenarios
pytest tests/unit/governance/test_compass.py::TestIntegration -v

# Test config validation
pytest tests/unit/governance/test_compass.py::TestConfigValidation -v
```

**With coverage:**
```bash
# Run with coverage report
pytest tests/unit/governance/test_compass.py --cov=scripts.ci.compass_gate --cov=scripts.ops.compass_apply -v
```

### 9.2 Test Output Example

```
$ pytest tests/unit/governance/test_compass.py -v

============================= test session starts ==============================
platform linux -- Python 3.11.0
rootdir: /home/tacopants/projects/ChiseAI
collected 20 items

tests/unit/governance/test_compass.py::TestCompassGate::test_load_compass_config_exists PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_load_compass_config_not_found PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_match_glob_patterns PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_get_veto_patterns PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_check_sensitive_paths_no_match PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_check_sensitive_paths_with_match PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_check_pr_labels_from_env PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_run_gate_check_passes_no_sensitive PASSED
tests/unit/governance/test_compass.py::TestCompassGate::test_run_gate_check_fails_veto_without_approval PASSED
tests/unit/governance/test_compass.py::TestCompassApply::test_detect_sensitive_changes_no_match PASSED
tests/unit/governance/test_compass.py::TestCompassApply::test_detect_sensitive_changes_with_match PASSED
tests/unit/governance/test_compass.py::TestCompassApply::test_apply_label_already_present PASSED
tests/unit/governance/test_compass.py::TestCompassApply::test_apply_label_new PASSED
tests/unit/governance/test_compass.py::TestCompassApply::test_run_apply_no_sensitive PASSED
tests/unit/governance/test_compass.py::TestCompassApply::test_run_apply_with_sensitive PASSED
tests/unit/governance/test_compass.py::TestIntegration::test_full_workflow_sensitive_change PASSED
tests/unit/governance/test_compass.py::TestIntegration::test_full_workflow_approved PASSED
tests/unit/governance/test_compass.py::TestConfigValidation::test_compass_config_structure PASSED
tests/unit/governance/test_compass.py::TestConfigValidation::test_human_approval_config_structure PASSED

============================== 20 passed in 0.45s ==============================
```

### 9.3 Manual Testing

**Test auto-labeling:**
```bash
# Create test scenario
echo "test" > src/execution/test_file.py
git add src/execution/test_file.py

# Test apply (dry run)
git diff --cached --name-only | python3 scripts/ops/compass_apply.py --dry-run

# Clean up
git checkout -- src/execution/test_file.py
rm -f src/execution/test_file.py
```

**Test gate check:**
```bash
# Simulate sensitive change
echo "src/execution/order_manager.py" | python3 scripts/ci/compass_gate.py --check

# Simulate approved change
CI_PR_LABELS="COMPASS-VETO,HUMAN-APPROVED" \
  echo "src/execution/order_manager.py" | python3 scripts/ci/compass_gate.py --check
```

### 9.4 Adding New Tests

When modifying compass functionality, add tests to `tests/unit/governance/test_compass.py`:

```python
def test_new_feature(self):
    """Test description."""
    # Arrange
    files = ["src/execution/new_feature.py"]
    
    # Act
    with patch.object(compass_apply, "load_compass_config") as mock_load:
        mock_load.return_value = {
            "auto_label": {"enabled": True, "label_name": "COMPASS-VETO"},
            "veto_paths": {"execution": ["src/execution/**/*.py"]},
        }
        result = compass_apply.run_apply(files, 123, dry_run=True)
    
    # Assert
    assert result["would_apply_label"] is True
```

---

## 10. Configuration Reference

### 10.1 compass.yaml Structure

```yaml
---
# Soul-Guided Compass Policy
version: "1.0.0"
effective_date: "2026-02-25"

# Veto Principles
veto_principles:
  - execution_safety
  - risk_management
  - infrastructure_core
  - financial_invariants
  - kill_switch_systems

# Veto Path Patterns
veto_paths:
  execution:
    - "src/execution/**/*.py"
    - "src/trading/**/*.py"
  risk:
    - "src/risk/**/*.py"
  infrastructure:
    - "infrastructure/terraform/**/*.tf"
  secrets:
    - "**/*secret*"
  invariants:
    - "docs/invariants/**/*"

# Approval Requirements
approval_requirements:
  compass_veto_override:
    label: "HUMAN-APPROVED"
    approvers:
      - Captain Craig
      - Merlin
    max_duration_hours: 48

# CI Gate Configuration
ci_gate:
  name: "compass-gate"
  blocking: true
  fail_on:
    - compass_veto_present_without_approval
    - sensitive_path_changed_without_label

# Auto-labeling Configuration
auto_label:
  enabled: true
  label_name: "COMPASS-VETO"
  dry_run: false
```

### 10.2 human_approval.yaml Structure

```yaml
---
# Human Approval Policy
version: "1.0.0"

# Sensitive Path Categories
sensitive_paths:
  critical_execution:
    description: "Code that executes live trades"
    paths:
      - "src/execution/order_manager.py"
    approval_required: true
    min_approvers: 1

# Approval Workflow
workflow:
  steps:
    1: "PR created with changes to sensitive paths"
    2: "compass_apply.py auto-detects and applies COMPASS-VETO label"
    3: "compass_gate.py blocks CI until HUMAN-APPROVED label added"
    4: "Human reviewer assesses changes"
    5: "If approved, HUMAN-APPROVED label added"
    6: "compass_gate.py passes, CI continues"

  escalation:
    timeout_hours: 48
    auto_escalate_to: "Captain Craig"
```

---

## 11. References

### 11.1 Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Compass Policy | `docs/policy/compass.yaml` | Main policy configuration |
| Human Approval Policy | `docs/policy/human_approval.yaml` | Approval workflow config |
| Incident Response | `docs/runbooks/incident_response.md` | General incident procedures |
| ACP Rollback | `docs/runbooks/acp-rollback-runbook.md` | Emergency rollback procedures |

### 11.2 Source Code

| Component | Location |
|-----------|----------|
| Compass Apply Script | `scripts/ops/compass_apply.py` |
| Compass Gate Script | `scripts/ci/compass_gate.py` |
| Unit Tests | `tests/unit/governance/test_compass.py` |

### 11.3 External Resources

- **Gitea API Docs:** https://docs.gitea.io/en-us/api-usage/
- **Woodpecker CI Docs:** https://woodpecker-ci.org/docs
- **YAML Spec:** https://yaml.org/spec/

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-25 | Merlin | Initial runbook creation |

---

*This runbook was created per ST-SOUL-001 requirements and is ready for operational use.*
