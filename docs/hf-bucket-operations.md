# Reusable Hugging Face Bucket Operations

This document defines the reusable Bucket lifecycle used by this repository. It
is intentionally framework-neutral so the same design can be copied to other
model-development repositories.

## 1. Design goals

The Bucket is mutable development/evaluation object storage. The Hugging Face
Model Repo is the promoted artifact repository. Git is the source of truth for
code, schemas, target definitions, and workflow logic.

The design has five explicit goals:

1. configuration changes are versioned and reproducible;
2. candidate and experiment identifiers are machine allocated;
3. human-readable prefixes describe purpose but never own a sequence;
4. evaluation runs remain immutable, globally unique execution records;
5. GitHub Actions can select a target from `HF_TARGETS_JSON` without encoding
   Bucket names in source code.

## 2. Canonical Bucket tree

```text
hf://buckets/<namespace>/<bucket>/
├── config/
│   ├── current.json
│   └── versions/
│       ├── config-000001/
│       │   ├── reference.json
│       │   ├── evaluation-schema.json
│       │   └── datasets-lock.json
│       ├── config-000002/
│       │   ├── reference.json
│       │   ├── evaluation-schema.json
│       │   └── datasets-lock.json
│       └── ...
├── experiments/
│   ├── <prefix>-000001/
│   │   └── README.md
│   ├── <prefix>-000002/
│   │   └── README.md
│   └── ...
├── candidates/
│   ├── <prefix>-000001/
│   │   ├── README.md
│   │   ├── metadata.json
│   │   └── <model artifacts>
│   ├── <prefix>-000002/
│   └── ...
├── reference/
│   ├── manifests/
│   ├── outputs/
│   ├── tensors/
│   └── metadata/
├── runs/
│   └── <run-id>/
│       ├── run-context.json
│       ├── samples.jsonl
│       ├── metrics.json
│       └── promotion.json
├── benchmarks/
│   └── <candidate-id>/
│       └── <environment-provider>/
│           └── <run-id>.json
├── scripts/
└── tmp/
```

The tree is framework-neutral. NeMo, Transformers, CTC, TDT, Whisper
autoregressive decoding, CPU, CUDA, DirectML, and CoreML are metadata/runtime
properties rather than top-level storage categories.

## 3. Target routing with GitHub Repository Variables

GitHub Actions uses one Repository Variable:

```text
HF_TARGETS_JSON
```

Example:

```json
{
  "model-a": {
    "HF_BUCKET": "example/model-a-dev-bucket",
    "HF_MODEL_REPO": "example/model-a-dev"
  },
  "model-b": {
    "HF_BUCKET": "example/model-b-dev-bucket",
    "HF_MODEL_REPO": "example/model-b-dev"
  }
}
```

Rules:

- target IDs are stable logical target names;
- every `HF_BUCKET` must be unique inside the map;
- `HF_MODEL_REPO` identifies the development/promoted artifact repo;
- Bucket routing is operational state and is not duplicated into
  `reference.json`;
- model/framework/decoder semantics remain source-controlled target config.

The required secret is:

```text
HF_TOKEN
```

## 4. Versioned configuration

### 4.1 Why `config/current.json` exists

Buckets are mutable object storage. Overwriting
`config/revisions/reference.json` would lose the simple path from an old run to
the exact three revision documents that governed it.

The canonical design therefore stores immutable configuration sets under
`config/versions/` and keeps only a small mutable pointer in `current.json`.

### 4.2 `current.json`

Minimum form:

```json
{
  "schema_version": 1,
  "config_version": "config-000002"
}
```

The active version must match:

```text
config-[0-9]{6}
```

### 4.3 Version directory

```text
config/versions/config-000002/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

A published `config-NNNNNN` directory is immutable. To change any of the three
documents, create a new configuration version and then update `current.json`.
Do not mutate an older version in place.

### 4.4 Fetch selection

`scripts/hf/hf-fetch-revisions.sh` performs:

```text
HF_BUCKET
  ↓
config/current.json
  ↓
config_version
  ↓
config/versions/<config_version>/
  ↓
reference.json + evaluation-schema.json + datasets-lock.json
  ↓
.ci/hf/config/revisions/
  ↓
strict RevisionBundle validation
```

For normal execution, `current.json` is authoritative.

For reproduction of an old run, set:

```bash
HF_CONFIG_VERSION=config-000123
```

The override selects that immutable version while still recording which version
was selected.

Local staging contains:

```text
.ci/hf/config/
├── current.json
├── resolved.json
└── revisions/
    ├── reference.json
    ├── evaluation-schema.json
    └── datasets-lock.json
