# RTF CPU Benchmark Action

`.github/workflows/rtf-cpu-benchmark-run.yml` is the CPU-only RTF benchmark
entry point. It deliberately exposes only these services:

- `hf-inference-endpoint`: an already provisioned Hugging Face Inference
  Endpoint configured with `accelerator=cpu`. The workflow sends fixture WAV
  bytes to `endpoint_url` (or the `HF_INFERENCE_ENDPOINT_URL` secret) and
  measures client-observed service RTF.
- `runpod-pod`: a temporary RunPod Pod created with `--compute-type cpu`. The
  digest-pinned RTF image is executed over SSH with `RTF_PROVIDER=cpu`.

The CPU target is recorded in the existing `gpu` contract field so the Rust
ranking contract remains unchanged. Use an HF instance label such as
`intel-spr-x4` for the HF lane and a RunPod CPU label such as `cpu3c` for the
RunPod lane. The selected target is not inferred from the endpoint response;
the endpoint or provider configuration must match the dispatch input.

Both lanes run guarded batch 1 by default. `full-matrix` runs batch 1, 8, and
32 sequentially. Results are collected through the existing service-result
workflow and stored under:

```text
rtf-scores/smoke/hf-inference-endpoint/<cpu-target>/batch-<n>/
rtf-scores/smoke/runpod-pod/<cpu-target>/batch-<n>/
```

CPU metrics use `provider=cpu`, `environment=linux`, `dtype=float32`, and null
GPU telemetry. If a known hourly CPU price is supplied, it is recorded in the
legacy `gpu_price_per_hour` field and used to calculate
`cost_per_audio_hour`; without a price, the result remains valid metrics but is
excluded from cost-based ranking.

The HF lane does not create or mutate an Endpoint. This is intentional: HF
Inference Endpoint creation, quota, scale-to-zero, and billing are separate
provider lifecycle concerns. The endpoint must already expose an audio-to-text
HTTP response containing `text`, `generated_text`, or `transcription`.

The RunPod lane follows the official CPU Pod contract: `compute-type cpu`, no
GPU ID, bounded readiness polling, SSH execution, and cleanup on exit.

- [HF Inference Endpoint pricing and CPU instances](https://huggingface.co/docs/inference-endpoints/en/support/pricing)
- [HF Inference Endpoint configuration](https://huggingface.co/docs/inference-endpoints/guides/configuration)
- [RunPod CPU Pod CLI](https://docs.runpod.io/runpodctl/reference/runpodctl-pod)
- [RunPod Pod API](https://docs.runpod.io/api-reference/pods/POST/pods)
