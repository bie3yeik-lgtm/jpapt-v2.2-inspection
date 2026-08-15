# ONNX Export

## Purpose

ONNX is a deployment artifact, not the canonical source representation.

The canonical model/reference is the pinned upstream NeMo model.

```text
NeMo model
    ↓
reference validation
    ↓
ONNX export
    ↓
structural validation
    ↓
candidate
```

## Initial target

The first export target is the simpler CTC deployment path.

```text
waveform/features
    ↓
frontend
    ↓
FastConformer encoder
    ↓
CTC head
    ↓
logits
```

TDT export and decoding are added after CTC correctness is stable.

## Reference environment

Canonical export development runs in:

```text
docker/Dockerfile.nemo
```

The container isolates:

- NeMo
- PyTorch
- CUDA
- canonical reference dependencies

The normal ORT runtime must not depend on this environment.

## Pinned source revision

The source model revision must be obtained from:

```text
.ci/hf/config/revisions/reference.json
```

which is downloaded from:

```text
hf://buckets/<namespace>/<bucket>/config/revisions/reference.json
```

Do not export from a floating `main`, `latest`, or implicit HEAD revision.

## Audio/frontend boundary

The common input boundary is:

```text
CanonicalAudio
float32
mono
16000 Hz
```

Two export strategies are supported conceptually.

### Frontend outside ONNX

```text
CanonicalAudio
    ↓
standalone frontend
    ↓
features
    ↓
encoder/head ONNX
```

Advantages:

- easiest frontend parity inspection
- easier localization of conversion errors
- explicit Rust frontend path later

This is the preferred initial development path.

### Frontend inside ONNX

```text
CanonicalAudio waveform
    ↓
frontend + encoder/head ONNX
```

Advantages:

- simpler deployment interface

Disadvantages:

- frontend differences become part of the graph
- harder to isolate numerical mismatch

This can be adopted after parity is understood.

## Export modules

Expected Python implementation:

```text
python/src/parakeet_onnx/export/
├── ctc.py
├── tdt.py
├── metadata.py
└── validate.py
```

### `ctc.py`

Responsibilities:

- prepare pinned NeMo model
- isolate CTC path
- define export input/output contracts
- invoke export
- write candidate artifacts

### `tdt.py`

Future responsibilities:

- predictor export
- joint export
- duration/token output contract
- TDT deployment components

### `metadata.py`

Responsibilities:

- candidate identity
- model/source revision
- primary artifact
- input/output contract
- decoder type
- tokenizer identity
- frontend strategy
- compatibility metadata

### `validate.py`

Responsibilities:

- load exported ONNX
- run ONNX checker
- inspect inputs/outputs
- verify expected tensor names/dtypes/ranks
- create ORT CPU session
- perform minimal numerical comparison

## Candidate staging

Exports should first go to a disposable local path such as:

```text
tmp/export/<candidate-id>/
```

Example:

```text
tmp/export/ctc-0007/
├── model.onnx
├── metadata.json
└── tokenizer/
```

After local validation they may be uploaded to:

```text
hf://buckets/<namespace>/<bucket>/candidates/ctc-0007/
```

Do not write directly to the final Model Repo.

## Candidate metadata

If a candidate contains more than one ONNX file, `metadata.json` must identify
the primary artifact.

Conceptual example:

```json
{
  "schema_version": 1,
  "candidate": {
    "candidate_id": "ctc-0007",
    "primary_artifact": "model.onnx"
  }
}
```

This is required for unambiguous SHA-256 promotion verification.

## Validation checkpoints

At minimum:

```text
1. graph loads
2. graph passes structural validation
3. CPUExecutionProvider session creates
4. input/output contract matches metadata
5. frontend parity passes where frontend is external
6. encoder output parity is within threshold
7. logits parity is within threshold
8. tokens/text meet parity rules
```

## Dynamic shapes

Audio ASR inputs are variable length.

The export contract should preserve dynamic time dimensions where required
rather than producing OS-specific model files by default.

Provider-specific incompatibilities should be treated as provider/runtime
issues before introducing multiple model artifacts.

The portable baseline is preferred.

## Numerical parity

Do not judge export correctness only by final transcript.

Intermediate checkpoints may expose significant numerical drift that happens
not to change the decoded text for a small sample.

Recommended progression:

```text
frontend
    ↓
encoder
    ↓
logits
    ↓
tokens
    ↓
text
```

## Artifact SHA-256

The candidate ONNX SHA-256 is part of the run identity.

Promotion requires:

```text
run-context artifact SHA
        ==
metrics candidate artifact SHA
        ==
actual candidate file SHA
```

This prevents a candidate from being replaced after evaluation.

## Release

The release path is:

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
