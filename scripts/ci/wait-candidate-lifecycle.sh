#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"

repository="${1:?repository owner/name is required}"
request_key="${2:?request_key is required}"
timeout_seconds="${3:-1800}"
github_output="${4:-}"

[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
  echo "ERROR: repository must use owner/name: $repository" >&2
  exit 2
}
[[ "$request_key" =~ ^[0-9a-f]{24}$ ]] || {
  echo "ERROR: request_key must be 24 lowercase hex characters" >&2
  exit 2
}
[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: timeout_seconds must be a positive integer" >&2
  exit 2
}

deadline=$((SECONDS + timeout_seconds))
last_state=dispatched
artifact_id=""
while (( SECONDS < deadline )); do
  for state in acknowledged completed running dispatched; do
    name="candidate-lifecycle-$request_key-$state"
    found="$(gh api "/repos/$repository/actions/artifacts?per_page=100&name=$name" \
      --jq '.artifacts | sort_by(.created_at) | reverse | .[0].id // empty')"
    if [[ -n "$found" ]]; then
      artifact_id="$found"
      if [[ "$state" != "$last_state" ]]; then
        echo "observed lifecycle state=$state artifact_id=$artifact_id"
        last_state="$state"
      fi
      if [[ "$state" == acknowledged ]]; then
        if [[ -n "$github_output" ]]; then
          {
            echo "artifact_id=$artifact_id"
            echo "state=$state"
          } >> "$github_output"
        fi
        echo "lifecycle acknowledged: artifact_id=$artifact_id"
        exit 0
      fi
      break
    fi
  done
  sleep 10
done

echo "ERROR: timed out waiting for acknowledged lifecycle; last observed state=$last_state" >&2
exit 1
