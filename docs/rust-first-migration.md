# Rust-first migration

## Status

**Completed for the defined production/runtime scope.**

Rust is the canonical implementation for stable, model-independent production/runtime responsibilities. Python remains only at explicit Python-native ML/tooling, dataset acquisition, reference/parity, and compatibility-test boundaries.

The target was never zero Python source files. The target was a Python layer with almost no business rules, validation policy, orchestration state, deterministic bookkeeping, or runtime-critical behavior. The final repository audit confirms that target has been reached.

## Canonical architecture

```text
                 +-------------------------------------------+
                 | Python-native / reference boundary        |
                 | ONNX/PyTorch tooling, HF datasets, E2E    |
                 +--------------------+----------------------+
                                      |
                           versioned file contracts
                                      |
                                      v
+-----------------------------------------------------------------------+
| Rust canonical core                                                    |
|                                                                       |
| asr-contracts  schemas/config/revisions/candidate/run-context/policy   |
| asr-audio      decode/resample/canonical waveform                      |
| asr-runtime    ONNX Runtime + provider handling                        |
| asr-metrics    normalization/CER/WER/telemetry                         |
| asr-eval       evaluation orchestration                                |
| asr-capsule    Parquet persistence/read/validate/analytics             |
| asr-hf         deterministic HF routing/layout/allocation bookkeeping  |
+-----------------------------------------------------------------------+
                                      |
                              thin shell / hf CLI
                                      |
                                      v
                         HF Bucket / Model Repo / CI
```

## Python retention policy

Python may remain when at least one of the following is true:

1. the upstream library is Python-only or its supported canonical API is Python;
2. the code is a reference/parity implementation used to prove Rust behavior;
3. replacing it would add a custom network/protocol implementation with lower reliability than a supported ecosystem tool;
4. it is test-only fixture/scaffolding around Python-native model tooling.

Python must not own production JSON/schema validation, filesystem/hash policy, deterministic artifact bookkeeping, run-context construction, provider policy, evaluation orchestration, metrics policy, or HF routing/allocation policy.

## Completed migration areas

### Contracts and persisted results

Rust owns:

- run-context, benchmark, sample-result, and run-directory validation;
- generated candidate contract validation;
- revision bundle validation and resolved config handling;
- Parquet capsule validation/summary and operational upload preflight;
- promotion/benchmark/config publication validation.

Python readers remain only where they provide compatibility/reference coverage, such as the Rust-producer -> Python-reader capsule interoperability test.

### Evaluation/runtime orchestration

Rust owns:

- resolved manifest consumption and contract checks;
- evaluator orchestration and result production;
- run-context construction;
- evaluator capability policy;
- provider strict-mode run-context construction;
- CoreML/DirectML readiness classification and readiness JSON emission.

The operational Rust evaluator does not shell out to Python for runtime policy or run-context construction.

### Hugging Face deterministic policy

Rust owns:

- target/bucket routing;
- runtime profile/decoder resolution;
- target/catalog validation and fingerprints;
- allocation catalog prefixes/fingerprints;
- deterministic sequence/allocation bookkeeping;
- repository/config identity policy.

Network/authentication operations continue to prefer the official `hf` CLI rather than reimplementing Hub protocols in Rust solely to eliminate a thin wrapper.

### Repository/CI policy

Rust owns stable repository policy including:

- GitHub Actions governed-version validation;
- catalog normalization/fingerprinting;
- evaluator capability validation;
- provider readiness classification.

Dead Python policy entrypoints and stale callers were deleted rather than mechanically ported.

## Intentional Python boundaries after final audit

The final `scripts/ci/*.py` surface is intentionally limited to five files:

| File | Classification | Reason retained |
|---|---|---|
| `resolve-candidate-artifacts.py` | `python-boundary` | Uses CandidateArtifacts and Python ONNX graph inspection to produce the versioned candidate execution contract consumed by Rust. |
| `prepare-rust-manifest.py` | `python-boundary` | Uses Hugging Face `datasets` acquisition/materialization; emits a materialized revision-pinned manifest consumed by Rust. |
| `e2e-provider-ctc.py` | `reference/test` | Builds synthetic ONNX fixtures for provider readiness probes. |
| `e2e-ctc-onnx.py` | `reference/test` | Public-model/reference ONNX preparation. |
| `e2e-rust-ctc.py` | `reference/parity` | Cross-checks Rust behavior against the Python/reference path. |

Additional inline Python in workflows is restricted to one of these categories:

- environment/package setup for Python-native tests;
- Python unit tests;
- public-model/reference workflows;
- Rust/Python interoperability tests;
- Python-native model/dataset preparation.

The public-model E2E workflow may resolve exact Hub revisions and manipulate models in Python because it is a reference/parity workflow, not a production runtime dependency.

## Compatibility strategy

The contract between Python-native preparation and production Rust is a versioned file, not a Python object.

Required compatibility patterns include:

- Python producer -> Rust consumer;
- Rust producer -> Python reference consumer;
- golden JSON/Parquet fixtures read by both;
- byte/hash equality where deterministic serialization is required;
- metric/tensor tolerances where exact equality is inappropriate.

A Python module can be removed only when no operational script or production workflow needs its Python-native behavior and compatibility coverage exists for the persisted contract.

## Dependency policy

- Keep Rust dependencies exact where Arrow/Parquet/ORT compatibility is sensitive.
- Do not add a Python dependency when an existing Rust crate or official CLI handles the responsibility.
- Production Rust must not shell out to Python.
- Keep official CLIs for authentication/network operations when replacing them would create a less reliable custom protocol implementation.
- Do not port Python reference or ML-tooling code merely to reduce the Python file count.

## Completion audit

The completion audit performed after the provider-readiness migration found:

- no remaining callers of the deleted stable-policy Python entrypoints;
- no remaining Python run-context generator;
- no remaining Python evaluator-capability policy;
- no remaining Python provider-readiness policy;
- exactly five `scripts/ci/*.py` files, all classified above as Python-native or reference/test boundaries.

Future Python additions under operational CI should be reviewed against the retention policy above. Stable model-independent policy belongs in Rust; Python additions should terminate at a versioned file boundary consumed and independently validated by Rust.
