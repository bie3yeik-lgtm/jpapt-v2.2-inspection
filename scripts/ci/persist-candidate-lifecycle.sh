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

# Every event path includes the canonical lifecycle observation digest.
# Re-observing semantically identical JSON is idempotent even if whitespace or
# object key ordering differs in the local file representation.
hf buckets cp --token "$HF_TOKEN" "$snapshot" "$base/events/$evidence_key.lifecycle.json"

# states/<state>.json is a materialized lookup view. Backfills and delayed
# persisters must never replace a newer observation with an older one.
state_remote="$base/states/$state.json"
state_tmp="$(mktemp)"
write_state=true
if hf buckets cp --token "$HF_TOKEN" "$state_remote" "$state_tmp" >/dev/null 2>&1; then
  python scripts/ci/build-candidate-request-lifecycle.py --validate "$state_tmp" >/dev/null
  write_state="$(python scripts/ci/compare-candidate-lifecycle-state.py \
    --existing "$state_tmp" \
    --incoming "$snapshot")"
fi
rm -f "$state_tmp"
if [[ "$write_state" == true ]]; then
  hf buckets cp --token "$HF_TOKEN" "$snapshot" "$state_remote"
else
  echo "[lifecycle-persist] keeping newer materialized state=$state for request_key=$request_key"
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
done

echo "[lifecycle-persist] request_key=$request_key state=$state observation=$observation_sha256 event=$evidence_key bucket=$HF_LIFECYCLE_BUCKET"
