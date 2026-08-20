#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 ghcr.io/<owner>/<package>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
IMAGE_NAME="$1"
[[ "$IMAGE_NAME" =~ ^ghcr\.io/([A-Za-z0-9._-]+)/([A-Za-z0-9._/-]+)$ ]] || usage
OWNER="${BASH_REMATCH[1]}"
PACKAGE="${BASH_REMATCH[2]}"
: "${GH_TOKEN:?GH_TOKEN is required}"

if ! digest="$(gh api --paginate --slurp \
  "/users/${OWNER}/packages/container/${PACKAGE}/versions?per_page=100" \
  | jq -er 'add | max_by(.updated_at) | .metadata.container.digest')"; then
  # Package-version listing requires a token scope that is not consistently
  # available to repository GITHUB_TOKENs. Registry manifest inspection reads
  # only the tag metadata and does not download image layers.
  digest="$(docker buildx imagetools inspect "${IMAGE_NAME}:latest" \
    | awk '/^Digest:/ {print $2; exit}')"
fi
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "unable to resolve immutable GHCR digest for ${IMAGE_NAME}: ${digest:-empty}" >&2
  exit 1
}
printf '%s@%s\n' "$IMAGE_NAME" "$digest"
