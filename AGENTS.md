# AGENTS.md

## Repository constitution

`AGENTS.md` is the repository's authoritative engineering constitution.

It is the **only file in this repository on which destructive operations are forbidden**.

The following operations must never be performed on `AGENTS.md`:

- deletion;
- replacement with an empty or placeholder document;
- wholesale removal of existing project rules merely to simplify an implementation;
- temporary removal during migrations or refactors;
- generation from another file in a way that discards manually maintained rules;
- treating this file as disposable compatibility documentation.

Changes to `AGENTS.md` must preserve its role as the durable source of repository-wide rules. Rules may be clarified, extended, reorganized, or explicitly superseded when project policy changes, but the file itself and the repository constitution it contains must remain present.

All other repository files, schemas, implementations, workflows, and documentation may be changed destructively when required by the task and when doing so produces a cleaner canonical design.

If an implementation conflicts with `AGENTS.md`, the implementation must be changed unless the task explicitly updates this constitution first.

## Project objective

This repository is a **quality evaluator and research control plane for ONNX ASR models**.

The project assumes that source ASR models can originate from heterogeneous technical stacks such as:

- Transformers;
- NVIDIA NeMo;
- PyTorch;
- other source-model frameworks used by upstream Hugging Face repositories.

For each source model, research or conversion work may produce original ONNX artifacts optimized for different execution environments. The relationship between the source repository and the corresponding development Hugging Face Bucket is defined through repository variables such as:

```text
HF_TARGETS_JSON
```

Each Hugging Face Bucket contains candidate ONNX artifacts and evaluation evidence for one source-model line. Candidates may be optimized independently for CPU, CUDA, DirectML, CoreML, or other explicitly supported environments.

The repository evaluates ASR accuracy, runtime behavior, provider behavior, and conversion quality across GitHub Actions runners. Evaluation results are serialized according to statically defined schemas and written back to the appropriate Hugging Face Bucket so that model-improvement research can be compared reproducibly over time.

The primary purpose is therefore not simply to export ONNX files. The repository exists to make **model quality investigation, regression detection, environment comparison, and iterative model improvement reproducible and efficient**.

## System model

The canonical lifecycle is:

```text
upstream HF Model Repo
  ↓ exact immutable revision
source-framework reference environment
  ↓
research / conversion / optimization
  ↓
HF Bucket
  └─ candidates/
       ├─ environment-specific ONNX artifacts
       ├─ generated contracts
       └─ conversion evidence
  ↓
GitHub Actions runners
  ├─ CPU
  ├─ CUDA
  ├─ DirectML
  └─ CoreML
  ↓
strict Rust evaluator
  ↓
schema-validated results
  ↓
HF Bucket runs/ and benchmarks/
  ↓
comparison / acceptance / further research
```

Source-model repositories, development Buckets, candidate artifacts, evaluation runs, and final release Model Repositories are separate identities and must not be conflated.

## Primary language: Rust

Rust is the default implementation language for repository logic.

The repository intentionally relies on Rust's language constraints, including:

- static typing;
- explicit enums and state transitions;
- ownership and lifetime guarantees;
- strict deserialization;
- exhaustive matching;
- compile-time validation of interfaces where possible.

The implementation philosophy is VSDD-like: specifications and schemas are treated as executable contracts, and the implementation should make invalid or ambiguous states difficult or impossible to represent.

The following are expected to be Rust-owned whenever practical:

- evaluation contracts;
- runtime contracts;
- candidate identity validation;
- provider evidence semantics;
- result aggregation;
- CER/WER authority;
- acceptance decisions;
- artifact integrity validation;
- Bucket safety operations;
- release CLI behavior;
- schema-adjacent semantic validation.

Model evaluation is highly sensitive to execution environment differences. Therefore the evaluator core and its schemas must be grounded in strict Rust definitions rather than loosely inferred runtime data.

## Secondary language: Python

Python is a secondary and deliberately limited implementation language.

Python may be preferred over Rust when its flexibility, compatibility, or reproducibility is materially more important than static guarantees, especially for:

- reproducing an upstream source-model environment;
- NVIDIA NeMo integration;
- Transformers/PyTorch integration;
- Hugging Face ecosystem compatibility;
- export adapters that must call framework-native Python APIs;
- dataset materialization where the upstream ecosystem is Python-native;
- GHCR/container entrypoint scripts used to produce evidence;
- small operational adapters where using Rust would reduce reproducibility or compatibility.

Python must not become the authority for repository-wide acceptance logic merely because the model ecosystem is Python-first.

Python is dynamically typed and library-version-sensitive. That makes it valuable for framework interoperability but less suitable as the final authority for stable evaluation semantics. Python output must therefore be converted into explicit evidence that can be checked by static schemas and, where possible, strict Rust semantic validation.

