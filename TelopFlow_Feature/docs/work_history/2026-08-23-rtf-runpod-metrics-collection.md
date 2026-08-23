# RunPod RTF metrics collection remediation

## Objective

Ensure that a RunPod benchmark does not publish a completed result while
provider metrics required by `asr-rtf-rank` are absent. The provider adapter
must carry the rented GPU price into the container, and the benchmark runner
must collect GPU utilization during the timed inference.

## Changed responsibility

- `scripts/run-benchmark.sh` reads the effective `adjustedCostPerHr` first,
  then `costPerHr` (including snake_case compatibility), accepting the string
  representation documented by the RunPod REST API, and transfers it as
  `RTF_GPU_PRICE_PER_HOUR`.
- A ready Pod without a numeric price stops before remote execution with
  `RUNPOD_GPU_PRICE_UNAVAILABLE`.
- `benchmark_runner/cli.py` samples `nvidia-smi` every 0.5 seconds only during
  timed inference, averages valid values, and calculates
  `cost_per_audio_hour = gpu_price_per_hour * rtf`.
- RunPod results are blocked with a typed error when the price or utilization
  metric is unavailable. HF Jobs are allowed to retain provider-null metrics
  when the service does not expose them.

## Contract relation

`build-rtf-benchmark-record.py` already maps the service metrics to
`gpu_utilization_percent`, `gpu_price_per_hour`, and `cost_per_audio_hour`.
The Rust ranker excludes records with missing CER or cost, and Rust contract
validation rejects completed records with missing CER or GPU price. This
change therefore supplies the provider-side cost inputs without weakening
the Rust acceptance gate.

## Verification evidence

Executed on the implementation branch:

```text
bash -n scripts/run-benchmark.sh scripts/ci/test-rtf-provider-adapters.sh docker/rtf-benchmark/entrypoint.sh   PASS
python -m py_compile <benchmark_runner Python files>                                                        PASS
uv run ruff check docker/rtf-benchmark/benchmark-runner/benchmark_runner/cli.py                             PASS
git diff --check                                                                                             PASS
bash scripts/ci/test-rtf-provider-adapters.sh --mode mock --provider all                                      PASS
```

The mock verifies provider environment transfer and covers normal RunPod,
no-instance, low-balance, Pod-create-timeout, and SSH-info failure paths.
No live Pod was created by this change.

## Official provider constraints

RunPod documents `costPerHr` as the hourly credit price and
`adjustedCostPerHr` as the effective price after Savings Plans. RunPod also
documents that Pods are billed by the second and that billing history is
available separately. The benchmark uses the effective hourly price as a
deterministic estimate for `cost_per_audio_hour`; it does not claim that this
is a post-run invoice total.

The official RunPod Pod API documents `costPerHr` and `adjustedCostPerHr` in
the Pod response, and the `runpodctl pod get` documentation defines that
command as the detailed Pod lookup used by the adapter:

- <https://docs.runpod.io/api-reference/pods/GET/pods/podId>
- <https://docs.runpod.io/pods/pricing>
- <https://docs.runpod.io/runpodctl/reference/runpodctl-pod>

The Hugging Face Dataset Viewer documentation exposes dataset feature names
and row values. The locked Common Voice dataset displays audio and
transcription text; its source convention is `sentence`. The fixture loader
now normalizes `sentence` (and explicit transcript aliases) to the canonical
`text` field before content probing and CER calculation:

- <https://huggingface.co/docs/dataset-viewer/en/quick_start>
- <https://huggingface.co/datasets/japanese-asr/ja_asr.common_voice_8_0>

## Remaining external dependency

Any fixture line that lacks a non-empty `text`, `sentence`, `transcription`,
or `reference_text` is now rejected before inference. The runner must not
fabricate transcription references. The fixture/resolver producer must
therefore publish pinned, non-empty transcript values; otherwise the run is
blocked rather than producing a rankable record. This is separate from
RunPod price and utilization collection.

## Rollback

Revert the adapter and runner changes together. Existing result artifacts are
not rewritten, and no provider-side resource is mutated by the implementation
itself.
