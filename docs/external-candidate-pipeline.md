# External candidate package pipeline

This repository accepts requests from arbitrary GitHub repositories. `largoyo/Premiere-AutoProcess-Plugin` is not special-cased.

## 1. Bootstrap a repository-backed HF Bucket

Run **External Repository Bucket Bootstrap** manually or send `repository_dispatch` type `jpapt.bucket-bootstrap` with at least:

```json
{
  "event_type": "jpapt.bucket-bootstrap",
  "client_payload": {
    "repository": "owner/repository"
  }
}
```

The workflow:

1. reads GitHub repository metadata;
2. infers the HF namespace from `hf_namespace`, `HF_DEFAULT_NAMESPACE`, or the authenticated `HF_TOKEN` user;
3. creates or reuses `namespace/<reponame>-bucket`;
4. writes `bucket.json` into the Bucket;
5. generates `.jpapt/hf-bucket.yml`;
6. writes that YAML back to the source repository when `write_repo_config=true`.

Required secrets/variables:

- `HF_TOKEN`: HF token allowed to create/read/write the target Bucket and optionally submit Jobs.
- `SOURCE_REPO_TOKEN`: fine-grained PAT or GitHub App token with **Contents: write** on arbitrary source repositories. GitHub's per-repository `GITHUB_TOKEN` cannot write to unrelated repositories.
- `HF_DEFAULT_NAMESPACE` (optional repository variable): preferred HF owner/org when it differs from the authenticated user.

Generated source config defaults missing information instead of rejecting a general repository:

```yaml
schema_version: 1
source_repository: owner/repository
source_ref: main
hf_bucket: namespace/repository-bucket
candidate:
  collection: candidates
  default: latest
datasets:
  default_source: bucket
  bucket_prefix: datasets
  repository_dataset: ""
evaluation:
  default_suite: smoke
  suites: [smoke, parity, probe]
package:
  registry: ghcr.io
  default_name: repository
```

## 2. Candidate -> runtime-specific OCI package -> evaluation

Run **Candidate Package Evaluate** manually or send `repository_dispatch` type `jpapt.candidate-evaluate`.

Only `source_repository` is mandatory. The workflow attempts to read `.jpapt/hf-bucket.yml` from that repository. Missing configuration is not fatal when a safe default can be derived.

Resolution order is intentionally deterministic:

1. explicit dispatch/manual input;
2. source repository `.jpapt/hf-bucket.yml`;
3. generated convention/default.

This means:

- `hf_bucket`: explicit value -> repository config -> `<HF namespace>/<reponame>-bucket`;
- `candidate_id`: explicit `candidate-NNNNNN` -> repository `candidate.default` -> latest;
- `package_name`: explicit value -> repository `package.default_name` -> repository name;
- `dataset_source=auto`: repository `datasets.default_source` -> `bucket`.

Important inputs:

| Input | Default | Meaning |
|---|---|---|
| `candidate_id` | repository default/latest | Empty means the Bucket candidate resolver selects the newest candidate unless the source config pins one. |
| `package_name` | source config/repo name | GHCR package name. |
| `dataset_source` | `auto` | Resolve from source config, otherwise `bucket`. Explicit values are `bucket`, `repository`, `custom`. |
| `dataset_id` | empty | HF dataset repository for `custom`, or override for `repository`. |
| `suite` | `smoke` | `smoke`, `parity`, or `probe` for GitHub execution. **HF Jobs accepts only `smoke`.** |
| `executor` | `github` | `github` or `hf_jobs`. `hf_jobs` is intentionally smoke-only. |
| `environment` | `linux-cpu` | `linux-cpu`, `linux-cuda`, `macos-coreml`. DirectML is retired and rejected. |
| `hf_flavor` | `cpu-basic` | HF Jobs hardware flavor; availability is checked with `hf jobs hardware` immediately before job creation. |
| `hf_jobs_image` | empty | Optional immutable image override. When set for HF Jobs it must use `@sha256:<64 hex>` and must resolve anonymously. |
| `dry_run` | false | Resolve routing and print a coarse time estimate without candidate download/build/evaluation. |

