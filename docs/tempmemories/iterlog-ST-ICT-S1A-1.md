# Incident Log: ST-ICT-S1A-1

## Incidents

INCIDENT:
id: INC-2026-0406-ICT-S1A-1
story_id: ST-ICT-S1A-1
severity: P0
detected: 2026-04-06T00:00:00Z
resolved: null

symptom: |
Post-branch reconcile step #3 claimed commit c5e19b1efeb2c09381ff87baca480ed6dda5f245 "IS on main"
but `git branch --contains c5e19b1` against origin/main returns empty.
git log origin/main -5 shows tip is 275c2f752a721347a4cf059facfbd0f227cf0b18 which does NOT contain c5e19b1.

root_cause: |
git branch --contains c5e19b1 was run against LOCAL main (which may have been ahead of origin/main
due to local worktree state), not against origin/main. The guardrail explicitly requires
git branch --contains <commit> using origin/main reference. Local main can diverge from origin/main
in worktree context.

missed_signal: |
Post-branch reconcile step #3 ("Confirm merged commit is on main") used git branch --contains <sha>
against local branch context, not against origin/main — violating AGENTS.md CROSS-BRANCH
VERIFICATION GUARDRAIL which explicitly requires git branch --contains using origin/main reference.

impact: - "False positive merge claim recorded for ST-ICT-S1A-1" - "Loss of confidence in post-branch reconcile verification" - "Potential for subsequent work to proceed from incorrect assumption about merge state"

evidence:
claimed_sha: c5e19b1efeb2c09381ff87baca480ed6dda5f245
origin_main_tip: 275c2f752a721347a4cf059facfbd0f227cf0b18
git_branch_contains_origin_main: "empty (commit not contained)"
guardrail_violated: "git branch --contains <commit> without origin/ prefix"

resolution: |
Incident logged. Worktree state audit required before any dependent work proceeds.

prevention_rule: |
Always use git branch --contains origin/<branch> when verifying merge containment,
especially when running from a worktree. Local main can diverge from origin/main.

follow_up_tasks: - "Update post-branch reconcile script to always prefix with origin/" - "Add explicit 'origin/main' check to chise-post-branch-reconcile command" - "Audit all reconcile scripts for similar local-vs-remote branch comparison issues"

lessons_learned: - "Local branch state is NOT authoritative for cross-branch verification" - "Origin tracking branches are required for accurate merge containment checks" - "Worktree isolation protects git operations but introduces local state divergence risk"
