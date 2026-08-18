#!/usr/bin/env bash
set -euo pipefail

image="${1:?digest-pinned image reference is required}"

[[ "$image" =~ ^[A-Za-z0-9._/-]+(:[A-Za-z0-9._-]+)?@sha256:[0-9A-Fa-f]{64}$ ]] || {
  echo "ERROR: HF Jobs image must be digest-pinned with @sha256:<64 hex>: $image" >&2
  exit 2
}
command -v docker >/dev/null 2>&1 || {
  echo "ERROR: docker CLI is required for anonymous HF Jobs image preflight" >&2
  exit 2
}

# Deliberately isolate Docker credentials. HF Jobs cannot rely on the GitHub
# runner's GHCR login, so the selected image must resolve anonymously from a
# fresh client configuration before any paid remote Job is created.
docker_config="$(mktemp -d)"
trap 'rm -rf "$docker_config"' EXIT

if ! DOCKER_CONFIG="$docker_config" docker manifest inspect "$image" >/dev/null; then
  echo "ERROR: selected HF Jobs image is not anonymously pullable: $image" >&2
  echo "ERROR: publish the package publicly or supply a public digest-pinned hf_jobs_image override" >&2
  exit 3
fi

echo "HF Jobs image anonymous pull preflight passed: $image"