All `repository_dispatch` values are validated explicitly. Manual `choice` inputs are not considered sufficient validation because dispatch payloads do not inherit GitHub UI choice constraints.

For `executor=hf_jobs`, Rust request resolution rejects `probe` and `parity` **before the candidate package build**. Those suites remain available with `executor=github`.

## Package identity and cache

`docker/candidate-package/Dockerfile` embeds the resolved candidate and records source repository, Bucket, candidate ID, runtime environment, ONNX Runtime package, and package name as OCI labels.

The image is runtime-specific:

| Environment | Python ORT package | Requested provider |
|---|---|---|
| `linux-cpu` | `onnxruntime` | `CPUExecutionProvider` |
| `linux-cuda` | `onnxruntime-gpu` | `CUDAExecutionProvider` |
| `macos-coreml` | `onnxruntime` | `CoreMLExecutionProvider` |

BuildKit uses GitHub Actions cache with `type=gha`, scoped by package **and runtime environment**. A CUDA image therefore does not reuse a CPU image layer scope as if they represented the same runtime.

After build/push, the workflow reads the produced `sha256:` digest and passes `ghcr.io/...@sha256:...` to evaluation. Mutable tags remain convenience aliases only; validation evidence is tied to the immutable digest.

## Dataset routing

`bucket` uses `hf://buckets/<bucket>/datasets`.

`repository` reads `datasets.repository_dataset` from the source repository's `.jpapt/hf-bucket.yml`. An explicit `dataset_id` overrides it.

`custom` requires an explicit `dataset_id`.

For the generic package evaluator, parity cases are `.npz` files containing arrays named `input__<onnx-input-name>` and `output__<onnx-output-name>`.

- `probe` creates ONNX Runtime sessions and records model I/O/provider registration.
- `smoke` loads every ONNX model and, when an `.npz` case exists, performs one inference.
- `parity` requires reference `.npz` cases and checks outputs with numerical tolerances.

The HF Jobs operational test surface deliberately uses only `smoke`; `probe` and `parity` are not remote-HF test modes.

## Strict provider evidence

The generic evaluator does **not** silently fall back to CPU anymore.

If the requested provider is absent from `onnxruntime.get_available_providers()`, the evaluator writes a result with:

```json
{
  "passed": false,
  "failure": "REQUESTED_PROVIDER_UNAVAILABLE"
}
```

and exits non-zero. The report also records platform information, ONNX Runtime version, requested provider, available providers, and active providers for every session.

This rule is important for CoreML and CUDA validation: a successful CPU inference is not evidence that the requested provider works.

## GitHub runner behavior

- `linux-cpu` uses `ubuntu-latest`.
- `macos-coreml` uses `macos-14` and evaluates the same candidate natively.
DirectML requests are rejected before dispatch and have no native evaluation path.
- `linux-cuda` with `executor=github` requires a self-hosted runner carrying labels `self-hosted`, `linux`, `x64`, `gpu` and a Docker/NVIDIA runtime capable of `docker run --gpus all`.

`ubuntu-latest` is deliberately not treated as CUDA-capable. If no suitable self-hosted GPU runner exists, the guarded HF Jobs smoke route can validate the Linux CUDA package remotely.

Hosted macOS runners cannot execute the Linux OCI package as a native CoreML environment, so that path fetches the identical candidate and runs the strict evaluator natively. The GHCR package remains provenance for the candidate/runtime build, while provider evidence is produced by the target OS.

## HF Jobs smoke behavior

HF Jobs is deliberately restricted to **smoke validation on Linux**. The operational entrypoint is the manual-only **HF Jobs Smoke** workflow (`.github/workflows/hf-jobs-smoke.yml`). It has no suite input and requires `confirm_smoke=true`. It dispatches the canonical evaluator with fixed values:

