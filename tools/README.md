# Development Tools

This directory contains repository-local development utilities that do not
belong to the production ASR runtime, evaluation runtime, CI wrappers, or
Hugging Face lifecycle scripts.

At the initial project stage this directory intentionally contains only this
document.

Do not add a tool here merely because a script needs a place to live.
Executable code should be placed according to its actual responsibility.

---

## Purpose

The `tools/` directory is reserved for development-time utilities such as:

- ONNX graph inspection
- ONNX metadata inspection
- tensor comparison diagnostics
- intermediate tensor inspection
- model input/output signature inspection
- tokenizer inspection
- profiling helpers
- benchmark-result exploration
- experimental conversion diagnostics
- one-off migration utilities that become useful enough to retain
- visualization or report-generation helpers for developers

These tools may depend on heavyweight or optional packages that are not
required by the normal evaluation runtime.

---

## What does not belong here

### Development environment setup

Use:

```text
scripts/dev/
```

Examples:

```text
scripts/dev/setup.sh
scripts/dev/setup.ps1
scripts/dev/doctor.py
```

---

### Hugging Face operations

Use:

```text
scripts/hf/
```

Examples:

```text
scripts/hf/hf-fetch-revisions.sh
scripts/hf/hf-fetch-candidate.sh
scripts/hf/hf-fetch-reference.sh
scripts/hf/hf-push-run.sh
scripts/hf/hf-push-benchmark.sh
scripts/hf/hf-promote-model.sh
```

---

### CI-specific wrappers

Use:

```text
scripts/ci/
```

Examples:

```text
scripts/ci/validate-revisions.sh
scripts/ci/resolve-candidate-artifacts.py
scripts/ci/prepare-rust-manifest.py
```

---

### Dataset logic

Use:

```text
python/src/parakeet_onnx/datasets/
```

Examples:

- manifest parsing
- deterministic sample selection
- dataset revision resolution
- audio materialization
- dataset caches

---

### Audio processing

Use:

```text
python/src/parakeet_onnx/audio/
```

Examples:

- audio decoding
- channel downmix
- resampling
- canonical waveform generation
- frontend feature extraction

---

### ONNX export implementation

Use:

```text
python/src/parakeet_onnx/export/
```

Examples:

- CTC export
- TDT export
- ONNX metadata generation
- exported-model validation

---

### ONNX Runtime implementation

Use:

```text
python/src/parakeet_onnx/runtime/
```

Examples:

- InferenceSession creation
- Execution Provider configuration
- tensor input/output handling
- provider assignment inspection

---

### Evaluation implementation

Use:

```text
python/src/parakeet_onnx/evaluation/
```

Examples:

- CER/WER calculation
- parity comparison
- result models
- benchmark aggregation
- result serialization

---

### Production Rust implementation

Use:

```text
rust/crates/
```

Development utilities must not become an alternative implementation location
for production Rust code.

---

## Design principle

A tool should live here only if its primary purpose is:

> helping a developer inspect, diagnose, compare, profile, migrate, or
> understand project artifacts.

A tool whose output is required for a normal evaluation run belongs in the
corresponding Python or Rust implementation layer instead.

For example:

```text
Inspect an ONNX graph manually
        ↓
tools/

Create the ONNX model used by evaluation
        ↓
python/src/parakeet_onnx/export/
```

Likewise:

```text
Explore differences between two tensor files
        ↓
tools/

Perform the official parity comparison used by CI
        ↓
python/src/parakeet_onnx/evaluation/
```

This distinction prevents experimental development utilities from becoming
implicit production dependencies.

---

## Tool requirements

Every retained executable tool should satisfy the following requirements.

### 1. Repository-root independence

A tool must not assume that the current working directory is the repository
root.

Python tools should use the common repository path resolver:

```python
from parakeet_onnx.config.paths import (
    RepositoryPaths,
)

paths = RepositoryPaths.discover()
```

or the equivalent project API.

Shell wrappers should derive the repository root from their own location or
Git.

---

### 2. No implicit network access

A diagnostic tool must not unexpectedly download:

- Hugging Face models
- datasets
- ONNX files
- reference artifacts

Network access must be explicit.

If a tool requires an artifact from Hugging Face, use the existing lifecycle
scripts or clearly expose an explicit command-line option.

