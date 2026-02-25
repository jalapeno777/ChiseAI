## Protocol: Story Lifecycle v2.0

> **Purpose**: Prevent orphaned branches, completion-state drift, and handoff failures through explicit lifecycle stages with clear ownership, validation, and recovery procedures.

---

### Phase 1: Story Start

**Owner**: Jarvis (Orchestrator)

**Steps**:
1. **Validate story readiness**
   ```bash
   # Check story exists in workflow status
   python3 scripts/validate_status_sync.py --verbose
   ```

2. **Create feature branch**
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/<STORY-ID>-<slug>
   git push -u origin feature/<STORY-ID>-<slug>
   ```

3. **Initialize isolated worktree session**
   ```bash
   python3 scripts/swarm/session.py start \
     --story-id=<STORY-ID> \
     --agent=<worker-agent> \
     --branch=feature/<STORY-ID>-<slug> \
     --worktree-root=.swarm-worktrees \
     --scopes="src/path/" "tests/path/"
   ```

4. **Start iteration log**
   ```bash
   # Redis iterlog initialization
   redis_state_hset(name="bmad:chiseai:iterlog:story:<STORY-ID>", key="story_title", value="<title>")
   redis_state_hset(name="bmad:chiseai:iterlog:story:<STORY-ID>", key="phase", value="implementation")
   redis_state_hset(name="bmad:chiseai:iterlog:story:<STORY-ID>", key="status", value="in_progress")
   redis_state_hset(name="bmad:chiseai:iterlog:story:<STORY-ID>", key="started_at", value="<ISO8601>")
   redis_state_expire(name="bmad:chiseai:iterlog:story:<STORY-ID>", expire_seconds=432000)
   ```

5. **Query prior context (Qdrant)**
   ```python
   qdrant_qdrant-find(query="<relevant keywords for story>")
   ```

6. **Delegate to worker with complete contract**
   - Include SCOPE_GLOBS, FORBIDDEN_GLOBS, BRANCH, WORKTREE_PATH
   - Include MEMORY_CONTEXT from Qdrant findings
   - Include EXIT_CONDITIONS and INCIDENT_TEMPLATE

**Validation**:
- `git branch --show-current` returns `feature/<STORY-ID>-<slug>`
- Session file exists at `.swarm-worktrees/<STORY-ID>-<agent>/.swarm-session.json`
- Redis lease exists: `bmad:chiseai:branch-lease:feature/<STORY-ID>-<slug>`
- Worker acknowledges contract receipt

**Failure Recovery**:
| Failure | Recovery Action |
|---------|-----------------|
| Branch exists | Use `--force` flag or append timestamp to slug |
| Session exists | Run `session.py close --remove-worktree` first, or use `--force` |
| Redis unavailable | Continue with file-based iterlog fallback; mark for manual import |
| Scope conflict | STOP - another story owns scope; re-scope or wait |

---

### Phase 2: Worker Execution

**Owner**: Worker (dev/senior-dev/quickdev)

**Steps**:
1. **Verify session before any git action**
   ```bash
   python3 scripts/swarm/session.py verify \
     --story-id=<STORY-ID> \
     --branch=feature/<STORY-ID>-<slug> \
     --worktree-path=/path/to/worktree \
     --check-canonical
   ```

2. **Check scope ownership**
   ```bash
   # Verify no conflicts
   python3 scripts/swarm/session.py verify --story-id=<STORY-ID> --check-canonical
   # Or check Redis directly
   redis_state_hget(name="bmad:chiseai:ownership", key="<scope>")
   ```

3. **Execute implementation**
   - Follow SCOPE_GLOBS constraints
   - Log decisions to Redis iterlog
   - Never edit FORBIDDEN_GLOBS paths

4. **Log significant decisions**
   ```python
   redis_state_rpush(
     name="bmad:chiseai:iterlog:story:<STORY-ID>:decisions",
     value=json.dumps({
       "decision": "<decision text>",
       "rationale": "<why>",
       "timestamp": "<ISO8601>"
     })
   )
   ```

5. **Commit with proper format**
   ```bash
   git add <scoped-files>
   git commit -m "<type>(<scope>): <description> (<STORY-ID>)"
   ```

6. **Push regularly**
   ```bash
   git push origin feature/<STORY-ID>-<slug>
   ```

**Validation**:
- Session verification passes before each commit
- All changes within SCOPE_GLOBS
- No modifications to FORBIDDEN_GLOBS
- Commits follow `<type>(<scope>): description (<STORY-ID>)` format

**Failure Recovery**:
| Failure | Recovery Action |
|---------|-----------------|
| Session verification fails | STOP - report to Jarvis; do not proceed |
| Need to edit outside scope | STOP - report to Jarvis for re-scoping |
| Merge conflict with main | Rebase: `git fetch origin && git rebase origin/main` |
| 3+ failed attempts on same issue | STOP - escalate to Jarvis |
| Redis unavailable | Use file fallback in `docs/tempmemories/iterlog-<STORY-ID>.md` |

---

### Phase 3: Worker Done & Handoff

**Owner**: Worker → Jarvis

**Steps**:
1. **Run local pre-commit gates**
   ```bash
   # Repo sanity
   git status -sb
   git branch --show-current
   
   # Local CI checks
   python3 scripts/local-ci-checks.sh  # or equivalent
   
   # Status sync validation
   python3 scripts/validate_status_sync.py
   
   # Iterloop compliance
   python3 scripts/validate_iterloop_compliance.py --story-id=<STORY-ID>
   ```

2. **Update workflow status**
   ```bash
   # Edit docs/bmm-workflow-status.yaml
   # Set story status to "completed"
   # Validate changes
   python3 scripts/validate_status_sync.py
   ```

3. **Final commit and push**
   ```bash
   git add docs/bmm-workflow-status.yaml
   git commit -m "chore(status): mark <STORY-ID> as completed (<STORY-ID>)"
   git push origin feature/<STORY-ID>-<slug>
   ```

4. **Close worktree session (with merge enforcement)**
   ```bash
   python3 scripts/swarm/session.py close \
     --worktree-path=/path/to/worktree \
     --enforce-merged \
     --allow-unmerged  # If PR not yet created
   ```

5. **Report handoff to Jarvis**
   ```markdown
   ## WORKER HANDOFF
   
   Story ID: <STORY-ID>
   Branch: feature/<STORY-ID>-<slug>
   Head SHA: <commit-sha>
   
   Files Changed:
   | File | Change Type | Lines |
   |------|-------------|-------|
   | <path> | <added/modified/deleted> | +N/-M |
   
   Validation Results:
   - Local CI: PASS/FAIL (details)
   - Status Sync: PASS/FAIL
   - Iterloop Compliance: PASS/FAIL
   
   Blockers: <None or list>
   
   Ready for: PR creation and merge
   ```

**Validation**:
- All pre-commit gates pass
- Working tree clean (or explicitly documented dirty state)
- Status sync validates without errors
- Session closed successfully
- Handoff document complete with all required fields

**Failure Recovery**:
| Failure | Recovery Action |
|---------|-----------------|
| Pre-commit gates fail | Fix issues, re-run gates, re-push |
| Status sync fails | Fix YAML, validate again |
| Session close fails (unmerged) | Use `--allow-unmerged` if PR pending |
| CI fails | Diagnose with `chise-ci-root-cause.md` |

---

### Phase 4: Verify & Merge

**Owner**: Merlin (Merge Authority)

**Steps**:
1. **Receive handoff from Jarvis**
   - Jarvis delegates PR sweep to Merlin
   - Include list of stories ready for merge

2. **Run PR sweep**
   ```bash
   python3 scripts/ops/merlin_pr_sweep.py --wait
   ```

3. **For each story branch, create PR**
   ```bash
   # PR title must contain story ID token
   gh pr create \
     --title "feat(scope): description (<STORY-ID>)" \
     --body "## Summary\n- Change 1\n- Change 2\n\nCloses <STORY-ID>"
   ```

4. **Register PR for lifecycle monitoring**
   ```bash
   python3 scripts/pr_lifecycle/integration.py register \
     --pr-number=<PR-NUMBER> \
     --story-id=<STORY-ID> \
     --branch=feature/<STORY-ID>-<slug> \
     --head-sha=<SHA> \
     --agent=merlin
   ```

5. **Monitor CI and handle failures**
   ```bash
   # Check PR status
   python3 scripts/pr_lifecycle/integration.py summary --pr-number=<PR-NUMBER>
   
   # If CI fails, diagnose
   python3 scripts/pr_lifecycle/recovery_handlers.py ci-failure \
     --pr-number=<PR-NUMBER> \
     --diagnosis='{"tool": "<tool>", "kind": "<kind>"}'
   ```

6. **Merge on green CI**
   ```bash
   # Verify authority and acquire lock
   python3 scripts/swarm/session.py verify \
     --story-id=<STORY-ID> \
     --branch=feature/<STORY-ID>-<slug> \
     --require-main-merge-authority \
     --acquire-main-merge-lock
   
   # Merge PR
   gh pr merge <PR-NUMBER> --squash --delete-branch
   ```

7. **Update story status to "merged"**
   ```bash
   # Edit docs/bmm-workflow-status.yaml
   # Set story status to "completed" (or add "merged" status)
   ```

**Validation**:
- PR created with story ID in title
- PR registered in lifecycle system
- CI passes (green)
- Merge lock acquired successfully
- Branch deleted after merge
- Story status updated

**Failure Recovery**:
| Failure | Recovery Action |
|---------|-----------------|
| CI fails | Diagnose with `chise-ci-root-cause.md`, apply fix, re-push |
| Merge conflict | Rebase branch on main, force-push, re-run CI |
| Merge lock conflict | Wait for other merge to complete, retry |
| Systemic failures | Use consolidation mode in `merlin_pr_sweep.py` |

---

### Phase 5: Cleanup

**Owner**: Merlin

**Steps**:
1. **Verify branch deletion**
   ```bash
   # Check local branches
   git branch | grep feature/<STORY-ID>
   # Should return nothing
   
   # Check remote branches
   git ls-remote --heads origin | grep feature/<STORY-ID>
   # Should return nothing
   ```

2. **Clean up worktree**
   ```bash
   # If not already removed
   python3 scripts/swarm/session.py close \
     --worktree-path=/path/to/worktree \
     --remove-worktree
   ```

3. **Release Redis leases**
   ```bash
   # Automatic on session close, but verify
   redis_state_delete(key="bmad:chiseai:branch-lease:feature/<STORY-ID>-<slug>")
   redis_state_delete(key="bmad:chiseai:worktree-lease:<path-slug>")
   ```

4. **Release scope ownership**
   ```bash
   redis_state_hdel(name="bmad:chiseai:ownership", key="<scope>")
   ```

5. **Run branch hygiene check**
   ```bash
   python3 scripts/swarm/branch_hygiene_check.py
   ```

**Validation**:
- No local branch exists for story
- No remote branch exists for story
- Worktree directory removed
- Redis leases cleaned up
- Scope ownership released

**Failure Recovery**:
| Failure | Recovery Action |
|---------|-----------------|
| Branch still exists | Force delete: `git branch -D feature/<STORY-ID>-<slug>` |
| Worktree in use | Close any processes using it, then remove |
| Redis lease persists | Manual delete or wait for TTL expiry |

---

### Phase 6: Memory Sync

**Owner**: Jarvis

**Steps**:
1. **Close iteration log**
   ```python
   redis_state_hset(
     name="bmad:chiseai:iterlog:story:<STORY-ID>",
     key="status",
     value="completed"
   )
   redis_state_hset(
     name="bmad:chiseai:iterlog:story:<STORY-ID>",
     key="completed_at",
     value="<ISO8601>"
   )
   redis_state_hset(
     name="bmad:chiseai:iterlog:story:<STORY-ID>",
     key="merged_at",
     value="<ISO8601>"
   )
   ```

2. **Promote learnings to Qdrant**
   ```python
   qdrant_qdrant-store(
     information="""
     ---
     project: ChiseAI
     scope: <area>
     type: decision|pattern|anti-pattern
     story_id: <STORY-ID>
     tags: [tag1, tag2]
     ---
     
     # <Title>
     
     ## Decision/Pattern
     <description>
     
     ## Context
     <why this was chosen>
     
     ## Trade-offs
     <pros/cons>
     """,
     metadata={
       "project": "ChiseAI",
       "scope": "<area>",
       "type": "decision",
       "story_id": "<STORY-ID>"
     }
   )
   ```

3. **Update validation registry**
   ```bash
   # Edit docs/validation/validation-registry.yaml
   # Add validation entry for story
   # Validate
   python3 scripts/validate_status_sync.py --full
   ```

4. **Archive iterlog (optional)**
   ```bash
   # Export Redis iterlog to file for long-term storage
   # (TTL will expire after 5 days)
   ```

**Validation**:
- Redis iterlog shows status="completed"
- Qdrant contains new knowledge entry
- Validation registry updated
- Status sync passes

**Failure Recovery**:
| Failure | Recovery Action |
|---------|-----------------|
| Qdrant unavailable | Write to `docs/tempmemories/` with `needs_manual_import: true` |
| Validation sync fails | Fix registry YAML, re-validate |
| Redis unavailable | Use file fallback, mark for manual import |

---

### State Reconciliation Loop

**Owner**: Automated (cron/scheduler - Woodpecker CI)

**Frequency**: Every 5 minutes (configurable via `CHISE_PR_HEALTH_SCAN_INTERVAL_SEC`)

**Steps**:
1. **Scan for orphaned branches**
   ```bash
   python3 scripts/swarm/branch_hygiene_check.py
   ```

2. **Check PR lifecycle health**
   ```bash
   python3 scripts/pr_lifecycle/health_monitor.py scan
   ```

3. **Detect stuck PRs**
   ```bash
   python3 scripts/pr_lifecycle/health_monitor.py check
   ```

4. **Trigger recovery for stuck PRs**
   ```bash
   python3 scripts/pr_lifecycle/health_monitor.py recovery --dry-run
   # If dry-run shows actionable items:
   python3 scripts/pr_lifecycle/health_monitor.py recovery
   ```

5. **Validate status sync drift**
   ```bash
   python3 scripts/validate_status_sync.py --full
   ```

6. **Check iterloop compliance gaps**
   ```bash
   python3 scripts/validate_iterloop_compliance.py
   ```

7. **Report findings to Jarvis**
   - Log to Redis: `bmad:chiseai:reconciliation:<timestamp>`
   - Include: orphaned branches, stuck PRs, status drift, missing iterlogs

**Validation**:
- No orphaned branches (merged PRs with existing branches)
- No PRs stuck >30 minutes without action
- Status sync passes without errors
- All stories have iterlog entries

**Failure Recovery**:
| Failure | Recovery Action |
|---------|-----------------|
| Orphaned branches found | Auto-delete if merged, escalate if unmerged |
| Stuck PRs detected | Trigger recovery handlers, escalate if max retries reached |
| Status drift detected | Alert Jarvis for manual reconciliation |
| Missing iterlogs | Create from available data, flag for review |

---

## Failure Mode Prevention Matrix

| Failure Mode | Prevention Mechanism | Detection | Recovery |
|--------------|---------------------|-----------|----------|
| **Orphaned branches** | Session `--enforce-merged` flag | Branch hygiene check | Auto-delete merged branches |
| **Completion-state drift** | Status sync validation | `validate_status_sync.py` | Manual reconciliation by Jarvis |
| **Worktree not cleaned** | `--remove-worktree` flag in close | Session verification | Manual cleanup command |
| **Redis iterlog not closed** | Iteration close command | Iterloop compliance check | File fallback + manual import |
| **PR not tracked** | PR lifecycle registration | Health monitor scan | Auto-registration from branch map |
| **Merge without authority** | `--require-main-merge-authority` lock | Session verification | Block merge, escalate to Merlin |
| **Scope conflict** | Redis ownership hash | Pre-edit ownership check | STOP and report to Jarvis |

---

## Command Quick Reference

| Phase | Command | Purpose |
|-------|---------|---------|
| Start | `session.py start` | Create isolated worktree |
| Start | `iterloop-start` | Initialize Redis iterlog |
| Execution | `session.py verify` | Validate session before edits |
| Execution | `qdrant-find` | Query prior context |
| Handoff | `precommit-gates` | Run all validation gates |
| Handoff | `session.py close --enforce-merged` | Close with merge check |
| Merge | `merlin_pr_sweep.py` | Batch PR processing |
| Merge | `pr_lifecycle/integration.py register` | Track PR state |
| Merge | `session.py verify --require-main-merge-authority` | Acquire merge lock |
| Cleanup | `branch_hygiene_check.py` | Find orphaned branches |
| Cleanup | `session.py close --remove-worktree` | Remove worktree |
| Memory | `iterloop-close` | Close iterlog, promote learnings |
| Memory | `qdrant-store` | Store long-term knowledge |
| Reconciliation | `health_monitor.py scan` | Detect stuck PRs |
| Reconciliation | `validate_status_sync.py --full` | Check status drift |

---

## Implementation Checklist

- [ ] Phase 1: Story Start - All steps automated
- [ ] Phase 2: Worker Execution - Session verification enforced
- [ ] Phase 3: Handoff - Pre-commit gates mandatory
- [ ] Phase 4: Merge - Authority lock enforced
- [ ] Phase 5: Cleanup - Automatic branch/worktree removal
- [ ] Phase 6: Memory - Qdrant promotion automated
- [ ] Reconciliation Loop - Scheduled in Woodpecker CI
