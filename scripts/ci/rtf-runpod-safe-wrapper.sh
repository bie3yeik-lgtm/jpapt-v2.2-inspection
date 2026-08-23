#!/usr/bin/env bash
set -euo pipefail

# Local-only outer safety boundary for RunPod benchmark commands. The inner
# adapter has its own cleanup trap, but a terminal/WSL interruption can stop
# the process before that trap runs. Keep this wrapper as a non-exec parent so
# it can terminate the child and delete only Pods with the exact run name.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHILD_PID=""

[[ -n "${RTF_RUN_ID:-}" ]] || {
  echo "RTF_RUN_ID is required for the RunPod safety wrapper" >&2
  exit 2
}
[[ "$RTF_RUN_ID" =~ ^rtf-[A-Za-z0-9._-]+-b(1|8|32)$ ]] || {
  echo "RTF_RUN_ID does not match the guarded RunPod naming contract" >&2
  exit 2
}
command -v runpodctl >/dev/null || {
  echo "runpodctl is required for the RunPod safety wrapper" >&2
  exit 1
}
command -v jq >/dev/null || {
  echo "jq is required for the RunPod safety wrapper" >&2
  exit 1
}
[[ $# -gt 0 ]] || {
  echo "usage: rtf-runpod-safe-wrapper.sh --provider runpod --image <digest-pinned-image>" >&2
  exit 2
}

delete_named_pods() {
  local candidate_ids candidate_id
  candidate_ids="$(runpodctl pod list --all --name "$RTF_RUN_ID" --output json 2>/dev/null \
    | jq -r '.[] | (.id // .podId // .pod_id) // empty' 2>/dev/null || true)"
  while IFS= read -r candidate_id; do
    [[ -n "$candidate_id" ]] || continue
    echo "RunPod safety cleanup: deleting Pod for exact run $RTF_RUN_ID" >&2
    runpodctl pod delete "$candidate_id" >/dev/null || \
      echo "::error::RunPod safety cleanup failed for exact run $RTF_RUN_ID" >&2
  done <<< "$candidate_ids"
}

cleanup_on_signal() {
  if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill -TERM "$CHILD_PID" 2>/dev/null || true
  fi
  delete_named_pods
  exit 143
}

trap cleanup_on_signal INT TERM HUP
trap delete_named_pods EXIT

set +e
bash "$ROOT/scripts/run-benchmark.sh" "$@" &
CHILD_PID=$!
wait "$CHILD_PID"
status=$?
CHILD_PID=""
set -e
exit "$status"
