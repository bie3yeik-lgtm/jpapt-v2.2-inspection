# Multi-framework ASR targets

This repository supports more than one canonical ASR framework while keeping
the same evaluation datasets, manifests, provider configs, result schemas, and
Hugging Face storage lifecycle.

## Supported target profiles

Static target profiles live under:

```text
config/hf-targets/
```

Current targets:

| Target | Canonical source | Framework | Default decoder | HF Model Repo | HF Bucket |
|---|---|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `nemo` | `ctc` | `gawohok7/jpapt-v2.2-dev` | `gawohok7/jpapt-v2.2-dev-bucket` |
| `kotoba-whisper-v1.0` | `kotoba-tech/kotoba-whisper-v1.0` | `transformers` | `whisper_autoregressive` | `gawohok7/tf-v1-onnx-dev` | `gawohok7/tf-v1-onnx-dev-bucket` |

Both targets use `datasets_policy = "shared-default"`. This means the existing
JSUT, Common Voice, and ReazonSpeech evaluation dataset locks/manifests remain
the evaluation corpus contract. A target does not get a private dataset suite
just because its reference framework differs.

## Revision documents

Every target Bucket uses the same three files:

```text
config/revisions/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

### NeMo reference example

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
    "revision": "<REFERENCE_ARTIFACT_REVISION>",
    "canonical_framework": "nemo"
  },
  "decoders": {
    "supported": ["ctc", "tdt"],
    "default": "ctc"
  }
}
```

### Transformers reference example

```json
{
  "schema_version": 1,
  "model": {
    "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    "revision": "<FULL_HF_COMMIT_SHA>",
    "tokenizer_revision": "<FULL_HF_COMMIT_SHA>"
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

`canonical_framework` is framework identity, not an ONNX Execution Provider.
`transformers` means the authoritative pre-ONNX behavior is generated through
the pinned Transformers model/processor. ONNX Runtime remains the deployment
runtime.

### Evaluation schema decoder declaration

The same `evaluation-schema.json` contract can describe one or multiple decoder
families:

```json
{
  "schema_version": 1,
  "schema": {
    "id": "asr-evaluation-v1",
    "revision": "<SCHEMA_REVISION>"
  },
  "decoders": {
    "supported": [
      "ctc",
      "tdt",
      "whisper_autoregressive"
    ],
    "default": "whisper_autoregressive"
  }
}
```

A target-specific evaluation schema may list only the decoders relevant to that
target. The revision loader rejects a reference decoder that is not allowed by
the selected evaluation schema.

## Validate HF Layout

The `Validate HF Layout` workflow supports manual target selection.

GitHub:

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

`repository-vars` preserves the existing behavior and reads:

```text
HF_BUCKET      = repository variable
HF_MODEL_REPO  = repository variable
```

The named targets instead resolve the Bucket/Model Repo and expected
model/framework/decoder from `config/hf-targets/<target>.toml`.

After downloading the three revision files, the workflow validates:

```text
selected target upstream model
        ==
reference.json model.repo_id

selected target canonical framework
        ==
reference.json reference.canonical_framework

selected target default decoder
        in
reference.json decoders.supported
        and
evaluation-schema.json decoders.supported
```

This prevents accidentally validating the Parakeet revision set while pointing
the workflow at the Whisper development Bucket, or vice versa.

## Transformers reference adapter

The optional Transformers reference layer is:

```text
python/src/parakeet_onnx/reference/transformers.py
```

Install it with:

```bash
pip install -e ".[transformers]"
```

The adapter uses a pinned revision with:

```text
AutoProcessor.from_pretrained(...)
AutoModelForSpeechSeq2Seq.from_pretrained(...)
model.generate(...)
processor.batch_decode(...)
```

For `kotoba-whisper-v1.0`, generation defaults to:

```text
language = ja
task     = transcribe
```

This adapter is the canonical pre-ONNX reference boundary. It does not claim
that the existing Rust CTC evaluator can drive Whisper autoregressive ONNX
graphs. Whisper ONNX requires a generation controller and KV-cache management,
which remain separate runtime work.

## Scope of this extension

Implemented by this extension:

- framework-neutral HF revision parsing
- canonical framework identity (`nemo`, `transformers`, future values)
- framework-neutral decoder declarations
- reference/evaluation-schema decoder compatibility validation
- static multi-model HF target profiles
- `kotoba-whisper-v1.0` model configuration
- reuse of existing dataset manifests/locks
- manual HF layout validation for the Whisper development Bucket
- pinned Transformers speech-seq2seq reference adapter

Not claimed by this extension:

- automatic Whisper ONNX export
- Rust Whisper autoregressive generation
- Rust KV-cache controller
- automatic population of private HF Bucket revision documents

Those are implementation stages after the storage/revision/reference contract is
validated.
