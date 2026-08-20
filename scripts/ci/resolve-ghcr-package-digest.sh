#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 ghcr.io/<owner>/<package> [tag]" >&2
  exit 2
}

[[ $# -eq 1 || $# -eq 2 ]] || usage
IMAGE_NAME="$1"
IMAGE_TAG="${2:-latest}"
[[ "$IMAGE_NAME" =~ ^ghcr\.io/([A-Za-z0-9._-]+)/([A-Za-z0-9._/-]+)$ ]] || usage
OWNER="${BASH_REMATCH[1]}"
PACKAGE="${BASH_REMATCH[2]}"
[[ "$IMAGE_TAG" =~ ^[A-Za-z0-9._-]+$ ]] || usage
: "${GH_TOKEN:?GH_TOKEN is required}"

printf '%s' "$GH_TOKEN" | docker login ghcr.io \
  --username "${GITHUB_ACTOR:-github-actions[bot]}" --password-stdin >/dev/null 2>&1 || true
digest="$(docker buildx imagetools inspect "${IMAGE_NAME}:${IMAGE_TAG}" 2>/dev/null \
  | awk '/^Digest:/ {print $2; exit}' || true)"
if [[ ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  # Package-version listing is a fallback for environments where registry
  # manifest inspection is unavailable. The normal path always resolves the
  # package's current latest tag directly.
  digest="$(gh api --paginate --slurp \
    "/users/${OWNER}/packages/container/${PACKAGE}/versions?per_page=100" 2>/dev/null \
    | jq -er 'add | max_by(.updated_at) | .metadata.container.digest' 2>/dev/null || true)"
fi
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "unable to resolve immutable GHCR digest for ${IMAGE_NAME}: ${digest:-empty}" >&2
  exit 1
}
printf '%s@%s\n' "$IMAGE_NAME" "$digest"
