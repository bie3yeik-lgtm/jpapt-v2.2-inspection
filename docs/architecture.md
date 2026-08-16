# Architecture

## Purpose

This repository develops, validates, and promotes ONNX deployment artifacts for
Japanese ASR models across multiple canonical frameworks.

Current reference families include:

```text
NeMo / Hybrid FastConformer
Transformers / Whisper
```

ONNX Runtime is the portable deployment runtime. Python owns canonical model
integration/export/evaluation orchestration; Rust owns the production-oriented
runtime/evaluator path where implemented.

## Architectural principles

1. Development artifact, upstream model, tokenizer/processor, and reference revisions are pinned independently.
2. Evaluation dataset revisions are always pinned.
3. Large model, audio, and tensor artifacts are not stored in Git.
4. Hugging Face Bucket is used for mutable development/evaluation artifacts.
5. Hugging Face Model Repo contains only validated release artifacts.
6. Canonical framework is selected per target (`nemo`, `transformers`, ...).
7. ONNX Runtime is the deployment/runtime abstraction.
8. CPU, CUDA, DirectML, and CoreML are Execution Provider concerns, not model definitions.
9. Generic audio processing is separated from model-specific feature extraction.
10. Python and Rust evaluators consume the same logical data contracts.

## Repository layers

```text
config/
    Static model, target, provider, environment, and evaluation configuration.

evaluation/
    JSON Schemas, deterministic manifests, and Git-tracked smoke expectations.

python/src/parakeet_onnx/
    Canonical Python implementation and framework adapters.

rust/crates/
    Production/runtime implementation.

scripts/
    Operational wrappers for development, CI, and Hugging Face lifecycle.

docker/
    Isolated framework/reference/export environments where required.

docs/
    Architectural and operational documentation.
```

## External storage

```text
GitHub Repository
    source code
    configuration
    schemas
    manifests
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

### Revision identity

Each target Bucket contains:

```text
config/revisions/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

`reference.json` must identify all of the following independently:

```text
development_artifact  generated ONNX/deployment repo + revision
upstream              canonical source checkpoint repo + revision
tokenizer             tokenizer/processor repo + revision
reference             reference implementation/artifact revision
canonical_framework   nemo / transformers / ...
decoders              supported/default decoding contract
```

There is no legacy revision mode. Old overloaded `model.revision` metadata is
not part of the runtime contract.

## ASR pipeline abstraction

Framework-specific model execution begins after canonical audio.

```text
audio asset
    ↓
decode
    ↓
CanonicalAudio
float32 / mono / 16 kHz
    ↓
framework/model frontend
    ↓
encoder/model graph
    ↓
decoder-specific outputs
    ↓
text
```

Examples:

```text
Parakeet CTC: FastConformer -> CTC logits -> CTC collapse
Parakeet TDT: FastConformer -> predictor/joint -> duration-aware decode
Whisper:      encoder -> autoregressive decoder -> tokenizer
```

The current Python and Rust ONNX evaluators are still CTC-oriented; target
routing and revision contracts are already framework-neutral.

## Dataset boundary

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

`ResolvedDatasetSample.audio_path` is a materialized local audio asset readable
through ordinary file I/O.

## Audio boundary

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

## Reference and candidate paths

Reference execution is target-specific:

```text
CanonicalAudio
      ↓
canonical framework adapter
      ↓
reference model outputs
      ↓
reference tokens/text/tensors
```

Candidate execution:

```text
CanonicalAudio
      ↓
candidate frontend/runtime contract
      ↓
ONNX Runtime
      ↓
candidate tokens/text/tensors
```

Parity checkpoints may include frontend, encoder, logits, tokens, text, CER,
and WER depending on the target architecture.

## Configuration

```text
config/models/
config/hf-targets/
config/providers/
config/environments/
config/evaluation/
```

- Model configuration describes architecture/framework semantics.
- HF target configuration binds model semantics to upstream/reference/decoder/storage roles.
- Provider configuration describes ONNX Runtime Execution Providers.
- Environment configuration describes OS/cache/resource policy.
- Evaluation configuration describes suite and acceptance behavior.

## Python architecture

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

Python is authoritative for framework integration, canonical reference
generation, initial ONNX export, tensor diagnostics, and dataset materialization.

## Rust architecture

```text
rust/crates/
├── asr-runtime/
├── asr-audio/
├── asr-metrics/
└── asr-eval/
```

Rust consumes resolved/materialized evaluation inputs rather than reimplementing
the Hugging Face `datasets` ecosystem.

## Reproducibility identity

Every meaningful evaluation run records:

```text
candidate artifact SHA-256
development artifact repo/revision
upstream repo/revision
tokenizer repo/revision
reference implementation revision
Git commit/ref/dirty state
OS and architecture
runtime/backend versions
Execution Provider
dataset-lock revision/hash
evaluation-schema revision/hash
resolved configuration snapshot
```

These fields are serialized into `run-context.json`.

## Release lifecycle

```text
pinned target identities
        ↓
canonical framework reference/export
        ↓
ONNX candidate
        ↓
HF Bucket/candidates/
        ↓
smoke / parity / full
        ↓
acceptance.passed == true
        ↓
hf-promote-model.sh
        ↓
HF Model Repo
```

Promotion must verify that the artifact SHA-256 evaluated by the accepted run
matches the candidate artifact being promoted.
