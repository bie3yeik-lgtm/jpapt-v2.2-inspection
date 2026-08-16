# Multi-framework ASR targets

This repository supports multiple canonical ASR frameworks while sharing the
evaluation dataset, provider, result-schema, and Hugging Face Bucket lifecycle.

For the complete reusable Bucket operating model, see
`docs/hf-bucket-operations.md`.

## Target/storage mapping

Static model semantics live in `config/hf-targets/*.toml`. GitHub Actions
storage routing is controlled by Repository Variable `HF_TARGETS_JSON`.

```json
{
  "kotoba-whisper-v1.0": {
    "HF_BUCKET": "gawohok7/tf-v1-onnx-dev-bucket",
    "HF_MODEL_REPO": "gawohok7/tf-v1-onnx-dev"
  },
  "parakeet-tdt_ctc-0.6b-ja": {
    "HF_BUCKET": "gawohok7/jpapt-v2.2-dev-bucket",
    "HF_MODEL_REPO": "gawohok7/jpapt-v2.2-dev"
  }
}
```

`HF_BUCKET` values must be unique. `resolve-hf-target.py` resolves target IDs to
storage and can reverse-resolve a Bucket to its target.

## Manual Bucket selection

These workflows accept `hf_bucket`:

```text
Validate HF Layout
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
```

The input is a string because GitHub Actions cannot dynamically construct
`workflow_dispatch` choice options from a Repository Variable. The value is
validated against `HF_TARGETS_JSON` before remote access.

The resolver exports:

```text
HF_TARGET_ID
HF_BUCKET
HF_MODEL_REPO
EXPECTED_DEVELOPMENT_REPO_ID
EXPECTED_UPSTREAM_REPO_ID
EXPECTED_TOKENIZER_REPO_ID
EXPECTED_FRAMEWORK
EXPECTED_DECODER
```

There is no legacy revision mode.

## Versioned revision documents

Every initialized target Bucket uses:

```text
config/
├── current.json
└── versions/
    └── config-NNNNNN/
        ├── reference.json
        ├── evaluation-schema.json
        └── datasets-lock.json
```

`config/current.json` identifies the active immutable configuration set.
`hf-fetch-revisions.sh` follows that pointer, stages the three documents under
`.ci/hf/config/revisions/`, writes `.ci/hf/config/resolved.json`, and runs the
strict `RevisionBundle` loader.

Historical reproduction can override the pointer with:

```bash
HF_CONFIG_VERSION=config-000123
```

The selected version is stored in `run-context.json.revisions.config_version`.

## `reference.json`

All targets separate the source/provenance identities:

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "gawohok7/tf-v1-onnx-dev",
    "revision": "<DEVELOPMENT_ARTIFACT_COMMIT_SHA>"
  },
  "upstream": {
    "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    "revision": "<UPSTREAM_MODEL_COMMIT_SHA>"
  },
  "tokenizer": {
    "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    "revision": "<TOKENIZER_OR_PROCESSOR_COMMIT_SHA>"
  },
  "reference": {
    "id": "transformers-reference-v1",
    "revision": "<REFERENCE_IMPLEMENTATION_REVISION>",
    "canonical_framework": "transformers"
  },
  "decoders": {
    "supported": ["whisper_autoregressive"],
    "default": "whisper_autoregressive"
  }
}
```

Meanings:

| Field | Meaning |
|---|---|
| `development_artifact` | Exact HF Model Repo snapshot containing the development/promoted deployment artifact. |
| `upstream` | Canonical source checkpoint used to generate/reference the artifact. |
| `tokenizer` | Exact tokenizer/processor source and revision. |
| `reference` | Canonical framework implementation used to produce expected results. |

The Bucket ID itself is not duplicated into `reference.json`.

Legacy `model`, root/model `tokenizer_revision`, singular `decoder`, and
`decorders` forms are rejected.

## `evaluation-schema.json`

Canonical form:

```json
{
  "schema_version": 1,
  "schema": {
    "id": "asr-evaluation-v1",
    "revision": "<SCHEMA_REVISION>"
  },
  "decoders": {
    "supported": ["ctc", "tdt", "whisper_autoregressive"],
    "default": "ctc"
  }
}
```

Decoder entries may be strings or structured objects; the loader normalizes
them to decoder IDs before compatibility validation.

## Revision validation

After staging the selected config version:

```bash
python scripts/ci/validate-revisions.py \
  --root .ci/hf/config/revisions \
  --expected-development-repo-id gawohok7/tf-v1-onnx-dev \
  --expected-upstream-repo-id kotoba-tech/kotoba-whisper-v1.0 \
  --expected-tokenizer-repo-id kotoba-tech/kotoba-whisper-v1.0 \
  --expected-framework transformers \
  --expected-decoder whisper_autoregressive
```

The loader validates shape and decoder compatibility; the CLI verifies target
identity.

## Validate HF Layout flow

PR/push validation intentionally stays repository-local:

```text
pull_request / push
  -> source-controlled target/schema/script validation
  -> synthetic strict revision fixtures
  -> sequence allocator unit tests
```

Manual validation checks the real selected Bucket:

```text
workflow_dispatch
  -> resolve HF_BUCKET
  -> fetch config/current.json
  -> resolve config/versions/config-NNNNNN
  -> strict RevisionBundle validation
  -> target identity validation
  -> required Bucket layout validation
```

Required lifecycle collections include `experiments/`, `candidates/`, `runs/`,
`benchmarks/`, `reference/`, `scripts/`, and `tmp/`.

## Candidate and experiment identities

New candidate and experiment IDs are machine allocated as:

```text
<prefix>-NNNNNN
```

The numeric suffix is one sequence per collection, independent of prefix.

Candidate export may remain locally `unallocated`; `hf-push-candidate.sh`
assigns the durable Bucket candidate ID and updates `metadata.json` on publish.

Evaluation workflow inputs still select an existing `candidate_id` explicitly
for reproducibility.

Experiment prefixes currently include:

```text
cpu-full-eval
cross-platform-parity
rust-eval
```

A cross-platform matrix shares one experiment ID while every concrete runtime
execution gets its own run ID.

## Evaluation behavior by target

The selected Bucket resolves `HF_TARGET_ID`, which is passed into the target
model configuration path. This prevents storage selection from silently using a
different model configuration.

The current Python and Rust ONNX evaluators remain CTC-only. Transformers
Whisper targets can be selected and revision-validated, but evaluation stops at
an explicit decoder compatibility error until Whisper autoregressive runtime
support is implemented.

## Dataset policy

Current targets use the shared evaluation dataset policy. Switching storage
targets does not silently switch the evaluation corpus.

## Current target summary

| Target | Canonical upstream | Framework | Default decoder | HF Model Repo | HF Bucket |
|---|---|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `nemo` | `ctc` | `gawohok7/jpapt-v2.2-dev` | `gawohok7/jpapt-v2.2-dev-bucket` |
| `kotoba-whisper-v1.0` | `kotoba-tech/kotoba-whisper-v1.0` | `transformers` | `whisper_autoregressive` | `gawohok7/tf-v1-onnx-dev` | `gawohok7/tf-v1-onnx-dev-bucket` |
