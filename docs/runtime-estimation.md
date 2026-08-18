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
CandidateRuntimeEstimateV4
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

## Metadata-only target candidate measurement

The estimator can obtain the concrete target candidate workload without downloading candidate payloads.

Boundary helper:

```text
scripts/ci/measure-candidate-bucket-size.py
```

The helper:

1. lists only HF Bucket metadata under `candidates/`;
2. replays the normalized request and source config through the Rust `asr-candidate-request` contract to obtain candidate intent;
3. reuses Rust `asr-hf resolve-candidate-location` to select the canonical or historical candidate location;
4. sums file sizes supplied by Bucket metadata for the selected candidate.

Python therefore owns only the Hugging Face API boundary. Candidate/default/latest/location semantics remain Rust-owned.

In Candidate Request Gateway and Candidate Package Evaluate V2, the estimate step already runs in the same job that created:

```text
/tmp/request.json
/tmp/source.json
```

and exposes the resolved:

```text
HF_BUCKET
```

When `--target-candidate-bytes` is not supplied explicitly, the estimator detects these files and automatically invokes the metadata-only workload probe. No workflow-specific duplicate candidate-selection logic is required.

If the HF metadata boundary is unavailable, workload measurement degrades to `workload_probe_method=unavailable` and normal historical/fallback runtime estimation continues. Structural request/candidate contract errors remain fail-closed in the workload helper itself.

## Estimate V4 workload fields

The estimate records:

```text
workload_probe_method
target_candidate_id
target_candidate_bytes
target_candidate_files
target_candidate_legacy_layout
workload_warning
observed_dataset_bytes_p50
observed_package_bytes_p50
observed_candidate_bytes_p50
candidate_size_ratio_p50
size_scaling_applied
```

`workload_probe_method` is one of:

```text
none
explicit
metadata-only
unavailable
```

`candidate_size_ratio_p50` is:

```text
target_candidate_bytes / observed_candidate_bytes_p50
```

and is only present when comparable historical candidate-byte evidence exists.

## Size evidence is not runtime scaling

Current contract:

```text
size_scaling_applied = false
```

The candidate-size ratio does **not** change `estimate_minutes`.

This is deliberate. Existing provenance records different workload measures depending on execution path:

- native macOS CoreML / Windows DirectML evaluation records materialized `candidate_bytes`;
- Linux OCI evaluation records pulled image `package_bytes` while `candidate_bytes` is zero;
- HF Jobs historical provenance currently does not provide comparable positive candidate/package size measurements.

A candidate directory byte total must not be treated as interchangeable with OCI image size. Therefore the estimator only computes the candidate ratio when historical `candidate_bytes` are positive and comparable.

Likewise, dataset source can be Bucket, repository, or custom. A single target dataset-size resolver is not yet authoritative for all three routing modes.

## Conditions for future size-aware prediction

Do not introduce a multiplicative or linear size correction merely because a target/historical ratio is available.

A future scaling model should first establish:

1. comparable target and historical workload definitions for the selected executor/environment;
2. enough samples in the relevant provenance cohort;
3. an explicit fitted model or conservative bounded heuristic validated against held-out runs;
4. error metrics demonstrating improvement over the current p90/fallback baseline;
5. a source-controlled contract change that sets `size_scaling_applied=true` only when that model was actually used.

Until those conditions are met, workload sizes are explanatory evidence only.

## Explicit `latest` candidate semantics

Candidate requests may use:

```text
candidate-NNNNNN
latest
blank
```

Downstream Bucket resolution represents latest as an omitted concrete candidate ID. The Rust request contract therefore normalizes an explicit `latest` to the same blank/latest representation while preserving caller intent: an explicit `latest` must not be replaced by a configured concrete candidate default.

The workload probe replays that same Rust contract before resolving the actual Bucket candidate, so planning and evaluation use identical latest/default semantics.

## Contract CI

Focused gates:

```text
Candidate Workload Probe Contracts
Candidate Runtime Estimate Contracts
```

They verify:

- canonical and historical candidate path size aggregation;
- Rust resolver output validation;
- metadata-only HF boundary behavior with a fake client;
- normalized request -> Rust request resolver -> Rust candidate location resolver wiring;
- explicit `latest` overriding a configured concrete default;
- estimator V4 schema validation;
- explicit and automatic target candidate size evidence;
- fallback runtime remaining unchanged when size evidence is present;
- `size_scaling_applied=false` as a schema invariant.
