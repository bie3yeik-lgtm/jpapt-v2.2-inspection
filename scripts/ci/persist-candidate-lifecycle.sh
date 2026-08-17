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
    evidence_key = f"gateway-{run_id or 'unknown'}-{state}-{snapshot_key}"
elif state == "running":
    evidence_key = (
        f"evaluation-{snapshot['evaluation_run_id']}-"
        f"{snapshot['evaluation_run_attempt']}-running-{snapshot_key}"
    )
elif state == "completed":
    evidence_key = (
        f"evaluation-{snapshot['evaluation_run_id']}-"
        f"{snapshot['evaluation_run_attempt']}-completed-{snapshot_key}"
    )
elif state == "acknowledged":
    evidence_key = (
        f"evaluation-{snapshot['evaluation_run_id']}-"
        f"{snapshot['evaluation_run_attempt']}-receiver-"
        f"{snapshot['receiver_run_id']}-acknowledged-{snapshot_key}"
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

# Every event path includes a content digest. Re-observing identical bytes is
# idempotent; any materially different snapshot is written to a new path.
hf buckets cp --token "$HF_TOKEN" "$snapshot" "$base/events/$evidence_key.lifecycle.json"

# states/<state>.json is a materialized lookup view. Backfills and delayed
# persisters must never replace a newer observation with an older one.
state_remote="$base/states/$state.json"
state_tmp="$(mktemp)"
write_state=true
if hf buckets cp --token "$HF_TOKEN" "$state_remote" "$state_tmp" >/dev/null 2>&1; then
  python scripts/ci/build-candidate-request-lifecycle.py --validate "$state_tmp" >/dev/null
  write_state="$(python - "$state_tmp" "$snapshot" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

def parse(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)

existing = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
incoming = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if existing["request_id"] != incoming["request_id"] or existing["state"] != incoming["state"]:
    raise SystemExit("materialized lifecycle state identity mismatch")
print("true" if parse(incoming["updated_at"]) >= parse(existing["updated_at"]) else "false")
PY
)"
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

echo "[lifecycle-persist] request_key=$request_key state=$state event=$evidence_key bucket=$HF_LIFECYCLE_BUCKET"
