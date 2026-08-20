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
13. Rust is the canonical implementation language for production/runtime,
    validation, evaluation orchestration, capsule persistence, analytics, and
    other behavior that can be implemented without Python-only ML tooling.
14. Python must be kept as a thin compatibility/reference layer. New Python
    production logic requires a concrete reason why the responsibility cannot
    live in Rust.
15. Python remains appropriate at boundaries that are intrinsically tied to
    Python-first ecosystems such as NeMo/PyTorch model export or a Hugging Face
    API that has no adequate Rust/CLI equivalent. Keep those boundaries narrow,
    explicit, deterministic, and machine-readable.
16. When a stable Python contract already exists, migrate it to Rust behind
    compatibility tests before deleting or reducing the Python implementation.
17. Shell and PowerShell remain orchestration wrappers only; they should invoke
    Rust binaries for core behavior whenever a Rust implementation exists.

## Repository responsibilities

```text
config/       static configuration
evaluation/   schemas, manifests, lightweight expected data
rust/         canonical production/runtime/validation implementation
python/       thin Python-only ML/HF compatibility and reference layer
scripts/      operational wrappers only
docker/       canonical NeMo reference/export environment
docs/         architecture and workflow documentation
tools/        optional inspection/diagnostic utilities
```

## Rust-first migration order

Prefer migration in this order so each phase reduces Python runtime surface
without destabilizing model export:

```text
1. capsule read/validate/analytics + run validation
2. JSON contract validation and generated-candidate I/O
3. evaluation orchestration and dataset-manifest handling
4. Hugging Face operational logic where CLI/API support is sufficient
5. model-independent preprocessing/frontend utilities
6. Python-only export/reference code last
```

For a migrated responsibility, CI must prove compatibility against existing
fixtures/contracts before the Python implementation is removed.

## Do not place production logic in scripts

Shell and PowerShell scripts must remain thin wrappers.

Core behavior belongs primarily under:

```text
rust/crates/
```

Python-only boundary behavior may live under:

```text
python/src/parakeet_onnx/
```

Existing protocol/CI compatibility helpers under `scripts/ci/` may remain while
their contracts are being migrated, but do not expand them into a second
runtime authority when the same responsibility can live in Rust.

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

Supported active logical EPs in the current project specification:

```text
cpu
cuda
coreml
```

Platform boundaries are part of the contract:

```text
CPU       Linux / Windows / macOS
CUDA      Linux GPU
CoreML    macOS / Apple Silicon
```

CoreML means ONNX Runtime CoreML Execution Provider only. DirectML is retired;
old DirectML artifacts are historical audit data only and are not an active
execution or acceptance route.

Keep provider registration, successful session creation, successful inference,
provider execution proof, and node-assignment proof separate. Non-CPU strict
provider runs must not silently pass through CPU fallback.

Do not introduce MLX or native Core ML model conversion into the canonical
runtime path unless the project specification is explicitly changed.

## Hugging Face lifecycle

### DirectML retirement

DirectML is retired from the active JPAPT contract as of 2026-08-20. New
DirectML or `windows-directml` requests, dispatches, receipts, HF Jobs, and
Bucket completion claims are rejected. Existing DirectML workflow code and
artifacts remain only for historical audit and must not be extended.

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
