#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log() { printf '[hf-allocate-id] %s\n' "$*" >&2; }
fail() { printf '[hf-allocate-id] ERROR: %s\n' "$*" >&2; exit 1; }

COLLECTION="${1:-}"
PREFIX="${2:-}"

[[ "$COLLECTION" == "candidates" || "$COLLECTION" == "experiments" ]] \
  || fail "collection must be 'candidates' or 'experiments'"
[[ -n "$PREFIX" ]] || fail "prefix is required"
[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"
REMOTE_ROOT="hf://buckets/${BUCKET}/${COLLECTION}"

# Allocation is Bucket-scoped. HF_TARGETS_JSON represents only the current
# operational routing snapshot: Bucket assignments may change in later
# snapshots, but within one snapshot every HF_BUCKET must be unique.
if [[ -n "${HF_TARGETS_JSON:-}" ]]; then
  HF_TARGET_ID="$(python - "$BUCKET" <<'PY'
import json
import os
import sys

bucket=sys.argv[1]
raw=json.loads(os.environ["HF_TARGETS_JSON"])
if not isinstance(raw,dict):
    raise SystemExit("HF_TARGETS_JSON root must be an object")
seen={}
for target,entry in raw.items():
    if not isinstance(entry,dict):
        raise SystemExit(f"HF_TARGETS_JSON entry {target!r} must be an object")
    value=entry.get("HF_BUCKET")
    if not isinstance(value,str) or not value.strip():
        raise SystemExit(f"HF_TARGETS_JSON entry {target!r}.HF_BUCKET must be non-empty")
    value=value.strip()
    if value in seen:
        raise SystemExit(
            f"HF_BUCKET {value!r} is assigned to both {seen[value]!r} and "
            f"{target!r} in the current routing snapshot"
        )
    seen[value]=target
matches=[target for value,target in seen.items() if value==bucket]
if len(matches)!=1:
    raise SystemExit(
        f"HF_BUCKET {bucket!r} is not present in the current routing snapshot"
    )
print(matches[0])
PY
)"
  export HF_TARGET_ID
fi

listing="$(mktemp)"
readme="$(mktemp)"
trap 'rm -f "$listing" "$readme" "${listing}.err"' EXIT

if ! hf buckets list --token "$HF_TOKEN" "$REMOTE_ROOT" -R -q >"$listing" 2>"${listing}.err"; then
  if grep -qiE 'not found|does not exist|no files|empty' "${listing}.err"; then
    : >"$listing"
  else
    cat "${listing}.err" >&2
    fail "failed to list ${REMOTE_ROOT}"
  fi
fi

ID="$(python scripts/ci/next-hf-sequence-id.py --prefix "$PREFIX" --listing "$listing")"
SEQUENCE="${ID##*-}"
CREATED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

cat >"$readme" <<EOF
# ${ID}

This directory identifier was allocated automatically from the largest existing
six-digit sequence in \`${COLLECTION}/\` plus one.

- collection: \`${COLLECTION}\`
- bucket: \`${BUCKET}\`
- prefix: \`${PREFIX}\`
- sequence: \`${SEQUENCE}\`
- allocated_at: \`${CREATED_AT}\`
- target_id: \`${HF_TARGET_ID:-not-resolved}\`
- candidate_id: \`${CANDIDATE_ID:-not-applicable}\`
- evaluation_id: \`${EVALUATION_ID:-not-applicable}\`
- provider_id: \`${PROVIDER_ID:-not-applicable}\`
- github_run_id: \`${GITHUB_RUN_ID:-local}\`
- github_run_attempt: \`${GITHUB_RUN_ATTEMPT:-local}\`

The numeric suffix is machine-managed. Do not manually renumber or reuse it.
The prefix is descriptive only and does not define an independent sequence.
The target/Bucket association above is a snapshot of routing at allocation time,
not a permanent target identity.
EOF

hf buckets cp --token "$HF_TOKEN" "$readme" "${REMOTE_ROOT}/${ID}/README.md" >/dev/null

log "Allocated ${COLLECTION}/${ID} in ${BUCKET}"
printf '%s\n' "$ID"
