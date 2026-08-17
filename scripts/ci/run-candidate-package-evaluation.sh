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

path_bytes() {
  python - "$1" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
if not root.exists():
    print(0)
    raise SystemExit(0)
print(sum(path.stat().st_size for path in root.rglob('*') if path.is_file()))
PY
}

path_files() {
  python - "$1" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
print(sum(1 for path in root.rglob('*') if path.is_file()) if root.exists() else 0)
PY
}

if [[ "$DATASET_SOURCE" == "bucket" ]]; then
  hf buckets sync --token "$HF_TOKEN" "hf://buckets/$HF_BUCKET/datasets" .ci/dataset
else
  : "${DATASET_ID:?DATASET_ID is required for repository/custom dataset sources}"
  hf download --repo-type dataset "$DATASET_ID" --local-dir .ci/dataset --token "$HF_TOKEN"
fi

dataset_bytes="$(path_bytes .ci/dataset)"
dataset_files="$(path_files .ci/dataset)"
candidate_bytes=0
candidate_files=0
package_bytes=0

if [[ "$ENVIRONMENT" == linux-* ]]; then
  : "${IMAGE_REF:?IMAGE_REF is required for Linux package evaluation}"
  : "${GHCR_TOKEN:?GHCR_TOKEN is required for Linux package evaluation}"
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin
  docker pull "$IMAGE_REF"
  package_bytes="$(docker image inspect "$IMAGE_REF" --format '{{.Size}}')"
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
  candidate_bytes="$(path_bytes .ci/candidate)"
  candidate_files="$(path_files .ci/candidate)"
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
  --argjson dataset_bytes "$dataset_bytes" \
  --argjson dataset_files "$dataset_files" \
  --argjson candidate_bytes "$candidate_bytes" \
  --argjson candidate_files "$candidate_files" \
  --argjson package_bytes "$package_bytes" \
  '{schema_version:2,source_repository:$source_repository,hf_bucket:$hf_bucket,candidate_id:$candidate_id,image:$image,image_digest:$image_digest,suite:$suite,environment:$environment,provider:$provider,dataset_source:$dataset_source,dataset_id:$dataset_id,dataset_bytes:$dataset_bytes,dataset_files:$dataset_files,candidate_bytes:$candidate_bytes,candidate_files:$candidate_files,package_bytes:$package_bytes}' \
  > results/candidate-package/evaluation-provenance.json
