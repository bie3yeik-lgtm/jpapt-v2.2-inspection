#!/usr/bin/env bash
set -euo pipefail

image="${1:?digest-pinned image reference is required}"
require_public="${GHCR_REQUIRE_PUBLIC:-true}"

[[ "$require_public" == true || "$require_public" == false ]] || {
  echo "ERROR: GHCR_REQUIRE_PUBLIC must be true or false: $require_public" >&2
  exit 2
}

[[ "$image" =~ ^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$ ]] || {
  echo "ERROR: image must be digest-pinned with lowercase @sha256:<64 hex>: $image" >&2
  exit 2
}

digest="${image#*@}"
image_name="${image%@sha256:*}"
if [[ "$image_name" == /* || "$image_name" == */ || "$image_name" == *//* ]]; then
  echo "ERROR: image name contains an ambiguous slash structure: $image_name" >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: docker CLI is required for anonymous GHCR public verify" >&2
  exit 2
}

docker_config="$(mktemp -d)"
trap 'rm -rf "$docker_config"' EXIT

verification_method="docker_manifest_inspect_anonymous"
http_status="200"
anonymous_pull_namespace=false

if DOCKER_CONFIG="$docker_config" docker manifest inspect "$image" >/dev/null; then
  anonymous_pull_namespace=true
else
  if [[ "$require_public" == true ]]; then
    echo "ERROR: image is not anonymously resolvable: $image" >&2
    exit 3
  fi
  http_status="403"
  verification_method="docker_manifest_inspect_anonymous_failed"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "digest=$digest"
    echo "verification_method=$verification_method"
    echo "http_status=$http_status"
    echo "anonymous_pull_namespace=$anonymous_pull_namespace"
    echo "credentials_used=false"
  } >>"$GITHUB_OUTPUT"
fi

output_dir="${GHCR_VERIFY_OUTPUT_DIR:-}"
if [[ -n "$output_dir" ]]; then
  command -v jq >/dev/null 2>&1 || {
    echo "ERROR: jq is required when GHCR_VERIFY_OUTPUT_DIR is set" >&2
    exit 2
  }
  mkdir -p "$output_dir"
  if [[ "$require_public" == true ]]; then
    require_public_json=true
  else
    require_public_json=false
  fi
  if [[ "$anonymous_pull_namespace" == true ]]; then
    anonymous_json=true
  else
    anonymous_json=false
  fi
  jq -n \
    --arg schema_version "1" \
    --arg image "$image" \
    --arg digest "$digest" \
    --arg verification_method "$verification_method" \
    --arg http_status "$http_status" \
    --argjson credentials_used false \
    --argjson anonymous_pull_namespace "$anonymous_json" \
    --argjson require_public "$require_public_json" \
    '{
      schema_version: ($schema_version | tonumber),
      image: $image,
      digest: $digest,
      credentials_used: $credentials_used,
      anonymous_pull_namespace: $anonymous_pull_namespace,
      require_public: $require_public,
      verification_method: $verification_method,
      http_status: $http_status
    }' >"$output_dir/receipt.json"
fi

echo "GHCR public verify passed: $image (anonymous_pull_namespace=$anonymous_pull_namespace)"
