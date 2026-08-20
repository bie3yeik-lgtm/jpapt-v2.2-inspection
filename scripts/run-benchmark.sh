#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --provider {hf|runpod} --image <digest-pinned-image>" >&2
  exit 2
}

PROVIDER=""
IMAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) PROVIDER="${2:?missing provider}"; shift 2 ;;
    --image) IMAGE="${2:?missing image}"; shift 2 ;;
    *) usage ;;
  esac
done
[[ "$PROVIDER" == "hf" || "$PROVIDER" == "runpod" ]] || usage
[[ -n "$IMAGE" ]] || usage

: "${RTF_RUN_ID:?RTF_RUN_ID is required}"
: "${RTF_MANIFEST:=/workspace/benchmark-v1.jsonl}"
: "${RTF_MODEL_ID:?RTF_MODEL_ID is required}"
: "${RTF_MODEL_REVISION:?RTF_MODEL_REVISION is required}"
: "${RTF_DATASET_ID:?RTF_DATASET_ID is required}"
: "${RTF_DATASET_REVISION:?RTF_DATASET_REVISION is required}"
: "${RTF_GPU:?RTF_GPU is required}"
: "${RTF_OUTPUT:=/output/metrics.json}"
: "${RTF_BATCH_SIZE:=1}"
: "${RTF_PRECISION:=float16}"
: "${RTF_DECODER:=tdt}"
: "${RTF_SERVICE_ID:=${PROVIDER}-job}"
: "${HF_FLAVOR:=a10g-small}"
: "${RUNPOD_GPU_ID:=${RTF_GPU}}"

case "$PROVIDER" in
  hf)
    command -v hf >/dev/null || { echo "hf CLI is required" >&2; exit 1; }
    # The image entrypoint consumes these variables. Do not print this command:
    # it contains the provider credential when HF_JOB_ENV is configured.
    hf_env=(
      -e "RTF_RUN_ID=$RTF_RUN_ID" -e "RTF_MANIFEST=$RTF_MANIFEST"
      -e "RTF_OUTPUT=$RTF_OUTPUT" -e "RTF_MODEL_ID=$RTF_MODEL_ID"
      -e "RTF_MODEL_REVISION=$RTF_MODEL_REVISION" -e "RTF_DATASET_ID=$RTF_DATASET_ID"
      -e "RTF_DATASET_REVISION=$RTF_DATASET_REVISION" -e "RTF_GPU=$RTF_GPU"
      -e "RTF_BATCH_SIZE=$RTF_BATCH_SIZE" -e "RTF_PRECISION=$RTF_PRECISION"
      -e "RTF_DECODER=$RTF_DECODER" -e "RTF_PROVIDER=cuda" -e "RTF_SERVICE_ID=hf-jobs"
    )
    hf_secrets=()
    [[ -n "${HF_TOKEN:-}" ]] && hf_secrets=(--secrets HF_TOKEN)
    hf jobs run --flavor "$HF_FLAVOR" "${hf_env[@]}" "${hf_secrets[@]}" "$IMAGE" python benchmark.py
    ;;
  runpod)
    command -v runpodctl >/dev/null || { echo "runpodctl is required" >&2; exit 1; }
    pod_id=""
    cleanup() {
      if [[ -n "$pod_id" ]]; then
        runpodctl pod delete "$pod_id" >/dev/null || true
      fi
    }
    trap cleanup EXIT
    env_json="$(jq -cn \
      --arg run_id "$RTF_RUN_ID" --arg manifest "$RTF_MANIFEST" \
      --arg output "$RTF_OUTPUT" --arg model_id "$RTF_MODEL_ID" \
      --arg model_revision "$RTF_MODEL_REVISION" --arg dataset_id "$RTF_DATASET_ID" \
      --arg dataset_revision "$RTF_DATASET_REVISION" --arg gpu "$RTF_GPU" \
      --arg batch "$RTF_BATCH_SIZE" --arg precision "$RTF_PRECISION" \
      --arg decoder "$RTF_DECODER" \
      '{RTF_RUN_ID:$run_id,RTF_MANIFEST:$manifest,RTF_OUTPUT:$output,RTF_MODEL_ID:$model_id,RTF_MODEL_REVISION:$model_revision,RTF_DATASET_ID:$dataset_id,RTF_DATASET_REVISION:$dataset_revision,RTF_GPU:$gpu,RTF_BATCH_SIZE:$batch,RTF_PRECISION:$precision,RTF_DECODER:$decoder,RTF_PROVIDER:"cuda",RTF_SERVICE_ID:"runpod-pod"}')"
    pod_json="$(runpodctl pod create --name "${RTF_RUN_ID}" --image "$IMAGE" \
      --gpu-id "$RUNPOD_GPU_ID" --env "$env_json" --docker-args 'sleep infinity' --wait --output json)"
    pod_id="$(jq -er '.id // .podId // .pod_id' <<<"$pod_json")"
    runpodctl exec "$pod_id" -- python benchmark.py
    runpodctl exec "$pod_id" -- cat "$RTF_OUTPUT" > "${RTF_LOCAL_OUTPUT:-metrics.json}"
    ;;
esac
