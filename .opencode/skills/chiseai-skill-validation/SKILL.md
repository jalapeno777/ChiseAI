---
name: chiseai-skill-validation
description: Validate skill markdown files have proper structure, frontmatter, and required sections.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-skill-validation

## Goal

Ensure all ChiseAI skill markdown files maintain consistent structure, proper frontmatter, and include all required sections for reliable agent skill loading and execution.

## When To Use

- **Creating new skills** - Before finalizing any new skill file
- **Updating existing skills** - After modifying skill content or structure
- **Before skill PR submission** - Validate all skills in a PR pass quality gates
- **During skill audits** - Systematic review of skill repository health
- **Onboarding new skill authors** - Reference for skill creation standards
- **CI skill validation** - Automated checks in pre-commit hooks or CI pipelines

## When Not To Use

- **Non-skill documentation** - Regular markdown docs don't follow skill structure
- **Quick content fixes** - Minor typo corrections that don't affect structure
- **External skill repos** - Only validate ChiseAI repo skills
- **Command files** - `.opencode/command/*.md` files have different structure
- **Agent configuration** - AGENTS.md and similar config files have their own format

## Required Skill Structure

### Frontmatter Requirements

Every skill MUST include valid YAML frontmatter at the file start:

```yaml
---
name: <skill-name>
description: <one-line description of what the skill does>
metadata:
  version: "<major.minor>"
  opencode_min_version: "<version>"
  author: "<author-name>"
  last_updated: "<YYYY-MM-DD>"
---
```

**Required Fields:**
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `name` | string | Skill identifier, must match directory name | Exact match with parent directory |
| `description` | string | Brief description of skill purpose | Max 120 chars, ends with period |
| `metadata.version` | string | Semantic version (major.minor) | Format: `X.Y` |
| `metadata.opencode_min_version` | string | Minimum opencode version | Format: `X.Y.Z` |
| `metadata.author` | string | Author/team identifier | Non-empty string |
| `metadata.last_updated` | string | Last modification date | ISO date: `YYYY-MM-DD` |

### Required Sections (In Order)

Every skill MUST contain these sections in this exact order:

1. **Goal** - Single paragraph explaining the skill's purpose
2. **When To Use** - Bullet list of appropriate use cases
3. **When Not To Use** - Bullet list of inappropriate use cases (with **bold** warnings)
4. **[Skill-Specific Content]** - Variable sections based on skill type
5. **Exit Conditions** - When to stop and escalate
6. **Troubleshooting/Safety** - Common issues and safety checks
7. **Related Skills** - Links to related skills (if any)
8. **Related Commands** - Links to related commands (if any)

**Section Headers Format:**
- Use `##` for all major sections
- Use `###` for subsections
- Section names must match exactly (case-sensitive)

### Naming Conventions

**Directory Name:**
- Format: `chiseai-<domain>-<function>`
- All lowercase with hyphens
- Examples: `chiseai-validation`, `chiseai-git-workflow`, `chiseai-memory-ops`

**File Name:**
- Always: `SKILL.md` (uppercase)
- Located at: `.opencode/skills/<skill-name>/SKILL.md`

## Validation Checklist

Use this checklist to validate any skill file:

### Frontmatter Validation
- [ ] Frontmatter exists at file start (between `---` markers)
- [ ] Frontmatter is valid YAML (no syntax errors)
- [ ] `name` field present and matches parent directory name
- [ ] `description` field present and concise (under 120 chars)
- [ ] `metadata.version` present in `X.Y` format
- [ ] `metadata.opencode_min_version` present in `X.Y.Z` format
- [ ] `metadata.author` field present
- [ ] `metadata.last_updated` in `YYYY-MM-DD` format

### Structure Validation
- [ ] `## Goal` section exists
- [ ] `## When To Use` section exists with bullet list
- [ ] `## When Not To Use` section exists with bullet list
- [ ] `## Exit Conditions` section exists
- [ ] `## Troubleshooting/Safety` section exists
- [ ] `## Related Skills` section exists (can be empty)
- [ ] `## Related Commands` section exists (can be empty)
- [ ] Sections appear in required order

