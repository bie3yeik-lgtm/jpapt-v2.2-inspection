# Hugging Face Storage Layout

## Purpose

The project separates mutable development/evaluation data from released model
artifacts.

```text
Hugging Face Bucket
    development and evaluation state

Hugging Face Model Repo
    validated release artifacts
```

## Target routing

GitHub Actions receives target storage through `vars.HF_TARGETS_JSON`.
Operational scripts consume the resolved values:

```text
HF_TOKEN
HF_BUCKET
HF_MODEL_REPO
```

`HF_BUCKET` and `HF_MODEL_REPO` use `namespace/name` form. Secrets must not be
committed to Git.

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

Pins the development artifact, canonical upstream, tokenizer/processor,
reference implementation, framework, and decoder identities independently.

Canonical structure:

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "gawohok7/tf-v1-onnx-dev",
    "revision": "<DEVELOPMENT_ARTIFACT_REVISION>"
  },
  "upstream": {
    "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    "revision": "<UPSTREAM_REVISION>"
  },
  "tokenizer": {
    "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    "revision": "<TOKENIZER_REVISION>"
  },
  "reference": {
    "id": "transformers-reference-v1",
    "revision": "<REFERENCE_REVISION>",
    "canonical_framework": "transformers"
  },
  "decoders": {
    "supported": ["whisper_autoregressive"],
    "default": "whisper_autoregressive"
  }
}
```

There is one canonical contract. Old `model`, `model_id`, `model_revision`,
`decoder`, and `decorders` forms are invalid.

### `evaluation-schema.json`

Pins evaluation rules and thresholds. Its identity is represented by the
required `schema` object and it declares compatible decoders through the
required `decoders` object.

It is not the same thing as:

```text
evaluation/schemas/*.schema.json
```

The HF document answers which acceptance-rule revision applies. Git JSON
Schemas answer whether generated result documents are structurally valid.

### `datasets-lock.json`

Pins exact evaluation dataset revisions. Logical IDs used by manifests map
through this document, for example:

```text
jsut-basic5000
common-voice-8-ja
reazonspeech-test
```

## Revision fetch and validation

```text
HF Bucket/config/revisions
        ↓
hf-fetch-revisions.sh
        ↓
.ci/hf/config/revisions
        ↓
RevisionBundle strict loader
        ↓
validate-revisions.py target identity check
```

`hf-fetch-revisions.sh` always runs project-level validation with the active
Python environment. A downloaded but invalid revision bundle is rejected before
candidate evaluation.

## `candidates/`

Unvalidated or not-yet-promoted deployment artifacts.

```text
candidates/
└── <candidate-id>/
    ├── model.onnx
    ├── metadata.json
    └── tokenizer/
```

Candidates may be replaced during active development, so evaluation identity
must always include artifact SHA-256.

## `reference/`

Canonical framework-generated evaluation/reference artifacts. Depending on the
target, the canonical framework may be NeMo or Transformers.

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

`run-context.json` serializes the same three repository revision identities:
`development_artifact`, `upstream`, and `tokenizer`.

Runs are append-oriented history and operational scripts must not use
destructive synchronization by default.

## `benchmarks/`

Lightweight comparable summaries.

```text
benchmarks/
└── <candidate-id>/
    └── <benchmark-name>/
        └── <run-id>.json
```

Typical benchmark names include `linux-cpu`, `windows-cpu`, `macos-cpu`,
`coreml`, `cuda`, and `directml`.

## `scripts/` and `tmp/`

Bucket `scripts/` is reserved for artifact-history material when a concrete
need exists. Normal source code remains in Git under `scripts/hf/`.

`tmp/` is disposable and must never be treated as canonical evaluation identity
or release state.

## Local staging

```text
.ci/hf/config/revisions/   revision locks
.ci/candidate/             candidate artifacts
.ci/reference/             reference assets
.ci/promotion/             promotion staging
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

Promotion verifies artifact identity and records provenance back into the
Bucket.

## Model Repo policy

The Model Repo contains validated artifacts only.

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

Do not store large runtime artifacts in Git:

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

Git stores source/config/schema/manifest/lightweight expected data.

## Lifecycle

```text
strict reference revisions
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
