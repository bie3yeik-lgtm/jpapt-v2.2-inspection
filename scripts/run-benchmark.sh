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
: "${RTF_FIXTURE_REPO_ID:?RTF_FIXTURE_REPO_ID is required}"
: "${RTF_FIXTURE_REVISION:?RTF_FIXTURE_REVISION is required}"
: "${RTF_RESULT_REPO_ID:=gawohok7/rtf-benchmark-fixtures}"
: "${RTF_RESULT_PATH:=results/${RTF_RUN_ID}/metrics.json}"
: "${RTF_IMAGE_DIGEST:=${IMAGE##*@}}"
if [[ "$RTF_IMAGE_DIGEST" == *@* ]]; then
  RTF_IMAGE_DIGEST="${RTF_IMAGE_DIGEST##*@}"
fi
[[ "$RTF_IMAGE_DIGEST" =~ ^sha256:[0-9a-fA-F]{64}$ ]] || {
  echo "RTF_IMAGE_DIGEST must be sha256-pinned" >&2
  exit 2
}
: "${RTF_GPU:?RTF_GPU is required}"
: "${RTF_OUTPUT:=/output/metrics.json}"
: "${RTF_BATCH_SIZE:=1}"
: "${RTF_PRECISION:=float16}"
: "${RTF_DECODER:=tdt}"
: "${RTF_SERVICE_ID:=${PROVIDER}-job}"
: "${HF_FLAVOR:=a10g-small}"
: "${RUNPOD_GPU_ID:=${RTF_GPU}}"

case "$PROVIDER:$RTF_GPU" in
  hf:t4|hf:l4|runpod:a5000|runpod:l4|runpod:rtx3090|runpod:rtx4090) ;;
  *) echo "provider/GPU is outside the Phase 1 RTF matrix: $PROVIDER/$RTF_GPU" >&2; exit 2 ;;
esac

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
      -e "RTF_FIXTURE_REPO_ID=$RTF_FIXTURE_REPO_ID" -e "RTF_FIXTURE_REVISION=$RTF_FIXTURE_REVISION"
      -e "RTF_RESULT_REPO_ID=$RTF_RESULT_REPO_ID" -e "RTF_RESULT_PATH=$RTF_RESULT_PATH"
      -e "RTF_IMAGE_DIGEST=$RTF_IMAGE_DIGEST"
      -e "RTF_BATCH_SIZE=$RTF_BATCH_SIZE" -e "RTF_PRECISION=$RTF_PRECISION"
      -e "RTF_DECODER=$RTF_DECODER" -e "RTF_PROVIDER=cuda" -e "RTF_SERVICE_ID=hf-jobs"
    )
    [[ -n "${HF_TOKEN:-}" ]] || { echo "HF_TOKEN is required for HF Jobs" >&2; exit 1; }
    hf_log="${RTF_HF_LOG:-hf-job.log}"
    set +e
    hf jobs run --flavor "$HF_FLAVOR" "${hf_env[@]}" \
      --secrets "HF_TOKEN=$HF_TOKEN" "$IMAGE" python benchmark.py 2>&1 | tee "$hf_log"
    hf_status=${PIPESTATUS[0]}
    set -e
    receipt_line="$(grep '^RTF_RESULT_RECEIPT=' "$hf_log" | tail -n 1 || true)"
    [[ -n "$receipt_line" ]] || {
      echo 'HF Job did not emit RTF_RESULT_RECEIPT' >&2
      exit "$hf_status"
    }
    printf '%s\n' "${receipt_line#RTF_RESULT_RECEIPT=}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
    [[ "$hf_status" -eq 0 ]] || exit "$hf_status"
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
      --arg decoder "$RTF_DECODER" --arg fixture_repo "$RTF_FIXTURE_REPO_ID" \
      --arg fixture_revision "$RTF_FIXTURE_REVISION" --arg hf_token "${HF_TOKEN:-}" \
      --arg result_repo "$RTF_RESULT_REPO_ID" --arg result_path "$RTF_RESULT_PATH" \
      --arg image_digest "$RTF_IMAGE_DIGEST" \
      '{RTF_RUN_ID:$run_id,RTF_MANIFEST:$manifest,RTF_OUTPUT:$output,RTF_MODEL_ID:$model_id,RTF_MODEL_REVISION:$model_revision,RTF_DATASET_ID:$dataset_id,RTF_DATASET_REVISION:$dataset_revision,RTF_GPU:$gpu,RTF_BATCH_SIZE:$batch,RTF_PRECISION:$precision,RTF_DECODER:$decoder,RTF_FIXTURE_REPO_ID:$fixture_repo,RTF_FIXTURE_REVISION:$fixture_revision,RTF_RESULT_REPO_ID:$result_repo,RTF_RESULT_PATH:$result_path,RTF_IMAGE_DIGEST:$image_digest,HF_TOKEN:$hf_token,RTF_PROVIDER:"cuda",RTF_SERVICE_ID:"runpod-pod"}')"
    pod_json="$(runpodctl pod create --name "${RTF_RUN_ID}" --image "$IMAGE" \
      --gpu-id "$RUNPOD_GPU_ID" --env "$env_json" --docker-args 'sleep infinity' --wait --output json)"
    pod_id="$(jq -er '.id // .podId // .pod_id' <<<"$pod_json")"
    runpodctl exec "$pod_id" -- python benchmark.py
    runpodctl exec "$pod_id" -- cat "$RTF_OUTPUT" > "${RTF_LOCAL_OUTPUT:-metrics.json}"
    runpodctl exec "$pod_id" -- cat "${RTF_RECEIPT:-/output/result-receipt.json}" > "${RTF_LOCAL_RECEIPT:-result-receipt.json}"
    ;;
esac