```

`resolved.json` records at least:

```json
{
  "schema_version": 1,
  "config_version": "config-000123",
  "current_version": "config-000200",
  "selection_source": "override"
}
```

The selected `config_version` is serialized into `run-context.json.revisions`.

## 5. Strict `reference.json` identity model

`reference.json` has four separate responsibilities:

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "example/development-model-repo",
    "revision": "<MODEL_REPO_COMMIT>"
  },
  "upstream": {
    "repo_id": "vendor/upstream-model",
    "revision": "<UPSTREAM_COMMIT>"
  },
  "tokenizer": {
    "repo_id": "vendor/tokenizer-or-processor",
    "revision": "<TOKENIZER_COMMIT>"
  },
  "reference": {
    "id": "framework-reference-v1",
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

- `development_artifact`: promoted/development HF Model Repo snapshot;
- `upstream`: source checkpoint used for conversion/reference;
- `tokenizer`: tokenizer/processor source, independently pinned;
- `reference`: implementation that produces the canonical expected result.

No Bucket ID is stored in `reference.json`.

## 6. Machine-managed sequential IDs

### 6.1 ID shape

Candidates and experiments use:

```text
<prefix>-NNNNNN
```

Examples:

```text
kotoba-whisper-v1.0-candidate-000002
cpu-full-eval-000003
cross-platform-parity-000004
rust-eval-000005
```

The six-digit suffix is the identity sequence. The prefix is descriptive only.

### 6.2 One sequence per collection

The allocator does **not** maintain a separate counter for each prefix.

Given:

```text
experiments/
├── cpu-full-eval-000002/
├── graph-optimization-000003/
└── cross-platform-parity-000007/
```

allocating prefix `cpu-full-eval` produces:

```text
cpu-full-eval-000008
```

This rule prevents two semantically different prefixes from accidentally
reusing the same numeric identity.

### 6.3 `000001` as an example/reserved directory

If a structure example already exists as:

```text
something-000001/README.md
```

the allocator sees `000001`, therefore the first real allocation is `000002`.
No special-case code is required.

### 6.4 Allocation algorithm

`scripts/hf/hf-allocate-id.sh`:

1. recursively lists all objects below `candidates/` or `experiments/`;
2. reads the first path component for each object;
3. extracts every trailing six-digit suffix;
4. finds the maximum suffix irrespective of prefix;
5. adds one;
6. writes `<allocated-id>/README.md` immediately;
7. returns the allocated ID.

The helper implementing the deterministic numeric rule is:

```text
scripts/ci/next-hf-sequence-id.py
```

### 6.5 Why README is created immediately

Object storage has no durable empty directory. Writing `README.md` serves two
purposes:

- it reserves/materializes the allocated path;
- it explains why the directory exists and who/what allocated it.

README metadata includes the collection, prefix, sequence, allocation time,
target, candidate, evaluation, provider, and GitHub run identifiers when
available.

The numeric suffix must never be manually reused or renumbered.

## 7. Concurrency and race avoidance

A pure `list → max + 1 → write` algorithm is not safe when two allocators run at
the same time.

GitHub Actions therefore isolates allocation in a short job with:

```yaml
concurrency:
  group: hf-experiment-id-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

Only the allocator job is serialized. The expensive evaluation jobs remain
parallel.

When this design is copied to another repository, every workflow that allocates
from the same Bucket collection must use the **same concurrency-group naming
convention**. Otherwise independent workflows can race.

For local/manual publishing, avoid running multiple allocation commands against
the same Bucket simultaneously. A future server-side atomic allocator can
replace this restriction without changing the ID format.

## 8. Candidate lifecycle

### 8.1 Candidate creation

A candidate is an artifact selected for evaluation. The human does not choose
the numeric ID.

Publish with:

```bash
HF_TOKEN=... \
HF_BUCKET=example/model-dev-bucket \
HF_TARGET_ID=model-a \
bash scripts/hf/hf-push-candidate.sh ./local-candidate
```

Default prefix is derived from the target:

```text
model-a-candidate-NNNNNN
```

An explicit descriptive prefix may be supplied when a workflow has a stable
semantic purpose:

```bash
bash scripts/hf/hf-push-candidate.sh ./local-candidate encoder-only
```

The script:

1. allocates the next candidate ID;
2. creates the remote README reservation;
3. updates local `metadata.json.candidate_id` when present;
4. syncs the artifact directory without deleting the reservation README.

### 8.2 Candidate selection for evaluation

Evaluation workflows still receive `candidate_id` as an input. This is not
manual ID allocation; it explicitly identifies **which existing immutable
candidate is being evaluated**.

Automatically evaluating "the newest candidate" would make a rerun select a
different artifact and would break reproducibility, so selection remains
explicit.

## 9. Experiment lifecycle

Experiments are automatically allocated when an evaluation workflow starts.
Current prefixes include:

```text
cpu-full-eval
cross-platform-parity
rust-eval
```

One logical cross-platform workflow receives one experiment ID. Matrix jobs for
Linux, Windows, macOS, CPU, CoreML, etc. share that experiment ID so the
experiment groups multiple execution runs of the same evaluation intent.