### Content Quality
- [ ] Goal is clear and single-paragraph
- [ ] "When To Use" has at least 2 items
- [ ] "When Not To Use" has at least 1 item with **bold** warning
- [ ] Exit Conditions define clear escalation paths
- [ ] Troubleshooting includes common issues table
- [ ] Related commands reference existing `.opencode/command/*.md` files
- [ ] Related skills reference existing skills

### Cross-Reference Validation
- [ ] All `Related Commands` files exist in `.opencode/command/`
- [ ] All `Related Skills` directories exist in `.opencode/skills/`
- [ ] No broken internal references

## Templates

### Skill Structure Template (Full)

```markdown
---
name: <skill-name>
description: <Brief description of what this skill does.>
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "<YYYY-MM-DD>"
---

# <skill-name>

## Goal

<One paragraph explaining the skill's purpose and value to agents.>

## When To Use

- **Use case 1** - Brief explanation
- **Use case 2** - Brief explanation
- **Use case 3** - Brief explanation
- **Use case 4** - Brief explanation

## When Not To Use

- **<Warning context>** - Why this doesn't apply
- **<Another context>** - Why this doesn't apply
- **<Third context>** - Why this doesn't apply

## <Skill-Specific Section 1>

<Content specific to this skill's domain>

### Subsection

<Additional detail>

## <Skill-Specific Section 2>

<More specific content>

## Exit Conditions

Stop and escalate to Jarvis if:
- **<Condition 1>** - <why this requires escalation>
- **<Condition 2>** - <why this requires escalation>
- **<Condition 3>** - <why this requires escalation>

## Troubleshooting/Safety

### Common Issues
| Issue | Resolution |
|-------|------------|
| <Issue 1> | <How to fix> |
| <Issue 2> | <How to fix> |
| <Issue 3> | <How to fix> |

### Safety Checks
- [ ] <Safety check 1>
- [ ] <Safety check 2>
- [ ] <Safety check 3>

## Templates

<Optional: Include relevant templates for the skill's use cases>

## Examples

<Include 2-3 examples showing proper usage>

## Related Skills

- **<skill-name>** - <Brief explanation of relationship>

## Related Commands

- `.opencode/command/<command-name>.md` - <Brief explanation>
```

### Frontmatter Template

```yaml
---
name: chiseai-<domain>-<function>
description: <Action verb> <object> for <purpose/context>.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---
```

### Validation Report Template

```markdown
## Skill Validation Report

**Skill:** <skill-name>
**Path:** `.opencode/skills/<skill-name>/SKILL.md`
**Validated:** <YYYY-MM-DD HH:MM UTC>
**Validator:** <agent-id or "automated">

### Summary
- **Status:** PASS / FAIL
- **Total Checks:** <N>
- **Passed:** <N>
- **Failed:** <N>
- **Warnings:** <N>

### Frontmatter Validation
| Check | Status | Notes |
|-------|--------|-------|
| YAML Valid | PASS/FAIL | |
| name matches directory | PASS/FAIL | |
| description present | PASS/FAIL | |
| version format | PASS/FAIL | |
| opencode_min_version | PASS/FAIL | |
| author present | PASS/FAIL | |
| last_updated format | PASS/FAIL | |

### Structure Validation
| Section | Present | Order | Notes |
|---------|---------|-------|-------|
| Goal | YES/NO | CORRECT/WRONG | |
| When To Use | YES/NO | CORRECT/WRONG | |
| When Not To Use | YES/NO | CORRECT/WRONG | |
| Exit Conditions | YES/NO | CORRECT/WRONG | |
| Troubleshooting/Safety | YES/NO | CORRECT/WRONG | |
| Related Skills | YES/NO | CORRECT/WRONG | |
| Related Commands | YES/NO | CORRECT/WRONG | |

### Cross-Reference Validation
| Reference | Type | Exists | Path |
|-----------|------|--------|------|
| <name> | command/skill | YES/NO | <path> |

### Issues Found
<If any issues, list them here with severity and suggested fixes>

### Recommendations
<Optional: Improvement suggestions even if validation passed>
```