For example, prefer:

```bash
scripts/hf/hf-fetch-candidate.sh ctc-0007

uv run python tools/inspect_onnx.py \
  .ci/candidate/model.onnx
```

rather than having `inspect_onnx.py` silently download the candidate.

---

### 3. No modification by default

Inspection tools should be read-only unless their purpose is explicitly a
migration or transformation.

Prefer:

```bash
uv run python tools/inspect_onnx.py model.onnx
```

over commands that rewrite the inspected file.

A transforming tool should require an explicit output path:

```bash
uv run python tools/rewrite_metadata.py \
  input.onnx \
  --output output.onnx
```

Do not overwrite the input artifact by default.

---

### 4. Do not modify authoritative revision locks

Tools must not silently modify:

```text
reference.json
evaluation-schema.json
datasets-lock.json
```

These are authoritative evaluation inputs managed through the Hugging Face
Bucket lifecycle.

Any tool that intentionally creates or updates revision documents must:

1. produce a new file,
2. validate it,
3. show the resulting diff or identity,
4. require an explicit promotion/update operation.

---

### 5. Do not modify expected results automatically

Tools must not silently overwrite:

```text
evaluation/expected/smoke.json
```

Candidate output must never redefine expected output.

Expected-data initialization or regeneration must be based on the canonical
reference runtime and remain an explicit reviewed operation.

---

### 6. Large artifacts must not enter Git

Do not write large generated artifacts into `tools/`.

Examples:

```text
*.onnx
*.nemo
*.npy
*.npz
*.wav
*.flac
*.pt
*.safetensors
```

Use disposable locations such as:

```text
.cache/
tmp/
.ci/
results/
```

or Hugging Face storage as appropriate.

---

### 7. Prefer existing project data contracts

A diagnostic tool should consume existing project structures whenever
possible.

Prefer:

```text
ResolvedDatasetSample
CanonicalAudio
FeatureOutput
RunContext
SampleResult
BenchmarkResult
```

over inventing a second incompatible representation.

This makes diagnostic results directly comparable with official evaluation
results.

---

## Recommended command style

Python tools should normally be invoked through the locked project
environment:

```bash
mise exec -- uv run python tools/<tool>.py
```

If a Python package console command is later added:

```bash
mise exec -- uv run <command>
```

should remain the preferred invocation.

Do not rely on globally installed Python packages.

---

## Optional dependencies

Tools may use optional dependencies when their purpose justifies them.

For example:

```text
onnx
onnxruntime
numpy
torch
matplotlib
protobuf
```

Heavy diagnostic dependencies should not automatically become core runtime
dependencies.

Where practical, define a dedicated dependency group in `pyproject.toml`.

For example:

```toml
[dependency-groups]
tools = [
    "onnx",
    "numpy"
]
```

and run:

```bash
uv sync --group tools
```

The exact dependency set should only be added when the corresponding tool is
introduced.

---

## Output location

Tools should not scatter generated files throughout the repository.

Recommended defaults are:

```text
tmp/tools/
```

for disposable output, or:

```text
results/
```

when the result is related to an evaluation run.

For example:

```text
tmp/
└── tools/
    ├── graph/
    ├── tensors/
    └── reports/
```

These locations remain excluded from Git.

---

## Candidate tools

The following tools are likely to become useful as ONNX development
progresses.

They are intentionally not created until required.

### `inspect_onnx.py`

Potential responsibilities:

- display opset version
- display graph inputs
- display graph outputs
- display dynamic dimensions
- list initializers
- list operator types
- inspect model metadata
- inspect external-data references
- calculate model SHA-256
- detect unsupported or suspicious graph structures

Example:

```bash
uv run python tools/inspect_onnx.py \
  .ci/candidate/model.onnx
```

---

### `compare_tensors.py`

Potential responsibilities:

- load `.npy` / `.npz`
- verify shapes and dtypes
- calculate maximum absolute error
- calculate mean absolute error
- calculate relative L2 error
- locate maximum-error coordinates
- identify NaN/Inf differences

Example:

```bash
uv run python tools/compare_tensors.py \
  reference.npy \
  candidate.npy
```

The official CI parity calculation must still live in:

