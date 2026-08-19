#!/usr/bin/env bash
set -euo pipefail

image="${1:?digest-pinned image reference is required}"
plan="${HF_JOB_PLAN:-.ci/hf-jobs/hf-job-plan.json}"

[[ "$image" =~ ^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$ ]] || {
  echo "ERROR: HF Jobs image must be digest-pinned with lowercase @sha256:<64 hex>: $image" >&2
  exit 2
}

image_name="${image%@sha256:*}"
if [[ "$image_name" == /* || "$image_name" == */ || "$image_name" == *//* ]]; then
  echo "ERROR: HF Jobs image name contains an ambiguous slash structure: $image_name" >&2
  exit 2
fi
IFS='/' read -r -a image_parts <<<"$image_name"
for part in "${image_parts[@]}"; do
  if [[ -z "$part" || "$part" == "." || "$part" == ".." ]]; then
    echo "ERROR: HF Jobs image name contains an unsafe path segment: $image_name" >&2
    exit 2
  fi
done

# Production candidate evaluation writes this plan before reaching image
# preflight. When present, enforce environment/provider/hardware-class binding
# with Rust before any paid remote Job can be created.
if [[ -f "$plan" ]]; then
  command -v cargo >/dev/null 2>&1 || {
    echo "ERROR: cargo is required to validate HF Jobs hardware flavor policy" >&2
    exit 2
  }
  cargo run --quiet --locked -p asr-contracts --bin asr-hf-flavor-policy -- \
    validate --plan "$plan" >/dev/null
fi

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: docker CLI is required for anonymous HF Jobs image preflight" >&2
  exit 2
}

# Deliberately isolate Docker credentials. HF Jobs cannot rely on the GitHub
# runner's GHCR login, so the selected image must resolve anonymously from a
# fresh client configuration before any paid remote Job can be created.
docker_config="$(mktemp -d)"
trap 'rm -rf "$docker_config"' EXIT

if ! DOCKER_CONFIG="$docker_config" docker manifest inspect "$image" >/dev/null; then
  echo "ERROR: selected HF Jobs image is not anonymously pullable: $image" >&2
  echo "ERROR: publish the package publicly or supply a public digest-pinned hf_jobs_image override" >&2
  exit 3
fi

echo "HF Jobs image anonymous pull preflight passed: $image"
