---
name: system-self-audit
description: Evaluate repo health, workflow friction, recurring mistakes, and operational bottlenecks with a repeatable rubric
compatibility: opencode
metadata:
  audience: maintainers
  workflow: diagnostics
---
## What this skill does

This skill gives a repeatable framework for auditing an OpenCode-driven project.
It helps an agent identify:
- recurring implementation mistakes
- workflow slowdowns and wasted loops
- brittle configuration
- recurring infrastructure or provider friction
- weak feedback loops
- the highest ROI improvements

## When to use this skill

Use this skill when the user asks for:
- a self-audit
- workflow optimization
- infrastructure review
- repeated error analysis
- postmortems
- recommendations for reducing friction or repeated mistakes

## Audit rubric

### 1. Repo and config health
Check:
- `opencode.json`
- `.opencode/agents/`
- `.opencode/commands/`
- `.opencode/skills/`
- `.opencode/plugins/`
- CI scripts and local validation scripts
- Docker or service orchestration files if present

Look for:
- deprecated config patterns still in use
- unclear permission boundaries
- agents doing tasks that should be delegated
- hidden coupling between skills, plugins, agents, and MCPs
- brittle scripts or environment assumptions

### 2. Recent work quality
Inspect recent diffs and test signals.
Look for:
- repeated edits to the same files
- tests fixed after the fact instead of prevented earlier
- formatting and schema breakage
- churn without real progress
- changes that increase complexity without increasing reliability

### 3. Operational friction
Check for:
- repeated permission prompts
- repeated shell failures
- hangs from interactive commands
- repeated retries on the same failing step
- slow or unnecessary cold starts
- stale context or context bloat
- agent overlap or duplicated effort

### 4. Incident patterns
Look for repeated classes of failure:
- YAML/JSON formatting breakage
- config drift
- version mismatch
- provider instability
- stale worktrees or branch confusion
- weak test isolation
- lack of preflight checks
- hidden fallback behavior masking failures

### 5. Prevention strength
For each issue, ask:
- Can this be prevented automatically?
- Can it be detected earlier?
- Can the fix be encoded in a command, skill, plugin, formatter, test, or CI gate?
- Is the current setup relying too much on human memory?

## Output standard

Return findings in this order:
1. Executive summary
2. Top issues with evidence
3. Repeated patterns
4. Root causes
5. Quick wins under 30 minutes
6. Structural improvements
7. Next 3 tickets with acceptance criteria

## Good recommendation patterns

Prefer:
- exact config changes
- exact command or test additions
- precise plugin hooks to add
- measurable guardrails
- small fixes with strong prevention value

Avoid:
- generic advice without evidence
- telling the user to “be more careful”
- large rewrites when a narrow guardrail would solve it