Python and Rust evaluators write the experiment identifier to:

```text
run-context.json.metadata.experiment_id
```

`run_id` remains independently generated and globally unique.

## 10. Runs and benchmarks

### Runs

Runs are execution records rather than manually numbered project entities.
They use time/model/environment/provider/artifact identity rather than the
six-digit collection sequence.

```text
runs/<run-id>/
```

A run records:

- candidate ID;
- experiment ID;
- config version;
- revision bundle hash;
- upstream/tokenizer/development artifact identities;
- runtime/provider/environment;
- artifact SHA-256;
- GitHub run metadata.

### Benchmarks

Benchmarks are organized by candidate and execution environment/provider:

```text
benchmarks/<candidate-id>/
├── linux-cpu/
├── linux-cuda/
├── windows-cpu/
├── windows-cuda/
├── windows-directml/
├── macos-cpu/
└── macos-coreml/
```

Framework names are not needed in this level because candidate/run metadata
already identifies the target and decoder.

## 11. GitHub Actions responsibilities

### Validate HF Layout

PR/push:

- validates repository-owned schemas, target configs, and synthetic fixtures;
- does not require the mutable remote Bucket to be valid.

Manual `workflow_dispatch`:

- resolves the selected Bucket from `HF_TARGETS_JSON`;
- reads `config/current.json`;
- fetches the selected `config/versions/config-NNNNNN` set;
- validates the strict revision bundle against the selected target;
- validates required Bucket directories, including `experiments/`.

### CPU Full Evaluation

- user selects an existing candidate;
- allocator job creates `cpu-full-eval-NNNNNN`;
- evaluation reads the current config version;
- result records experiment/config identities.

### Cross Platform ONNX Parity

- one `cross-platform-parity-NNNNNN` experiment ID is allocated;
- all matrix jobs share it;
- each job still receives its own run ID and benchmark environment/provider.

### Rust Cross Platform Evaluation

- one `rust-eval-NNNNNN` experiment ID is allocated;
- all Rust matrix jobs share it;
- Rust serializes the same strict revision identities/config version as Python.

## 12. Reproducing an old evaluation

Given a previous `run-context.json`:

1. read `artifact.candidate_id`;
2. read `metadata.experiment_id`;
3. read `revisions.config_version`;
4. set `HF_CONFIG_VERSION` to that version;
5. fetch the exact candidate ID;
6. execute the same provider/environment/evaluation config;
7. compare artifact and revision bundle hashes before accepting the rerun.

Example:

```bash
export HF_CONFIG_VERSION=config-000023
bash scripts/hf/hf-fetch-revisions.sh
bash scripts/hf/hf-fetch-candidate.sh model-a-candidate-000041
```

## 13. Migrating this design to another repository

Copy/adapt these components:

```text
scripts/ci/next-hf-sequence-id.py
scripts/hf/hf-allocate-id.sh
scripts/hf/hf-push-candidate.sh
scripts/hf/hf-fetch-revisions.sh
scripts/hf/hf-fetch-candidate.sh
scripts/ci/validate-revisions.py
```

Also reproduce:

```text
HF_TOKEN secret
HF_TARGETS_JSON repository variable
config/current.json
config/versions/config-NNNNNN/
```

Recommended source-controlled concepts:

```text
config/hf-targets/
evaluation/schemas/
unit tests for revision loading
unit tests for ID allocation
```

When copying GitHub workflows, preserve the shared allocator concurrency group
for every workflow that allocates IDs in the same collection.

## 14. Operational invariants

The following are hard rules:

1. never overwrite an existing `config-NNNNNN` version;
2. never reuse a candidate/experiment numeric suffix;
3. prefixes may change; numeric allocation still scans the entire collection;
4. immediately materialize an allocation with README.md;
5. evaluation may select an old candidate explicitly;
6. normal execution follows `config/current.json`;
7. reproducibility may override with `HF_CONFIG_VERSION`;
8. `reference.json` never contains `HF_BUCKET`;
9. `development_artifact.repo_id` must match the selected target's
   `HF_MODEL_REPO`;
10. run identity and experiment identity are separate concepts;
11. no destructive Bucket sync is used for append-oriented history;
12. external Bucket state must not make ordinary PR source tests nondeterministic.

## 15. Identity summary

```text
Target ID
  └─ what logical model target is selected

Config version: config-NNNNNN
  └─ which immutable revision document set governs the run

Candidate ID: <prefix>-NNNNNN
  └─ which model artifact set is evaluated

Experiment ID: <prefix>-NNNNNN
  └─ which logical evaluation/experiment groups one or more runs

Run ID
  └─ one concrete execution on one runtime/provider/environment

Benchmark path
  └─ comparable summary of one run for one candidate/environment/provider
```

Keeping these identities separate is the core of the design.
