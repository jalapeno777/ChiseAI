#!/usr/bin/env bash
#
# rebuild_ci_image.sh - Rebuild CI Docker images and update ci.yaml
#
# Usage: ./scripts/ci/rebuild_ci_image.sh <image-name> [options]
#
# Arguments:
#   <image-name>         Image name without tag (e.g., chiseai-ci-dependency-audit)
#
# Options:
#   --tag <tag>         Custom tag suffix. Defaults to py311-YYYYMMDD
#   --no-push           Skip git commit and push (useful for testing)
#   --dry-run           Show what would happen without executing
#
# Exit codes:
#   0 - Success
#   1 - Validation error
#   2 - Build error
#   3 - Push error
#

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default values
IMAGE_NAME=""
CUSTOM_TAG=""
NO_PUSH=false
DRY_RUN=false

# Known CI images and their Dockerfile mappings
declare -A DOCKERFILE_MAP=(
    ["chiseai-ci-tools"]="infrastructure/docker/Dockerfile.ci-tools"
    ["chiseai-ci-lint"]="infrastructure/docker/Dockerfile.ci-lint"
    ["chiseai-ci-dependency-audit"]="infrastructure/docker/Dockerfile.ci-dependency-audit"
    ["chiseai-ci-risk-invariants"]="infrastructure/docker/Dockerfile.ci-risk-invariants"
    ["chiseai-ci-local-ci"]="infrastructure/docker/Dockerfile.ci-local-ci"
    ["chiseai-ci-brain-regression"]="infrastructure/docker/Dockerfile.ci-brain-regression"
    ["chiseai-ci-brain-eval"]="infrastructure/docker/Dockerfile.ci-brain-eval"
    ["chiseai-ci-pre-eval-ingestion"]="infrastructure/docker/Dockerfile.ci-pre-eval-ingestion"
    ["chiseai-ci-performance-gate"]="infrastructure/docker/Dockerfile.ci-performance-gate"
    ["chiseai-ci-autocog"]="infrastructure/docker/Dockerfile.ci-autocog"
)

usage() {
    echo "Usage: $0 <image-name> [options]"
    echo ""
    echo "Arguments:"
    echo "  <image-name>         Image name without tag (e.g., chiseai-ci-dependency-audit)"
    echo ""
    echo "Options:"
    echo "  --tag <tag>         Custom tag suffix. Defaults to py311-YYYYMMDD"
    echo "  --no-push           Skip git commit and push (useful for testing)"
    echo "  --dry-run           Show what would happen without executing"
    echo ""
    echo "Known images:"
    for img in "${!DOCKERFILE_MAP[@]}"; do
        echo "  - ${img}"
    done
    exit 1
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
# Handle options in any order (before, after, or mixed with positional args)

REMAINING_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            if [[ -z "${2:-}" || "$2" == -* ]]; then
                log_error "--tag requires a value"
                usage
            fi
            CUSTOM_TAG="$2"
            shift 2
            ;;
        --no-push)
            NO_PUSH=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        --)
            shift
            REMAINING_ARGS+=("$@")
            break
            ;;
        -*)
            log_error "Unknown option: $1"
            usage
            ;;
        *)
            REMAINING_ARGS+=("$1")
            shift
            ;;
    esac
done

# Set positional arguments from collected remaining args
set -- "${REMAINING_ARGS[@]}"

