#!/usr/bin/env bash
set -euo pipefail

baseline="${1:?baseline 40-hex SHA is required}"
head="${2:?head/public 40-hex SHA is required}"
output_json="${3:-.ci/upstream-contract-diff/report.json}"
source_repository="${SOURCE_REPOSITORY:-largoyo/Premiere-AutoProcess-Plugin}"

command -v cargo >/dev/null 2>&1 || {
  echo "ERROR: cargo is required to run upstream contract diff" >&2
  exit 2
}

cargo run --quiet --locked -p asr-contracts --bin asr-upstream-contract-diff -- \
  compare \
  --repo-root . \
  --baseline "$baseline" \
  --head "$head" \
  --output "$output_json" \
  --source-repository "$source_repository"
