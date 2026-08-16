# Hugging Face Storage Layout

## Purpose

The project separates mutable development/evaluation data from promoted model
artifacts.

```text
Hugging Face Bucket
    development, experiments, candidates, evaluation history

Hugging Face Model Repo
    validated promoted artifacts
```

For the complete reusable operating model, including sequential ID allocation,
concurrency, reproduction, and migration to other repositories, see:

```text
docs/hf-bucket-operations.md
```

## Target routing

GitHub Actions receives target storage through `vars.HF_TARGETS_JSON` and uses:

```text
HF_TOKEN
HF_BUCKET
HF_MODEL_REPO
```

Bucket routing is operational state. `reference.json` does not duplicate the
Bucket name.

## Canonical Bucket layout

```text
hf://buckets/<namespace>/<bucket>/
├── config/
│   ├── current.json
│   └── versions/
│       └── config-NNNNNN/
│           ├── reference.json
│           ├── evaluation-schema.json
│           └── datasets-lock.json
├── experiments/
│   └── <prefix>-NNNNNN/
│       └── README.md
├── candidates/
│   └── <prefix>-NNNNNN/
│       ├── README.md
│       ├── metadata.json
│       └── <deployment artifacts>
├── reference/
│   ├── manifests/
│   ├── outputs/
│   ├── tensors/
│   └── metadata/
├── runs/
│   └── <run-id>/
├── benchmarks/
│   └── <candidate-id>/
│       └── <environment-provider>/
├── scripts/
└── tmp/
```

Framework and decoder names are not top-level storage categories. NeMo,
Transformers, CTC, TDT, and Whisper autoregressive behavior are encoded in
configuration and metadata.

## Versioned revision configuration

### `config/current.json`

```json
{
  "schema_version": 1,
  "config_version": "config-000002"
}
```

Normal workflows follow this pointer. Reproduction may set:

```bash
HF_CONFIG_VERSION=config-000002
```

to select an immutable historical version directly.

### `config/versions/config-NNNNNN/`

Every version contains exactly the canonical revision documents:

```text
reference.json
evaluation-schema.json
datasets-lock.json
```

Published versions are immutable. Any revision-document change creates a new
`config-NNNNNN`, followed by an update of `current.json`.

### Fetch flow

```text
config/current.json
        ↓
config/versions/<selected-version>/
        ↓
hf-fetch-revisions.sh
        ↓
.ci/hf/config/revisions/
        ↓
RevisionBundle strict loader
```

The selected version is saved in `.ci/hf/config/resolved.json` and propagated to
`run-context.json.revisions.config_version`.

## `reference.json`

Canonical structure:

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "example/development-model-repo",
    "revision": "<DEVELOPMENT_ARTIFACT_REVISION>"
  },
  "upstream": {
    "repo_id": "vendor/upstream-model",
    "revision": "<UPSTREAM_REVISION>"
  },
  "tokenizer": {
    "repo_id": "vendor/tokenizer-or-processor",
    "revision": "<TOKENIZER_REVISION>"
  },
  "reference": {
    "id": "framework-reference-v1",
    "revision": "<REFERENCE_REVISION>",
    "canonical_framework": "transformers"
  },
  "decoders": {
    "supported": ["whisper_autoregressive"],
    "default": "whisper_autoregressive"
  }
}
```

Meanings:

- `development_artifact`: the HF Model Repo snapshot containing the development
  or promoted deployment artifact;
- `upstream`: the source model/checkpoint;
- `tokenizer`: the independently pinned tokenizer/processor source;
- `reference`: the implementation used to produce canonical expected results.

## `evaluation-schema.json`

Pins evaluation-rule identity and supported decoders through canonical `schema`
and `decoders` objects. It is separate from Git JSON Schema files under
`evaluation/schemas/`.

## `datasets-lock.json`

Pins exact evaluation dataset revisions and maps logical manifest IDs to their
HF Dataset repositories/revisions.

## Sequential candidate and experiment IDs

Candidates and experiments use:

```text
<prefix>-NNNNNN
```

The prefix is descriptive; the numeric sequence is machine managed across the
entire collection irrespective of prefix.

Example:

```text
experiments/
├── cpu-full-eval-000002/
├── cross-platform-parity-000003/
└── rust-eval-000004/
```

The next experiment with any prefix is `...-000005`.

`scripts/hf/hf-allocate-id.sh` lists the collection, computes maximum suffix + 1,
and immediately writes `README.md` to reserve/document the allocated path.
GitHub Actions serializes the short allocator job using a Bucket-scoped
concurrency group so heavy evaluations can still run in parallel.

## Candidates

Candidates are unpromoted deployment artifacts selected for evaluation.
New candidate publication uses:

```text
scripts/hf/hf-push-candidate.sh
```

which allocates the ID automatically. Existing candidate IDs remain explicit
inputs to evaluation workflows because selecting which immutable artifact to
evaluate is different from allocating a new ID.

A Whisper-style candidate may contain multiple ONNX graphs:

```text
candidates/<candidate-id>/
├── README.md
├── metadata.json
├── encoder.onnx
├── decoder.onnx
├── decoder_with_past.onnx
└── tokenizer/
```

A CTC candidate may contain one primary ONNX graph. The lifecycle structure is
the same.

## Experiments

Experiments group a logical attempt or evaluation across one or more concrete
runs. Current workflow prefixes include:

```text
cpu-full-eval
cross-platform-parity
rust-eval
```

The ID is recorded in:

```text
run-context.json.metadata.experiment_id
```

Cross-platform matrix jobs share one experiment ID but each produces its own
run ID.

## Reference assets

```text
reference/
├── manifests/
├── outputs/
├── tensors/
└── metadata/
```

Large canonical framework outputs/tensors belong in the Bucket rather than Git.

## Runs

```text
runs/<run-id>/
├── run-context.json
├── samples.jsonl
├── metrics.json
└── promotion.json
```

Runs are execution records, not sequential human-managed entities. They retain
candidate, experiment, configuration version, revision bundle, artifact hash,
runtime/provider, host, and Git identity.

## Benchmarks

Use environment/provider names rather than framework names:

```text
benchmarks/<candidate-id>/
├── linux-cpu/
├── linux-cuda/
├── windows-cpu/
├── windows-cuda/
├── windows-directml/
├── macos-cpu/
└── macos-coreml/
```

Only directories for actually executed benchmark configurations need to exist.

## `scripts/` and `tmp/`

Bucket `scripts/` is reserved for artifact-history material when required.
Source code remains in Git. `tmp/` is disposable and is never canonical
identity/history.

## Model Repo policy

Validated/promotion artifacts live in the Model Repo, for example:

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

Development candidates remain in the Bucket until promotion.

## Lifecycle

```text
config/current.json
        ↓
immutable config version
        ↓
export/build artifact
        ↓
auto-numbered candidate
        ↓
auto-numbered experiment
        ↓
one or more runs
        ↓
benchmarks
        ↓
acceptance
        ↓
promotion to HF Model Repo
```