Canonical principle:

```text
Python/framework runtime
    = source-model compatibility and evidence production

Rust
    = contract, runtime, quality, integrity, and acceptance authority
```

## Source-framework error absorption

The de facto model-development ecosystem is Python-first. The project must assume that differences can arise between:

- PyTorch/Transformers/NeMo reference execution;
- ONNX export;
- ONNX Runtime execution;
- Rust preprocessing or decoding;
- provider-specific graph execution.

A major development objective is therefore to **identify, measure, and absorb errors introduced by the Rust/ONNX deployment path without losing fidelity to the source-framework model**.

When supplied with upstream documentation, model cards, research notes, failure reports, or project instructions, development should use those materials to improve the evaluator rather than force source-framework behavior into pre-existing assumptions.

Do not infer unresolved model-specific constants from unrelated model generations or similarly named architectures. Checkpoint-derived information must come from the exact source artifact or generated evidence.

## Evaluation authority and evidence

Do not treat final transcript equality as the only correctness test.

Depending on the model and stage, distinguish at least:

```text
source identity
artifact integrity
frontend parity
encoder parity
logits parity
token parity
decoder/state parity
text parity
CER/WER quality
performance
provider registration
provider execution
provider assignment
fallback behavior
```

Registration of an execution provider is not proof that the provider executed the graph. Execution is not proof of node assignment. Provider evidence must use the strongest claim actually demonstrated by runtime evidence.

For source-model versus ONNX quality comparisons, authoritative quality metrics should be recomputed by the same Rust implementation whenever possible rather than trusting separately calculated framework metrics.

## Evaluation datasets

The authoritative evaluation dataset set is defined by the schema/configuration associated with each Hugging Face Bucket.

Frequently reused baseline datasets may additionally be declared in the repository variable:

```text
EVALUATION_BASE_DATASETS
```

`EVALUATION_BASE_DATASETS` is a convenience/default source, not permission to override a Bucket's locked evaluation contract.

Canonical evaluation must resolve dataset revisions immutably and materialize exact sample identity, including hashes where required by the schema.

`ResolvedDatasetSample.audio_path` must refer to a materialized local file readable through ordinary file I/O by the runtime performing the evaluation.

## Hugging Face targets and Buckets

Repository variables such as:

```text
HF_TARGETS_JSON
```

define the supported source-model-repository ↔ Hugging Face Bucket relationships.

A Bucket is a research/evaluation store, not simply a file dump.

Typical responsibilities include:

```text
config/       locked evaluation/runtime configuration
candidates/   immutable or write-once candidate model bundles
experiments/  research notes or experiment identities
runs/         execution evidence and run results
benchmarks/   comparable benchmark results
```

Candidate output must never overwrite expected/reference evidence.

Promotion requires accepted evaluation and verified artifact identity, including SHA-256 where defined by contract.

Do not publish or promote a candidate merely because export or session creation succeeded.

## GitHub Actions

GitHub Actions is the canonical distributed evaluation harness for environment-specific testing.

Workflows should support research automation across available runners and providers while preserving exact model, candidate, dataset, configuration, and runtime identity.

Research workflows should be designed so they can be driven through:

```text
repository_dispatch
```

when practical. Manual `workflow_dispatch` may still be used for explicitly human-gated or destructive operations.

`repository_dispatch` payloads must be validated as untrusted external input. They must resolve to source-controlled contracts or immutable external identities before affecting evaluation or Bucket state.

GitHub Actions may also host research utilities derived from model-improvement experiments, provided those utilities preserve the same contract, provenance, and safety principles as the evaluator.

Do not use GitHub Actions runner labels or provider availability as proof of accelerator execution. Runtime evidence remains authoritative.

## Available external services

Canonical external services available to this project are:

```text
GitHub
Hugging Face
GHCR
```

Use them according to the following responsibility split:

```text
GitHub
  source control, pull requests, Actions, repository variables/secrets

Hugging Face
  upstream Model Repositories, datasets, development Buckets, Jobs where appropriate

GHCR
  immutable/reproducible container images for framework or evaluation environments
```

Do not silently introduce a new persistent external control plane when the existing services can satisfy the requirement.

## Execution providers

Supported logical ONNX Runtime execution providers currently include:

```text
cpu
cuda
directml
coreml
```

CoreML means ONNX Runtime CoreML Execution Provider unless the project constitution is explicitly changed.

Do not introduce MLX or native Core ML model conversion into the canonical runtime path without an explicit project-policy change.

Environment-specific candidates may differ when provider constraints require different ONNX graphs or optimization strategies. Such variants must remain distinguishable by candidate/profile/runtime identity.

## Canonical waveform baseline

Unless a model-specific locked contract explicitly requires otherwise, preserve the common waveform boundary used by the evaluator:

