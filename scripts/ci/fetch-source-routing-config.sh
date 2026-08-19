#!/usr/bin/env bash
set -euo pipefail

repository="${1:?source repository owner/name is required}"
output_json="${2:?output JSON path is required}"
token="${SOURCE_REPO_TOKEN:-${GH_FALLBACK_TOKEN:-${GH_TOKEN:-}}}"

[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
  echo "ERROR: source repository must use owner/name: $repository" >&2
  exit 2
}
owner="${repository%%/*}"
name="${repository#*/}"
[[ "$owner" != "." && "$owner" != ".." && "$name" != "." && "$name" != ".." ]] || {
  echo "ERROR: source repository must not contain dot-only path segments: $repository" >&2
  exit 2
}

command -v gh >/dev/null 2>&1 || {
  echo "ERROR: gh CLI is required to fetch source routing config" >&2
  exit 2
}
command -v python >/dev/null 2>&1 || {
  echo "ERROR: python is required to decode source routing config" >&2
  exit 2
}

mkdir -p "$(dirname "$output_json")"
response="$(mktemp)"
stderr_file="$(mktemp)"
probe_response="$(mktemp)"
probe_stderr="$(mktemp)"
trap 'rm -f "$response" "$stderr_file" "$probe_response" "$probe_stderr"' EXIT

run_api() {
  local target="$1"
  local stdout_path="$2"
  local stderr_path="$3"
  local result=0
  if [[ -n "$token" ]]; then
    GH_TOKEN="$token" gh api --include "$target" >"$stdout_path" 2>"$stderr_path" || result=$?
  else
    gh api --include "$target" >"$stdout_path" 2>"$stderr_path" || result=$?
  fi
  printf '%s' "$result"
}

http_code() {
  awk 'toupper($1) ~ /^HTTP\// {code=$2} END {print code}' "$1"
}

status="$(run_api "/repos/$repository/contents/.jpapt/hf-bucket.yml" "$response" "$stderr_file")"
http_status="$(http_code "$response")"

if [[ "$status" -ne 0 && -z "$http_status" ]]; then
  echo "ERROR: source routing config lookup failed before receiving an HTTP response" >&2
  cat "$stderr_file" >&2 || true
  exit 3
fi

case "$http_status" in
  200)
    python - "$response" "$output_json" <<'PY'
import base64
import json
import sys
from pathlib import Path

import yaml

response_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
raw = response_path.read_text(encoding="utf-8")
separator = "\r\n\r\n" if "\r\n\r\n" in raw else "\n\n"
try:
    payload_text = raw.rsplit(separator, 1)[1]
except IndexError as error:
    raise SystemExit("source routing response did not contain an HTTP body") from error
payload = json.loads(payload_text)
encoded = payload.get("content")
if not isinstance(encoded, str) or not encoded.strip():
    raise SystemExit("source routing config response is missing non-empty content")
yaml_bytes = base64.b64decode("".join(encoded.split()), validate=True)
config = yaml.safe_load(yaml_bytes.decode("utf-8")) or {}
if not isinstance(config, dict):
    raise SystemExit("source routing config must decode to a YAML mapping")
output_path.write_text(json.dumps(config, separators=(",", ":")) + "\n", encoding="utf-8")
PY
    ;;
  404)
    # GitHub may deliberately return 404 for an inaccessible private repo.
    # Probe repository metadata with the same token: only a visible repository
    # plus a missing config file is eligible for generic-repository fallback.
    probe_status="$(run_api "/repos/$repository" "$probe_response" "$probe_stderr")"
    probe_http_status="$(http_code "$probe_response")"
    if [[ "$probe_status" -ne 0 || "$probe_http_status" != 200 ]]; then
      echo "ERROR: routing config returned 404 but source repository visibility could not be confirmed" >&2
      [[ -n "$probe_http_status" ]] && echo "ERROR: repository probe returned HTTP $probe_http_status" >&2
      cat "$probe_stderr" >&2 || true
      exit 3
    fi
    printf '{}\n' >"$output_json"
    ;;
  '')
    echo "ERROR: source routing config lookup returned no HTTP status" >&2
    cat "$stderr_file" >&2 || true
    exit 3
    ;;
  *)
    echo "ERROR: source routing config lookup failed with HTTP $http_status" >&2
    cat "$stderr_file" >&2 || true
    exit 3
    ;;
esac
