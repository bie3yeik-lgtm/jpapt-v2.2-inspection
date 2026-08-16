#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log() { printf '[hf-allocate-id] %s\n' "$*" >&2; }
fail() { printf '[hf-allocate-id] ERROR: %s\n' "$*" >&2; exit 1; }

COLLECTION="${1:-}"
PREFIX_KEY="${2:-}"

[[ "$COLLECTION" == "candidates" || "$COLLECTION" == "experiments" || "$COLLECTION" == "config" ]] \
  || fail "collection must be 'candidates', 'experiments', or 'config'"
[[ -n "$PREFIX_KEY" ]] || fail "allocation prefix key is required"

if [[ "${HF_ALLOCATOR_INTERNAL:-}" != "1" ]]; then
  exec bash scripts/hf/hf-request-id.sh "$COLLECTION" "$PREFIX_KEY"
fi

[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

PREFIX="$(python scripts/ci/resolve-allocation-catalog.py prefix "$PREFIX_KEY")" \
  || fail "failed to resolve allocation prefix key: $PREFIX_KEY"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
[[ "$BUCKET" == */* ]] || fail "HF_BUCKET must use namespace/bucket-name format"

case "$COLLECTION" in
  candidates|experiments)
    REMOTE_ROOT="hf://buckets/${BUCKET}/${COLLECTION}"
    ;;
  config)
    REMOTE_ROOT="hf://buckets/${BUCKET}/config/versions"
    [[ "$PREFIX_KEY" == "config.version" ]] \
      || fail "config allocations must use prefix key 'config.version'"
    ;;
esac

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

python - "$readme" "$ID" "$COLLECTION" "$BUCKET" "$PREFIX_KEY" "$PREFIX" "$SEQUENCE" "$CREATED_AT" <<'PY'
import json
import os
import sys
from pathlib import Path

path, allocation_id, collection, bucket, prefix_key, prefix, sequence, created_at = sys.argv[1:]
try:
    metadata = json.loads(os.environ.get("HF_ALLOCATION_METADATA_JSON", "{}"))
except json.JSONDecodeError as exc:
    raise SystemExit(f"HF_ALLOCATION_METADATA_JSON is invalid JSON: {exc}")
if not isinstance(metadata, dict):
    raise SystemExit("HF_ALLOCATION_METADATA_JSON must be a JSON object")

lines = [
    f"# {allocation_id}",
    "",
    "このディレクトリIDは中央Allocatorが自動採番しました。数値suffixは手動で再利用・変更しないでください。",
    "",
    f"- collection: `{collection}`",
    f"- bucket: `{bucket}`",
    f"- prefix_key: `{prefix_key}`",
    f"- resolved_prefix: `{prefix}`",
    f"- sequence: `{sequence}`",
    f"- allocated_at: `{created_at}`",
]
for key in sorted(metadata):
    value = metadata[key]
    if value is not None and value != "":
        rendered = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        lines.append(f"- {key}: `{rendered}`")
lines += [
    "",
    "prefixはconfig/hf-allocation-catalog.jsonで一元管理され、連番はcollection全体の最大suffix + 1で管理されます。",
    "targetとBucketの対応は採番時点のrouting snapshotであり、恒久的なidentityではありません。",
]
Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

hf buckets cp --token "$HF_TOKEN" "$readme" "${REMOTE_ROOT}/${ID}/README.md" >/dev/null

log "Allocated ${COLLECTION}/${ID} in ${BUCKET} using ${PREFIX_KEY} -> ${PREFIX}"
printf '%s\n' "$ID"
