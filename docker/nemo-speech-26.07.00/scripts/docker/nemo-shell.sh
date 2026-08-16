#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

docker run --rm -it \
  --gpus all \
  --shm-size=8g \
  -e HF_TOKEN \
  -v "$ROOT:/workspace" \
  -w /workspace \
  parakeet-nemo:dev \
  bash
