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

`HF_BUCKET` values must be unique. `scripts/ci/resolve-hf-target.py` can resolve
in both directions:

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

GitHub Actions does not support generating `workflow_dispatch` choice options
dynamically from a repository variable. Therefore `hf_bucket` is a string input,
but the workflow validates it against `HF_TARGETS_JSON` before any HF access.
An unknown Bucket fails with the currently configured Bucket values in the error
message.

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
ALLOW_LEGACY_REVISION_METADATA
```

This keeps storage routing dynamic while framework/decoder semantics remain
source-controlled.

## Revision documents

Every initialized target Bucket contains:

```text
config/revisions/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

## `reference.json`: explicit revision identities

New strict targets must separate three independent identities. Do not overload a
single `model.revision` field.

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

The three identities mean:

| Field | Meaning |
|---|---|
| `development_artifact` | The HF Model Repo that contains generated ONNX/deployment artifacts and the exact artifact revision under validation. |
| `upstream` | The canonical source checkpoint used to generate/reference the artifact. |
| `tokenizer` | The exact tokenizer/processor source and revision used for decoding/preprocessing. |

For the current Kotoba target:

```text
development_artifact.repo_id = gawohok7/tf-v1-onnx-dev
upstream.repo_id             = kotoba-tech/kotoba-whisper-v1.0
tokenizer.repo_id            = kotoba-tech/kotoba-whisper-v1.0
```

These revisions are deliberately independent. They may currently resolve to the
same commit for upstream/tokenizer, but the contract does not assume that.

## Legacy Parakeet compatibility

The existing Parakeet Bucket predates the explicit identity split and may still
contain:

```json
{
  "model": {
    "repo_id": "gawohok7/jpapt-v2.2-dev",
    "revision": "<DEVELOPMENT_ARTIFACT_REVISION>",
    "tokenizer_revision": "<LEGACY_TOKENIZER_REVISION>"
  }
}
```

The Parakeet target therefore keeps `revision_contract = "legacy"`. The loader
maps legacy `model.repo_id` / `model.revision` to the new development-artifact
identity internally and preserves `model_id` / `model_revision` properties only
as backward-compatible aliases.

Legacy mode also allows upstream/tokenizer/framework/decoder identity to be
missing. If a legacy field is present, it must still match the selected target.
New strict targets must use the explicit `development_artifact`, `upstream`, and
`tokenizer` objects.

## Revision validation

`validate-revisions.py` now validates each identity independently:

```bash
python scripts/ci/validate-revisions.py \
  --root .ci/hf/config/revisions \
  --expected-development-repo-id gawohok7/tf-v1-onnx-dev \
  --expected-upstream-repo-id kotoba-tech/kotoba-whisper-v1.0 \
  --expected-tokenizer-repo-id kotoba-tech/kotoba-whisper-v1.0 \
  --expected-framework transformers \
  --expected-decoder whisper_autoregressive
```

`--expected-model-id` remains a hidden compatibility alias for
`--expected-development-repo-id`; new workflow code must use the explicit name.

For legacy targets only:

```text
--allow-legacy-metadata
```

permits missing split identities and old framework/decoder metadata.

## Decoder declarations

Decoder declarations remain framework-neutral:

```json
{
  "decoders": {
    "supported": [
      "ctc",
      {"id": "tdt"},
      {"id": "whisper_autoregressive"}
    ],
    "default": "ctc"
  }
}
```

The legacy misspelling `decorders` is accepted on input, but all new metadata
must use `decoders`.

## Evaluation behavior by target

The Python evaluation workflows can resolve any target configured in
`HF_TARGETS_JSON`; runtime support still depends on the model implementation.

The Rust evaluator is currently CTC-first. `rust-eval.yml` therefore resolves
any selected Bucket, validates its revision identity, and then explicitly fails
before inference when the resolved target requires a decoder other than `ctc`.
For example, selecting the Kotoba Whisper Bucket currently produces a clear
`whisper_autoregressive` compatibility error rather than attempting to run a CTC
runtime against a Whisper graph.

## Dataset policy

Both current targets use `datasets_policy = "shared-default"`. Existing JSUT,
Common Voice, and ReazonSpeech locks/manifests therefore remain the evaluation
corpus contract; switching Bucket/model target does not silently switch the
evaluation dataset.

## Current target summary

| Target | Canonical upstream | Framework | Contract | Default decoder | HF Model Repo | HF Bucket |
|---|---|---|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `nemo` | legacy | `ctc` | `gawohok7/jpapt-v2.2-dev` | `gawohok7/jpapt-v2.2-dev-bucket` |
| `kotoba-whisper-v1.0` | `kotoba-tech/kotoba-whisper-v1.0` | `transformers` | strict | `whisper_autoregressive` | `gawohok7/tf-v1-onnx-dev` | `gawohok7/tf-v1-onnx-dev-bucket` |
