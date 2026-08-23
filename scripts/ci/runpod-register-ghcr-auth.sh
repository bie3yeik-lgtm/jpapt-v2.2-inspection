#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: runpod-register-ghcr-auth.sh --env-file PATH --username USER --confirm-new-token

Registers the CR_PAT from a local dotenv file as a RunPod container-registry
credential. The token is never printed or written to a repository artifact.
The explicit confirmation is required because the token must have been rotated
before this command is used.
EOF
  exit 2
}

ENV_FILE=""
USERNAME=""
CONFIRM_NEW_TOKEN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:?missing env file}"; shift 2 ;;
    --username) USERNAME="${2:?missing registry username}"; shift 2 ;;
    --confirm-new-token) CONFIRM_NEW_TOKEN=1; shift ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[[ -n "$ENV_FILE" && -f "$ENV_FILE" ]] || { echo 'a valid --env-file is required' >&2; exit 2; }
[[ -n "$USERNAME" ]] || { echo '--username is required' >&2; exit 2; }
[[ "$CONFIRM_NEW_TOKEN" -eq 1 ]] || {
  echo 'refusing to use CR_PAT without --confirm-new-token after token rotation' >&2
  exit 2
}
command -v runpodctl >/dev/null || { echo 'runpodctl is required' >&2; exit 1; }

CR_PAT=""
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  [[ "$line" == CR_PAT=* ]] || continue
  CR_PAT="${line#CR_PAT=}"
  if [[ "$CR_PAT" == \"* && "$CR_PAT" == *\" ]]; then
    CR_PAT="${CR_PAT:1:${#CR_PAT}-2}"
  elif [[ "$CR_PAT" == \'* && "$CR_PAT" == *\' ]]; then
    CR_PAT="${CR_PAT:1:${#CR_PAT}-2}"
  fi
  break
done < "$ENV_FILE"

[[ -n "$CR_PAT" ]] || { echo 'CR_PAT is missing from --env-file' >&2; exit 2; }
umask 077
response="$(runpodctl registry create \
  --name "ghcr-${USERNAME}" --username "$USERNAME" --password "$CR_PAT" --output json)"
unset CR_PAT

# Only return non-secret identity fields. Never echo the raw response because
# provider CLI responses can change independently of this wrapper.
jq -e '{id:(.id // .registryAuthId // .registry_auth_id),name}' <<<"$response"
