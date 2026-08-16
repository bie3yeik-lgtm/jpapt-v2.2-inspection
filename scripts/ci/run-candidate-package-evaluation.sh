#!/usr/bin/env bash
set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is required}"
: "${HF_BUCKET:?HF_BUCKET is required}"
: "${CANDIDATE_ID:?CANDIDATE_ID is required}"
: "${SUITE:?SUITE is required}"
: "${PROVIDER:?PROVIDER is required}"
: "${ENVIRONMENT:?ENVIRONMENT is required}"
: "${DATASET_SOURCE:?DATASET_SOURCE is required}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
mkdir -p .ci/dataset results/candidate-package

if [[ "$DATASET_SOURCE" == "bucket" ]]; then
  hf buckets sync --token "$HF_TOKEN" "hf://buckets/$HF_BUCKET/datasets" .ci/dataset
else
  : "${DATASET_ID:?DATASET_ID is required for repository/custom dataset sources}"
  hf download --repo-type dataset "$DATASET_ID" --local-dir .ci/dataset --token "$HF_TOKEN"
fi

if [[ "$ENVIRONMENT" == linux-* ]]; then
  : "${IMAGE_REF:?IMAGE_REF is required for Linux package evaluation}"
  : "${GHCR_TOKEN:?GHCR_TOKEN is required for Linux package evaluation}"
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin
  docker pull "$IMAGE_REF"
  gpu_args=()
  [[ "$ENVIRONMENT" == "linux-cuda" ]] && gpu_args=(--gpus all)
  docker run --rm "${gpu_args[@]}" \
    -v "$PWD/.ci/dataset:/data:ro" \
    -v "$PWD/results/candidate-package:/results" \
    "$IMAGE_REF" \
    --suite "$SUITE" \
    --provider "$PROVIDER" \
    --dataset-dir /data \
    --output /results/result.json
else
  export HF_BUCKET CANDIDATE_ID
  bash scripts/hf/hf-fetch-candidate.sh "$CANDIDATE_ID"
  python scripts/ci/generic-candidate-evaluate.py \
    --candidate-dir .ci/candidate \
    --dataset-dir .ci/dataset \
    --suite "$SUITE" \
    --provider "$PROVIDER" \
    --output results/candidate-package/result.json
fi

jq -n \
  --arg source_repository "${SOURCE_REPOSITORY:-}" \
  --arg hf_bucket "$HF_BUCKET" \
  --arg candidate_id "$CANDIDATE_ID" \
  --arg image "${IMAGE_REF:-}" \
  --arg image_digest "${IMAGE_DIGEST:-}" \
  --arg suite "$SUITE" \
  --arg environment "$ENVIRONMENT" \
  --arg provider "$PROVIDER" \
  --arg dataset_source "$DATASET_SOURCE" \
  --arg dataset_id "${DATASET_ID:-}" \
  '{schema_version:1,source_repository:$source_repository,hf_bucket:$hf_bucket,candidate_id:$candidate_id,image:$image,image_digest:$image_digest,suite:$suite,environment:$environment,provider:$provider,dataset_source:$dataset_source,dataset_id:$dataset_id}' \
  > results/candidate-package/evaluation-provenance.json
