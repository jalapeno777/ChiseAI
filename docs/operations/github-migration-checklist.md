# GitHub Migration Cutover Checklist

**Story:** REPO-MIGRATION-001
**Date:** 2025-05-25
**Source:** Gitea (localhost:3000) — craig/ChiseAI
**Target:** GitHub — [org/repo TBD by Craig]

## Pre-Migration Prerequisites

- [ ] All credentials rotated that were found in git history:
  - [ ] BYBIT_DEMO_API_KEY/SECRET (found in docs/verification/bybit-demo-trading-proof.md)
  - [ ] WOODPECKER_GITEA_SECRET (found in docs/evidence/Cron-Activation-Attempt-Log-2026-03-02.md)
  - [ ] taiga_secret_key/taiga_db_password (found in infrastructure/terraform/terraform.tfvars.template)
  - [ ] InfluxDB token (found in \_bmad-output/evidence/influx_query_with_token.txt)
- [ ] Task 4 decision made (history rewrite vs. credential-only rotation)
- [ ] GitHub organization/repository created
- [ ] GitHub team/members configured
- [ ] Branch protection rules defined for target repo
- [ ] GitHub Actions CI configured (replacing Woodpecker)

## Migration Steps

### Phase 1: Final Validation

- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Run linters: `ruff check src/ tests/` + `black --check src/ tests/`
- [ ] Run secret scan: `bash scripts/ci/secret_scan.sh`
- [ ] Verify all temp files absent from repo root
- [ ] Verify .gitleaks.toml and secret_scan.sh are present

### Phase 2: Repository Transfer

- [ ] Create final tag on Gitea: `git tag pre-github-migration-$(date +%Y%m%d)`
- [ ] Push tag to Gitea
- [ ] Add GitHub as remote: `git remote add github git@github.com:[org]/[repo].git`
- [ ] Push all branches to GitHub: `git push github --all`
- [ ] Push all tags to GitHub: `git push github --tags`
- [ ] Verify file count matches: `git ls-files | wc -l` should be ~5996

### Phase 3: CI/CD Migration

- [ ] Create GitHub Actions workflows (equivalent of .woodpecker/ci.yaml)
- [ ] Configure GitHub secrets (matching Gitea/Woodpecker secrets)
- [ ] Test CI pipeline on a feature branch
- [ ] Verify pre-commit hooks work with GitHub Actions

### Phase 4: Validation on GitHub

- [ ] Clone from GitHub: `git clone git@github.com:[org]/[repo].git /tmp/github-clone-test`
- [ ] Run test suite on GitHub clone
- [ ] Verify no secrets: `gitleaks detect --source . --no-git`
- [ ] Verify clean clone has no temp files
- [ ] Check CI runs green on GitHub

### Phase 5: DNS/Access Cutover

- [ ] Update any CI/CD references from Gitea to GitHub
- [ ] Update documentation references
- [ ] Notify team of migration completion
- [ ] Update MCP/agent configurations if needed

### Phase 6: Gitea Decommission (After Cool-Down Period)

- [ ] Set Gitea repo to read-only (7-day cool-down)
- [ ] Archive Gitea repo after cool-down
- [ ] Remove Gitea credentials from CI systems
- [ ] Update monitoring/alerting

## Rollback Plan

If migration fails or critical issues found:

1. **Immediate rollback (< 1 hour)**:
   - GitHub repo becomes read-only
   - All development continues on Gitea
   - No data loss (Gitea is still authoritative)

2. **Partial rollback (< 24 hours)**:
   - Fix specific issues on GitHub
   - Keep Gitea active as backup
   - Cherry-pick any fixes from Gitea to GitHub

3. **Full rollback**:
   - Delete GitHub repo
   - Resume all operations on Gitea
   - Re-plan migration with fixes

## Decision Log

| Decision                                | Choice            | Rationale              | Date       |
| --------------------------------------- | ----------------- | ---------------------- | ---------- |
| History rewrite vs. credential rotation | TBD               | Pending Craig decision | 2025-05-25 |
| CI platform                             | GitHub Actions    | Replacing Woodpecker   | 2025-05-25 |
| Migration strategy                      | Mirror + validate | Preserve full history  | 2025-05-25 |

## Risks

| Risk                           | Probability | Impact   | Mitigation                                            |
| ------------------------------ | ----------- | -------- | ----------------------------------------------------- |
| Credential rotation incomplete | Medium      | Critical | Complete all rotations before Phase 2                 |
| CI migration breaks builds     | Medium      | High     | Test on feature branch first                          |
| Git history contains secrets   | Confirmed   | High     | Rotate credentials; history rewrite if Craig approves |
| Team access issues             | Low         | Medium   | Pre-configure GitHub teams before migration           |
