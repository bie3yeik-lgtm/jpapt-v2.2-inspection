# Architecture

## Purpose

This repository develops, validates, and promotes ONNX deployment artifacts for
Japanese ASR models, with `nvidia/parakeet-tdt_ctc-0.6b-ja` as the primary
model.

The project uses NVIDIA NeMo as the canonical reference environment and ONNX
Runtime as the portable deployment runtime.

The initial implementation is Python-first. Rust is introduced later for
deployment/runtime code after the Python reference and evaluation contracts are
stable.

## Architectural principles

1. The upstream model/reference revision is always pinned.
2. Evaluation dataset revisions are always pinned.
3. Large model, audio, and tensor artifacts are not stored in Git.
4. Hugging Face Bucket is used for mutable development/evaluation artifacts.
5. Hugging Face Model Repo contains only validated release artifacts.
6. NeMo is the canonical reference implementation.
7. ONNX Runtime is the deployment/runtime abstraction.
8. CPU, CUDA, DirectML, and CoreML are Execution Provider concerns, not model
   definitions.
9. Generic audio processing is separated from model-specific feature extraction.
10. Python and future Rust evaluators consume the same logical data contracts.

## Repository layers

```text
config/
    Static model, provider, environment, and evaluation configuration.

evaluation/
    JSON Schemas, deterministic manifests, and Git-tracked smoke expectations.

python/src/parakeet_onnx/
    Canonical Python implementation.

rust/crates/
    Future production/runtime implementation.

scripts/
    Thin operational wrappers for development, CI, and Hugging Face lifecycle.

docker/
    Isolated canonical NeMo reference/export environment.

docs/
    Architectural and operational documentation.

tools/
    Optional developer inspection and diagnostic utilities.
```

## External storage

The project separates Git, Hugging Face Bucket, and Hugging Face Model Repo.

```text
GitHub Repository
    source code
    configuration
    schemas
    manifests
    lightweight expected data
          |
          v
Hugging Face Bucket
    config/revisions/
    candidates/
    reference/
    runs/
    benchmarks/
          |
          | validated promotion
          v
Hugging Face Model Repo
    released ONNX artifacts
    tokenizer/metadata
    release provenance
```

### Hugging Face Bucket

Expected layout:

```text
hf://buckets/<namespace>/<bucket>/
├── config/
│   └── revisions/
│       ├── reference.json
│       ├── evaluation-schema.json
│       └── datasets-lock.json
├── benchmarks/
├── runs/
├── candidates/
├── reference/
├── scripts/
└── tmp/
```

`reference.json` identifies the exact upstream model/reference revisions.

`datasets-lock.json` identifies the exact dataset revisions.

`evaluation-schema.json` identifies the acceptance-rule revision and numerical
thresholds. It is not a JSON Schema document.

### Hugging Face Model Repo

The Model Repo is the release boundary.

A typical promoted release contains:

```text
README.md
model.onnx
metadata.json
tokenizer/
release/
├── run-context.json
├── metrics.json
└── promotion.json
```

Candidates must not be exported directly into the Model Repo.

## Canonical ASR pipeline

The first deployment target is the CTC path.

```text
audio asset
    ↓
decode
    ↓
DecodedAudio
    ↓
downmix + resample
    ↓
CanonicalAudio
float32 / mono / 16 kHz
    ↓
model frontend
    ↓
FastConformer encoder
    ↓
CTC logits
    ↓
CTC collapse/token decoding
    ↓
text
```

TDT support is added after the CTC deployment path is stable.

## Dataset boundary

Evaluation manifests do not contain explicit hundreds of selected rows. They
contain deterministic selection directives.

```text
evaluation/manifests/*.jsonl
        +
datasets-lock.json
        ↓
DatasetResolver
        ↓
stable-hash selection
        ↓
DatasetMaterializer
        ↓
ResolvedDatasetSample
```

`ResolvedDatasetSample.audio_path` has a strict meaning:

> A materialized local audio asset that the evaluation runtime can read through
> ordinary file I/O.

It must not be a remote URL, Arrow reference, temporary HF Dataset object, or
other opaque reference.

## Audio boundary

Generic audio processing stops at `CanonicalAudio`.

```text
ResolvedDatasetSample.audio_path
        ↓
decode_audio_sample()
        ↓
DecodedAudio
        ↓
to_canonical_audio()
        ↓
CanonicalAudio
```

Canonical audio contract:

```text
dtype       float32
shape       [samples]
channels    mono
sample rate 16000 Hz
finite      yes
memory      C-contiguous
```

Model-specific feature extraction starts after this boundary.

This allows Python and Rust implementations to compare the exact same
canonical waveform before frontend parity is evaluated.

## Reference and candidate paths

Reference:

```text
CanonicalAudio
      ↓
NeMo preprocessor
      ↓
reference frontend output
      ↓
NeMo encoder/head
      ↓
reference logits/tokens/text
```

Candidate:

```text
CanonicalAudio
      ↓
candidate frontend
      ↓
ONNX encoder/head
      ↓
candidate logits/tokens/text
```

Parity checkpoints include:

```text
frontend
encoder
logits
tokens
text
CER/WER
```

## Runtime configuration

Configuration is intentionally namespaced instead of blindly deep-merged.

```text
config/models/
config/providers/
config/environments/
config/evaluation/
```

Model configuration describes the model.

Provider configuration describes the ONNX Runtime Execution Provider.

Environment configuration describes OS/cache/resource policy.

Evaluation configuration describes suite behavior and acceptance behavior.

## Python architecture

Important packages:

```text
parakeet_onnx/
├── config/
├── hf/
├── run_context/
├── datasets/
├── audio/
├── reference/
├── export/
├── runtime/
├── decoding/
├── evaluation/
└── cli/
```

Python remains authoritative for:

- NeMo loading
- canonical reference generation
- initial ONNX export
- tensor diagnostics
- initial evaluation orchestration

## Rust architecture

Planned crates:

```text
rust/crates/
├── asr-runtime/
├── asr-audio/
├── asr-metrics/
└── asr-eval/
```

Dependency direction:

```text
asr-audio ───────┐
                 │
asr-runtime ─────┼──> asr-eval
                 │
asr-metrics ─────┘
```

The library crates must not depend on `asr-eval`.

The initial Rust evaluator should consume already resolved/materialized
evaluation inputs rather than reimplementing the Hugging Face `datasets`
ecosystem.

## Reproducibility identity

Every meaningful evaluation run records:

```text
candidate artifact SHA-256
Git commit/ref/dirty state
OS and architecture
Python/runtime versions
ONNX Runtime version
Execution Provider
reference revision
dataset-lock revision/hash
evaluation-schema revision/hash
resolved configuration snapshot
```

These fields are serialized into `run-context.json`.

## Release lifecycle

```text
pinned upstream reference
        ↓
NeMo reference/export environment
        ↓
ONNX candidate
        ↓
HF Bucket/candidates/
        ↓
smoke
        ↓
parity
        ↓
full
        ↓
acceptance.passed == true
        ↓
hf-promote-model.sh
        ↓
HF Model Repo
```

Promotion must verify that the artifact SHA-256 evaluated by the accepted run
matches the candidate artifact being promoted.
