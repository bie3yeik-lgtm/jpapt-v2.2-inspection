#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# Parakeet ONNX development environment setup
#
# Supported environments:
#   - Linux
#   - WSL2
#   - macOS
#
# Responsibilities:
#   - Locate the repository root.
#   - Verify required bootstrap tools.
#   - Install mise-managed development tools.
#   - Create project-local runtime/cache directories.
#   - Synchronize the Python development environment with uv.
#   - Run the project environment doctor.
#
# Non-responsibilities:
#   - Download model candidates.
#   - Download evaluation datasets.
#   - Generate HF revision locks.
#   - Export ONNX models.
#   - Run evaluation.
#
# Those operations are performed by dedicated project commands/scripts.
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd
)"

ROOT="$(
    cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1
    pwd
)"

cd "$ROOT"

export PARAKEET_ONNX_REPO_ROOT="$ROOT"

# -----------------------------------------------------------------------------
# Logging helpers
# -----------------------------------------------------------------------------

log() {
    printf '[setup] %s\n' "$*"
}

warn() {
    printf '[setup] WARNING: %s\n' "$*" >&2
}

fail() {
    printf '[setup] ERROR: %s\n' "$*" >&2
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# -----------------------------------------------------------------------------
# Platform detection
# -----------------------------------------------------------------------------

detect_platform() {
    local uname_s

    uname_s="$(uname -s)"

    case "$uname_s" in
        Linux)
            if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
                printf '%s\n' "wsl2"
            else
                printf '%s\n' "linux"
            fi
            ;;

        Darwin)
            printf '%s\n' "macos"
            ;;

        *)
            fail "Unsupported Unix-like platform: $uname_s"
            ;;
    esac
}

PLATFORM="$(detect_platform)"

log "Repository root: $ROOT"
log "Platform: $PLATFORM"

# -----------------------------------------------------------------------------
# Repository sanity checks
# -----------------------------------------------------------------------------

[[ -f "$ROOT/pyproject.toml" ]] \
    || fail "pyproject.toml was not found in repository root."

[[ -f "$ROOT/mise.toml" ]] \
    || fail "mise.toml was not found in repository root."

[[ -d "$ROOT/config" ]] \
    || fail "config/ directory was not found."

[[ -d "$ROOT/evaluation" ]] \
    || fail "evaluation/ directory was not found."

[[ -d "$ROOT/python/src/parakeet_onnx" ]] \
    || fail "python/src/parakeet_onnx/ directory was not found."

# -----------------------------------------------------------------------------
# Bootstrap tool: mise
# -----------------------------------------------------------------------------

if ! command_exists mise; then
    fail \
        "mise is required but was not found in PATH. Install mise first, then rerun scripts/dev/setup.sh."
fi

log "mise: $(mise --version)"

# Trust only the repository that the user explicitly invoked this script from.
log "Trusting repository mise configuration..."
mise trust "$ROOT/mise.toml"

log "Installing mise-managed tools..."
mise install

# From this point onward, run project tools through mise exec so this script
# does not depend on whether shell activation has already been configured.
run_mise() {
    mise exec -- "$@"
}

# -----------------------------------------------------------------------------
# Verify required project tools
# -----------------------------------------------------------------------------

REQUIRED_TOOLS=(
    python
    uv
    rustc
    cargo
)

for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! run_mise "$tool" --version >/dev/null 2>&1; then
        fail "mise tool is unavailable after 'mise install': $tool"
    fi
done

log "Python: $(run_mise python --version 2>&1)"
log "uv: $(run_mise uv --version 2>&1)"
log "Rust: $(run_mise rustc --version 2>&1)"
log "Cargo: $(run_mise cargo --version 2>&1)"

# -----------------------------------------------------------------------------
# Project directories
# -----------------------------------------------------------------------------
#
# These paths correspond to config/environments/*.toml defaults.
#
# They are disposable runtime/cache locations and must remain excluded
# from Git.
# -----------------------------------------------------------------------------

DIRECTORIES=(
    ".cache"
    ".cache/models"
    ".cache/evaluation"
    ".cache/evaluation/audio"
    ".cache/huggingface"
    ".ci"
    ".ci/hf/config/revisions"
    ".ci/candidate"
    ".ci/reference"
    "results"
    "tmp"
)

log "Creating runtime/cache directories..."

for directory in "${DIRECTORIES[@]}"; do
    mkdir -p "$ROOT/$directory"
done

# -----------------------------------------------------------------------------
# Standard cache environment variables
# -----------------------------------------------------------------------------

export HF_HOME="${HF_HOME:-$ROOT/.cache/huggingface}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.cache/uv}"

mkdir -p "$HF_HOME"
mkdir -p "$UV_CACHE_DIR"

log "HF_HOME=$HF_HOME"
log "UV_CACHE_DIR=$UV_CACHE_DIR"

# -----------------------------------------------------------------------------
# Python environment
# -----------------------------------------------------------------------------

log "Synchronizing Python environment with uv..."

# --all-groups is appropriate when pyproject.toml uses dependency groups.
#
# Optional heavyweight extras such as NeMo should not automatically be
# installed by this general development bootstrap. They belong to their
# explicit development/export environment.
run_mise uv sync --locked

# -----------------------------------------------------------------------------
# Basic Python import verification
# -----------------------------------------------------------------------------

log "Verifying project Python package..."

run_mise uv run python - <<'PY'
import parakeet_onnx

print(
    "[setup] Imported parakeet_onnx from:",
    parakeet_onnx.__file__,
)
PY

# -----------------------------------------------------------------------------
# JSON Schema / TOML configuration sanity check
# -----------------------------------------------------------------------------

log "Running development environment diagnostics..."

run_mise uv run python "$ROOT/scripts/dev/doctor.py"

# -----------------------------------------------------------------------------
# Platform notes
# -----------------------------------------------------------------------------

case "$PLATFORM" in
    wsl2)
        log "WSL2 detected."
        log "Linux environment configuration will be used by the project."
        ;;

    macos)
        log "macOS detected."
        log "CoreML evaluation requires an ONNX Runtime build exposing CoreMLExecutionProvider."
        ;;

    linux)
        ;;
esac

# -----------------------------------------------------------------------------
# Completion
# -----------------------------------------------------------------------------

cat <<EOF

Development environment setup completed.

Repository:
  $ROOT

Important runtime directories:
  .cache/huggingface
  .cache/models
  .cache/evaluation
  .cache/evaluation/audio
  .ci/
  results/
  tmp/

Canonical materialized-audio cache:
  $ROOT/.cache/evaluation/audio

Next diagnostic command:
  mise exec -- uv run python scripts/dev/doctor.py

EOF

