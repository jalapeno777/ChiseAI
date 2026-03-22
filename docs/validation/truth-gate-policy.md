# Truth Gate Policy

## Overview

The Truth Gate Policy defines mandatory validation checks for all merge operations in the ChiseAI repository. These checks ensure that commits are properly verified, story IDs are valid, and merge claims are truthful.

## Mandatory Checks

### 1. Commit Existence Check

**Requirement**: The commit SHA must exist in the repository.

**Validation Command**:
```bash
git cat-file -t <commit-sha>
```

**Pass Criteria**: Command returns "commit"

**Fail Criteria**:
- Commit does not exist
- Invalid SHA format
- Repository access error

**Error Message**:
```
✗ commit-exists: Commit <sha> does not exist in repository
```

**Remediation**:
1. Verify the commit SHA is correct
2. Ensure you're in the correct repository
3. Check if the commit exists on a different branch
4. For new commits, ensure they have been pushed to the repository

---

### 2. Story ID Format Check

**Requirement**: Story IDs must match one of the recognized patterns.

**Valid Patterns** (must include a digit):
- `ST-*` - Story implementation
- `CH-*` - Chore/maintenance
- `FT-*` - Feature
- `REWARD-*` - Reward system
- `REPO-*` - Repository work
- `SAFETY-*` - Safety-critical
- `BRANCH-*` - Branch management
- `PAPER-*` - Paper trading
- `RECON-*` - Reconnaissance
- `TG-*` - Truth gate
- `GOV-*` - Governance
- `STRONG-*` - Strong system

**Validation**: Regex pattern matching

**Pass Criteria**: Story ID matches one of the valid patterns

**Fail Criteria**:
- Story ID is empty
- Story ID does not match any valid pattern
- Missing numeric component (e.g., "ST-" without number)

**Error Message**:
```
✗ story-id-format: Story ID '<id>' does not match valid pattern
```

**Remediation**:
1. Use one of the recognized story ID prefixes
2. Include a numeric identifier (e.g., `ST-001`, not `ST-`)
3. Check AGENTS.md for current story ID conventions

---

### 3. Commit on Branch Check

**Requirement**: The commit must be on the specified branch.

**Validation Command**:
```bash
git branch --contains <commit-sha>
```

**Pass Criteria**: Target branch appears in the list of branches containing the commit

**Fail Criteria**:
- Commit is not on the specified branch
- Branch does not exist
- Git command fails

**Error Message**:
```
✗ commit-on-branch: Commit <sha> is NOT on branch '<branch>'
```

**Remediation**:
1. Verify the commit has been merged to the target branch
2. Check if the commit exists on a different branch
3. For feature branches, ensure the branch has been properly pushed
4. Use `git branch --contains <commit>` to see which branches contain the commit

**Important Note**: This check is the primary defense against false merge claims. Always verify with `git branch --contains` before claiming a commit is merged.

---

### 4. PR Title Story ID Check

**Requirement**: PR titles must contain the story ID.

**Validation**: Search PR title for valid story ID pattern matching the expected story ID

**Pass Criteria**: PR title contains the expected story ID

**Fail Criteria**:
- PR title is empty
- PR title does not contain a story ID
- PR title contains a different story ID than expected

**Error Messages**:
```
✗ pr-title: PR title does not contain a valid story ID (expected '<id>')
✗ pr-title: PR title contains different story ID '<found>' (expected '<expected>')
```

**Remediation**:
1. Update PR title to include the story ID in parentheses: `feat: Description (ST-001)`
2. Ensure the story ID in the PR title matches the story being worked on
3. Follow the format: `<type>(<scope>): <description> (<story-id>)`

---

## Usage

### Basic Usage

```bash
# Validate commit and story ID
python3 scripts/validation/truth_gate_check.py --commit 5737a8ee --story-id TG-003

# Validate commit is on main branch
python3 scripts/validation/truth_gate_check.py --commit 5737a8ee --story-id TG-003 --branch main

# Validate PR title contains story ID
python3 scripts/validation/truth_gate_check.py --commit 5737a8ee --story-id TG-003 --pr "feat: Add feature (TG-003)"

# Full validation
python3 scripts/validation/truth_gate_check.py --commit 5737a8ee --story-id TG-003 --branch main --pr "feat: Add feature (TG-003)"
```

### Output Formats

**Text Output (default)**:
```
============================================================
TRUTH GATE CHECK: PASS
============================================================
Commit: 5737a8ee
Story ID: TG-003
Branch: main
------------------------------------------------------------
✓ story-id-format: Story ID 'TG-003' matches valid pattern
✓ commit-exists: Commit 5737a8ee exists in repository
✓ commit-on-branch: Commit 5737a8ee is on branch 'main'
------------------------------------------------------------
Total: 3 | Passed: 3 | Failed: 0
============================================================
```

