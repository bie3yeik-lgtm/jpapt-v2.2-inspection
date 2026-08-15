# NeMo Reference / Export Container

This directory defines the canonical NVIDIA NeMo environment used by the
Parakeet ONNX project.

```text
docker/
├── Dockerfile.nemo
└── README.md
```

The container is intentionally separate from the normal ONNX Runtime
development and evaluation environment.

---

## Purpose

The NeMo container is used for operations where NVIDIA NeMo is the canonical
reference implementation.

Typical responsibilities are:

- loading the pinned upstream Parakeet model
- generating reference transcriptions
- generating frontend reference tensors
- generating encoder reference tensors
- generating CTC logits
- generating future TDT reference outputs
- validating NeMo reference behavior
- developing ONNX export
- comparing exported ONNX behavior against NeMo

The normal evaluator should not require this container.

Conceptually:

```text
                    NeMo container
                         │
                         │ canonical reference
                         ▼
              reference transcription
              reference frontend
              reference encoder
              reference logits
                         │
                         │
                         ▼
                    HF Bucket
                    reference/
                         │
                         │
                         ▼
                  ONNX evaluator
```

---

# Why NeMo is isolated

The project has two substantially different runtime responsibilities.

## Reference/export runtime

```text
NVIDIA NeMo
PyTorch
CUDA
model loading
reference execution
ONNX export
```

This environment is heavyweight and tightly coupled to the NVIDIA software
stack.

## Deployment/evaluation runtime

```text
ONNX Runtime
CPU
CUDA EP
DirectML EP
CoreML EP
Rust
```

This runtime should remain as small and portable as possible.

Therefore:

```text
NeMo dependencies
      │
      X
normal runtime dependencies
```

must not be merged unnecessarily.

The NeMo Docker image is the isolation boundary.

---

# Canonical container image

The Dockerfile currently defaults to:

```text
nvcr.io/nvidia/nemo:26.02
```

The version must not silently float during canonical evaluation.

Although the Dockerfile exposes the image through:

```dockerfile
ARG NEMO_IMAGE=nvcr.io/nvidia/nemo:26.02
```

changing this argument is considered a reference-environment change.

Such a change should result in:

- a new reference run
- updated runtime identity
- new reference artifacts where necessary
- review of numerical parity
- potentially a new evaluation reference revision

Do not use:

```text
nvcr.io/nvidia/nemo:latest
```

for canonical evaluations.

---

# Building

From the repository root:

```bash
docker build \
  -f docker/Dockerfile.nemo \
  -t parakeet-onnx-nemo:26.02 \
  .
```

If the host UID/GID should be preserved:

```bash
docker build \
  -f docker/Dockerfile.nemo \
  --build-arg PROJECT_UID="$(id -u)" \
  --build-arg PROJECT_GID="$(id -g)" \
  -t parakeet-onnx-nemo:26.02 \
  .
```

---

# Using a different NeMo image

An explicit image can be supplied:

```bash
docker build \
  -f docker/Dockerfile.nemo \
  --build-arg \
    NEMO_IMAGE=nvcr.io/nvidia/nemo:<VERSION> \
  -t parakeet-onnx-nemo:<VERSION> \
  .
```

This must not be done implicitly in CI.

The chosen image version belongs in run provenance.

---

# NVIDIA GPU execution

On a CUDA-capable Docker host:

```bash
docker run \
  --rm \
  -it \
  --gpus all \
  --shm-size=8g \
  parakeet-onnx-nemo:26.02
```

Shared memory may need to be increased for some NeMo/PyTorch workloads.

The container must not assume a GPU exists merely because it was built from
an NVIDIA image.

Reference operations that work on CPU may still be executed without:

```text
--gpus all
```

but GPU is the normal environment for expensive NeMo execution.

---

# Repository bind mount

During interactive development, bind-mount the repository instead of
rebuilding the image after every source-code change.

From the repository root:

```bash
docker run \
  --rm \
  -it \
  --gpus all \
  --shm-size=8g \
  -v "$PWD:/workspace" \
  -w /workspace \
  parakeet-onnx-nemo:26.02
```

