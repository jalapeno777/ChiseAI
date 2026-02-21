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
          rg --files tests -g "test_${stem}.py" -g "*_${stem}.py" -g "*${stem}*.py"
        else
          find tests -type f \
            \( -name "test_${stem}.py" -o -name "*_${stem}.py" -o -name "*${stem}*.py" \) \
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

  printf "Merged-only pytest targets (%s): %s\n" "${#TARGETS[@]}" "${TARGETS[*]}"
  python3 -m pytest \
    --junitxml=_bmad-output/ci/pytest-junit.xml \
    "${TARGETS[@]}" \
    2>&1 | tee _bmad-output/ci/local-ci.log
  exit "${PIPESTATUS[0]}"
fi

# Run tests in batches to avoid file descriptor exhaustion
# Split by test directory to limit concurrent file opens
echo "Running tests in batches to manage file descriptors..."

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
      --cov=src \
      --cov-report=term-missing \
      --cov-append \
      --junitxml="_bmad-output/ci/pytest-junit-${batch_dir//\//_}.xml" \
      2>&1 || echo "$batch_dir" >> "$BATCH_TMP"
  else
    echo "pytest-cov not installed; running pytest without coverage enforcement" >&2
    python3 -m pytest \
      "$batch_dir" \
      --junitxml="_bmad-output/ci/pytest-junit-${batch_dir//\//_}.xml" \
      2>&1 || echo "$batch_dir" >> "$BATCH_TMP"
  fi
  
  # Small delay between batches to allow file handle cleanup
  sleep 1
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
