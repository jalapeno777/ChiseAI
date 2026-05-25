# Repo Migration + Secrets Sanitization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the ChiseAI repository for GitHub migration by sanitizing secrets, cleaning up temp/debug files, and verifying no regressions.

**Architecture:** 8-task sequential plan with hard gates between tasks. Tasks 1-3 are read-only or additive (no destructive changes). Task 4 is conditional on Task 2 findings. Tasks 5-6 are cleanup+verification. Tasks 7-8 are migration prep and sign-off.

**Tech Stack:** git, trufflehog, gitleaks, bash, pytest, ruff, black, mypy, bandit

---

## Task 1: Baseline Inventory (Read-Only) — 1SP

- [ ] Step 1: Record current branch list (`git branch -a`)
- [ ] Step 2: Record current tag list (`git tag -l`)
- [ ] Step 3: Record file count (`git ls-files | wc -l`)
- [ ] Step 4: Record last 10 commits on main (`git log --oneline -10`)
- [ ] Step 5: Check if `infrastructure/.env` is tracked (`git ls-files infrastructure/.env`)
- [ ] Step 6: Check if `terraform.tfstate` is tracked (`git ls-files terraform.tfstate`)
- [ ] Step 7: Record CI config state (`cat .woodpecker/ci.yaml | head -50`)
- [ ] Step 8: Save baseline to `docs/evidence/migration-baseline-$(date +%Y%m%d).md`
- [ ] Step 9: Commit the baseline document

**Verification:** Baseline file exists with all 7 data points. Committed to branch.

---

## Task 2: Deep Secret Scan — 1SP

- [ ] Step 1: Install trufflehog if not present (`pip install trufflehog` or download binary)
- [ ] Step 2: Install gitleaks if not present
- [ ] Step 3: Run trufflehog on full git history: `trufflehog git file://. --no-update --json 2>&1 | tee /tmp/trufflehog-results.json`
- [ ] Step 4: Run gitleaks on full git history: `gitleaks detect --source . --verbose 2>&1 | tee /tmp/gitleaks-results.txt`
- [ ] Step 5: Manual grep for common secret patterns in tracked files:
  ```bash
  git ls-files | xargs grep -l -E '(api_key|secret|token|password|credential).*=.*[A-Za-z0-9_\-]{20,}' 2>/dev/null | grep -v '.env.example' | grep -v '.gitignore' | tee /tmp/grep-secret-files.txt
  ```
- [ ] Step 6: Classify findings: confirmed secret / probable / false-positive
- [ ] Step 7: Write findings report to `docs/evidence/secret-scan-results-$(date +%Y%m%d).md`
- [ ] Step 8: IF secrets found in git history, flag Task 4 as REQUIRED and return findings to orchestrator
- [ ] Step 9: Commit the findings report

**Verification:** Scan report exists with classified findings. No real secrets in current tree.

---

## Task 3: Current-Tree Sanitization (Additive Only) — 2SP

- [ ] Step 1: Create `.gitleaks.toml` at repo root with allowlist for known false positives and path-based rules
- [ ] Step 2: Verify `.gitignore` covers all secret-bearing patterns — add any missing entries
- [ ] Step 3: Create `scripts/ci/secret_scan.sh` — a CI gate script that runs gitleaks and fails on new secrets
- [ ] Step 4: Make secret_scan.sh executable (`chmod +x`)
- [ ] Step 5: Add gitleaks pre-commit hook to `.pre-commit-config.yaml` (create if needed)
- [ ] Step 6: Run `pre-commit run --all-files` to verify hooks work
- [ ] Step 7: Run the new secret_scan.sh to verify it works
- [ ] Step 8: Commit all changes

**Verification:** gitleaks config exists, pre-commit hook active, CI script passes.

---

## Task 4: History Rewrite (CONDITIONAL) — BLOCKED

**STOP. Do NOT execute this task without explicit Craig approval via Aria.**

This task is ONLY needed if Task 2 finds secrets in git history.

If activated, the approach would be:

- [ ] Step 1: Rotate all compromised credentials
- [ ] Step 2: Install git-filter-repo
- [ ] Step 3: Create backup of .git directory
- [ ] Step 4: Run git-filter-repo to remove secrets
- [ ] Step 5: Force-push cleaned history
- [ ] Step 6: Verify no secrets remain in any commit

**Required before execution:**

1. Craig approval (via Aria)
2. Credential rotation plan confirmed
3. Backup verified
4. All team members notified of force-push

