#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: persist-candidate-lifecycle.sh <snapshot.json> [canonical-evidence.json ...]

Requires HF_LIFECYCLE_BUCKET and HF_TOKEN. When HF_LIFECYCLE_BUCKET is empty,
the helper exits successfully without writing remote state.
EOF
}

[[ $# -ge 1 ]] || { usage; exit 2; }
snapshot="$1"
shift

[[ -f "$snapshot" ]] || { echo "ERROR: lifecycle snapshot not found: $snapshot" >&2; exit 2; }

if [[ -z "${HF_LIFECYCLE_BUCKET:-}" ]]; then
  echo "[lifecycle-persist] HF_LIFECYCLE_BUCKET is not configured; keeping GitHub artifact evidence only."
  exit 0
fi
[[ -n "${HF_TOKEN:-}" ]] || { echo "ERROR: HF_TOKEN is required when HF_LIFECYCLE_BUCKET is configured." >&2; exit 2; }
[[ "$HF_LIFECYCLE_BUCKET" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
  echo "ERROR: HF_LIFECYCLE_BUCKET must use namespace/name." >&2
  exit 2
}

python scripts/ci/build-candidate-request-lifecycle.py --validate "$snapshot" >/dev/null

readarray -t metadata < <(
  python scripts/ci/build-candidate-lifecycle-event-key.py --snapshot "$snapshot"
)
request_key="${metadata[0]}"
state="${metadata[1]}"
evidence_key="${metadata[2]}"
observation_sha256="${metadata[3]}"
base="hf://buckets/$HF_LIFECYCLE_BUCKET/requests/$request_key"
request_execution_id="$(python - "$snapshot" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')).get('request_execution_id', ''))
PY
)"
execution_key=""
execution_base=""
if [[ -n "$request_execution_id" ]]; then
  execution_key="$(python scripts/ci/build-candidate-request-lifecycle.py --execution-key "$request_execution_id")"
  execution_base="$base/executions/$execution_key"
fi

materialize_state() {
  local target_base="$1"
  local require_execution_match="$2"
  local remote="$target_base/states/$state.json"
  local tmp
  tmp="$(mktemp)"
  local write_state=true
  if hf buckets cp --token "$HF_TOKEN" "$remote" "$tmp" >/dev/null 2>&1; then
    python scripts/ci/build-candidate-request-lifecycle.py --validate "$tmp" >/dev/null
    compare_args=(
      --existing "$tmp"
      --incoming "$snapshot"
    )
    if [[ "$require_execution_match" == true ]]; then
      compare_args+=(--require-execution-match)
    fi
    write_state="$(python scripts/ci/compare-candidate-lifecycle-state.py "${compare_args[@]}")"
  fi
  rm -f "$tmp"
  if [[ "$write_state" == true ]]; then
    hf buckets cp --token "$HF_TOKEN" "$snapshot" "$remote"
  else
    echo "[lifecycle-persist] keeping newer materialized state=$state target=$target_base"
  fi
}

# Request-level paths remain the backward-compatible aggregate view across all
# executions. Immutable events are authoritative recovery evidence.
hf buckets cp --token "$HF_TOKEN" "$snapshot" "$base/events/$evidence_key.lifecycle.json"
materialize_state "$base" false

# New evidence is additionally partitioned by execution identity. This prevents
# a reused request_id from collapsing independent attempts into one durable view.
if [[ -n "$execution_base" ]]; then
  hf buckets cp --token "$HF_TOKEN" "$snapshot" "$execution_base/events/$evidence_key.lifecycle.json"
  materialize_state "$execution_base" true
fi

for evidence in "$@"; do
  [[ -f "$evidence" ]] || { echo "ERROR: canonical evidence not found: $evidence" >&2; exit 2; }
  name="$(basename "$evidence")"
  digest="$(python - "$evidence" <<'PY'
import hashlib
import sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
  hf buckets cp --token "$HF_TOKEN" "$evidence" "$base/evidence/$digest-$name"
  if [[ -n "$execution_base" ]]; then
    hf buckets cp --token "$HF_TOKEN" "$evidence" "$execution_base/evidence/$digest-$name"
  fi
done

echo "[lifecycle-persist] request_key=$request_key execution_key=${execution_key:-legacy} state=$state observation=$observation_sha256 event=$evidence_key bucket=$HF_LIFECYCLE_BUCKET"
