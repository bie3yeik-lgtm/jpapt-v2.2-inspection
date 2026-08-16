# External candidate contract CI

`External Candidate Workflow Contracts` protects the repository-driven Bucket/candidate pipeline from syntax and contract regressions.

## Scope

The workflow intentionally validates only the generic external pipeline instead of every historical workflow in the repository:

- `.github/workflows/candidate-package-evaluate.yml`
- `.github/workflows/external-bucket-bootstrap.yml`
- `.github/workflows/external-candidate-contracts.yml`
- `docker/candidate-package/Dockerfile`
- `scripts/ci/generic-candidate-evaluate.py`
- `scripts/ci/run-candidate-package-evaluation.sh`

This prevents unrelated legacy or experiment workflows from blocking improvements to the external pipeline.

## Checks

1. `actionlint v1.7.12` validates GitHub Actions YAML and expression contexts.
2. `bash -n` validates the shared Bash evaluation helper.
3. `python -m py_compile` validates the generic evaluator.
4. `docker buildx build --check` validates the candidate package Dockerfile without performing a full package build.

The Go module/build cache is persisted with `actions/cache`, keyed to the pinned actionlint version and runner platform.

## Why this exists

An invalid GitHub Actions workflow can appear as a failed `push` run with no jobs at all. That failure mode was observed while developing `candidate-package-evaluate.yml`: GitHub registered the file by path but did not expose the configured workflow name and generated no executable jobs.

The candidate workflow was rewritten to use static runner jobs for Linux CPU, self-hosted Linux CUDA, macOS CoreML, Windows DirectML, and HF Jobs. GitHub now registers it under the explicit name `Candidate Package Evaluate`.

## Provider strictness

`generic-candidate-evaluate.py` treats the requested Execution Provider as part of the evidence contract. It does not silently turn a CoreML, DirectML, or CUDA request into a CPU success.

For non-CPU providers, strict mode also sets ONNX Runtime session configuration `session.disable_cpu_ep_fallback=1`. If the requested provider is unavailable or cannot create the session without CPU fallback, the evaluation fails and records a machine-readable failure reason.

## Runtime boundaries

The OCI package is always a Linux image. Linux CUDA packages install `onnxruntime-gpu`; other target environments use a Linux `onnxruntime` package inside the OCI image. macOS CoreML and Windows DirectML evidence is generated natively on their corresponding GitHub runners with the target-specific Python runtime package.

This separation prevents a Linux container from being presented as evidence for CoreML or DirectML while still keeping candidate/package provenance consistent across environments.
