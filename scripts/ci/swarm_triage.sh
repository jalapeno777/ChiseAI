#!/usr/bin/env bash
# Replay Woodpecker CI wrapper logic locally and emit a deterministic triage summary.
#
# Usage:
#   bash scripts/ci/swarm_triage.sh
#
# Optional env vars:
#   SWARM_TRIAGE_INSTALL_DEPS=1|0   (default: auto)
#   SWARM_TRIAGE_PYTHON=<path>      (default: auto-detect .venv-debug/.venv/python3)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

CI_DIR="_bmad-output/ci"
if [ -n "${SWARM_TRIAGE_PYTHON:-}" ]; then
  PYTHON_BIN="${SWARM_TRIAGE_PYTHON}"
elif [ -x ".venv-debug/bin/python" ]; then
  PYTHON_BIN=".venv-debug/bin/python"
elif [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

if [ -n "${SWARM_TRIAGE_INSTALL_DEPS:-}" ]; then
  INSTALL_DEPS="${SWARM_TRIAGE_INSTALL_DEPS}"
elif [[ "${PYTHON_BIN}" == .venv* ]] || [[ "${PYTHON_BIN}" == */.venv* ]] || [ -n "${VIRTUAL_ENV:-}" ]; then
  INSTALL_DEPS="1"
else
  INSTALL_DEPS="0"
fi

if [ -x ".venv-debug/bin/activate" ]; then
  ACTIVATE_CMD="source .venv-debug/bin/activate"
elif [ -x ".venv/bin/activate" ]; then
  ACTIVATE_CMD="source .venv/bin/activate"
else
  ACTIVATE_CMD=""
fi

mkdir -p "${CI_DIR}"

run_captured_step() {
  local step_name="$1"
  local step_log="$2"
  local step_status="$3"
  local step_cmd="$4"

  echo "=== [${step_name}] START ==="
  set +e
  if [ -n "${ACTIVATE_CMD}" ]; then
    bash -lc "${ACTIVATE_CMD} && ${step_cmd}" > "${step_log}" 2>&1
  else
    bash -lc "${step_cmd}" > "${step_log}" 2>&1
  fi
  local code=$?
  set -e

  echo "${code}" > "${step_status}"
  cat "${step_log}"
  echo "=== [${step_name}] END (exit=${code}) ==="
}

lint_cmd='
set -euo pipefail
if [ "'"${INSTALL_DEPS}"'" = "1" ]; then
  "'"${PYTHON_BIN}"'" -m pip install --no-cache-dir black ruff mypy pytest pytest-cov pyyaml types-PyYAML types-requests
fi
black --check . --extend-exclude "src/operations/backtest_runner.py|tests/test_backtest_runner.py|tests/grafana/test_dashboards.py" || echo "WARN: black violations (non-blocking)"
ruff check . || echo "WARN: ruff violations (non-blocking)"
mypy src scripts || echo "WARN: mypy violations (non-blocking)"
python3 scripts/validate_status_sync.py
python3 scripts/validate_iterloop_compliance.py
CHANGED_ITERLOGS="$(git diff --name-only origin/main...HEAD 2>/dev/null | grep -E "^docs/tempmemories/iterlog-.*\\.md$" || true)"
if [ -n "$(printf "%s" "${CHANGED_ITERLOGS}" | tr -d "[:space:]")" ]; then
  printf "%s\n" "${CHANGED_ITERLOGS}" | while IFS= read -r iterlog_path; do
    [ -z "$iterlog_path" ] && continue
    story_id="$(basename "$iterlog_path" .md | sed "s/^iterlog-//")"
    python3 scripts/validation/validate_insight_governance.py --story-id "${story_id}" --strict
    python3 scripts/validation/validate_metacog_compliance.py --story-id "${story_id}" --strict
  done
else
  python3 scripts/validation/validate_insight_governance.py --require-for-completed-only || true
  python3 scripts/validation/validate_metacog_compliance.py --require-for-completed-only || true
fi
python3 scripts/validate_pr_title.py
'

swarm_context_cmd='
set -euo pipefail
python3 scripts/ci/validate_swarm_context.py
'

security_cmd='
set -euo pipefail
if [ "'"${INSTALL_DEPS}"'" = "1" ]; then
  "'"${PYTHON_BIN}"'" -m pip install --no-cache-dir bandit
fi
bandit -q -r src -s B311,B107
'

local_ci_cmd='
set -euo pipefail
export PATH="'"$(dirname "${PYTHON_BIN}")"':${PATH}"
if [ "'"${INSTALL_DEPS}"'" = "1" ]; then
  "'"${PYTHON_BIN}"'" -m pip install --no-cache-dir pytest pytest-asyncio pytest-cov pyyaml requests
  "'"${PYTHON_BIN}"'" -m pip install --no-cache-dir ccxt influxdb-client asyncpg numpy scipy
fi
if [ ! -x scripts/local-ci-checks.sh ]; then
  echo "scripts/local-ci-checks.sh not found or not executable"
  exit 1
fi
./scripts/local-ci-checks.sh
'

run_captured_step "swarm-context" "${CI_DIR}/swarm-context.log" "${CI_DIR}/swarm-context.status" "${swarm_context_cmd}"
run_captured_step "lint" "${CI_DIR}/lint.log" "${CI_DIR}/lint.status" "${lint_cmd}"
run_captured_step "security-scan" "${CI_DIR}/security-scan.log" "${CI_DIR}/security-scan.status" "${security_cmd}"
run_captured_step "local-ci" "${CI_DIR}/local-ci-full.log" "${CI_DIR}/local-ci.status" "${local_ci_cmd}"

overall_code=0
for status_file in \
  "${CI_DIR}/lint.status" \
  "${CI_DIR}/security-scan.status" \
  "${CI_DIR}/local-ci.status"; do
  if [ ! -f "${status_file}" ] || [ "$(cat "${status_file}")" != "0" ]; then
    overall_code=1
  fi
done

if [ "${overall_code}" -eq 0 ]; then
  echo "swarm_triage: PASS"
else
  echo "swarm_triage: FAIL"
fi

exit "${overall_code}"