# Validate we have exactly one positional argument
if [[ $# -lt 1 ]]; then
    usage
fi

IMAGE_NAME="$1"

# Validate image name
if [[ -z "${DOCKERFILE_MAP[$IMAGE_NAME]:-}" ]]; then
    log_error "Unknown image: ${IMAGE_NAME}"
    echo ""
    echo "Known images:"
    for img in "${!DOCKERFILE_MAP[@]}"; do
        echo "  - ${img}"
    done
    exit 1
fi

DOCKERFILE="${DOCKERFILE_MAP[$IMAGE_NAME]}"

# Generate tag
if [[ -z "${CUSTOM_TAG}" ]]; then
    TAG_DATE="$(date +%Y%m%d)"
    NEW_TAG="py311-${TAG_DATE}"
else
    NEW_TAG="${CUSTOM_TAG}"
fi

FULL_IMAGE="${IMAGE_NAME}:${NEW_TAG}"

# All Woodpecker YAML files that may reference CI image tags.
# If you add a new Woodpecker pipeline that uses CI images, add it here.
WOODPECKER_CONFIGS=(
    "${REPO_ROOT}/.woodpecker/ci.yaml"
    "${REPO_ROOT}/.woodpecker/push.yaml"
    "${REPO_ROOT}/.woodpecker/cron-security.yaml"
    "${REPO_ROOT}/.woodpecker/autocog-scheduler.yaml"
)

# Dry run output
if [[ "${DRY_RUN}" == true ]]; then
    log_info "=== DRY RUN MODE ==="
    log_info "Would rebuild image: ${FULL_IMAGE}"
    log_info "Would use Dockerfile: ${DOCKERFILE}"
    log_info "Would update ALL Woodpecker configs referencing ${IMAGE_NAME} with tag: ${NEW_TAG}"
    log_info "Config files searched:"
    for wp_file in "${WOODPECKER_CONFIGS[@]}"; do
        log_info "  - ${wp_file}"
    done
    if [[ "${NO_PUSH}" == true ]]; then
        log_info "Would NOT commit or push changes"
    else
        log_info "Would commit and push changes to main"
    fi
    exit 0
fi

log_info "Starting CI image rebuild for: ${IMAGE_NAME}"
log_info "New tag: ${NEW_TAG}"

# ============================================
# Step 1: Validate prerequisites
# ============================================
log_info "Step 1: Validating prerequisites..."

# Check docker
if ! command -v docker &> /dev/null; then
    log_error "docker is not available"
    exit 1
fi

# Check git
if ! command -v git &> /dev/null; then
    log_error "git is not available"
    exit 1
fi

# Check we're in a git repo
cd "${REPO_ROOT}"
if ! git rev-parse --is-inside-work-tree &> /dev/null; then
    log_error "Not inside a git repository"
    exit 1
fi

# Check working tree is clean (unless --no-push)
if [[ "${NO_PUSH}" == false ]]; then
    if [[ -n "$(git status --porcelain)" ]]; then
        log_error "Working tree is not clean. Commit or stash changes before running."
        git status --porcelain
        exit 1
    fi
fi

# Check Dockerfile exists
if [[ ! -f "${REPO_ROOT}/${DOCKERFILE}" ]]; then
    log_error "Dockerfile not found: ${DOCKERFILE}"
    exit 1
fi

log_success "Prerequisites validated"

# ============================================
# Step 2: Detect old tag across all Woodpecker configs
# ============================================
log_info "Step 2: Detecting old tag across all Woodpecker configs..."

CI_YAML="${REPO_ROOT}/.woodpecker/ci.yaml"

# Grep for the image and extract its current tag from any Woodpecker config
# Pattern: image: chiseai-ci-<name>:<tag>
OLD_TAG_LINE=""
for wp_file in "${WOODPECKER_CONFIGS[@]}"; do
    if [[ -f "${wp_file}" ]]; then
        OLD_TAG_LINE="$(grep -E "^\s+image:\s+${IMAGE_NAME}:" "${wp_file}" | head -1 || true)"
        if [[ -n "${OLD_TAG_LINE}" ]]; then
            break
        fi
    fi
done

if [[ -z "${OLD_TAG_LINE}" ]]; then
    log_error "Could not find ${IMAGE_NAME} in any Woodpecker config"
    log_error "Searched:"
    for wp_file in "${WOODPECKER_CONFIGS[@]}"; do
        log_error "  - ${wp_file}"
    done
    exit 1
fi

# Parse out the old tag
OLD_TAG="$(echo "${OLD_TAG_LINE}" | sed -E 's/.*image:\s+[^:]+:(.+)/\1/' | tr -d ' ')"
log_info "Current tag: ${OLD_TAG}"

if [[ "${OLD_TAG}" == "${NEW_TAG}" ]]; then
    log_warning "Old tag and new tag are the same: ${NEW_TAG}"
    log_warning "The image will be rebuilt with the same tag."
    log_warning "Use --tag to specify a different tag, or remove the old image manually first."
fi

log_success "Old tag detected: ${OLD_TAG}"

# ============================================
# Step 3: Build the new image
# ============================================
log_info "Step 3: Building new image: ${FULL_IMAGE}..."

docker build \
    -f "${DOCKERFILE}" \
    -t "${FULL_IMAGE}" \
    "${REPO_ROOT}/infrastructure/docker/"

if [[ $? -ne 0 ]]; then
    log_error "Docker build failed"
    exit 2
fi

log_success "Image built: ${FULL_IMAGE}"

# ============================================
# Step 4: Update all Woodpecker configs
# ============================================
log_info "Step 4: Updating all Woodpecker configs with new tag..."

CHANGED_FILES=()
for wp_file in "${WOODPECKER_CONFIGS[@]}"; do
    if [[ ! -f "${wp_file}" ]]; then
        continue
    fi
    # Check if this file references the image with the old tag
    if grep -qE "^\s+image:\s+${IMAGE_NAME}:${OLD_TAG}" "${wp_file}"; then
        sed -i.bak "s|^\(\s*image:\s*${IMAGE_NAME}:\)${OLD_TAG}|\1${NEW_TAG}|" "${wp_file}"
        if [[ ! -f "${wp_file}.bak" ]]; then
            log_error "sed backup failed for ${wp_file}"
            exit 1
        fi
        # Verify the change was made
        if ! grep -q "${IMAGE_NAME}:${NEW_TAG}" "${wp_file}"; then
            log_error "Failed to update ${wp_file} with new tag"
            mv "${wp_file}.bak" "${wp_file}"
            exit 1
        fi
        rm "${wp_file}.bak"
        CHANGED_FILES+=("${wp_file}")
        log_success "Updated ${wp_file}"
    fi
done

if [[ ${#CHANGED_FILES[@]} -eq 0 ]]; then
    log_error "No files were updated. This should not happen since Step 2 found the tag."
    exit 1
fi

log_success "Updated ${#CHANGED_FILES[@]} file(s) with new tag: ${NEW_TAG}"

# ============================================
# Step 5: Validate with yamllint
# ============================================
log_info "Step 5: Validating changed files with yamllint..."

if command -v yamllint &> /dev/null; then
    for wp_file in "${CHANGED_FILES[@]}"; do
        if ! yamllint "${wp_file}"; then
            log_error "yamllint validation failed for ${wp_file}. Reverting changes..."
            # Revert using git
            git checkout "${CHANGED_FILES[@]}"
            exit 1
        fi
    done
    log_success "yamllint validation passed for all changed files"
else
    log_warning "yamllint not installed, skipping validation"
fi

# ============================================
# Step 6: Clean up old image (unless --no-push)
# ============================================
if [[ "${NO_PUSH}" == false && "${OLD_TAG}" != "${NEW_TAG}" ]]; then
    log_info "Step 6: Removing old image: ${IMAGE_NAME}:${OLD_TAG}..."
    docker rmi "${IMAGE_NAME}:${OLD_TAG}" 2>/dev/null || log_warning "Could not remove old image (may not exist locally)"
    log_success "Old image cleanup attempted"
fi

# ============================================
# Step 7: Commit and push (unless --no-push)
# ============================================
if [[ "${NO_PUSH}" == false ]]; then
    log_info "Step 7: Committing and pushing changes..."

    git add "${CHANGED_FILES[@]}"

    COMMIT_MSG="ci: rebuild ${IMAGE_NAME} with tag ${NEW_TAG}"

    if ! git commit -m "${COMMIT_MSG}"; then
        log_error "Git commit failed"
        exit 3
    fi

    log_info "Changes committed: ${COMMIT_MSG}"

    if ! git push origin main; then
        log_error "Git push failed"
        exit 3
    fi

    log_success "Pushed to origin/main"
fi

# ============================================
# Step 8: Verify no stale tags remain
# ============================================
log_info "Step 8: Verifying no stale tags remain in repo..."

STALE_REFS="$(git grep -l "${IMAGE_NAME}:${OLD_TAG}" -- '*.yaml' '*.yml' '*.sh' 2>/dev/null || true)"
if [[ -n "${STALE_REFS}" ]]; then
    log_error "Stale tag references found after update!"
    log_error "The following files still reference ${IMAGE_NAME}:${OLD_TAG}:"
    echo "${STALE_REFS}"
    log_error "Add these files to WOODPECKER_CONFIGS in the script, or update them manually."
    if [[ "${NO_PUSH}" == false ]]; then
        log_error "WARNING: Changes have already been committed. Manual fix required."
    fi
    exit 1
fi

log_success "No stale tag references found"

# ============================================
# Summary
# ============================================
echo ""
log_success "=== REBUILD COMPLETE ==="
echo ""
echo "  Image:    ${FULL_IMAGE}"
echo "  Tag:      ${NEW_TAG}"
echo "  Files:    ${CHANGED_FILES[*]}"
if [[ "${NO_PUSH}" == true ]]; then
    echo "  Push:     SKIPPED (--no-push)"
else
    echo "  Push:     Done"
fi
echo ""

exit 0