## Examples

### Example 1: Valid Skill (Passes All Checks)

**File:** `.opencode/skills/chiseai-example-valid/SKILL.md`

```yaml
---
name: chiseai-example-valid
description: Example skill demonstrating proper structure and validation.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-example-valid

## Goal

Demonstrate the correct structure and content for a ChiseAI skill file that will pass all validation checks.

## When To Use

- Creating reference examples for skill authors
- Testing skill validation scripts
- Onboarding new team members to skill patterns

## When Not To Use

- **Production use** - This is an example only
- **Documentation** - Use proper docs for documentation needs

## Example Functionality

This section shows how skill-specific content should be structured.

### Basic Pattern
1. Clear heading hierarchy
2. Actionable content
3. Examples where helpful

## Exit Conditions

Stop and escalate to Jarvis if:
- **Example conflicts with real patterns** - Update this example to match

## Troubleshooting/Safety

### Common Issues
| Issue | Resolution |
|-------|------------|
| "Not a real skill" | This is intentional - use as reference only |

### Safety Checks
- [ ] Verify this is only used as reference
- [ ] Do not copy without adapting to actual use case

## Related Skills

- **chiseai-skill-validation** - This skill validates structure

## Related Commands

- None (example skill)
```

**Validation Result:**
```
Skill Validation Report

Skill: chiseai-example-valid
Path: .opencode/skills/chiseai-example-valid/SKILL.md
Validated: 2026-02-23 15:30 UTC

Summary:
  Status: PASS
  Total Checks: 15
  Passed: 15
  Failed: 0
  Warnings: 0

All validation checks passed.
```

### Example 2: Invalid Skill (Missing Sections) With Fixes

**Original File (Invalid):** `.opencode/skills/chiseai-broken/SKILL.md`

```yaml
---
name: chiseai-broken
description: A skill with missing sections
metadata:
  version: "1.0"
  author: "ChiseAI Team"
---

# chiseai-broken

## Goal

This skill has problems.

## When To Use

- When testing validation

## Exit Conditions

Stop if things break.
```

**Validation Report:**
```
Skill Validation Report

Skill: chiseai-broken
Path: .opencode/skills/chiseai-broken/SKILL.md
Validated: 2026-02-23 15:35 UTC

Summary:
  Status: FAIL
  Total Checks: 15
  Passed: 7
  Failed: 6
  Warnings: 2

Issues Found:

  [ERROR] Frontmatter: Missing required field 'opencode_min_version'
  [ERROR] Frontmatter: Missing required field 'last_updated'
  [ERROR] Structure: Missing required section 'When Not To Use'
  [ERROR] Structure: Missing required section 'Troubleshooting/Safety'
  [ERROR] Structure: Missing required section 'Related Skills'
  [ERROR] Structure: Missing required section 'Related Commands'
  
  [WARNING] Content: 'When To Use' has only 1 item (minimum 2 recommended)
  [WARNING] Content: Exit Conditions lacks specific escalation guidance
```

**Fixed File:**

```yaml
---
name: chiseai-broken
description: A skill with all required sections after fixes.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-broken

## Goal

Demonstrate common validation issues and their fixes for skill authors.

## When To Use

- When testing validation scripts
- When learning about skill structure
- When debugging validation failures

## When Not To Use

- **Production workflows** - This is a test/example skill
- **Actual skill development** - Use proper templates instead

## Example Content

This skill was created to show validation errors and fixes.

## Exit Conditions

Stop and escalate to Jarvis if:
- **Validation infrastructure fails** - Cannot run validation checks
- **Unknown error patterns** - Error not in documented troubleshooting

## Troubleshooting/Safety

### Common Issues
| Issue | Resolution |
|-------|------------|
| Missing frontmatter fields | Add all required metadata fields |
| Missing sections | Add sections in required order |

### Safety Checks
- [ ] All required sections present
- [ ] Frontmatter complete
- [ ] Cross-references valid

## Related Skills

- **chiseai-skill-validation** - Validates this skill's structure

## Related Commands

- None (example skill)
```

