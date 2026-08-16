#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

exec cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-revisions "$@"
