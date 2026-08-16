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

## 2. Candidate -> Dockerfile -> GHCR Package -> evaluation

Run **Candidate Package Evaluate** manually or send `repository_dispatch` type `jpapt.candidate-evaluate`.

Only `source_repository` is mandatory. `hf_bucket` is taken from `.jpapt/hf-bucket.yml`; if neither is supplied, the workflow derives `<HF namespace>/<reponame>-bucket`.

Important inputs:

| Input | Default | Meaning |
|---|---|---|
| `candidate_id` | latest | Empty means the existing Bucket candidate resolver selects the newest candidate; `candidate-NNNNNN` pins a sequence. |
| `package_name` | source repo name | GHCR package name. |
| `dataset_source` | `bucket` | `bucket`, `repository`, or `custom`. |
| `dataset_id` | empty | HF dataset repository for `custom`, or override for `repository`. |
| `suite` | `smoke` | `smoke`, `parity`, or `probe`. |
| `executor` | `github` | `github` or `hf_jobs`. |
| `environment` | `linux-cpu` | `linux-cpu`, `linux-cuda`, `macos-coreml`, `windows-directml`. |
| `hf_flavor` | `cpu-basic` | HF Jobs hardware flavor. |
| `dry_run` | false | Resolve all routing and print a coarse time estimate without downloading/building/running. |

The generated OCI image is defined by `docker/candidate-package/Dockerfile`. It embeds the resolved candidate and records source repository, Bucket, candidate ID, and package name as OCI labels. BuildKit uses GitHub Actions cache with `type=gha`, scoped per package.

## Dataset routing

`bucket` synchronizes `hf://buckets/<bucket>/datasets`.

`repository` reads `datasets.repository_dataset` from the source repository's `.jpapt/hf-bucket.yml`. This is intentionally separate from the Bucket dataset so a repository can keep an authoritative evaluation dataset on the HF Dataset Hub.

`custom` uses the freely supplied `dataset_id`.

For the generic package evaluator, parity cases are `.npz` files containing arrays named `input__<onnx-input-name>` and `output__<onnx-output-name>`. `probe` validates ONNX session creation/signatures. `smoke` loads every ONNX model and, when an `.npz` case exists, performs one inference. `parity` requires reference `.npz` cases and checks outputs with numerical tolerance.

## OS/provider behavior

Linux CPU/CUDA executes the generated OCI package directly. Hosted macOS and Windows runners cannot execute the same Linux OCI image natively, so those selections use the identical candidate and generic evaluator natively with `CoreMLExecutionProvider` or `DmlExecutionProvider`. This keeps provider probing truthful instead of pretending a Linux container validates CoreML/DirectML.

HF Jobs is restricted by this workflow to Linux environments. Hugging Face Jobs accepts a Docker image, a hardware flavor, environment/secrets, and Dataset/Bucket volumes; Bucket volumes can therefore be mounted directly at `/data`. The GHCR image must be pullable by HF Jobs (for example public, or otherwise exposed through a registry mechanism HF Jobs can access).

## Dispatch example

```json
{
  "event_type": "jpapt.candidate-evaluate",
  "client_payload": {
    "source_repository": "largoyo/Premiere-AutoProcess-Plugin",
    "candidate_id": "candidate-000042",
    "dataset_source": "bucket",
    "suite": "parity",
    "executor": "hf_jobs",
    "environment": "linux-cuda",
    "hf_flavor": "a10g-small",
    "dry_run": false
  }
}
```

A request from any other repository uses the same contract; no sender allow-list is required by these workflows.