```text
float32
mono
16000 Hz
finite
C-contiguous
```

Generic audio decoding/resampling must remain separate from model-specific frontend logic.

Do not assume a source model's mel count, normalization, dither, scaling, tokenizer IDs, blank ID, duration vocabulary, tensor bindings, or state shapes from this generic waveform baseline.

## Schema and contract policy

Schemas are static, source-controlled evaluation contracts.

When a schema has not yet been used as a public/stable compatibility contract, destructive redesign is preferable to retaining ambiguous legacy fields.

Important identities should be concrete rather than nullable placeholders.

Prefer:

```text
explicit enum
explicit version
exact immutable revision
exact SHA-256
exact artifact role
exact provider/evaluation identity
```

over implicit defaults, type coercion, guessed values, or later mutation.

JSON structural validation alone is insufficient for security- or identity-sensitive contracts. Add typed semantic validation in Rust where cross-field invariants matter.

Unknown fields should generally be rejected for generated identity contracts and core execution records.

## Scripts and production logic

Do not place stable production logic in shell, PowerShell, or ad-hoc scripts.

Scripts should remain thin operational wrappers around canonical implementations.

Primary stable logic belongs under:

```text
rust/crates/
```

Python framework-compatibility logic belongs under:

```text
python/src/parakeet_onnx/
```

A script may remain Python when it is specifically a container/Hugging Face/framework entrypoint, but reusable behavior should be moved into the Python package rather than duplicated in scripts.

## Repository responsibilities

```text
config/       static and versioned configuration
evaluation/   schemas, manifests, lightweight expected data
rust/         canonical evaluator/runtime/contract implementation
python/       framework compatibility, source reference, export support
scripts/      thin operational wrappers
docker/       reproducible framework/reference/export environments
docs/         architecture and workflow documentation
tools/        optional inspection and diagnostics
.github/      CI, evaluation workflows, research automation
```

## Git and artifact restrictions

Do not commit large generated model, dataset, audio, tensor, or runtime-cache artifacts to Git unless a task explicitly changes this policy.

Typical exclusions include:

```text
.cache/
.ci/
results/
tmp/
target/
.venv/

*.onnx
*.nemo
*.safetensors
*.npy
*.npz
*.wav
*.flac
```

Large evaluation/model artifacts belong in Hugging Face Buckets, Model Repositories, GHCR, or workflow artifacts according to their lifecycle.

## Development and validation rules

Prefer deterministic and revision-pinned workflows.

Do not use floating model or dataset revisions in canonical evaluation after resolution. A human may request `main`, but canonical evidence must record the resolved immutable revision.

Keep model, provider, environment, candidate, and evaluation identities separate.

Keep development Bucket artifacts separate from final Model Repository releases.

For hybrid CTC/TDT systems, establish the simpler CTC deployment/evaluation path before claiming TDT runtime quality unless the task explicitly requires a different order.

Do not make TDT runtime-quality claims when only TDT export/state validation exists.

Do not weaken strict contracts merely to make legacy tests pass when the relevant contract has not been stabilized for external compatibility.

## Development direction

The evaluator should evolve toward higher fidelity to the original source-model implementation while keeping the deployed ONNX/Rust path reproducible across environments.

Development should prioritize:

1. source-framework parity and provenance;
2. deterministic ONNX export and artifact integrity;
3. Rust/runtime correctness;
4. provider-specific execution evidence;
5. ASR quality regression measurement;
6. performance measurement;
7. research utilities that accelerate model improvement.

GitHub Actions should increasingly serve both as the evaluation matrix and as a reproducible research-utility layer for model optimization experiments.

## Long-term direction

After the ASR evaluator becomes sufficiently mature, the project may expand beyond raw ASR accuracy into **post-correction evaluation for video subtitle generation**.

The long-term objective is to evaluate models that understand a conversation as a coherent sequence rather than as isolated utterances, including deeper contextual correction suitable for subtitle production.

This future evaluator may consider context such as:

- preceding and following utterances;
- speaker continuity;
- conversational semantics;
- terminology consistency;
- subtitle readability;
- segmentation and line-break quality;
- timing/context relationships with video content.

This future direction must be built on top of, not at the expense of, the reproducible source identity, dataset identity, model-quality, and runtime-evidence foundations established by the ASR evaluator.

## Existing operational commands

Environment setup:

```bash
scripts/dev/setup.sh
```

Doctor:

```bash
mise exec -- uv run python scripts/dev/doctor.py
```

Fetch revision locks:

```bash
scripts/hf/hf-fetch-revisions.sh
```

Promotion:

```bash
scripts/hf/hf-promote-model.sh <candidate-id> <accepted-run-directory>
```

When these commands conflict with newer canonical Rust CLI behavior or updated workflow contracts, update the wrappers rather than duplicating or bypassing the canonical implementation.
