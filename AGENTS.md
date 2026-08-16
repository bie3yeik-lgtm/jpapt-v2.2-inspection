# AGENTS.md

## Project objective

Develop and validate ONNX deployment artifacts for Japanese ASR, beginning
with `nvidia/parakeet-tdt_ctc-0.6b-ja`.

## Required engineering rules

1. Prefer deterministic and revision-pinned workflows.
2. Do not use floating model or dataset revisions in canonical evaluation.
3. Do not commit large model, audio, tensor, or dataset artifacts.
4. Keep Hugging Face Bucket development artifacts separate from final Model
   Repo releases.
5. Keep model, provider, environment, and evaluation configuration separated.
6. Treat ONNX as a deployment artifact, not the canonical source model.
7. Implement the CTC deployment path before TDT.
8. Keep generic audio processing separate from model-specific frontend logic.
9. Preserve the canonical waveform contract:
    - float32
    - mono
    - 16000 Hz
    - finite
    - C-contiguous
10. `ResolvedDatasetSample.audio_path` must refer to a materialized local file.
11. Candidate output must never overwrite expected/reference data.
12. Promotion requires accepted evaluation and verified artifact SHA-256.
13. Python is the initial implementation language.
14. Rust should adopt stable contracts rather than reimplementing unresolved
    Python/Hugging Face behavior prematurely.

## Repository responsibilities

```text
config/       static configuration
evaluation/   schemas, manifests, lightweight expected data
python/       canonical Python implementation
rust/         future production/runtime implementation
scripts/      operational wrappers
docker/       canonical NeMo reference/export environment
docs/         architecture and workflow documentation
tools/        optional inspection/diagnostic utilities
```

## Do not place production logic in scripts

Shell and PowerShell scripts must remain thin wrappers.

Core behavior belongs under:

```text
python/src/parakeet_onnx/
```

or later:

```text
rust/crates/
```

## Git restrictions

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
*.safetensors
*.npy
*.npz
*.wav
*.flac
```

## Validation expectations

Before considering an ONNX candidate correct, distinguish:

```text
frontend parity
encoder parity
logits parity
token parity
text parity
ASR quality
performance
provider fallback
```

Do not use final transcript equality as the only numerical correctness test.

## Execution Providers

Supported logical EPs:

```text
cpu
cuda
directml
coreml
```

CoreML means ONNX Runtime CoreML Execution Provider only.

Do not introduce MLX or native Core ML model conversion into the canonical
runtime path unless the project specification is explicitly changed.

## Hugging Face lifecycle

Development:

```text
HF Bucket/candidates/
HF Bucket/reference/
HF Bucket/runs/
HF Bucket/benchmarks/
```

Release:

```text
HF Model Repo
```

Do not promote unvalidated candidates directly.

## Development commands

Environment setup:

```bash
scripts/dev/setup.sh
```

Doctor:

```bash
mise exec -- uv run python scripts/dev/doctor.py
```

Fetch revision locks:

```bash
scripts/hf/hf-fetch-revisions.sh
```

Promotion:

```bash
scripts/hf/hf-promote-model.sh <candidate-id> <accepted-run-directory>
```
