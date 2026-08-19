#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"

repository="${1:?repository owner/name is required}"
body_file="${2:?dispatch body file is required}"
max_attempts="${3:-3}"

[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
  echo "ERROR: repository must use owner/name: $repository" >&2
  exit 2
}
owner="${repository%%/*}"
name="${repository#*/}"
if [[ "$owner" == "." || "$owner" == ".." || "$name" == "." || "$name" == ".." ]]; then
  echo "ERROR: repository must not contain dot path segments: $repository" >&2
  exit 2
fi
[[ -f "$body_file" ]] || {
  echo "ERROR: dispatch body does not exist: $body_file" >&2
  exit 2
}
[[ "$max_attempts" =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: max_attempts must be a positive integer" >&2
  exit 2
}
command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is required to validate repository dispatch body" >&2
  exit 2
}
if ! jq -e '
  type == "object"
  and (.event_type | type == "string" and length > 0 and length <= 100)
  and (.client_payload | type == "object")
' "$body_file" >/dev/null 2>&1; then
  echo "ERROR: repository dispatch body must contain event_type (1..100 chars) and object client_payload: $body_file" >&2
  exit 2
fi

attempt=1
while true; do
  if gh api \
    --method POST \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "/repos/$repository/dispatches" \
    --input "$body_file"; then
    echo "repository_dispatch accepted: repository=$repository attempt=$attempt"
    exit 0
  fi

  if (( attempt >= max_attempts )); then
    echo "ERROR: repository_dispatch failed after $attempt attempts: $repository" >&2
    exit 1
  fi

  delay=$((attempt * attempt + 1))
  echo "WARN: repository_dispatch attempt $attempt failed; retrying in ${delay}s" >&2
  sleep "$delay"
  attempt=$((attempt + 1))
done