### Example 3: Skill Update Validation

**Scenario:** Updating `chiseai-validation` skill to add new validation pattern.

**Before Update Check:**
```bash
# Validate current state is valid before changes
$ python3 scripts/validate_skill.py .opencode/skills/chiseai-validation/SKILL.md

Skill Validation Report
  Status: PASS
  All checks passed - safe to proceed with updates
```

**Changes Made:**
1. Updated `metadata.version` from "1.0" to "1.1"
2. Updated `metadata.last_updated` to current date
3. Added new section "Performance Validation" between existing sections

**After Update Validation:**
```bash
$ python3 scripts/validate_skill.py .opencode/skills/chiseai-validation/SKILL.md

Skill Validation Report

Skill: chiseai-validation
Path: .opencode/skills/chiseai-validation/SKILL.md
Validated: 2026-02-23 16:00 UTC

Summary:
  Status: PASS
  Total Checks: 15
  Passed: 15
  Failed: 0
  Warnings: 0

Version Change: 1.0 -> 1.1
Last Updated: 2026-02-23

New content validated successfully.
```

**Key Update Checklist:**
- [ ] Increment version number
- [ ] Update last_updated date
- [ ] Validate structure after changes
- [ ] Test skill loading in opencode
- [ ] Update related documentation if needed

## Exit Conditions

Stop and escalate to Jarvis if:

- **Validation script errors** - The validation tool itself is broken or producing unexpected output
- **Batch validation failures** - More than 3 skills fail validation in a single run (may indicate systemic issue)
- **Cross-reference cascade** - Fixing one skill's references breaks validation of another
- **Frontmatter syntax unclear** - YAML parsing fails but cause is not obvious
- **Skill loading failure** - Validated skill fails to load in opencode (structure may be correct but incompatible)
- **New section requirements** - Need to add new required sections to all skills (coordination required)

## Troubleshooting/Safety

### Common Issues

| Issue | Resolution |
|-------|------------|
| "Name doesn't match directory" | Ensure `name` field exactly matches parent folder name (case-sensitive) |
| "Invalid YAML in frontmatter" | Check for special characters, proper quoting, and correct indentation |
| "Missing required section" | Add the missing section in the correct order |
| "Section out of order" | Reorder sections to match required structure |
| "Related command not found" | Verify command file exists in `.opencode/command/` |
| "Related skill not found" | Verify skill directory exists in `.opencode/skills/` |
| "Description too long" | Shorten description to under 120 characters |
| "Invalid date format" | Use `YYYY-MM-DD` format for last_updated |

### Validation Workflow Safety

```markdown
## Safe Validation Workflow

1. **Before editing**: Validate current state (should be PASS)
2. **Make changes**: Edit skill content
3. **Update metadata**: Increment version, update date
4. **Validate again**: Ensure changes don't break structure
5. **Test loading**: Verify opencode can load the skill
6. **Commit**: Only commit if validation passes
```

### Safety Checks

- [ ] Always validate before committing skill changes
- [ ] Increment version on any content change
- [ ] Update last_updated date when modifying skills
- [ ] Test skill loading after structural changes
- [ ] Document new section requirements before enforcing
- [ ] Coordinate with team when adding new required sections

### Bulk Validation

To validate all skills at once:

```bash
# Validate all skills in the repository
for skill_dir in .opencode/skills/*/; do
    skill_file="${skill_dir}SKILL.md"
    if [ -f "$skill_file" ]; then
        echo "Validating: $skill_file"
        python3 scripts/validate_skill.py "$skill_file"
    fi
done
```

## Related Skills

- **chiseai-validation** - General validation patterns for ChiseAI workflows
- **chiseai-git-workflow** - Git workflow for skill PRs and updates
- **chiseai-worker-contracts** - Delegation patterns for skill creation tasks

## Related Commands

- `.opencode/command/chise-precommit-gates.md` - Includes skill validation in pre-commit
- `.opencode/command/chise-iterloop-start.md` - Start iteration for skill work
- `.opencode/command/chise-iterloop-close.md` - Close iteration after skill completion
