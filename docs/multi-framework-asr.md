# Multi-framework ASR targets

This repository supports more than one canonical ASR framework while keeping
the same evaluation datasets, manifests, provider configs, result schemas, and
Hugging Face storage lifecycle.

## Supported target profiles

Static target profiles live under `config/hf-targets/`.

| Target | Canonical upstream | Framework | Revision contract | Default decoder | HF Model Repo | HF Bucket |
|---|---|---|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `nemo` | `legacy` | `ctc` | `gawohok7/jpapt-v2.2-dev` | `gawohok7/jpapt-v2.2-dev-bucket` |
| `kotoba-whisper-v1.0` | `kotoba-tech/kotoba-whisper-v1.0` | `transformers` | `strict` | `whisper_autoregressive` | `gawohok7/tf-v1-onnx-dev` | `gawohok7/tf-v1-onnx-dev-bucket` |

Both targets use `datasets_policy = "shared-default"`. The existing JSUT,
Common Voice, and ReazonSpeech evaluation dataset locks/manifests therefore
remain the evaluation corpus contract.

## Upstream identity versus development artifact identity

Two model identities are intentionally kept separate:

```text
canonical upstream model
        -> framework reference behavior
        -> ONNX export source

HF development model repo
        -> generated candidate/release artifact identity
        -> reference.json model.repo_id
```

For example:

```text
Parakeet upstream:  nvidia/parakeet-tdt_ctc-0.6b-ja
Parakeet dev repo:  gawohok7/jpapt-v2.2-dev

Whisper upstream:   kotoba-tech/kotoba-whisper-v1.0
Whisper dev repo:   gawohok7/tf-v1-onnx-dev
```

The canonical upstream is declared in `config/models/*.toml` and
`config/hf-targets/*.toml`. `reference.json model.repo_id` identifies the
selected development model repository whose generated artifacts are being
validated. This follows the contract already used by the existing Parakeet
Bucket.

## Revision documents

Every initialized target Bucket uses:

```text
config/revisions/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

### New strict Transformers reference example

For the Kotoba Whisper target, the intended `reference.json` shape is:

```json
{
  "schema_version": 1,
  "model": {
    "repo_id": "gawohok7/tf-v1-onnx-dev",
    "revision": "<DEVELOPMENT_ARTIFACT_REVISION>",
    "tokenizer_revision": "<PINNED_UPSTREAM_OR_ARTIFACT_REVISION>"
  },
  "reference": {
    "id": "transformers-reference-v1",
    "revision": "<REFERENCE_ARTIFACT_REVISION>",
    "canonical_framework": "transformers"
  },
  "decoders": {
    "supported": ["whisper_autoregressive"],
    "default": "whisper_autoregressive"
  }
}
```

The canonical export/reference source remains
`kotoba-tech/kotoba-whisper-v1.0`; it is not replaced by the development repo.

### Existing Parakeet legacy compatibility

The current Parakeet Bucket predates explicit `canonical_framework` and decoder
metadata in `reference.json`. Its target profile therefore declares:

```toml
[reference]
canonical_framework = "nemo"
revision_contract = "legacy"
```

Legacy mode means missing framework/decoder fields are tolerated during the
migration. If those fields are present, they must still be compatible with the
target. New targets should use `revision_contract = "strict"`.

### Decoder declarations

Decoder declarations are framework-neutral. The revision loader accepts both
simple IDs and structured entries:

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

For compatibility with older metadata, the misspelling `decorders` is also
accepted on input, but normalized code and new documents should always use
`decoders`.

The loader checks that decoders required by `reference.json` are allowed by
`evaluation-schema.json` whenever both documents declare them.

## Validate HF Layout

The workflow supports manual target selection:

```text
Actions
  -> Validate HF Layout
  -> Run workflow
  -> target
```

Available values:

```text
repository-vars
parakeet-tdt_ctc-0.6b-ja
kotoba-whisper-v1.0
```

`repository-vars` preserves the original behavior. Named targets instead load
Bucket, Model Repo, framework, decoder, and revision-contract policy from
`config/hf-targets/<target>.toml`.

On pull requests and pushes, a target matrix also probes both configured
Buckets. An initialized target is fully validated. An uninitialized target is
reported as a warning so adding a new target profile does not make every PR
fail before its remote revision files have been bootstrapped.

Manual validation of a named target remains strict: if its revision bundle is
missing or invalid, the manually requested run fails.

### Current Kotoba Whisper Bucket state

At the time this target was added, `gawohok7/tf-v1-onnx-dev-bucket` did not yet
contain:

```text
config/revisions/reference.json
config/revisions/evaluation-schema.json
config/revisions/datasets-lock.json
```

Therefore automatic PR validation reports the target as configured but
uninitialized. Before strict manual validation can pass, those three documents
must be populated. `datasets-lock.json` should reuse the same dataset contract
as the existing project rather than introducing a Whisper-specific evaluation
corpus.

## Transformers reference adapter

The optional canonical reference layer is:

```text
python/src/parakeet_onnx/reference/transformers.py
```

Install it with:

```bash
pip install -e ".[transformers]"
```

It loads pinned revisions through:

```text
AutoProcessor.from_pretrained(...)
AutoModelForSpeechSeq2Seq.from_pretrained(...)
model.generate(...)
processor.batch_decode(...)
```

For `kotoba-whisper-v1.0`, the model config specifies Japanese transcription:

```text
language = ja
task     = transcribe
```

This is the canonical pre-ONNX reference boundary. ONNX Runtime remains the
deployment runtime.

## Scope

Implemented:

- framework-neutral HF revision parsing
- `nemo` and `transformers` canonical framework identities
- framework-neutral decoder declarations
- structured/legacy decoder metadata compatibility
- reference/evaluation-schema decoder compatibility checks
- per-target `legacy` / `strict` revision policies
- static Parakeet and Kotoba Whisper HF target profiles
- `kotoba-whisper-v1.0` model configuration
- reuse of existing evaluation datasets/manifests
- target-aware `Validate HF Layout`
- pinned Transformers speech-seq2seq reference adapter

Not implemented by this change:

- automatic Whisper ONNX export
- Rust Whisper autoregressive generation
- Rust KV-cache controller
- automatic mutation/bootstrap of private HF Bucket revision documents

Those are later runtime/export stages. The current Rust evaluator remains
CTC-first and must not be treated as a Whisper autoregressive runtime simply
because the storage/reference layer is now framework-neutral.