```text
suite = smoke
executor = hf_jobs
dry_run = false
```

The generic V2 evaluator remains defensive: Rust `asr-candidate-request` rejects a non-smoke HF Jobs request before build, and Rust `asr-hf-job` rejects a non-smoke or tampered persisted plan before any HF CLI invocation.

The Rust HF Jobs plan is schema version 2 and is the authority for remote invocation. It binds:

- concrete candidate ID;
- Linux environment and ONNX Runtime provider;
- dataset routing and mounts;
- immutable digest-pinned selected image and digest;
- canonical output URI;
- fixed remote timeout `30m`;
- smoke-identifying labels;
- the exact `hf jobs run` argv.

Before any paid remote Job is created, the GitHub-side execution path performs two independent preflights:

1. `scripts/ci/hf-jobs-image-preflight.sh` resolves the selected digest-pinned OCI manifest with a fresh empty `DOCKER_CONFIG`. This proves the image is anonymously pullable and deliberately prevents a GitHub runner registry login from masking a private-image failure.
2. `asr-hf-job run` executes `hf jobs hardware` and requires the requested `hf_flavor` to appear in the returned hardware list.

A private/unreachable image or unavailable hardware flavor therefore fails before `hf jobs run` is invoked. The image preflight is intentionally anonymous because Hugging Face Jobs cannot depend on the GitHub runner's GHCR login state when it pulls the remote execution image.

The validated plan is uploaded as an Actions artifact **before remote execution**. The plan's canonical result location is:

```text
runs/hf-jobs/<candidate-id>/smoke-<github-run-id>-<attempt>/result.json
```

When `dataset_source=bucket`, `/jpapt-output/datasets` is used directly. Repository/custom datasets are mounted separately read-only.

The workflow invokes `hf jobs run` through the validated Rust plan without detach mode. The remote invocation includes the Rust-enforced `30m` timeout. Completion receipt generation independently rejects HF Jobs receipts whose suite is not `smoke`, and validates the selected image/digest and supplied result URI against the canonical smoke layout.

`hf_jobs_image` exists because the execution image must be pullable by Hugging Face Jobs. The default is the digest-pinned image built by the workflow. If that package is private or otherwise not anonymously resolvable, the preflight fails before remote Job creation; provide a public digest-pinned mirror through `hf_jobs_image` or publish the package for anonymous pull.

Pull-request and contract CI never create a real HF Job. They use fake `hf`/`docker` executables to prove hardware-preflight ordering, anonymous-image-preflight behavior, exact argv forwarding, unavailable-flavor rejection, and fail-closed behavior for tampered plans.

## Evaluation provenance

GitHub-runner evaluations upload two files when available:

```text
results/candidate-package/
├── result.json
└── evaluation-provenance.json
```

HF Jobs evaluation artifacts additionally preserve the validated `hf-job-plan.json`.

`evaluation-provenance.json` binds the evidence to:

- source repository;
- HF Bucket;
- resolved candidate ID;
- immutable image digest/reference;
- suite;
- environment/provider;
- dataset routing.

This prevents a later `latest` tag movement from changing the meaning of a historical evaluation artifact.

## Guarded HF Jobs smoke example

Prefer manually running **HF Jobs Smoke** rather than dispatching `Candidate Package Evaluate V2` directly. A corresponding fixed internal V2 request is equivalent to:

```json
{
  "source_repository": "owner/source-repository",
  "candidate_id": "candidate-000042",
  "dataset_source": "bucket",
  "suite": "smoke",
  "executor": "hf_jobs",
  "environment": "linux-cpu",
  "hf_flavor": "cpu-basic",
  "dry_run": false
}
```

A request using `executor=hf_jobs` with `suite=probe` or `suite=parity` is rejected. A request from any source repository otherwise uses the same routing contract; no source-repository allow-list is hard-coded in these workflows.
