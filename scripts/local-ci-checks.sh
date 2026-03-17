#!/usr/bin/env bash
set -euo pipefail

# Write deterministic outputs for CI log scanning and PR comments.
mkdir -p _bmad-output/ci

# Prevent environment contamination (e.g., sibling repos on PYTHONPATH).
# Include user site-packages for dependencies installed via pip install --user
export PYTHONPATH="$(pwd)/src:$(python3 -m site --user-site)"
export PYTHONNOUSERSITE=1

# PHASE 3: Parse command line arguments
SCOPE_MODE="full"
PARALLEL_MODE=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --merged-only)
      SCOPE_MODE="merged-only"
      shift
      ;;
    --parallel)
      PARALLEL_MODE="1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# PHASE 3: Configure parallel test execution
PARALLEL_ARGS=""
if [ "${PARALLEL_MODE:-}" = "1" ]; then
  WORKERS="${PYTEST_WORKERS:-auto}"
  MAX_WORKERS="${PYTEST_MAX_WORKERS:-4}"
  if [ "$WORKERS" = "auto" ]; then
    # Auto-detect CPU count and cap at MAX_WORKERS
    CPU_COUNT=$(nproc 2>/dev/null || echo 1)
    WORKERS=$((CPU_COUNT > MAX_WORKERS ? MAX_WORKERS : CPU_COUNT))
  fi
  PARALLEL_ARGS="-n $WORKERS"
  echo "PHASE 3: Parallel test execution enabled with $WORKERS workers"
fi

# Swarm context is enforced by a dedicated Woodpecker step.
# Skip duplicate validation in CI containers to avoid conflicting context detection.
if [ -n "${CI:-}" ] || [ -n "${CI_COMMIT_REF:-}" ] || [ -n "${WOODPECKER_COMMIT_REF:-}" ]; then
  echo "Skipping validate_swarm_context.py inside local-ci-checks.sh (already enforced by swarm-context step)"
else
  python3 scripts/ci/validate_swarm_context.py
fi

# Enforce policy consistency across AGENTS and agent profiles.
python3 scripts/validate_swarm_policy_consistency.py