The source tree then remains editable on the host.

---

# Cache mounts

Model and dataset downloads should survive container destruction.

Recommended:

```bash
docker run \
  --rm \
  -it \
  --gpus all \
  --shm-size=8g \
  -v "$PWD:/workspace" \
  -v parakeet-hf-cache:/workspace/.cache/huggingface \
  -v parakeet-torch-cache:/workspace/.cache/torch \
  parakeet-onnx-nemo:26.02
```

This gives:

```text
container
├── /workspace
│   ├── repository
│   └── .cache/
│       ├── huggingface/   <- Docker volume
│       └── torch/         <- Docker volume
```

The Hugging Face model cache should not be committed to Git.

---

# Using a host Hugging Face cache

A host cache may also be mounted explicitly.

Example:

```bash
docker run \
  --rm \
  -it \
  --gpus all \
  --shm-size=8g \
  -v "$PWD:/workspace" \
  -v "$HOME/.cache/huggingface:/workspace/.cache/huggingface" \
  parakeet-onnx-nemo:26.02
```

Whether to use a named Docker volume or host directory is an operational
choice.

The logical container path remains:

```text
/workspace/.cache/huggingface
```

---

# Hugging Face authentication

Do not bake `HF_TOKEN` into the image.

Pass it only at runtime.

Example:

```bash
docker run \
  --rm \
  -it \
  --gpus all \
  --shm-size=8g \
  -e HF_TOKEN \
  -e HF_BUCKET \
  -e HF_MODEL_REPO \
  -v "$PWD:/workspace" \
  parakeet-onnx-nemo:26.02
```

The corresponding shell may contain:

```bash
export HF_TOKEN="..."
export HF_BUCKET="<namespace>/<bucket>"
export HF_MODEL_REPO="<namespace>/<model-repo>"
```

Never write these values into:

```text
Dockerfile.nemo
docker/README.md
config/
evaluation/
```

---

# Expected container environment

The Dockerfile defines:

```text
PARAKEET_ONNX_REPO_ROOT=/workspace

HF_HOME=/workspace/.cache/huggingface

HF_HUB_CACHE=/workspace/.cache/huggingface/hub

HF_DATASETS_CACHE=/workspace/.cache/huggingface/datasets

TORCH_HOME=/workspace/.cache/torch
```

Project runtime data therefore has predictable locations.

---

# Runtime directory layout

Inside the container:

```text
/workspace/
├── .cache/
│   ├── huggingface/
│   ├── torch/
│   ├── models/
│   └── evaluation/
│       └── audio/
│
├── .ci/
│   ├── hf/
│   │   └── config/
│   │       └── revisions/
│   ├── candidate/
│   └── reference/
│
├── results/
└── tmp/
```

The same logical layout is used outside the container.

---

# Materialized audio contract

Dataset audio selected for evaluation is materialized before it enters the
audio processing layer.

The formal contract is:

```text
ResolvedDatasetSample.audio_path
```

points to:

> a materialized local audio asset readable by the evaluation runtime through
> ordinary file I/O.

Inside the container, materialized evaluation audio normally lives under:

```text
/workspace/.cache/evaluation/audio/
```

The processing flow remains:

```text
HF Dataset
    ↓
DatasetResolver
    ↓
DatasetMaterializer
    ↓
materialized local audio
    ↓
ResolvedDatasetSample.audio_path
    ↓
decode_audio_sample()
    ↓
DecodedAudio
    ↓
to_canonical_audio()
    ↓
float32 / mono / 16 kHz
```

The Docker layer does not alter this contract.

---

# Fetching revision locks

Before reference execution:

```bash
scripts/hf/hf-fetch-revisions.sh
```

This produces:

```text
.ci/hf/config/revisions/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

Reference code must use these pinned revisions.

Do not resolve a floating Hugging Face revision independently from inside
reference code.

---

# Model revision policy

The upstream model revision comes from:

```text
.ci/hf/config/revisions/reference.json
```

Conceptually:

```text
reference.json
       │
       ▼
nvidia/parakeet-tdt_ctc-0.6b-ja
       @
exact revision SHA
       │
       ▼
