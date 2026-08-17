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

readarray -t metadata < <(python - "$snapshot" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

snapshot_path = Path(sys.argv[1])
snapshot_bytes = snapshot_path.read_bytes()
snapshot = json.loads(snapshot_bytes.decode("utf-8"))
request_id = snapshot["request_id"]
request_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
state = snapshot["state"]
snapshot_key = hashlib.sha256(snapshot_bytes).hexdigest()[:16]
if state in {"planned", "dispatched", "rejected"}:
    run_id = snapshot.get("gateway_run_id")
    # gateway_run_attempt is not part of LifecycleV1. Include the snapshot digest
    # so a rerun cannot overwrite an earlier immutable event path.
    evidence_key = f"gateway-{run_id or 'unknown'}-{state}-{snapshot_key}"
elif state == "running":
    evidence_key = (
        f"evaluation-{snapshot['evaluation_run_id']}-"
        f"{snapshot['evaluation_run_attempt']}-running"
    )
elif state == "completed":
    evidence_key = (
        f"evaluation-{snapshot['evaluation_run_id']}-"
        f"{snapshot['evaluation_run_attempt']}-completed"
    )
elif state == "acknowledged":
    evidence_key = (
        f"evaluation-{snapshot['evaluation_run_id']}-"
        f"{snapshot['evaluation_run_attempt']}-receiver-"
        f"{snapshot['receiver_run_id']}-acknowledged"
    )
else:
    raise SystemExit(f"unsupported lifecycle state: {state}")
print(request_key)
print(state)
print(evidence_key)
PY
)
request_key="${metadata[0]}"
state="${metadata[1]}"
evidence_key="${metadata[2]}"
base="hf://buckets/$HF_LIFECYCLE_BUCKET/requests/$request_key"

# The event path is immutable evidence. The per-state path is a materialized
# lookup view only; consumers must never treat it as a replacement for the
# canonical event/evidence objects.
hf buckets cp --token "$HF_TOKEN" "$snapshot" "$base/events/$evidence_key.lifecycle.json"
hf buckets cp --token "$HF_TOKEN" "$snapshot" "$base/states/$state.json"

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

echo "[lifecycle-persist] request_key=$request_key state=$state event=$evidence_key bucket=$HF_LIFECYCLE_BUCKET"
