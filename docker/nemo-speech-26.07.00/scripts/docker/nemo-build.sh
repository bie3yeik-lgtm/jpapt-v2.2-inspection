#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

docker build \
  --file "$ROOT/docker/Dockerfile.nemo" \
  --tag parakeet-nemo:dev \
  "$ROOT"
