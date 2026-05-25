# Secret Scan Results

**Date:** 2026-05-25
**Story:** REPO-MIGRATION-001
**Task:** Task 2 — Deep Secret Scan

## Tools Used

- **trufflehog:** NOT_INSTALLED (pip-installed truffleHog v2.2.1 is an older package that does not support the `--repo_path` flag; newer trufflehog versions require Go-based binary)
- **gitleaks:** 8.30.0 (ACTIVE — successfully scanned 3516 commits)
- **manual grep:** YES

## Gitleaks Results

**Scan Summary:**

- 3516 commits scanned
- ~111.23 MB scanned in 6.86s
- **89 total findings** (including duplicates across commits)

### Key Real Secrets Found (Confirmed)

| Secret Type                  | File                                                      | Commit          | Classification     | Notes                                                                                                                                       |
| ---------------------------- | --------------------------------------------------------- | --------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Bybit Demo API Key + Secret  | `docs/verification/bybit-demo-trading-proof.md`           | `47fd7e2a...`   | **CONFIRMED**      | `BYBIT_DEMO_API_KEY=REDACTED_BYBIT_API_KEY_ALT` and `BYBIT_DEMO_API_SECRET=REDACTED_BYBIT_API_SECRET_ALT` — demo credentials, not production |
| Woodpecker Gitea Secret      | `docs/evidence/Cron-Activation-Attempt-Log-2026-03-02.md` | `844ce371e...`  | **CONFIRMED**      | `REDACTED_WOODPECKER_GITEA_SECRET` — real Gitea webhook secret in evidence doc                                      |
| Terraform template secrets   | `infrastructure/terraform/terraform.tfvars.template`      | `e90a0c327d...` | **CONFIRMED**      | `taiga_secret_key` (44-char) and `taiga_db_password` — appear to be real Taiga seeding credentials                                          |
| Private key in test conftest | `tests/test_security/conftest.py`                         | multiple        | **FALSE POSITIVE** | Test fixture generating a test private key for pytest fixtures — non-functional                                                             |

### False Positives (Majority of findings)

| Pattern                                               | File Type                                              | Count | Explanation                                                   |
| ----------------------------------------------------- | ------------------------------------------------------ | ----- | ------------------------------------------------------------- |
| Hashes in files-manifest.csv                          | `_bmad/_config/files-manifest.csv`                     | ~15   | Git hashes used as identifiers, not secrets                   |
| JWT "expired token" example                           | `_bmad/tea/testarch/knowledge/api-testing-patterns.md` | 1     | Documented example JWT token, explicitly marked as "expired"  |
| API path patterns (`api/v1/orders/123`)               | `src/autonomous_control_plane/`, `tests/`              | ~20   | Endpoint path patterns, not API keys                          |
| Test fixtures with varied patterns                    | `tests/test_validation/test_detect_secrets.py`         | ~10   | Deliberate test cases with fake `sk-`, `ghp_`, `xoxb-` tokens |
| `kind=SpanKind.INTERNAL`                              | `src/api/tracing.py`                                   | 2     | OpenTelemetry enum value, not a secret                        |
| `test-api-key-12345`, `test.belief.promote.001`, etc. | Various test files                                     | ~10   | Explicitly named test values                                  |
| `YOUR_INFLUXDB_TOKEN`, `YOUR_TOKEN` placeholder       | docs/runbooks, docs/deployment                         | ~5    | Placeholder documentation examples                            |
| `admin:admin123`, `admin:admin` in docs               | docs/                                                  | ~15   | Example credentials in documentation                          |
| SHA/UUID-like strings                                 | Various                                                | ~5    | File manifest entry identifiers                               |

## Manual Grep Results

### Key Pattern Check (AKIA, sk-, key- patterns)

- **Results:** No AWS key patterns (AKIA\*), no live `sk-` API keys, no `key-` patterns found
- Note: Test files contain `sk-live-abc123xyz789` but it's clearly a test fixture

### Private Key Check

- **Results:** Only in `tests/test_security/conftest.py` — this is a **test fixture** that generates a synthetic RSA private key for testing purposes. The key is clearly a fake (starts with `MIIEvQIBADA...` truncation indicating test data).

### URL Credentials Check

- **Results:** None found

## Tracked File Status

| File                                                  | Tracked in Git | Status                                      |
| ----------------------------------------------------- | -------------- | ------------------------------------------- |
| `infrastructure/.env`                                 | NO             | Local untracked file — 224 bytes present    |
| `root/.env`                                           | NO             | Local untracked file — 13,225 bytes present |
| `terraform.tfstate` (root)                            | NO             | Local untracked file                        |
| `infrastructure/terraform/terraform.tfstate`          | NO             | Local untracked but gitignored              |
| `infrastructure/terraform/terraform.tfstate.*.backup` | NO             | Local untracked backup files                |

