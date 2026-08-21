#!/usr/bin/env bash
set -euo pipefail

# Keep large variable-length audio batches from being trapped in fragmented
# CUDA segments. This does not hide a genuine OOM; it only improves reuse of
# otherwise-free reserved segments. Respect an explicit provider override.
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
if [[ "${RTF_CUDA_DIAGNOSTICS:-0}" == 1 || "${RTF_CUDA_DIAGNOSTICS:-}" == true ]]; then
  export CUDA_LAUNCH_BLOCKING="${CUDA_LAUNCH_BLOCKING:-1}"
  export TORCH_SHOW_CPP_STACKTRACES="${TORCH_SHOW_CPP_STACKTRACES:-1}"
fi

# RunPod's `--docker-args` supplies arguments to the image ENTRYPOINT; it does
# not replace ENTRYPOINT. The lifecycle wrapper uses `sleep infinity` to keep
# the container alive until it can invoke this entrypoint over SSH. Handle
# that control command before translating benchmark arguments.
if {
  [[ "$#" -eq 2 && "${1:-}" == "sleep" && "${2:-}" == "infinity" ]]
} || {
  [[ "$#" -eq 1 && "${1:-}" == "sleep infinity" ]]
}; then
  exec sleep infinity
fi

# HF Jobs commonly supplies `python benchmark.py`; RunPod commonly supplies no
# command. Support both forms while keeping one canonical runner.
if [[ "${1:-}" == "python" && "${2:-}" == "benchmark.py" ]]; then
  shift 2
fi
if [[ "${1:-}" == "--batch-size" ]]; then
  [[ "${2:-}" =~ ^(1|8|32)$ ]] || { echo "--batch-size must be one of 1, 8, or 32" >&2; exit 2; }
  export RTF_BATCH_SIZE="$2"
  shift 2
fi

content_gate=0
if [[ "$#" -eq 0 ]]; then
  content_gate=1
  : "${RTF_DATASET_ID:?RTF_DATASET_ID is required}"
  : "${RTF_DATASET_REVISION:?RTF_DATASET_REVISION is required}"
  : "${RTF_DATASET_CONFIGURATION:=default}"
  : "${RTF_DATASET_SPLIT:=test}"
  : "${RTF_DATASET_SEED:=rtf-benchmark-v1-common-voice-ja}"
  : "${RTF_DATASET_COUNT_MIN:=20}"
  : "${RTF_DATASET_COUNT_MAX:=50}"
  : "${RTF_DATASET_TARGET_TOTAL_SEC:=5400}"
  : "${RTF_INSPECTION_PROFILE:=smoke}"
  : "${RTF_DATASET_MAX_DURATION_SEC:=600}"
  : "${RTF_MANIFEST:=/workspace/benchmark-v1.jsonl}"
  : "${RTF_FIXTURE_REPO_ID:=}"
  : "${RTF_FIXTURE_REVISION:=}"
  : "${RTF_FIXTURE_FILENAME:=benchmark-v1.jsonl}"
  : "${RTF_OUTPUT:=/output/metrics.json}"
  : "${RTF_CONTENT_OUTPUT:=/output/content.json}"
  : "${RTF_RUN_ID:?RTF_RUN_ID is required}"
  : "${RTF_MODEL_ID:?RTF_MODEL_ID is required}"
  : "${RTF_MODEL_REVISION:?RTF_MODEL_REVISION is required}"
  : "${RTF_DECODER:=tdt}"
  : "${RTF_BATCH_SIZE:=1}"
  : "${RTF_PRECISION:=float16}"
  : "${RTF_REPEAT:=3}"
  : "${RTF_PROVIDER:=cuda}"
  : "${RTF_SERVICE_ID:?RTF_SERVICE_ID is required}"
  : "${RTF_GPU:?RTF_GPU is required}"
  : "${RTF_FIXTURE_MANIFEST_SHA256:=}"
  : "${RTF_PROFILE_ID:=${RTF_INSPECTION_PROFILE}}"
  if [[ -n "$RTF_FIXTURE_REPO_ID" ]]; then
    : "${HF_TOKEN:?HF_TOKEN is required when RTF_FIXTURE_REPO_ID is set}"
    : "${RTF_FIXTURE_REVISION:?RTF_FIXTURE_REVISION is required when RTF_FIXTURE_REPO_ID is set}"
    fixture_args=(
      python -m benchmark_runner.load_fixture \
      --repo-id "$RTF_FIXTURE_REPO_ID" --revision "$RTF_FIXTURE_REVISION" \
      --filename "$RTF_FIXTURE_FILENAME" --output-manifest "$RTF_MANIFEST" \
      --audio-dir /workspace/benchmark-audio
    )
    if [[ -n "$RTF_FIXTURE_MANIFEST_SHA256" ]]; then
      fixture_args+=(--expected-manifest-sha256 "$RTF_FIXTURE_MANIFEST_SHA256")
    fi
    "${fixture_args[@]}"
  elif [[ ! -f "$RTF_MANIFEST" ]]; then
    python -m benchmark_runner.resolve_dataset \
      --dataset-id "$RTF_DATASET_ID" --revision "$RTF_DATASET_REVISION" \
      --configuration "$RTF_DATASET_CONFIGURATION" --split "$RTF_DATASET_SPLIT" \
      --count-min "$RTF_DATASET_COUNT_MIN" --count-max "$RTF_DATASET_COUNT_MAX" \
      --target-total-sec "$RTF_DATASET_TARGET_TOTAL_SEC" --max-duration-sec "$RTF_DATASET_MAX_DURATION_SEC" \
      --seed "$RTF_DATASET_SEED" \
      --output-dir /workspace/benchmark-audio --manifest "$RTF_MANIFEST"
  fi
  set -- \
    --manifest "$RTF_MANIFEST" --output "$RTF_OUTPUT" \
    --run-id "$RTF_RUN_ID" --model-id "$RTF_MODEL_ID" \
    --model-revision "$RTF_MODEL_REVISION" --dataset-id "$RTF_DATASET_ID" \
    --dataset-revision "$RTF_DATASET_REVISION" --decoder "$RTF_DECODER" \
    --batch-size "$RTF_BATCH_SIZE" --precision "$RTF_PRECISION" \
    --repeat "$RTF_REPEAT" --provider "$RTF_PROVIDER" \
    --service-id "$RTF_SERVICE_ID" --gpu "$RTF_GPU" \
    --profile "$RTF_PROFILE_ID" --fixture-repo-id "$RTF_FIXTURE_REPO_ID" \
    --fixture-revision "$RTF_FIXTURE_REVISION"