```text
python/src/parakeet_onnx/evaluation/
```

This tool would only expose the comparison interactively.

---

### `inspect_ort.py`

Potential responsibilities:

- show ONNX Runtime version
- list available Execution Providers
- display provider options
- create a test session
- inspect actual provider assignments
- identify CPU fallback
- inspect optimized graph output

This is especially useful for:

```text
CPUExecutionProvider
CUDAExecutionProvider
DmlExecutionProvider
CoreMLExecutionProvider
```

---

### `inspect_audio.py`

Potential responsibilities:

- inspect source sample rate
- inspect channel count
- inspect duration
- inspect decoded dtype/range
- inspect canonical waveform
- verify float32 mono 16 kHz contract

It should use:

```text
parakeet_onnx.audio.decode
parakeet_onnx.audio.resample
```

rather than implementing an independent decoder/resampler.

---

### `inspect_manifest.py`

Potential responsibilities:

- show manifest entries
- show requested counts
- resolve deterministic selections
- show selected sample IDs
- detect overlap
- display duration distribution
- display dataset/revision provenance

Actual selection semantics must remain implemented in:

```text
parakeet_onnx.datasets
```

---

### `inspect_reference.py`

Potential responsibilities:

- inspect canonical NeMo reference metadata
- show reference revision
- list stored checkpoints
- list frontend/encoder/logit tensors
- verify artifact SHA-256 values

---

### `compare_runs.py`

Potential responsibilities:

Compare two:

```text
run-context.json
samples.jsonl
metrics.json
```

sets and summarize:

- revision differences
- model differences
- provider differences
- CER/WER changes
- RTF changes
- memory changes
- parity changes
- provider fallback changes

The official benchmark comparison CLI may later move into:

```text
parakeet_onnx.cli.compare
```

if it becomes part of the normal project workflow.

---

## Python vs Rust tools

Python is preferred for early development and investigation because the model
reference stack is Python/NeMo-based.

A tool should be rewritten in Rust only when one of the following becomes
important:

- Python overhead materially affects the measurement
- the diagnostic concerns Rust-specific runtime behavior
- the functionality becomes part of the deployment runtime
- maintaining Python and Rust behavior separately becomes undesirable

Do not rewrite diagnostic tools in Rust merely for consistency.

---

## Temporary experiments

Short-lived experimental scripts do not need to be retained.

Before committing a new file under `tools/`, ask:

1. Will this utility likely be used again?
2. Does it encode a non-obvious diagnostic procedure?
3. Is its behavior testable?
4. Does it belong to another package instead?
5. Would retaining it reduce future debugging effort?

If the answer is mostly no, keep the experiment outside the repository or
remove it after use.

---

## Tests

Reusable tools should be testable.

If a tool contains substantial reusable logic, move that logic into:

```text
python/src/parakeet_onnx/
```

and leave only CLI orchestration in:

```text
tools/
```

Tests should then live under:

```text
python/tests/
```

This avoids creating a second untested implementation layer.

---

## Relationship to future CLI commands

The project already reserves:

```text
python/src/parakeet_onnx/cli/
├── export.py
├── evaluate.py
├── compare.py
└── benchmark.py
```

A utility should migrate from `tools/` to the public CLI when it becomes part
of the normal supported workflow.

For example:

```text
early experimentation
    ↓
tools/compare_runs.py

workflow becomes stable
    ↓
parakeet_onnx.cli.compare
```

At that point the old development tool should normally be removed rather
than kept as a duplicate interface.

---

## Current state

No executable development tool is required yet.

The project currently has clear implementation locations for:

```text
configuration
datasets
audio
reference runtime
ONNX export
ONNX Runtime
decoding
evaluation
Hugging Face lifecycle
CI
development setup
```

Therefore adding placeholder Python scripts to this directory would only
create unused interfaces.

Tools should be introduced when an actual diagnostic requirement appears.

---

## Expected future structure

A possible future structure is:

```text
tools/
├── README.md
├── inspect_onnx.py
├── inspect_ort.py
├── inspect_audio.py
├── inspect_manifest.py
├── inspect_reference.py
├── compare_tensors.py
└── compare_runs.py
```

This is a direction, not a requirement.

The repository should add only the tools that become concretely useful.
