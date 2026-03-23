#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${1:-py311-20260322}"
IMAGE_NAME="chiseai-ci-performance-gate:${IMAGE_TAG}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "Building ${IMAGE_NAME}..."
docker build \
  -f "${REPO_ROOT}/infrastructure/docker/Dockerfile.ci-performance-gate" \
  -t "${IMAGE_NAME}" \
  "${REPO_ROOT}"

echo "Build complete: ${IMAGE_NAME}"
