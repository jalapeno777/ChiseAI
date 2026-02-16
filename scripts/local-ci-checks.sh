#!/usr/bin/env bash
set -euo pipefail

# Write deterministic outputs for CI log scanning and PR comments.
mkdir -p _bmad-output/ci

# Prevent environment contamination (e.g., sibling repos on PYTHONPATH).
# Include user site-packages for dependencies installed via pip install --user
export PYTHONPATH="$(pwd)/src:$(python3 -m site --user-site)"
export PYTHONNOUSERSITE=1

SCOPE_MODE="full"
if [ "${1:-}" = "--merged-only" ]; then
  SCOPE_MODE="merged-only"
fi

# Swarm context is enforced by a dedicated Woodpecker step.
# Skip duplicate validation in CI containers to avoid conflicting context detection.
if [ -n "${CI:-}" ] || [ -n "${CI_COMMIT_REF:-}" ] || [ -n "${WOODPECKER_COMMIT_REF:-}" ]; then
  echo "Skipping validate_swarm_context.py inside local-ci-checks.sh (already enforced by swarm-context step)"
else
  python3 scripts/ci/validate_swarm_context.py
fi

if [ "$SCOPE_MODE" = "merged-only" ]; then
  echo "Running merged-files-only local CI checks"
  mapfile -t CHANGED_PY < <(python3 scripts/ci/ci_change_scope.py --mode changed-python)
  if [ "${#CHANGED_PY[@]}" -eq 0 ]; then
    echo "No changed python files detected; skipping pytest in merged-only mode"
    exit 0
  fi

  declare -A TARGET_MAP
  for path in "${CHANGED_PY[@]}"; do
    if [[ "$path" == tests/*.py ]] && [ -f "$path" ]; then
      TARGET_MAP["$path"]=1
      continue
    fi

    if [[ "$path" == src/*.py ]]; then
      stem="$(basename "$path" .py)"
      while IFS= read -r candidate; do
        TARGET_MAP["$candidate"]=1
      done < <(rg --files tests -g "test_${stem}.py" -g "*_${stem}.py" -g "*${stem}*.py" || true)
    fi
  done

  TARGETS=()
  for key in $(printf '%s\n' "${!TARGET_MAP[@]}" | sort); do
    TARGETS+=("$key")
  done

  if [ "${#TARGETS[@]}" -eq 0 ]; then
    echo "No matching test files found for changed python files; running syntax check on changed files"
    python3 -m py_compile "${CHANGED_PY[@]}"
    exit 0
  fi

  printf "Merged-only pytest targets (%s): %s\n" "${#TARGETS[@]}" "${TARGETS[*]}"
  python3 -m pytest \
    --junitxml=_bmad-output/ci/pytest-junit.xml \
    "${TARGETS[@]}" \
    2>&1 | tee _bmad-output/ci/local-ci.log
  exit "${PIPESTATUS[0]}"
fi

if python3 -c "import pytest_cov" >/dev/null 2>&1; then
  python3 -m pytest \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=xml:_bmad-output/ci/coverage.xml \
    --cov-fail-under=80 \
    --junitxml=_bmad-output/ci/pytest-junit.xml \
    2>&1 | tee _bmad-output/ci/local-ci.log
else
  echo "pytest-cov not installed; running pytest without coverage enforcement" >&2
  python3 -m pytest \
    --junitxml=_bmad-output/ci/pytest-junit.xml \
    2>&1 | tee _bmad-output/ci/local-ci.log
fi