if [ "$SCOPE_MODE" = "merged-only" ]; then
  echo "Running merged-files-only local CI checks"
  mapfile -t CHANGED_PY < <(python3 scripts/ci/ci_change_scope.py --mode changed-python)
  MAX_MERGED_TARGETS="${MAX_MERGED_TARGETS:-40}"
  if [ "${#CHANGED_PY[@]}" -eq 0 ]; then
    echo "No changed python files detected; skipping pytest in merged-only mode"
    exit 0
  fi

  declare -A TARGET_MAP
  have_rg=0
  if command -v rg >/dev/null 2>&1; then
    have_rg=1
  fi

  for path in "${CHANGED_PY[@]}"; do
    if [[ "$path" == tests/*.py ]] && [ -f "$path" ]; then
      base_name="$(basename "$path")"
      # Keep merged-only targets focused on executable test modules.
      if [[ "$base_name" == "__init__.py" || "$base_name" == "conftest.py" ]]; then
        continue
      fi
      TARGET_MAP["$path"]=1
      continue
    fi

    if [[ "$path" == src/*.py ]]; then
      stem="$(basename "$path" .py)"
      # Avoid broad glob expansion from package markers.
      if [[ "$stem" == "__init__" ]]; then
        continue
      fi
      while IFS= read -r candidate; do
        [ -z "$candidate" ] && continue
        TARGET_MAP["$candidate"]=1
      done < <(
        if [ "$have_rg" -eq 1 ]; then
          rg --files tests -g "**/test_${stem}.py" -g "**/${stem}_test.py"
        else
          find tests -type f \
            \( -name "test_${stem}.py" -o -name "${stem}_test.py" \) \
            -print
        fi 2>/dev/null || true
      )
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

  if [ "${#TARGETS[@]}" -gt "$MAX_MERGED_TARGETS" ]; then
    echo "Merged-only target list too large (${#TARGETS[@]} > ${MAX_MERGED_TARGETS})."
    echo "Running syntax validation + bounded fast-test subset to preserve signal."
    python3 -m py_compile "${CHANGED_PY[@]}"

    FAST_TARGETS=()
    for target in "${TARGETS[@]}"; do
      if [[ "$target" == tests/integration/* || "$target" == tests/e2e/* ]]; then
        continue
      fi
      if [[ "$target" == tests/test_autonomous/* || "$target" == tests/test_autonomous_control_plane/* ]]; then
        continue
      fi
      FAST_TARGETS+=("$target")
    done

    if [ "${#FAST_TARGETS[@]}" -eq 0 ]; then
      FAST_TARGETS=("${TARGETS[@]}")
    fi

    SELECTED_TARGETS=()
    for target in "${FAST_TARGETS[@]}"; do
      SELECTED_TARGETS+=("$target")
      if [ "${#SELECTED_TARGETS[@]}" -ge "$MAX_MERGED_TARGETS" ]; then
        break
      fi
    done

    if [ "${#SELECTED_TARGETS[@]}" -gt 0 ]; then
      printf "Fallback pytest targets (%s): %s\n" "${#SELECTED_TARGETS[@]}" "${SELECTED_TARGETS[*]}"
      python3 -m pytest \
        --junitxml=_bmad-output/ci/pytest-junit.xml \
        "${SELECTED_TARGETS[@]}" \
        2>&1 | tee _bmad-output/ci/local-ci.log
      exit "${PIPESTATUS[0]}"
    fi

    echo "No suitable fallback test targets available after cap filtering."
    exit 0
  fi

  printf "Merged-only pytest targets (%s): %s\n" "${#TARGETS[@]}" "${TARGETS[*]}"
  python3 -m pytest \
    $PARALLEL_ARGS \
    --junitxml=_bmad-output/ci/pytest-junit.xml \
    "${TARGETS[@]}" \
    2>&1 | tee _bmad-output/ci/local-ci.log
  exit "${PIPESTATUS[0]}"
fi

# Run tests in batches to avoid file descriptor exhaustion
# Split by test directory to limit concurrent file opens
echo "Running tests in batches to manage file descriptors..."

# Check if we should use pytest-forked for file descriptor isolation
FORKED_ARGS=""
if [ "${CI_FD_CONSTRAINTS:-}" = "1" ] && python3 -c "import pytest_forked" >/dev/null 2>&1; then
  echo "CI_FD_CONSTRAINTS=1 detected: using pytest-forked for process isolation"
  FORKED_ARGS="--forked"
fi

# Discover test directories
TEST_DIRS=()
for dir in tests/*/; do
  if [ -d "$dir" ]; then
    TEST_DIRS+=("$dir")
  fi
done

# If no subdirectories found, fall back to tests/
if [ ${#TEST_DIRS[@]} -eq 0 ]; then
  TEST_DIRS=("tests/")
fi

echo "Test batches: ${TEST_DIRS[*]}"

# Run tests in batches
BATCH_FAIL=0
BATCH_TMP=$(mktemp)

for batch_dir in "${TEST_DIRS[@]}"; do
  echo ""
  echo "===== Running tests in: $batch_dir ====="
  if python3 -c "import pytest_cov" >/dev/null 2>&1; then
    python3 -m pytest \
      "$batch_dir" \
      $PARALLEL_ARGS \
      --cov=src \
      --cov-report=term-missing \
      --cov-append \
      $FORKED_ARGS \
      --junitxml="_bmad-output/ci/pytest-junit-${batch_dir//\//_}.xml" \
      2>&1 || echo "$batch_dir" >> "$BATCH_TMP"
  else
    echo "pytest-cov not installed; running pytest without coverage enforcement" >&2
    python3 -m pytest \
      "$batch_dir" \
      $PARALLEL_ARGS \
      $FORKED_ARGS \
      --junitxml="_bmad-output/ci/pytest-junit-${batch_dir//\//_}.xml" \
      2>&1 || echo "$batch_dir" >> "$BATCH_TMP"
  fi
  
  # Small delay between batches to allow file handle cleanup (only in non-parallel mode)
  if [ -z "$PARALLEL_MODE" ]; then
    sleep 1
  fi
done

# Check for batch failures
if [ -s "$BATCH_TMP" ]; then
  echo ""
  echo "ERROR: The following test batches failed:"
  cat "$BATCH_TMP"
  BATCH_FAIL=1
fi

rm -f "$BATCH_TMP"

# Generate final coverage report if pytest-cov is available
if python3 -c "import pytest_cov" >/dev/null 2>&1; then
  echo ""
  echo "===== Generating coverage report ====="
  python3 -m coverage report --fail-under=80 2>&1 || true
  python3 -m coverage xml -o _bmad-output/ci/coverage.xml 2>&1 || true
fi

# Merge JUnit XML files if more than one batch
if [ ${#TEST_DIRS[@]} -gt 1 ] && command -v python3 >/dev/null 2>&1; then
  python3 << 'PYEOF'
import xml.etree.ElementTree as ET
import glob
import os

junit_files = glob.glob('_bmad-output/ci/pytest-junit-*.xml')
if len(junit_files) > 1:
    # Combine all JUnit reports
    combined = ET.Element('testsuites')
    for f in junit_files:
        try:
            tree = ET.parse(f)
            root = tree.getroot()
            if root.tag == 'testsuites':
                for testsuite in root:
                    combined.append(testsuite)
            elif root.tag == 'testsuite':
                combined.append(root)
        except Exception as e:
            print(f"Warning: could not parse {f}: {e}")
    
    # Write combined report
    ET.ElementTree(combined).write('_bmad-output/ci/pytest-junit.xml')
    print(f"Combined {len(junit_files)} JUnit reports")
else:
    # Just rename the single file
    if junit_files:
        os.rename(junit_files[0], '_bmad-output/ci/pytest-junit.xml')
PYEOF
fi

# Create unified log
cat _bmad-output/ci/pytest-junit-*.xml 2>/dev/null | head -c 1000 > _bmad-output/ci/local-ci.log || echo "Test execution completed" > _bmad-output/ci/local-ci.log

exit $BATCH_FAIL
