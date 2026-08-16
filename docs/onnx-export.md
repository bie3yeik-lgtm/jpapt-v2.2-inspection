# ONNX Export

## Purpose

ONNX is a deployment artifact, not the canonical source representation.
The canonical source/reference framework is selected by the HF target profile.

```text
pinned target
    ↓
canonical framework/reference
    ↓
ONNX export
    ↓
structural validation
    ↓
candidate
```

Current examples include NeMo/Parakeet and Transformers/Whisper.

## Pinned source revisions

Export must use the exact identities from:

```text
.ci/hf/config/revisions/reference.json
```

which is downloaded from:

```text
hf://buckets/<HF_BUCKET>/config/revisions/reference.json
```

The fields have distinct meanings:

```text
development_artifact.revision  revision of generated deployment-artifact repo
upstream.revision              source checkpoint revision used for export
 tokenizer.revision            tokenizer/processor revision
reference.revision             canonical reference implementation/artifact revision
```

Do not export from a floating `main`, `latest`, or implicit HEAD revision.
Do not use `development_artifact.revision` as a substitute for the upstream
checkpoint revision.

## Audio/frontend boundary

The common input boundary is:

```text
CanonicalAudio
float32
mono
16000 Hz
```

Framework/model-specific frontend logic begins after this boundary.

Two export strategies are supported conceptually.

### Frontend outside ONNX

```text
CanonicalAudio
    ↓
standalone framework frontend
    ↓
features
    ↓
model ONNX
```

This is useful when frontend parity must be inspected independently.

### Frontend inside ONNX

```text
CanonicalAudio waveform
    ↓
frontend + model ONNX
```

This simplifies deployment but moves frontend compatibility into the graph.

## Export adapters

The export layer should dispatch by the selected target/framework rather than
assuming NeMo globally.

```text
python/src/parakeet_onnx/export/
├── ctc.py
├── tdt.py
├── metadata.py
└── validate.py
```

Architecture-specific adapters may additionally exist for Transformers/Whisper.

Responsibilities:

- load the exact `upstream` revision
- load the exact `tokenizer` revision
- create the requested decoder-specific graph(s)
- write candidate metadata with provenance
- validate ONNX structure and runtime contract

## Candidate staging

Exports first go to disposable local staging:

```text
tmp/export/<candidate-id>/
├── model.onnx
├── metadata.json
└── tokenizer/
```

After local validation they may be uploaded to:

```text
hf://buckets/<HF_BUCKET>/candidates/<candidate-id>/
```

Do not write development candidates directly to the final Model Repo.

## Candidate metadata

Candidate metadata must identify the primary artifact and preserve source
provenance. If multiple ONNX files exist, the primary artifact must be explicit.

```json
{
  "schema_version": 1,
  "candidate": {
    "candidate_id": "ctc-0007",
    "primary_artifact": "model.onnx"
  }
}
```

## Validation checkpoints

At minimum:

```text
1. graph loads
2. graph passes structural validation
3. CPUExecutionProvider session creates where applicable
4. input/output contract matches metadata
5. frontend parity passes where frontend is external
6. architecture-specific intermediate parity is within threshold
7. decoder/token/text parity meets target rules
8. run-context records exact revision identities
```

## Dynamic shapes

Audio ASR inputs are variable length. Preserve dynamic time dimensions where
required rather than producing OS-specific model files by default.
Provider-specific incompatibilities should be treated as provider/runtime issues
before introducing multiple model artifacts.

## Numerical parity

Do not judge export correctness only by final transcript. Compare meaningful
architecture-specific intermediate checkpoints before token/text metrics.

## Artifact SHA-256

The candidate ONNX SHA-256 is part of the run identity. Promotion requires the
artifact SHA evaluated by the accepted run to match the artifact being
promoted.

## Release

```text
candidate
    ↓
smoke
    ↓
parity
    ↓
full
    ↓
acceptance
    ↓
scripts/hf/hf-promote-model.sh
    ↓
HF Model Repo
```

The Model Repo is not a development scratch location.