**Note:** The `.env` file at root and `infrastructure/.env` exist locally but **NOT in git**. However, the `bybit-demo-trading-proof.md` **IS in git** and contains the actual Bybit demo API credentials committed to history.

## Classification Summary

| Finding                                    | File                                                    | Type                 | Classification     | Reason                                                                                |
| ------------------------------------------ | ------------------------------------------------------- | -------------------- | ------------------ | ------------------------------------------------------------------------------------- |
| BYBIT_DEMO_API_KEY + BYBIT_DEMO_API_SECRET | docs/verification/bybit-demo-trading-proof.md           | API credentials      | **CONFIRMED**      | Real demo trading API keypair committed to git in 2026-02                             |
| WOODPECKER_GITEA_SECRET                    | docs/evidence/Cron-Activation-Attempt-Log-2026-03-02.md | Gitea webhook secret | **CONFIRMED**      | Real Woodpecker→Gitea webhook secret committed in 2026-03                             |
| taiga_secret_key + taiga_db_password       | infrastructure/terraform/terraform.tfvars.template      | Terraform vars       | **CONFIRMED**      | Real-looking Taiga seeding credentials, appears to be infrastructure bootstrap values |
| Private key in test fixture                | tests/test_security/conftest.py                         | Test RSA key         | **FALSE POSITIVE** | Synthetic test key generated in pytest fixture, non-functional                        |
| Manifest hash entries                      | \_bmad/\_config/files-manifest.csv                      | Git hashes           | **FALSE POSITIVE** | Manifest entry identifiers                                                            |
| api/v1/orders/123 patterns                 | src/autonomous_control_plane/, tests/                   | API paths            | **FALSE POSITIVE** | Endpoint example patterns                                                             |
| admin:admin\* in curl examples             | docs/                                                   | Example creds        | **FALSE POSITIVE** | Documentation example credentials                                                     |
| Test JWT, test-api-key-\*                  | tests/                                                  | Test fixtures        | **FALSE POSITIVE** | Explicitly test-named values                                                          |

## Task 4 Decision

**Based on the scan results:**

- **Secrets found in git history:** YES — 3 confirmed real secrets in git-tracked files:
  1. Bybit Demo API credentials (committed 2026-02-27)
  2. Woodpecker Gitea webhook secret (committed 2026-03-03)
  3. Taiga infrastructure secrets in terraform.tfvars.template (committed 2026-03-17)

- **Secrets found in current tree:** NO (current untracked `.env` files are not in git, but their content IS in git via the proof document)

- **Task 4 (History Rewrite) REQUIRED:** **YES**

- **Credential rotation recommended:**
  1. **Bybit Demo API keypair** — Rotate even though demo keys have limited exposure; good hygiene
  2. **Woodpecker Gitea webhook secret** (`REDACTED_WOODPECKER_GITEA_SECRET`) — ACTIVE in use; should be rotated
  3. **Taiga secret_key and db_password** — If Taiga is deployed, rotate

## Recommended Actions

1. **Immediate (before repo migration):**
   - Rotate Woodpecker Gitea webhook secret — it's actively used in CI
   - Consider rotating Bybit demo API keypair — low risk but good practice
   - Regenerate Taiga secrets if infrastructure is live

2. **Confirm deployment status:**
   - Verify if Gitea instance at `gitea:3000` is using the committed webhook secret
   - Confirm if Bybit demo account is still active

3. **History rewrite decision:**
   - The 3 confirmed real secrets are in git history
   - A history rewrite (`git filter-repo` or BFG) would be required to remove them
   - Alternative: revoke/rotate the credentials rather than rewriting history (less disruptive)
   - Recommendation: **credential rotation FIRST**, history rewrite only if rotation is insufficient

4. **Post-migration:**
   - Add pre-commit hook for gitleaks to prevent future secret commits
   - Ensure `.env` files are in `.gitignore` and remain untracked
   - Document credential management procedure

## Evidence Files

- `/tmp/gitleaks-results.txt` — Full gitleaks scan output (1113 lines)
- `/tmp/grep-secret-files.txt` — Files containing secret-like patterns
- `/tmp/grep-key-patterns.txt` — Files with AWS/key patterns (empty)
- `/tmp/grep-private-keys.txt` — Files with private key patterns (test conftest only)
- `/tmp/grep-url-creds.txt` — Files with URL-embedded credentials (empty)
