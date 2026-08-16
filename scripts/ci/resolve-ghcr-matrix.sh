#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

fail() {
  printf '[ghcr-matrix] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

require_command jq
require_command cargo

[[ -n "${HF_TARGETS_JSON:-}" ]] || fail "HF_TARGETS_JSON repository variable is empty"
printf '%s' "$HF_TARGETS_JSON" | jq -e 'type == "object"' >/dev/null \
  || fail "HF_TARGETS_JSON must be a JSON object keyed by target ID"

TARGET_FILTER="${GHCR_TARGET_FILTER:-}"
NAMESPACE="${GHCR_NAMESPACE:-${GITHUB_REPOSITORY_OWNER:-}}"
[[ -n "$NAMESPACE" ]] || fail "GHCR namespace cannot be resolved"
NAMESPACE="$(printf '%s' "$NAMESPACE" | tr '[:upper:]' '[:lower:]')"

entries='[]'
matched=0

mapfile -t dockerfiles < <(find docker -mindepth 2 -maxdepth 2 -type f -name Dockerfile -print | sort)
(( ${#dockerfiles[@]} > 0 )) || fail "docker/*/Dockerfile was not found"

for dockerfile in "${dockerfiles[@]}"; do
  context="$(dirname "$dockerfile")"
  source_repo="$(sed -n 's/^LABEL io\.jpapt\.source\.repo_id="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"
  source_framework="$(sed -n 's/^LABEL io\.jpapt\.source\.framework="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"
  package="$(sed -n 's/^LABEL io\.jpapt\.ghcr\.package="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"
  role="$(sed -n 's/^LABEL io\.jpapt\.role="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"

  [[ -n "$source_repo" ]] || fail "$dockerfile must declare LABEL io.jpapt.source.repo_id"
  [[ -n "$source_framework" ]] || fail "$dockerfile must declare LABEL io.jpapt.source.framework"
  [[ -n "$package" ]] || fail "$dockerfile must declare LABEL io.jpapt.ghcr.package"
  [[ -n "$role" ]] || fail "$dockerfile must declare LABEL io.jpapt.role"

  while IFS= read -r target_id; do
    [[ -n "$target_id" ]] || continue
    if [[ -n "$TARGET_FILTER" && "$target_id" != "$TARGET_FILTER" ]]; then
      continue
    fi

    route="$(printf '%s' "$HF_TARGETS_JSON" | jq -ce --arg id "$target_id" '.[$id]')"
    var_bucket="$(printf '%s' "$route" | jq -er '.HF_BUCKET | strings | select(length > 0)')"
    var_model_repo="$(printf '%s' "$route" | jq -er '.HF_MODEL_REPO | strings | select(length > 0)')"

    resolved="$(cargo run --quiet --locked -p asr-hf -- resolve-target --target "$target_id")"
    resolved_bucket="$(printf '%s\n' "$resolved" | sed -n 's/^HF_BUCKET=//p')"
    resolved_model_repo="$(printf '%s\n' "$resolved" | sed -n 's/^HF_MODEL_REPO=//p')"
    resolved_upstream="$(printf '%s\n' "$resolved" | sed -n 's/^EXPECTED_UPSTREAM_REPO_ID=//p')"
    resolved_framework="$(printf '%s\n' "$resolved" | sed -n 's/^EXPECTED_FRAMEWORK=//p')"
    resolved_variant="$(printf '%s\n' "$resolved" | sed -n 's/^ASR_RUNTIME_VARIANT=//p')"

    [[ "$var_bucket" == "$resolved_bucket" ]] \
      || fail "HF_TARGETS_JSON/$target_id HF_BUCKET=$var_bucket disagrees with source-controlled target=$resolved_bucket"
    [[ "$var_model_repo" == "$resolved_model_repo" ]] \
      || fail "HF_TARGETS_JSON/$target_id HF_MODEL_REPO=$var_model_repo disagrees with source-controlled target=$resolved_model_repo"

    if [[ "$resolved_upstream" != "$source_repo" || "$resolved_framework" != "$source_framework" ]]; then
      continue
    fi

    image="ghcr.io/${NAMESPACE}/${package}"
    object="$(jq -cn \
      --arg target_id "$target_id" \
      --arg docker_context "$context" \
      --arg dockerfile "$dockerfile" \
      --arg package "$package" \
      --arg image "$image" \
      --arg role "$role" \
      --arg source_repo "$source_repo" \
      --arg framework "$source_framework" \
      --arg bucket "$resolved_bucket" \
      --arg model_repo "$resolved_model_repo" \
      --arg runtime_variant "$resolved_variant" \
      '{target_id:$target_id,docker_context:$docker_context,dockerfile:$dockerfile,package:$package,image:$image,role:$role,source_repo:$source_repo,framework:$framework,bucket:$bucket,model_repo:$model_repo,runtime_variant:$runtime_variant}')"
    entries="$(jq -c --argjson item "$object" '. + [$item]' <<<"$entries")"
    matched=$((matched + 1))
  done < <(printf '%s' "$HF_TARGETS_JSON" | jq -r 'keys[]')
done

(( matched > 0 )) || fail "no Dockerfile matched any HF_TARGETS_JSON target${TARGET_FILTER:+ (filter=$TARGET_FILTER)}"

matrix="$(jq -c '{include:.}' <<<"$entries")"
printf '%s\n' "$matrix"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'matrix=%s\n' "$matrix" >> "$GITHUB_OUTPUT"
fi