**JSON Output**:
```bash
python3 scripts/validation/truth_gate_check.py --commit 5737a8ee --story-id TG-003 --json
```

**Verbose Output**:
```bash
python3 scripts/validation/truth_gate_check.py --commit 5737a8ee --story-id TG-003 --verbose
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | One or more checks failed |
| 2 | Invalid arguments or git error |

---

## Integration with CI/CD

### Woodpecker CI Integration

Add to `.woodpecker.yml`:

```yaml
steps:
  truth-gate-check:
    image: python:3.11
    commands:
      - python3 scripts/validation/truth_gate_check.py --commit $CI_COMMIT_SHA --story-id $STORY_ID --branch main
    when:
      - event: pull_request
```

### Pre-Merge Hook

Add to `.git/hooks/pre-merge`:

```bash
#!/bin/bash
# Truth gate validation before merge

COMMIT=$1
STORY_ID=$(python3 scripts/validation/extract_story_id_from_pr.py --from-title "$PR_TITLE")

python3 scripts/validation/truth_gate_check.py \
    --commit "$COMMIT" \
    --story-id "$STORY_ID" \
    --branch main

if [ $? -ne 0 ]; then
    echo "Truth gate check failed. Merge aborted."
    exit 1
fi
```

---

## Manual Override Procedures

### When Override is Needed

In exceptional circumstances, truth gate checks may need to be bypassed:

1. **Emergency hotfixes** requiring immediate merge
2. **Repository maintenance** where git history is being rewritten
3. **CI system failures** preventing normal validation

### Override Process

1. **Document the override**:
   - Create an incident record
   - Explain why the override is necessary
   - Document the risks of bypassing checks

2. **Obtain approval**:
   - Emergency: Captain Craig approval required
   - Non-emergency: Team lead approval

3. **Execute with logging**:
   ```bash
   # Log the override
   echo "OVERRIDE: $(date) - $(whoami) - Reason: <reason>" >> docs/validation/override-log.txt
   
   # Proceed with merge
   git merge --no-verify <branch>
   ```

4. **Post-override actions**:
   - Verify the merge was correct
   - Run validation manually after merge
   - Create post-mortem if warranted

### Override Logging Format

```
[YYYY-MM-DD HH:MM:SS UTC]
Override by: <username>
Commit: <sha>
Story ID: <id>
Reason: <detailed explanation>
Approved by: <approver>
Risk assessment: <brief risk description>
Follow-up required: <yes/no>
```

---

## Error Messages and Remediation

### Common Errors

| Error | Cause | Remediation |
|-------|-------|-------------|
| `Commit <sha> does not exist` | SHA is wrong or not pushed | Verify SHA, push commit |
| `Story ID does not match valid pattern` | Invalid story ID format | Use valid prefix with number |
| `Commit is NOT on branch` | Not merged to target branch | Merge commit to target branch first |
| `PR title does not contain story ID` | Missing story ID in title | Update PR title |
| `Not a git repository` | Wrong directory | Run from repo root or use --repo-root |

### Troubleshooting

**Git Access Issues**:
```bash
# Verify git is available
git --version

# Check repository status
git status

# Verify remote access
git fetch origin
```

**Permission Issues**:
```bash
# Ensure script is executable
chmod +x scripts/validation/truth_gate_check.py

# Check file ownership
ls -la scripts/validation/truth_gate_check.py
```

---

## Policy Compliance

### Required for All Merges

- [ ] Commit exists in repository
- [ ] Story ID format is valid
- [ ] Commit is on target branch (verified with `git branch --contains`)
- [ ] PR title contains story ID

### Validation Frequency

| Event | Checks Required |
|-------|-----------------|
| Pull Request Created | Story ID format, PR title |
| Pre-Merge | All checks |
| Post-Merge Verification | Commit on main |
| Nightly Audit | Sample of recent merges |

### Non-Compliance Consequences

1. **CI Failure**: Non-compliant PRs will fail CI checks
2. **Merge Block**: Non-compliant PRs cannot be merged
3. **Audit Flag**: Non-compliance is logged for governance review
4. **Escalation**: Repeated non-compliance escalates to governance team

---

## References

- [AGENTS.md](../../AGENTS.md) - Agent workflow and story ID conventions
- [truth_gate_check.py](../../scripts/validation/truth_gate_check.py) - Validation script
- [extract_story_id_from_pr.py](../../scripts/validation/extract_story_id_from_pr.py) - Story ID extraction
- [validation-registry.yaml](./validation-registry.yaml) - Validation registry

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-16 | Initial policy creation |

---

## Contact

For questions or issues with truth gate validation:
- **Governance Team**: governance@chiseai.local
- **CI/CD Issues**: #ci-cd-support channel
- **Emergency**: Contact Captain Craig
