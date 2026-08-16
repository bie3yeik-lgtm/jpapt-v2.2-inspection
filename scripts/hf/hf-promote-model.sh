#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# Compatibility entrypoint. Promotion identity is now candidate-metadata driven
# and supports both single-graph CTC and multi-graph TDT/Whisper bundles.
exec bash "$SCRIPT_DIR/hf-promote-candidate.sh" "$@"