NeMo reference loader
```

Do not replace the pinned revision with:

```text
main
latest
HEAD
```

during canonical reference generation.

---

# Dataset revision policy

Dataset versions are controlled by:

```text
datasets-lock.json
```

Evaluation manifests only contain logical dataset IDs:

```text
jsut-basic5000
common-voice-8-ja
reazonspeech-test
```

Resolution is:

```text
manifest dataset_id
       +
datasets-lock.json
       ↓
HF dataset repository
       @
exact revision
```

The Docker environment must not change these semantics.

---

# Reference generation

The canonical path is:

```text
locked upstream model
       ↓
NeMo
       ↓
CanonicalAudio
       ↓
NeMo frontend
       ↓
frontend output
       ↓
FastConformer encoder
       ↓
encoder output
       ↓
CTC head
       ↓
logits
       ↓
CTC decode
```

Reference artifacts can then be compared against the ONNX candidate.

---

# Frontend parity

The project deliberately separates:

```text
generic audio processing
```

from:

```text
model-specific frontend processing
```

The generic boundary is:

```text
CanonicalAudio
float32
mono
16000 Hz
```

The NeMo frontend receives this canonical representation.

This permits:

```text
CanonicalAudio
      │
      ├───────────────┐
      ▼               ▼
NeMo frontend    candidate frontend
      │               │
      ▼               ▼
reference         candidate
features          features
      │               │
      └───────┬───────┘
              ▼
           parity
```

This is one of the principal responsibilities of this container.

---

# ONNX export

ONNX export implementation belongs in:

```text
python/src/parakeet_onnx/export/
```

not in:

```text
docker/
```

The Dockerfile only supplies the reference/export environment.

Conceptually:

```bash
uv run parakeet-onnx export ...
```

or:

```bash
python -m parakeet_onnx.cli.export ...
```

once the CLI implementation is completed.

---

# Candidate location

Newly exported candidates should initially be written to a disposable local
location, for example:

```text
tmp/export/
```

They should then be validated before being uploaded to:

```text
hf://buckets/<namespace>/<bucket>/candidates/<candidate-id>/
```

The lifecycle is:

```text
NeMo
  ↓
ONNX export
  ↓
tmp/export/
  ↓
local structural validation
  ↓
HF Bucket candidates/
  ↓
evaluation
  ↓
promotion
```

Do not export directly into the HF Model Repo.

---

# Reference artifacts

Canonical reference artifacts belong in the Hugging Face Bucket:

```text
reference/
```

rather than Git.

Potential contents include:

```text
reference/
├── manifests/
├── outputs/
├── tensors/
└── metadata/
```

Examples of large reference data:

```text
frontend tensors
encoder tensors
logits
token sequences
reference audio-derived data
```

should never be placed under:

```text
evaluation/expected/
```

The Git-tracked:

```text
evaluation/expected/smoke.json
```

is intentionally limited to lightweight expected semantic behavior.

---

# CPU use

The Dockerfile does not fail merely because CUDA is unavailable.

This is intentional.

Some tasks such as:

```text
configuration inspection
model metadata inspection
small reference diagnostics
serialization testing
```

do not intrinsically require GPU execution.

However, expensive NeMo reference runs should generally use the intended
CUDA execution environment.

---

# macOS

This NeMo container is not the canonical macOS/CoreML evaluation
environment.

macOS evaluation belongs to the host ONNX Runtime environment:

```text
macOS
  ↓
ONNX Runtime
  ├── CPUExecutionProvider
  └── CoreMLExecutionProvider
```

Do not attempt to evaluate CoreML EP inside `Dockerfile.nemo`.

The container's canonical responsibility is NeMo reference generation.

---

# Windows

On Windows, the recommended conceptual split is:

```text
WSL2 / Docker
    ↓
NeMo reference/export

native Windows
    ↓
ONNX Runtime
    ├── CPU
    ├── CUDA
    └── DirectML