fi

# Content is the first provider acceptance gate. A provider run must return
# one real hypothesis from the pinned fixture before it is allowed to spend
# resources on full-batch timing or publish metrics.
if [[ "$content_gate" -eq 1 ]]; then
  set +e
  python -m benchmark_runner.content_probe \
    --manifest "$RTF_MANIFEST" --output "$RTF_CONTENT_OUTPUT" \
    --run-id "$RTF_RUN_ID" --model-id "$RTF_MODEL_ID" \
    --model-revision "$RTF_MODEL_REVISION" --dataset-id "$RTF_DATASET_ID" \
    --dataset-revision "$RTF_DATASET_REVISION" --decoder "$RTF_DECODER" \
    --precision "$RTF_PRECISION" --provider "$RTF_PROVIDER" \
    --service-id "$RTF_SERVICE_ID" --gpu "$RTF_GPU" \
    --profile "$RTF_PROFILE_ID" --fixture-repo-id "$RTF_FIXTURE_REPO_ID" \
    --fixture-revision "$RTF_FIXTURE_REVISION"
  content_status=$?
  set -e
  if [[ "$content_status" -ne 0 ]]; then
    echo 'provider content gate failed; full metrics execution is blocked' >&2
    exit "$content_status"
  fi
fi

error_log="${RTF_ERROR_LOG:-/tmp/rtf-benchmark-error.log}"
rm -f "$error_log"
set +e
python -m benchmark_runner "$@" 2> "$error_log"
runner_status=$?
set -e
cat "$error_log" >&2 || true

publish_status=0
if [[ -f "${RTF_OUTPUT:-/output/metrics.json}" ]]; then
  python -m benchmark_runner.publish_result || publish_status=$?
fi

if [[ "$runner_status" -ne 0 ]]; then
  if [[ ! -s "${RTF_OUTPUT:-/output/metrics.json}" && ! -s "${RTF_RECEIPT:-/output/result-receipt.json}" ]]; then
    if grep -Eqi 'illegal memory access|cudaErrorIllegalAddress' "$error_log"; then
      export RTF_FAILURE_CODE="PROVIDER_CUDA_ILLEGAL_ACCESS"
      export RTF_FAILURE_MESSAGE="benchmark process terminated with a CUDA illegal memory access"
    elif grep -Eqi 'out of memory|CUDA OOM|cuda out of memory' "$error_log"; then
      export RTF_FAILURE_CODE="PROVIDER_CUDA_OOM"
      export RTF_FAILURE_MESSAGE="benchmark process terminated with CUDA out of memory"
    else
      export RTF_FAILURE_CODE="${RTF_FAILURE_CODE:-BENCHMARK_INFERENCE_FAILED}"
      export RTF_FAILURE_MESSAGE="${RTF_FAILURE_MESSAGE:-benchmark process exited without producing metrics}"
    fi
    python -m benchmark_runner.publish_result || publish_status=$?
  fi
  exit "$runner_status"
fi
exit "$publish_status"
