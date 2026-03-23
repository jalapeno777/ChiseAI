#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${1:-py311-20260323}"
IMAGE_NAME="chiseai-ci-dependency-audit:${IMAGE_TAG}"

echo "Building ${IMAGE_NAME}..."
docker build \
  -f infrastructure/docker/Dockerfile.ci-dependency-audit \
  -t "${IMAGE_NAME}" \
  .

echo "Build complete: ${IMAGE_NAME}"
