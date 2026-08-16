# Rust-first migration plan

## Goal

Make Rust the canonical implementation for every stable, model-independent,
production/runtime responsibility. Keep Python only where the ecosystem itself
requires Python (primarily NeMo/PyTorch export/reference execution and narrowly
scoped Hugging Face integration without an adequate Rust/CLI equivalent).

The target is not zero Python source files. The target is a Python layer that
contains almost no business rules, validation policy, orchestration state, or
runtime-critical behavior.

## Target architecture

```text
                 +-------------------------------+
                 | Python-only ML boundary       |
                 | NeMo / PyTorch / export       |
                 +---------------+---------------+
                                 |
                      machine-readable contracts
                                 |
                                 v
+------------------------------------------------------------------+
| Rust canonical core                                               |
|                                                                  |
| asr-contracts  config/contracts/candidate/run-context validation  |
| asr-audio      decode/resample/canonical waveform                 |
| asr-runtime    ONNX Runtime + provider handling                   |
| asr-metrics    normalization/CER/WER/telemetry                    |
| asr-eval       evaluation orchestration                           |
| asr-capsule    Parquet persistence/read/validate/analytics        |
| asr-hf         deterministic HF object/layout operations (later)  |
+------------------------------------------------------------------+
                                 |
                          thin shell wrappers
                                 |
                                 v
                   HF Bucket / Model Repo / CI
```

## Python retention policy

Python may remain when at least one of the following is true:

1. the upstream library is Python-only or its supported canonical API is Python;
2. the code is a reference/parity implementation used to prove Rust behavior;
3. replacing it would add a custom network/protocol implementation with lower
   reliability than an official CLI;
4. it is temporary migration scaffolding with an explicit removal milestone.

Python should not remain merely for JSON parsing, schema validation, filesystem
operations, hashing, Parquet processing, evaluation orchestration, audio
processing, metrics, provider selection, or deterministic artifact bookkeeping.

## Migration phases

### Phase 1 — capsule and upload validation (started here)

- expose `asr-capsule` as a stable CLI;
- move Parquet validation/summary used by operational workflows to Rust;
- make `hf-push-run.sh` invoke Rust for capsule validation;
- retain Python reader/analytics temporarily for compatibility tests;
- add Rust/Python interop coverage before later Python deletion.

Exit criteria:

- operational Parquet validation no longer imports `datasets` or `pyarrow`;
- Rust CLI validates run ID and reports sample/diagnostic/artifact/metric counts;
- CI covers the CLI and existing Python compatibility path.

### Phase 2 — contracts and JSON I/O

Create an `asr-contracts` crate and migrate:

- run-context validation;
- benchmark/sample-result validation;
- generated-candidate contract loading and validation;
- deterministic JSON/JSONL read/write helpers;
- revision-pin and SHA-256 invariants.

Then replace Python validation in HF push/promote scripts with Rust commands.
Python schema functions become compatibility/reference helpers only.

### Phase 3 — dataset manifest and evaluation orchestration

Move to Rust:

- resolved manifest parsing;
- sample materialization contract checks;
- run allocation/input validation;
- evaluator orchestration;
- result/receipt production.

Keep dataset acquisition in Python only where Hugging Face `datasets` is still
required. Its output must be a fully materialized, revision-pinned manifest that
Rust can consume without importing `datasets`.

### Phase 4 — Hugging Face operations

Prefer the official `hf` CLI behind thin scripts first. Move policy and layout
rules to Rust:

- object paths and immutable run naming;
- upload preflight;
- promotion receipts and hash verification;
- candidate/reference/run relationship validation.

Do not reimplement authentication or HTTP protocols solely to eliminate a thin
CLI wrapper.

### Phase 5 — model-independent Python utilities

Audit and migrate remaining Python implementations of:

- audio preprocessing;
- decoding shared with runtime;
- metrics/normalization;
- provider/runtime inspection;
- filesystem/hash/config helpers.

Delete Python duplicates after parity fixtures prove equivalence.

### Phase 6 — minimize the export/reference boundary

Keep only the code that genuinely requires NeMo/PyTorch/Transformers or other
Python-first model tooling. The boundary should accept and emit versioned files,
not Python objects consumed by production Rust.

## Compatibility strategy

During migration, the contract is the files and schemas, not Python classes.
Every migrated area should use at least one of these tests:

- Python producer -> Rust consumer;
- Rust producer -> Python reference consumer;
- golden JSON/Parquet fixtures read by both;
- byte/hash equality where deterministic serialization is required;
- metric/tensor tolerances where exact equality is inappropriate.

A Python module can be removed only when no operational script or production
workflow imports it and compatibility coverage exists for its persisted contract.

## Dependency policy

- Keep Rust dependencies exact for Arrow/Parquet/ORT where compatibility is
  sensitive.
- Do not add a Python dependency when an existing Rust crate or official CLI
  handles the responsibility.
- Do not make production Rust shell out to Python.
- Python may invoke a built Rust CLI only as temporary compatibility scaffolding;
  final operational entrypoints should invoke Rust directly.

## Immediate work queue

1. `asr-capsule validate` and `asr-capsule summary` CLI.
2. Switch HF run preflight Parquet validation to that CLI.
3. Add CLI unit/integration coverage.
4. Introduce `asr-contracts` and migrate JSON contract validation.
5. Remove `datasets/pyarrow` from operational capsule validation dependencies.
6. Audit Python package by module and mark each as `migrate`, `reference`, or
   `python-boundary`.
