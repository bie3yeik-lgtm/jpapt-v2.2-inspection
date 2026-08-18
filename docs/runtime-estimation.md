# Runtime estimation and workload evidence

Candidate request planning estimates execution time from observed workflow history while keeping workload-size evidence separate from the prediction formula.

## Current estimator

Canonical helper:

```text
scripts/ci/estimate-candidate-runtime.py
```

Machine-readable output contract:

```text
contracts/candidate-runtime-estimate.schema.json
CandidateRuntimeEstimateV5
```

A plan uses one of two methods:

```text
historical
fallback
```

For historical GitHub execution the estimator sums successful durations for the relevant canonical V2 run boundary:

```text
Resolve request
Build digest-pinned candidate package
selected execution job
```

For HF Jobs it uses the successful `Hugging Face Jobs` execution job when matching evidence is available.

The planning estimate is the observed p90 rounded upward. It is intentionally conservative and does not include queue delay that is not represented by GitHub job execution timestamps.

When no usable history exists, suite/environment fallback values remain authoritative.

## Provenance cohorts

Historical samples are selected in this order:

1. exact source repository + dataset identity, when at least three samples exist;
2. source repository, when at least three samples exist;
3. global suite/environment history.

The selected cohort is reported in the estimate object. A smaller exact cohort does not override a sufficiently populated broader cohort.

## Metadata-only workload measurement

Runtime planning can measure both the candidate and selected dataset source without downloading their payloads.

Boundary helpers:

```text
scripts/ci/measure-candidate-bucket-size.py
scripts/ci/measure-dataset-source-size.py
scripts/ci/measure-runtime-workload.py
```

Machine-readable boundaries:

```text
contracts/candidate-workload-probe.schema.json
contracts/dataset-workload-probe.schema.json
contracts/runtime-workload-evidence.schema.json
```

### Candidate

The candidate helper:

1. lists only HF Bucket metadata under `candidates/`;
2. replays the normalized request and source config through Rust `asr-candidate-request` to obtain candidate intent;
3. reuses Rust `asr-hf resolve-candidate-location` to select the canonical or historical candidate location;
4. sums file sizes supplied by Bucket metadata for the selected candidate.

Python therefore owns only the Hugging Face API boundary. Candidate/default/latest/location semantics remain Rust-owned.

### Dataset

The dataset helper mirrors what `run-candidate-package-evaluation.sh` materializes:

```text
bucket source      -> <HF bucket>/datasets recursively
repository source  -> complete HF dataset repository tree
custom source      -> complete HF dataset repository tree
```

For Bucket sources it uses Bucket file metadata. For repository/custom sources it uses dataset repository file metadata. The helper sums metadata sizes only; it does not download dataset payloads.

This makes `target_dataset_bytes` directly comparable with positive historical `dataset_bytes` produced by the evaluation runner for the same dataset identity.

### Composed evidence

`measure-runtime-workload.py` combines candidate and dataset evidence into `RuntimeWorkloadEvidenceV1`. `fully_available=true` means both measurements were available; partial metadata failure remains visible without pretending that the missing side is zero bytes.

## Automatic planning integration

In Candidate Request Gateway and Candidate Package Evaluate V2, the estimate step runs inside GitHub Actions with:

```text
/tmp/request.json
/tmp/source.json
HF_BUCKET
DATASET_SOURCE
DATASET_ID
```

The estimator therefore can invoke candidate and dataset metadata probes automatically. Outside GitHub Actions, automatic metadata probing is disabled unless `ENABLE_WORKLOAD_PROBE=true` is explicitly set. Explicit `--target-candidate-bytes` / `--target-dataset-bytes` values never require network access.

If the HF metadata boundary is unavailable, the affected workload measurement becomes `unavailable` and normal historical/fallback estimation continues. Structural request/candidate contract errors remain fail-closed at their owning boundary.

## Estimate V5 workload fields

Candidate evidence:

```text
workload_probe_method
workload_warning
target_candidate_id
target_candidate_bytes
target_candidate_files
target_candidate_legacy_layout
observed_candidate_bytes_p50
candidate_size_ratio_p50
```

Dataset evidence:

```text
dataset_workload_probe_method
dataset_workload_warning
target_dataset_bytes
target_dataset_files
observed_dataset_bytes_p50
dataset_size_ratio_p50
```

Additional historical package evidence remains:

```text
observed_package_bytes_p50
```

Both workload probe method fields are one of:

```text
none
explicit
metadata-only
unavailable
```

Ratios are explanatory evidence:

```text
candidate_size_ratio_p50 = target_candidate_bytes / observed_candidate_bytes_p50
dataset_size_ratio_p50   = target_dataset_bytes   / observed_dataset_bytes_p50
```

and are present only when the corresponding target and historical measurements are positive and comparable.

## Size evidence is not runtime scaling

Current contract:

```text
size_scaling_applied = false
```

Neither candidate nor dataset size ratio changes `estimate_minutes`.

This is deliberate. Candidate provenance uses different workload measures depending on execution path:

- native macOS CoreML / Windows DirectML evaluation records materialized `candidate_bytes`;
- Linux OCI evaluation records pulled image `package_bytes` while `candidate_bytes` is zero;
- HF Jobs historical provenance currently does not provide comparable positive candidate/package size measurements.

A candidate directory byte total must not be treated as interchangeable with OCI image size. The estimator therefore computes the candidate ratio only from positive historical `candidate_bytes`.

Dataset bytes are more comparable because all local evaluation paths materialize the selected dataset source and record its total file bytes. Even so, a dataset-size ratio alone does not establish a linear relationship with runtime: decoding duration, audio duration, sample count, preprocessing, provider behavior, and caching can dominate byte size.

## Conditions for future size-aware prediction

Do not introduce a multiplicative or linear correction merely because workload ratios are available.

A future scaling model should first establish:

1. comparable target and historical workload definitions for the selected executor/environment;
2. enough samples in the relevant provenance cohort;
3. audio-duration/sample-count evidence where appropriate, not only storage bytes;
4. an explicit fitted model or conservative bounded heuristic validated against held-out runs;
5. error metrics demonstrating improvement over the current p90/fallback baseline;
6. a source-controlled contract change that permits `size_scaling_applied=true` only when that model was actually used.

Until those conditions are met, workload sizes are explanatory evidence only.

## Explicit `latest` candidate semantics

Candidate requests may use:

```text
candidate-NNNNNN
latest
blank
```

Downstream Bucket resolution represents latest as an omitted concrete candidate ID. The Rust request contract normalizes an explicit `latest` to the same blank/latest representation while preserving caller intent: an explicit `latest` must not be replaced by a configured concrete candidate default.

The workload probe replays that same Rust contract before resolving the actual Bucket candidate, so planning and evaluation use identical latest/default semantics.

## Contract CI

Focused gates:

```text
Candidate Workload Probe Contracts
Dataset Workload Probe Contracts
Candidate Runtime Estimate Contracts
```

They verify:

- canonical/historical candidate path size aggregation;
- Rust resolver output validation and explicit `latest` semantics;
- Bucket and dataset-repository metadata-only dataset measurement;
- composed candidate + dataset workload evidence;
- normalized request -> Rust request resolver -> Rust candidate location resolver wiring;
- estimator V5 schema validation;
- explicit and automatic candidate/dataset size evidence;
- fallback runtime remaining unchanged when workload evidence is present;
- `size_scaling_applied=false` as a schema invariant.
