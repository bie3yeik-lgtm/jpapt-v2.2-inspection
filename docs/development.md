# Development

## Supported environments

The repository is designed for:

```text
Linux / WSL2
Windows
macOS Apple Silicon
```

The environments have different responsibilities rather than pretending to be
identical.

## Recommended role split

### Linux / WSL2

Primary responsibilities:

- canonical NeMo development
- Docker reference/export workflows
- Python reference generation
- general CPU correctness
- CUDA when available

### Windows

Primary responsibilities:

- native ONNX Runtime
- CPU
- CUDA
- DirectML
- future Rust deployment

### macOS Apple Silicon

Primary responsibilities:

- ONNX Runtime CPU
- CoreML Execution Provider
- local Apple Silicon CPU/CoreML comparison

The project does not use MLX or native Core ML model conversion as its main
deployment path.

## Bootstrap

Unix-like systems:

```bash
scripts/dev/setup.sh
```

Native Windows:

```powershell
scripts/dev/setup.ps1
```

Both scripts:

- locate repository root
- trust/install mise tools
- create disposable cache/runtime directories
- synchronize the Python environment
- run the development doctor

## Environment doctor

Run:

```bash
mise exec -- uv run python scripts/dev/doctor.py
```

The doctor checks:

- repository layout
- Python
- required packages
- TOML configuration
- JSON Schemas
- manifests
- smoke expected state
- cache directories
- revision staging
- ONNX Runtime providers
- Git state

Warnings are not fatal; failed required checks produce a non-zero exit code.

## Cache locations

Logical defaults:

```text
.cache/
├── models/
├── evaluation/
│   └── audio/
└── huggingface/

.ci/
results/
tmp/
```

Environment configuration lives in:

```text
config/environments/
├── linux.toml
├── windows.toml
└── macos.toml
```

The materialized audio cache should be configured as:

```toml
[path]
materialized_audio_cache = ".cache/evaluation/audio"
```

## Python workflow

The initial implementation is Python-first.

Main source root:

```text
python/src/parakeet_onnx/
```

Major packages:

```text
config/
hf/
run_context/
datasets/
audio/
reference/
export/
runtime/
decoding/
evaluation/
cli/
```

Use the locked uv environment:

```bash
mise exec -- uv run python ...
```

Avoid depending on global Python packages.

## NeMo workflow

Heavy NeMo/reference/export work is isolated in:

```text
docker/Dockerfile.nemo
```

Build:

```bash
docker build \
  -f docker/Dockerfile.nemo \
  -t parakeet-onnx-nemo:26.02 \
  .
```

Typical GPU run:

```bash
docker run \
  --rm \
  -it \
  --gpus all \
  --shm-size=8g \
  -e HF_TOKEN \
  -e HF_BUCKET \
  -e HF_MODEL_REPO \
  -v "$PWD:/workspace" \
  -v parakeet-hf-cache:/workspace/.cache/huggingface \
  parakeet-onnx-nemo:26.02
```

Do not bake secrets into the image.

## Fetch locked revisions

Before canonical reference/export work:

```bash
scripts/hf/hf-fetch-revisions.sh
```

Result:

```text
.ci/hf/config/revisions/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

Do not replace these with floating revisions.

## Dataset flow

```text
manifest
    +
datasets-lock
    ↓
DatasetResolver
    ↓
deterministic sample set
    ↓
DatasetMaterializer
    ↓
ResolvedDatasetSample.audio_path
```

`audio_path` is guaranteed to be a normal local file.

Generic audio processing then produces:

```text
CanonicalAudio
float32 / mono / 16 kHz
```

## Export workflow

Conceptual command once the CLI is complete:

```bash
uv run parakeet-onnx export ...
```

Local export staging:

```text
tmp/export/<candidate-id>/
```

Then upload or stage it as an HF Bucket candidate.

Do not release directly from the exporter.

## Evaluation workflow

Conceptual form:

```bash
uv run parakeet-onnx evaluate \
  --provider cpu \
  --candidate .ci/candidate \
  --manifest evaluation/manifests/parity.jsonl \
  --output results/linux-cpu
```

Expected output:

```text
results/linux-cpu/
├── run-context.json
├── samples.jsonl
└── metrics.json
```

## HF workflow

Fetch candidate:

```bash
scripts/hf/hf-fetch-candidate.sh <candidate-id>
```

Fetch reference:

```bash
scripts/hf/hf-fetch-reference.sh
```

Upload run:

```bash
scripts/hf/hf-push-run.sh results/<run>
```

Upload benchmark:

```bash
scripts/hf/hf-push-benchmark.sh \
  results/<run>/metrics.json \
  <benchmark-name>
```

Promote accepted model:

```bash
scripts/hf/hf-promote-model.sh \
  <candidate-id> \
  results/<accepted-full-run>
```

Dry-run promotion:

```bash
HF_PROMOTION_DRY_RUN=1 \
scripts/hf/hf-promote-model.sh \
  <candidate-id> \
  results/<accepted-full-run>
```

## GitHub Actions

Expected workflows:

```text
.github/workflows/
├── validate-hf-layout.yml
├── cross-platform-parity.yml
└── cpu-full-eval.yml
```

Hosted runners are used.

No self-hosted runner is required by the project design.

### Cross-platform parity

Expected matrix:

```text
ubuntu-latest   CPU
windows-latest  CPU
macos-15        CPU
macos-15        CoreML
```

Hosted macOS CoreML is primarily correctness/parity, not authoritative
performance for a particular local Mac.

### Full evaluation

Canonical hosted full suite:

```text
Ubuntu CPU
768 samples
```

This provides a predictable release gate without requiring specialized hosted
GPU hardware.

## Rust development

Planned crates:

```text
rust/crates/
├── asr-runtime/
├── asr-audio/
├── asr-metrics/
└── asr-eval/
```

Rust is introduced after Python contracts are stable.

The goal is not to duplicate every Python/HF feature.

Initial Rust evaluator input should use already resolved/materialized samples
and the shared JSON contracts.

Primary Rust migration targets:

- audio decode/resample
- standalone frontend where appropriate
- ORT runtime
- CTC/TDT decoding
- CER/WER and timing
- production evaluation/runtime

## Python vs Rust benchmarking

When comparing implementations use:

```text
same ONNX artifact
same artifact SHA-256
same EP
same sample set
same batch size
same decoder
same machine where possible
```

Compare separately:

- ORT-only inference time
- total end-to-end time
- non-ORT overhead
- peak RAM

Moving from Python to Rust does not imply that native ORT kernel execution
itself becomes substantially faster.

## Tools

`tools/` is reserved for optional developer diagnostics.

Examples of future candidates:

```text
inspect_onnx.py
inspect_ort.py
inspect_audio.py
inspect_manifest.py
compare_tensors.py
compare_runs.py
```

Official runtime/evaluation logic must remain in the Python/Rust packages, not
leak into ad-hoc tools.

## Git hygiene

Do not commit:

```text
.cache/
.ci/
results/
tmp/
target/
.venv/

*.onnx
*.nemo
*.npy
*.npz
*.wav
*.flac
```

The repository should remain source/configuration oriented.

## Recommended development order

```text
1. configuration and revision locking
2. deterministic dataset resolution
3. audio materialization/canonicalization
4. NeMo reference path
5. CTC ONNX export
6. ORT CPU parity
7. cross-platform EP parity
8. full evaluation
9. release promotion
10. Rust runtime migration
11. TDT deployment path
```

This sequence keeps the simplest CTC path as the first deployment baseline and
avoids mixing reference, provider, and language-porting problems at the same
time.
