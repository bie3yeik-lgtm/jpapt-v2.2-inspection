#!/usr/bin/env bash
set -euo pipefail

# HF Jobs commonly supplies `python benchmark.py`; RunPod commonly supplies no
# command. Support both forms while keeping one canonical runner.
if [[ "${1:-}" == "python" && "${2:-}" == "benchmark.py" ]]; then
  shift 2
fi

if [[ "$#" -eq 0 ]]; then
  : "${RTF_DATASET_ID:?RTF_DATASET_ID is required}"
  : "${RTF_DATASET_REVISION:?RTF_DATASET_REVISION is required}"
  : "${RTF_DATASET_CONFIGURATION:=ja}"
  : "${RTF_DATASET_SPLIT:=test}"
  : "${RTF_DATASET_SEED:=rtf-benchmark-v1-common-voice-ja}"
  : "${RTF_DATASET_COUNT_MIN:=20}"
  : "${RTF_DATASET_COUNT_MAX:=50}"
  : "${RTF_DATASET_TARGET_TOTAL_SEC:=5400}"
  : "${RTF_MANIFEST:=/workspace/benchmark-v1.jsonl}"
  : "${RTF_OUTPUT:=/output/metrics.json}"
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
  if [[ ! -f "$RTF_MANIFEST" ]]; then
    python -m benchmark_runner.resolve_dataset \
      --dataset-id "$RTF_DATASET_ID" --revision "$RTF_DATASET_REVISION" \
      --configuration "$RTF_DATASET_CONFIGURATION" --split "$RTF_DATASET_SPLIT" \
      --count-min "$RTF_DATASET_COUNT_MIN" --count-max "$RTF_DATASET_COUNT_MAX" \
      --target-total-sec "$RTF_DATASET_TARGET_TOTAL_SEC" --seed "$RTF_DATASET_SEED" \
      --output-dir /workspace/benchmark-audio --manifest "$RTF_MANIFEST"
  fi
  set -- \
    --manifest "$RTF_MANIFEST" --output "$RTF_OUTPUT" \
    --run-id "$RTF_RUN_ID" --model-id "$RTF_MODEL_ID" \
    --model-revision "$RTF_MODEL_REVISION" --dataset-id "$RTF_DATASET_ID" \
    --dataset-revision "$RTF_DATASET_REVISION" --decoder "$RTF_DECODER" \
    --batch-size "$RTF_BATCH_SIZE" --precision "$RTF_PRECISION" \
    --repeat "$RTF_REPEAT" --provider "$RTF_PROVIDER" \
    --service-id "$RTF_SERVICE_ID" --gpu "$RTF_GPU"
fi

exec python -m benchmark_runner "$@"
