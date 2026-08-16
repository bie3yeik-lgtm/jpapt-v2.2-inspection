# Multi-framework ASR targets

This repository supports multiple canonical ASR frameworks while sharing the
evaluation dataset, manifest, provider, result-schema, and Hugging Face storage
lifecycle.

## Target/storage mapping

Static model semantics remain in `config/hf-targets/*.toml`, while GitHub
Actions storage selection is controlled by the repository variable
`HF_TARGETS_JSON`.

Recommended value:

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

`HF_BUCKET` values must be unique. `scripts/ci/resolve-hf-target.py` resolves in
both directions:

```text
target id -> HF_BUCKET / HF_MODEL_REPO
HF_BUCKET -> target id -> framework / decoder / storage
```

The Bucket-to-target direction requires `HF_TARGETS_JSON`; it intentionally does
not guess from static TOML storage.

## GitHub Actions Bucket selection

The following manual workflows expose `hf_bucket`:

```text
Validate HF Layout
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
```

Enter one of the `HF_BUCKET` values present in `vars.HF_TARGETS_JSON`, for
example:

```text
gawohok7/jpapt-v2.2-dev-bucket
gawohok7/tf-v1-onnx-dev-bucket
```

GitHub Actions cannot generate `workflow_dispatch` choice options dynamically
from a repository variable. Therefore `hf_bucket` is a string input, but the
workflow validates it against `HF_TARGETS_JSON` before HF access.

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

There is no revision-policy or legacy-mode flag. All targets use the same
revision contract.

## Revision documents

Every initialized target Bucket contains:

```text
config/revisions/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

`hf-fetch-revisions.sh` downloads all three files and always runs the project
`RevisionBundle` loader with the active Python environment. Invalid revision
metadata therefore fails immediately after download rather than being deferred
to evaluation.

## `reference.json`: canonical revision contract

All targets must separate three independent repository identities:

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
    "revision": "<REFERENCE_IMPLEMENTATION_OR_ARTIFACT_REVISION>",
    "canonical_framework": "transformers"
  },
  "decoders": {
    "supported": ["whisper_autoregressive"],
    "default": "whisper_autoregressive"
  }
}
```

The identities mean:

| Field | Meaning |
|---|---|
| `development_artifact` | HF Model Repo containing generated ONNX/deployment artifacts and the exact artifact revision under validation. |
| `upstream` | Canonical source checkpoint used to generate/reference the artifact. |
| `tokenizer` | Exact tokenizer/processor source and revision used for preprocessing/decoding. |

These revisions are deliberately independent. An upstream model and tokenizer
may currently share a commit, but the contract does not assume they always do.

The following old forms are invalid and must be migrated before validation:

```text
model.repo_id / model.revision
model_id / model_revision
tokenizer_revision at model/root level
decoder
decorders
missing upstream/tokenizer identities
missing reference.id/reference.revision/reference.canonical_framework
```

## `evaluation-schema.json`

The schema identity and decoder declaration are also canonicalized:

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

Old top-level `schema_id` / `schema_revision`, singular `decoder`, and misspelled
`decorders` are not accepted.

Decoder entries may still be strings or structured objects when extra metadata
is useful:

```json
{
  "decoders": {
    "supported": [
      "ctc",
      {"id": "tdt", "thresholds": {}},
      {"id": "whisper_autoregressive", "thresholds": {}}
    ],
    "default": "ctc"
  }
}
```

## Revision validation

Target identity validation is explicit:

```bash
python scripts/ci/validate-revisions.py \
  --root .ci/hf/config/revisions \
  --expected-development-repo-id gawohok7/tf-v1-onnx-dev \
  --expected-upstream-repo-id kotoba-tech/kotoba-whisper-v1.0 \
  --expected-tokenizer-repo-id kotoba-tech/kotoba-whisper-v1.0 \
  --expected-framework transformers \
  --expected-decoder whisper_autoregressive
```

The loader first validates the document shape and decoder compatibility. The CLI
then verifies that the selected target matches the three repository identities,
framework, and decoder.

## Validate HF Layout flow

The workflow is separated into three responsibilities:

```text
local-contracts
  -> validate source-controlled config/tests
  -> build target matrix from config/hf-targets/*.toml

workflow_dispatch
  -> validate-selected
  -> strict validation of the chosen HF_BUCKET

pull_request / push
  -> validate-targets matrix
  -> probe each source-controlled target
  -> report external Bucket drift as warnings
```

The automatic matrix is generated from `config/hf-targets/*.toml`; adding a new
source-controlled target no longer requires editing a hard-coded matrix list.

## Evaluation behavior by target

The evaluation workflows resolve the selected Bucket and pass the resulting
`HF_TARGET_ID` into the model configuration path. This prevents a selected
storage target from silently falling back to another model config.

The current Python and Rust ONNX evaluators are CTC-first/CTC-only. A target such
as Kotoba Whisper can be selected and revision-validated, but evaluation stops
with an explicit decoder compatibility error before attempting incompatible
inference until the Whisper autoregressive runtime is implemented.

## Dataset policy

Current targets use `datasets_policy = "shared-default"`. Existing JSUT, Common
Voice, and ReazonSpeech locks/manifests remain the evaluation corpus contract;
switching target storage does not silently change the evaluation dataset.

## Current target summary

| Target | Canonical upstream | Framework | Default decoder | HF Model Repo | HF Bucket |
|---|---|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `nemo` | `ctc` | `gawohok7/jpapt-v2.2-dev` | `gawohok7/jpapt-v2.2-dev-bucket` |
| `kotoba-whisper-v1.0` | `kotoba-tech/kotoba-whisper-v1.0` | `transformers` | `whisper_autoregressive` | `gawohok7/tf-v1-onnx-dev` | `gawohok7/tf-v1-onnx-dev-bucket` |
