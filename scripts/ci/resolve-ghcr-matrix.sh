#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

fail() {
  printf '[ghcr-matrix] ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf '[ghcr-matrix] WARNING: %s\n' "$*" >&2
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

# Static GHCR target contexts are explicitly identified by config.json. Generic
# runtime-parametric Dockerfiles (for example docker/candidate-package) do not
# represent one source model and must never be forced into this static matrix.
mapfile -t target_configs < <(find docker -mindepth 2 -maxdepth 2 -type f -name config.json -print | sort)
(( ${#target_configs[@]} > 0 )) || fail "docker/*/config.json static target definitions were not found"

mapfile -t repository_targets < <(
  find config/hf-targets -maxdepth 1 -type f -name '*.toml' -printf '%f\n' \
    | sed 's/\.toml$//' \
    | sort
)
(( ${#repository_targets[@]} > 0 )) || fail "config/hf-targets contains no target definitions"

# HF_TARGETS_JSON is a checked routing/selection snapshot, not an authority
# capable of creating a new target. Extra variable entries are ignored until
# the repository has the corresponding config/hf-targets/<id>.toml contract.
while IFS= read -r variable_target; do
  [[ -n "$variable_target" ]] || continue
  if [[ ! -f "config/hf-targets/${variable_target}.toml" ]]; then
    warn "HF_TARGETS_JSON contains ${variable_target}, but the repository has no source-controlled target definition; ignoring it"
  fi
done < <(printf '%s' "$HF_TARGETS_JSON" | jq -r 'keys[]')

for config in "${target_configs[@]}"; do
  context="$(dirname "$config")"
  dockerfile="$context/Dockerfile"
  [[ -f "$dockerfile" ]] || fail "$context declares config.json but has no Dockerfile"

  source_repo="$(sed -n 's/^LABEL io\.jpapt\.source\.repo_id="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"
  source_framework="$(sed -n 's/^LABEL io\.jpapt\.source\.framework="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"
  package="$(sed -n 's/^LABEL io\.jpapt\.ghcr\.package="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"
  role="$(sed -n 's/^LABEL io\.jpapt\.role="\([^"]*\)"[[:space:]]*$/\1/p' "$dockerfile" | tail -n1)"

  [[ -n "$source_repo" ]] || fail "$dockerfile must declare LABEL io.jpapt.source.repo_id"
  [[ -n "$source_framework" ]] || fail "$dockerfile must declare LABEL io.jpapt.source.framework"
  [[ -n "$package" ]] || fail "$dockerfile must declare LABEL io.jpapt.ghcr.package"
  [[ -n "$role" ]] || fail "$dockerfile must declare LABEL io.jpapt.role"
  test "$(jq -er '.source.repo_id' "$config")" = "$source_repo" \
    || fail "$config source.repo_id disagrees with $dockerfile"
  test "$(jq -er '.source.framework' "$config")" = "$source_framework" \
    || fail "$config source.framework disagrees with $dockerfile"

  for target_id in "${repository_targets[@]}"; do
    if [[ -n "$TARGET_FILTER" && "$target_id" != "$TARGET_FILTER" ]]; then
      continue
    fi

    route="$(printf '%s' "$HF_TARGETS_JSON" | jq -ce --arg id "$target_id" '.[$id] // empty')"
    if [[ -z "$route" ]]; then
      warn "source-controlled target ${target_id} is absent from HF_TARGETS_JSON; excluding it from GHCR evaluation"
      continue
    fi
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
  done
done

(( matched > 0 )) || fail "no static Docker target matched a source-controlled HF target present in HF_TARGETS_JSON${TARGET_FILTER:+ (filter=$TARGET_FILTER)}"

matrix="$(jq -c '{include:.}' <<<"$entries")"
printf '%s\n' "$matrix"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'matrix=%s\n' "$matrix" >> "$GITHUB_OUTPUT"
fi
