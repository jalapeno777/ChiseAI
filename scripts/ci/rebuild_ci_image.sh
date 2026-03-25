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
if [[ $# -lt 1 ]]; then
    usage
fi

IMAGE_NAME="$1"
shift

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
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
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

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

# Dry run output
if [[ "${DRY_RUN}" == true ]]; then
    log_info "=== DRY RUN MODE ==="
    log_info "Would rebuild image: ${FULL_IMAGE}"
    log_info "Would use Dockerfile: ${DOCKERFILE}"
    log_info "Would update .woodpecker/ci.yaml with tag: ${NEW_TAG}"
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
# Step 2: Detect old tag in ci.yaml
# ============================================
log_info "Step 2: Detecting old tag in .woodpecker/ci.yaml..."

CI_YAML="${REPO_ROOT}/.woodpecker/ci.yaml"

# Grep for the image and extract its current tag
# Pattern: image: chiseai-ci-<name>:<tag>
OLD_TAG_LINE="$(grep -E "^\s+image:\s+${IMAGE_NAME}:" "${CI_YAML}" | head -1 || true)"

if [[ -z "${OLD_TAG_LINE}" ]]; then
    log_error "Could not find ${IMAGE_NAME} in ${CI_YAML}"
    exit 1
fi

# Parse out the old tag
OLD_TAG="$(echo "${OLD_TAG_LINE}" | sed -E 's/.*image:\s+[^:]+:(.+)/\1/' | tr -d ' ')"
log_info "Current tag in ci.yaml: ${OLD_TAG}"

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
# Step 4: Update ci.yaml
# ============================================
log_info "Step 4: Updating ${CI_YAML}..."

# Replace the old tag with the new tag for this specific image
# Only modify lines containing this specific image name
sed -i.bak "s|^\(\s*image:\s*${IMAGE_NAME}:\)${OLD_TAG}|\1${NEW_TAG}|" "${CI_YAML}"

if [[ ! -f "${CI_YAML}.bak" ]]; then
    log_error "sed backup failed"
    exit 1
fi

# Verify the change was made
if ! grep -q "${IMAGE_NAME}:${NEW_TAG}" "${CI_YAML}"; then
    log_error "Failed to update ci.yaml with new tag"
    mv "${CI_YAML}.bak" "${CI_YAML}"
    exit 1
fi

rm "${CI_YAML}.bak"
log_success "Updated ${CI_YAML} with new tag: ${NEW_TAG}"

# ============================================
# Step 5: Validate with yamllint
# ============================================
log_info "Step 5: Validating ${CI_YAML} with yamllint..."

if command -v yamllint &> /dev/null; then
    if ! yamllint "${CI_YAML}"; then
        log_error "yamllint validation failed. Reverting changes..."
        # Revert using git
        git checkout "${CI_YAML}"
        exit 1
    fi
    log_success "yamllint validation passed"
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

    git add "${CI_YAML}"

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
# Summary
# ============================================
echo ""
log_success "=== REBUILD COMPLETE ==="
echo ""
echo "  Image:    ${FULL_IMAGE}"
echo "  Tag:      ${NEW_TAG}"
echo "  File:     ${CI_YAML}"
if [[ "${NO_PUSH}" == true ]]; then
    echo "  Push:     SKIPPED (--no-push)"
else
    echo "  Push:     Done"
fi
echo ""

exit 0
