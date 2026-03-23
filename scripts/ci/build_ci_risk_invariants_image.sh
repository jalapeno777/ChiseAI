#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${1:-py311-20260322}"
IMAGE_NAME="chiseai-ci-risk-invariants:${IMAGE_TAG}"

echo "Building ${IMAGE_NAME}..."
docker build \
  -f infrastructure/docker/Dockerfile.ci-risk-invariants \
  -t "${IMAGE_NAME}" \
  .

echo "Build complete: ${IMAGE_NAME}"
