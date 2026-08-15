# Hugging Face Storage Layout

## Purpose

The project separates mutable development/evaluation data from released model
artifacts.

Two Hugging Face storage roles are used:

```text
Hugging Face Bucket
    development and evaluation state

Hugging Face Model Repo
    validated release artifacts
```

## Environment variables

Operational scripts use:

```text
HF_TOKEN
HF_BUCKET
HF_MODEL_REPO
```

`HF_BUCKET` format:

```text
<namespace>/<bucket>
```

`HF_MODEL_REPO` format:

```text
<namespace>/<model-repository>
```

Secrets must not be committed to Git.

## Bucket layout

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

## `config/revisions/`

### `reference.json`

Pins the canonical model/reference identity.

Conceptual structure:

```json
{
  "schema_version": 1,
  "model": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision": "<FULL_HF_COMMIT_SHA>",
    "tokenizer_revision": "<FULL_HF_COMMIT_SHA>"
  },
  "reference": {
    "id": "nemo-reference-v1",
    "revision": "<REFERENCE_ARTIFACT_REVISION>"
  }
}
```

### `evaluation-schema.json`

Pins evaluation rules and thresholds.

It is not the same thing as:

```text
evaluation/schemas/*.schema.json
```

The HF document answers:

> Which acceptance rule revision applies?

The Git JSON Schemas answer:

> Is this result document structurally valid?

### `datasets-lock.json`

Pins exact evaluation dataset revisions.

Logical IDs used by manifests map through this document, for example:

```text
jsut-basic5000
common-voice-8-ja
reazonspeech-test
```

## `candidates/`

Unvalidated or not-yet-promoted deployment artifacts.

Example:

```text
candidates/
└── ctc-0007/
    ├── model.onnx
    ├── metadata.json
    └── tokenizer/
```

Candidates may be replaced during active development, so evaluation identity
must always include artifact SHA-256.

## `reference/`

Canonical NeMo-generated evaluation/reference artifacts.

Possible structure:

```text
reference/
├── manifests/
├── outputs/
├── tensors/
└── metadata/
```

Large frontend/encoder/logit tensors belong here rather than Git.

## `runs/`

Complete evaluation histories.

```text
runs/
└── <run-id>/
    ├── run-context.json
    ├── samples.jsonl
    ├── metrics.json
    └── promotion.json
```

`promotion.json` is added when that accepted run is used to promote a
candidate.

Runs are append-oriented history and operational scripts must not use
destructive synchronization by default.

## `benchmarks/`

Lightweight comparable summaries.

Recommended layout:

```text
benchmarks/
└── <candidate-id>/
    └── <benchmark-name>/
        └── <run-id>.json
```

Examples of benchmark names:

```text
linux-cpu
windows-cpu
macos-cpu
coreml
cuda
directml
```

The benchmark file is normally a copy of validated `metrics.json`.

## `scripts/`

Reserved for Bucket-side operational material if required later.

Repository source scripts remain under:

```text
scripts/hf/
```

Do not duplicate normal source code into the Bucket unless there is a concrete
artifact-history requirement.

## `tmp/`

Disposable Bucket workspace.

Nothing under `tmp/` should be treated as canonical evaluation identity or a
release artifact.

## Local staging

HF revision files:

```text
.ci/hf/config/revisions/
```

Candidate:

```text
.ci/candidate/
```

Reference:

```text
.ci/reference/
```

Promotion staging:

```text
.ci/promotion/
```

These locations are disposable and excluded from Git.

## Operational scripts

```text
scripts/hf/
├── hf-fetch-revisions.sh
├── hf-fetch-candidate.sh
├── hf-fetch-reference.sh
├── hf-push-run.sh
├── hf-push-benchmark.sh
└── hf-promote-model.sh
```

### Revision fetch

```text
HF Bucket/config/revisions
        ↓
hf-fetch-revisions.sh
        ↓
.ci/hf/config/revisions
```

### Candidate fetch

```text
HF Bucket/candidates/<candidate-id>
        ↓
hf-fetch-candidate.sh
        ↓
.ci/candidate
```

### Reference fetch

```text
HF Bucket/reference
        ↓
hf-fetch-reference.sh
        ↓
.ci/reference
```

### Run upload

```text
results/<run>/
        ↓
hf-push-run.sh
        ↓
HF Bucket/runs/<run-id>/
```

### Benchmark upload

```text
metrics.json
        ↓
hf-push-benchmark.sh
        ↓
HF Bucket/benchmarks/...
```

### Promotion

```text
accepted candidate
        ↓
hf-promote-model.sh
        ↓
HF Model Repo
```

Promotion verifies artifact identity and records provenance back into the
Bucket.

## Model Repo policy

The Model Repo contains validated artifacts only.

Typical layout:

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

Development candidates must not be uploaded directly as official releases.

## Git policy

Do not store:

```text
*.onnx
*.nemo
*.npy
*.npz
*.wav
*.flac
large dataset caches
HF caches
```

in the Git repository.

Git stores only source/config/schema/manifest/lightweight expected data.

## Lifecycle

```text
reference revisions
        ↓
export candidate
        ↓
Bucket/candidates
        ↓
evaluation
        ↓
Bucket/runs + benchmarks
        ↓
acceptance
        ↓
promotion
        ↓
Model Repo
```
