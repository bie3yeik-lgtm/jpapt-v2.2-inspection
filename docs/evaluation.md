# Evaluation

## Purpose

Evaluation has two different goals and they must not be conflated.

### ASR quality

Compare candidate output against the dataset ground-truth transcription.

Metrics:

- CER
- WER

### Conversion/runtime parity

Compare ONNX behavior against the canonical NeMo reference implementation.

Possible checkpoints:

- frontend tensors
- encoder tensors
- CTC logits
- token IDs
- decoded text

A model can reproduce NeMo perfectly while NeMo itself still makes an ASR
error against the dataset ground truth.

Therefore:

```text
dataset reference text
    != necessarily
NeMo output

but a correct conversion aims for

NeMo output
    == candidate ONNX output
```

## Evaluation suites

### Smoke

Configuration:

```text
config/evaluation/smoke.toml
```

Manifest:

```text
evaluation/manifests/smoke.jsonl
```

Expected sample count:

```text
12
```

Purpose:

- pipeline health
- deterministic sample resolution
- tokenizer/decoder regression
- lightweight end-to-end validation

Git-tracked semantic expectations are stored in:

```text
evaluation/expected/smoke.json
```

### Parity

Configuration:

```text
config/evaluation/parity.toml
```

Manifest:

```text
evaluation/manifests/parity.jsonl
```

Expected sample count:

```text
48
```

Purpose:

- frontend parity
- encoder parity
- logits parity
- token/text parity
- cross-platform correctness

### CoreML parity

Manifest:

```text
evaluation/manifests/coreml-parity.jsonl
```

Expected sample count:

```text
40
```

Purpose:

- CoreML EP shape boundaries
- short/medium/long input coverage
- CPU-vs-CoreML correctness comparison

Performance on hosted macOS runners is not considered authoritative for a
specific local Apple Silicon machine.

### Full

Configuration:

```text
config/evaluation/full.toml
```

Manifest:

```text
evaluation/manifests/full.jsonl
```

Expected sample count:

```text
768
```

Purpose:

- aggregate ASR quality
- aggregate performance
- release acceptance
- promotion gate

The canonical hosted full evaluation is CPU-oriented and does not require
every EP to process all 768 samples on every commit.

## Deterministic manifest selection

Manifest entries describe selection rules rather than enumerating every row.

Example concept:

```json
{
  "schema_version": 1,
  "id": "smoke-jsut",
  "dataset_id": "jsut-basic5000",
  "selection": {
    "strategy": "stable_hash",
    "count": 6,
    "seed": "parakeet-onnx-smoke-jsut-v1"
  },
  "filters": {
    "min_duration_sec": 1.0,
    "max_duration_sec": 15.0
  },
  "tags": [
    "smoke",
    "japanese",
    "clean-speech"
  ]
}
```

Selection hash input:

```text
dataset_revision
+ "\n"
+ sample_identity
+ "\n"
+ seed
```

Encoding:

```text
UTF-8
```

Hash:

```text
SHA-256
```

Eligible rows are sorted by ascending digest and the first requested `count`
rows are selected.

The resolver must fail rather than silently reduce the requested count if too
few rows pass the filters.

## Sample identity

Stable identity priority:

1. explicit dataset sample ID
2. stable audio path/file identity
3. pinned row index

Because the dataset revision and split are locked, row index is an acceptable
last-resort identity.

## Materialization

Selected samples are materialized before audio processing.

```text
DatasetRecord
    ↓
DatasetMaterializer
    ↓
local file
    ↓
ResolvedDatasetSample.audio_path
```

Materialized assets are disposable cache data and normally live under:

```text
.cache/evaluation/audio/
```

They are validated with SHA-256.

## Git expected data vs HF reference data

### Git

```text
evaluation/expected/
└── smoke.json
```

Contains lightweight semantic expectations.

### HF Bucket

```text
reference/
```

Contains potentially large canonical reference outputs and tensors.

Do not commit large frontend, encoder, logits, `.npy`, audio, or model
artifacts into Git.

## `smoke.json` lifecycle

Initial state:

```text
null → uninitialized
```

Initialization:

```text
uninitialized → ready
```

`evaluation/schemas/expected.schema.json` structurally enforces these valid
states and transition metadata.

A ready file must include:

- pinned model revision
- tokenizer revision
- dataset-lock SHA-256
- manifest SHA-256
- normalization revision
- exactly 12 samples
- generation provenance

JSON Schema cannot prove that a declared previous-file hash actually refers to
the historical file; that provenance check belongs to a transition validator.

## Evaluation output

Per result directory:

```text
results/<provider-or-run-name>/
├── run-context.json
├── samples.jsonl
└── metrics.json
```

### `run-context.json`

Records reproducibility identity.

Validated by:

```text
evaluation/schemas/run-context.schema.json
```

### `samples.jsonl`

One result record per sample.

Validated per line by:

```text
evaluation/schemas/result.schema.json
```

### `metrics.json`

Aggregate benchmark/evaluation output.

Validated by:

```text
evaluation/schemas/benchmark.schema.json
```

## Timing metrics

Recommended components:

```text
audio decode
resample
frontend
encoder/inference
decoder
postprocess
total
```

Key metric:

```text
RTF = processing_time / audio_duration
```

The evaluator should distinguish:

```text
ORT-only RTF
```

from:

```text
end-to-end RTF
```

because a future Python-to-Rust migration may improve I/O, audio, decoding, and
metrics overhead without materially changing native ORT inference time.

## Memory

Record where supported:

- peak host RAM
- optional peak device memory

## Provider behavior

The evaluator should record:

- requested provider
- actual provider list
- provider assignment where inspectable
- CPU fallback
- provider errors

A successful session creation does not by itself prove that all graph nodes
executed on the intended EP.

## Acceptance

Acceptance rules belong to the locked HF Bucket document:

```text
config/revisions/evaluation-schema.json
```

Git JSON Schemas validate the structure of results; they do not define release
quality thresholds.

Promotion requires an accepted full run by default.

## Python and Rust parity

Both evaluators should ultimately use the same:

```text
manifests
materialized sample identity
canonical audio contract
result schema
benchmark schema
run-context contract
```

This makes runtime comparison mechanical rather than interpretive.