---

## Task 5: Repo Cleanup — 2-3SP

- [ ] Step 1: Delete all backup branches: `git branch | grep 'backup/' | xargs -I {} git branch -D {}`
  - Craig confirmed: ALL backup/\* branches can be deleted with NO preservation needed
- [ ] Step 2: Remove temp/debug root files:
  - fix_placement.py, fix_placement2.py, fix_placement3.py
  - stress_test_e2e.py, proof_loop_attempt5.py, run_forensic_proof_loop.py
  - fixes.patch, benchmark_pipeline.py, dedup_workflow.py, demo_brain_cicd.py
  - EOF, ENDOFFILE, 1, 61, .env.swp
  - coverage.json, coverage.xml, htmlcov/, .coverage
- [ ] Step 3: Archive root report files to `docs/archive/`:
  - IMPLEMENTATION*REPORT*_, PROOF*LOOP*_, verification-report-\*, etc.
- [ ] Step 4: Evaluate .serena/ directory — if committed to git, remove from tracking
- [ ] Step 5: Run `git status` to confirm clean state
- [ ] Step 6: Commit cleanup with message "chore: repo cleanup — remove temp files, archive reports, delete backup branches"

**Verification:** No temp/debug files at root. No backup/\* branches. Reports archived.

---

## Task 6: Verification Suite — 2SP

- [ ] Step 1: Run test suite: `pytest tests/ -v --tb=short 2>&1 | tee /tmp/test-results.txt`
- [ ] Step 2: Run linters: `ruff check src/ tests/ && black --check src/ tests/ && mypy src/`
- [ ] Step 3: Re-run secret scan: `bash scripts/ci/secret_scan.sh`
- [ ] Step 4: Clean clone test:
  ```bash
  cd /tmp && rm -rf chiseai-clone-test
  git clone /home/tacopants/projects/ChiseAI chiseai-clone-test
  cd chiseai-clone-test
  git ls-files | xargs grep -l -E '(api_key|secret|token|password).*=.*[A-Za-z0-9_\-]{20,}' 2>/dev/null | grep -v '.env.example' | grep -v '.gitignore'
  echo "Clean clone exit code: $?"
  ```
- [ ] Step 5: Write verification report to `docs/evidence/migration-verification-$(date +%Y%m%d).md`
- [ ] Step 6: Commit verification report

**Verification:** All tests pass, linters clean, secret scan clean, clean clone test passes.

---

## Task 7: GitHub Migration Plan — 1SP

- [ ] Step 1: Write migration cutover checklist to `docs/operations/github-migration-checklist.md`
  - Pre-migration checklist (credentials, access, backups)
  - Migration steps (mirror, configure, verify)
  - Post-migration verification
  - Rollback plan
- [ ] Step 2: Document rollback plan with specific commands
- [ ] Step 3: Commit

**Verification:** Checklist file exists with all sections. Rollback plan is actionable.

---

## Task 8: Final Release Gate — 1SP

- [ ] Step 1: Write sign-off report to `docs/evidence/migration-signoff-$(date +%Y%m%d).md` aggregating:
  - Baseline inventory summary
  - Secret scan results summary
  - Cleanup actions taken
  - Verification suite results
  - Outstanding risks/known issues
  - Approval status
- [ ] Step 2: Commit

**Verification:** Sign-off report exists with all evidence sections. No unresolved high/critical issues.

---

## Acceptance Criteria

- AC1: No real secrets in any tracked file in the current tree
- AC2: Secret scanning tooling is integrated (gitleaks config + pre-commit + CI script)
- AC3: All temp/debug files removed from repo root
- AC4: All backup/\* branches deleted
- AC5: Test suite passes post-cleanup
- AC6: Clean clone test shows no secrets
- AC7: GitHub migration checklist written with rollback plan
- AC8: All evidence documents committed

## Risk Register

| Risk                             | Likelihood | Impact   | Mitigation                                         |
| -------------------------------- | ---------- | -------- | -------------------------------------------------- |
| Secrets in git history           | Medium     | Critical | Task 2 deep scan + Task 4 conditional rewrite      |
| Secret scan false positives      | High       | Low      | Manual classification in Task 2                    |
| Test failures after cleanup      | Low        | Medium   | Task 6 verification suite                          |
| Credential rotation incomplete   | Low        | Critical | Task 4 blocked until rotation confirmed            |
| Git history rewrite breaks forks | Low        | High     | Coordinate with all contributors before force-push |