```

This keeps DirectML/native Windows testing independent from the Linux-based
NeMo container.

---

# Hugging Face Jobs

The Dockerfile is also intended to provide a reproducible basis for running
the same NeMo reference/export workload on remote GPU infrastructure.

The repository remains authoritative for:

```text
Dockerfile.nemo
config/
evaluation/
python/
```

while external execution infrastructure provides compute.

Secrets such as:

```text
HF_TOKEN
```

must be injected at execution time.

---

# Do not install another NeMo stack with uv

The NVIDIA base image owns the canonical:

```text
PyTorch
CUDA
NeMo
```

versions.

Therefore the Dockerfile intentionally installs this repository with:

```text
pip install --no-deps -e /workspace
```

after installing only the repository's additional utility dependencies.

Do not run a command that independently resolves another:

```text
torch
nemo-toolkit
CUDA Python stack
```

inside the reference container.

Otherwise the supposedly canonical container becomes a hybrid environment
whose behavior is no longer tied to its NVIDIA image version.

---

# Version identity

Every canonical reference run should record at least:

```text
container image
Python version
NeMo version
PyTorch version
CUDA availability/version
upstream model revision
tokenizer revision
dataset revisions
evaluation schema revision
Git commit
```

These identities belong in the run/reference provenance.

Container identity is just as important as model identity for numerical
reference data.

---

# Updating the NeMo container

When changing:

```dockerfile
ARG NEMO_IMAGE=...
```

perform the following sequence:

```text
1. Build the new image
        ↓
2. Run doctor/import verification
        ↓
3. Load pinned Parakeet model
        ↓
4. Run smoke reference
        ↓
5. Run parity reference
        ↓
6. Compare old/new frontend outputs
        ↓
7. Compare encoder outputs
        ↓
8. Compare logits/tokens/text
        ↓
9. Review differences
        ↓
10. Update reference revision only if intentional
```

A container upgrade must not automatically redefine canonical output.

---

# Security and reproducibility

Do not bake any of the following into the image:

```text
HF_TOKEN
GitHub tokens
AWS credentials
SSH private keys
personal cache contents
reference artifacts
candidate models
```

These are runtime inputs or external artifacts.

The Docker image itself should contain only:

```text
NVIDIA NeMo runtime
system dependencies
project source
project runtime dependencies
```

---

# What should remain outside the image

Do not COPY these directories as authoritative build-time data:

```text
.cache/
.ci/
results/
tmp/
target/
.venv/
```

They should be excluded through the repository `.dockerignore`.

The same applies to:

```text
*.onnx
*.nemo
*.wav
*.flac
*.npy
*.npz
```

unless a future dedicated test fixture is deliberately added.

---

# Typical local workflow

## 1. Build

```bash
docker build \
  -f docker/Dockerfile.nemo \
  -t parakeet-onnx-nemo:26.02 \
  .
```

## 2. Start

```bash
docker run \
  --rm \
  -it \
  --gpus all \
  --shm-size=8g \
  -e HF_TOKEN \
  -e HF_BUCKET \
  -e HF_MODEL_REPO \
  -v "$PWD:/workspace" \
  -v parakeet-hf-cache:/workspace/.cache/huggingface \
  parakeet-onnx-nemo:26.02
```

## 3. Fetch revision locks

Inside the container:

```bash
scripts/hf/hf-fetch-revisions.sh
```

## 4. Verify environment

```bash
python scripts/dev/doctor.py
```

## 5. Run reference/export commands

Once the Python CLI layer is implemented:

```bash
python -m parakeet_onnx.cli.export ...
```

or the corresponding project console command.

---

# Canonical lifecycle

The overall project lifecycle is:

```text
HF Bucket
config/revisions/
       │
       ▼
Dockerfile.nemo
       │
       ▼
canonical NeMo reference
       │
       ├───────────────┐
       ▼               ▼
reference data      ONNX export
       │               │
       ▼               ▼
HF Bucket         HF Bucket
reference/        candidates/
       │               │
       └───────┬───────┘
               ▼
            evaluate
               │
        ┌──────┴───────┐
        ▼              ▼
     rejected        accepted
                       │
                       ▼
              hf-promote-model.sh
                       │
                       ▼
                 HF Model Repo
```

The NeMo Docker environment exists only on the left-hand reference/export
side of this lifecycle.
