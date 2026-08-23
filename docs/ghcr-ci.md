# GHCR CI / Reference Environment Evaluation

## 1. Purpose

This repository uses GitHub Container Registry (GHCR) as an immutable execution-environment artifact for heavyweight reference/export environments such as NVIDIA NeMo.

The current Docker environment is:

```text
docker/nemo-speech-26.07.00/Dockerfile
  -> ghcr.io/<repository-owner>/nemo-speech-26.07.00
  -> source repo: nvidia/parakeet-tdt_ctc-0.6b-ja
  -> framework: nemo
  -> role: reference-export
```

The Docker image is not treated as the ASR candidate itself. Candidate ONNX artifacts remain in Hugging Face Buckets. The GHCR digest identifies the reference/evaluation environment used to execute a run.

## 2. Why digest identity is mandatory

Human-facing tags such as `latest` can move. A run therefore resolves a tag once, reads the immutable OCI digest, and executes:

```text
ghcr.io/<namespace>/<package>@sha256:<digest>
```

The run context stores GHCR provenance under `metadata.ghcr`:

```json
{
  "ghcr": {
    "image": "ghcr.io/<namespace>/nemo-speech-26.07.00",
    "digest": "sha256:...",
    "reference": "ghcr.io/<namespace>/nemo-speech-26.07.00@sha256:...",
    "docker_context": "docker/nemo-speech-26.07.00",
    "role": "reference-export"
  }
}
```

`results/<run>/ghcr-environment.json` is also emitted as an operational sidecar.

## 3. Dockerfile -> HF target resolution

A Dockerfile that participates in GHCR evaluation must contain these labels:

```dockerfile
LABEL io.jpapt.source.repo_id="nvidia/parakeet-tdt_ctc-0.6b-ja"
LABEL io.jpapt.source.framework="nemo"
LABEL io.jpapt.ghcr.package="nemo-speech-26.07.00"
LABEL io.jpapt.role="reference-export"
```

`scripts/ci/resolve-ghcr-matrix.sh` performs the mapping.

Inputs:

```text
Dockerfile labels
+
vars.HF_TARGETS_JSON
+
source-controlled config/hf-targets/*.toml
+
config/models/*.toml
+
config/asr-catalog.json
```

`HF_TARGETS_JSON` keeps the existing repository-variable routing shape:

```json
{
  "parakeet-tdt_ctc-0.6b-ja": {
    "HF_BUCKET": "gawohok7/jpapt-v2.2-dev-bucket",
    "HF_MODEL_REPO": "gawohok7/jpapt-v2.2-dev"
  }
}
```

The variable is not allowed to create a target or silently override source-controlled routing. The resolver first enumerates `config/hf-targets/*.toml`. For each repository-defined target that also exists in `HF_TARGETS_JSON`, it checks that `HF_BUCKET` and `HF_MODEL_REPO` exactly match `asr-hf resolve-target`. It then matches Dockerfile `source.repo_id` and `source.framework` to the resolved target.

An entry present only in `HF_TARGETS_JSON` is ignored with a warning until a corresponding source-controlled target exists. `kotoba-whisper-v2.2` is now source-controlled, so it participates in routing only through `config/hf-targets/kotoba-whisper-v2.2.toml`; when the variable snapshot also contains that target, its Bucket and Model Repo must exactly match the source-controlled route. Unknown variable-only targets remain warnings and cannot become runtime targets.

Therefore:

```text
HF_TARGETS_JSON
  = checked selection/routing snapshot

config/hf-targets + config/models + asr-catalog
  = canonical repository contract
```

## 4. Authentication

GHCR authentication uses only the repository workflow permission and the ephemeral `github.token`.

Read jobs declare:

```yaml
permissions:
  contents: read
  packages: read
```

Build/publish jobs elevate only their own required permissions:

```yaml
permissions:
  contents: read
  packages: write
  attestations: write
  id-token: write
```

`docker/login-action` uses:

```yaml
with:
  registry: ghcr.io
  username: ${{ github.actor }}
  password: ${{ github.token }}
```

There is no PAT fallback in the canonical workflow. `vars.SUPERSECRET` is not consumed by GHCR CI. Repository variables are treated as configuration rather than credentials.

## 5. GHCR Build and Publish

Workflow:

```text
.github/workflows/ghcr-build-publish.yml
```

Triggers:

- pull request changing `docker/**` or the workflow itself;
- push to `main` changing `docker/**`;
- manual dispatch;
- external repository dispatch through `repository-dispatch.yml`.

### Build contract

Environment import/version smoke is part of the Dockerfile itself. The final build stage imports NeMo/PyTorch/ONNX/ORT/HF and asserts the repository-pinned ORT/HF versions. A build cannot succeed if that environment contract is broken.

This is deliberate: a heavyweight image does not need to be exported to the runner's Docker daemon solely to execute a post-build import test.

### PR behavior

```text
PR event
  ↓
compare previous PR head -> current PR head
  ↓
Docker/build-workflow changed?
  ├─ no  -> finish after lightweight gate
  └─ yes -> Buildx build
              ↓
            Dockerfile-integrated import/version smoke
              ↓
            GHA build cache
              ↓
            lightweight provenance artifact
```

PR builds use:

```text
push = false
load = false
```

The large image is therefore not copied from BuildKit into the Docker daemon merely for smoke validation.

### Build cache strategy

The Buildx build uses two cache layers, independently scoped by Docker package:

```text
cache-from:
  GitHub Actions cache, version 2
  GHCR registry cache: <image>:buildcache

cache-to:
  GitHub Actions cache, mode=min, version 2
  GHCR registry cache, mode=min, non-PR events only
```

The GitHub Actions cache is the primary PR cache target and is exported on a
best-effort basis. Fork or restricted PRs may be unable to write it; the
export is therefore `ignore-error=true`. The registry cache is a durable
cross-runner source for publicly readable packages and is written only by
push/manual publish runs; fork or PR builds never write to GHCR.
`image-manifest=true`, OCI media types, and zstd compression keep the
registry cache consumable by current Buildx versions. A cache miss is safe:
Buildx falls back to a normal build, while cache export availability cannot
turn a valid image build into a failure.

The cache tag is an optimization artifact only. The published image identity
continues to be the returned immutable image digest; `:buildcache` must never
be used as an evaluation or promotion identity.

`pull_request.paths` evaluates the PR change set, which can cause the workflow to be started again after unrelated later commits. The explicit previous-head/current-head gate suppresses the expensive build on those synchronize events.

Concurrency is scoped to the heavyweight `build` job rather than the whole workflow. Docs-only synchronize runs never enter that concurrency group, while a newer real Docker build for the same package can cancel an obsolete build job.

### main/manual behavior

```text
Buildx build
  ↓
Dockerfile-integrated import/version smoke
  ↓
repository-token GHCR push
  ↓
validate returned sha256 digest
  ↓
GitHub artifact attestation
  ↓
14-day build provenance artifact
```

A just-pushed heavyweight image is **not** pulled back by this workflow. Registry-object verification is owned by `ghcr-audit.yml`, and actual digest-pinned execution is owned by `ghcr-evaluate.yml`. This avoids paying for a redundant pull while keeping those checks in dedicated lanes.

Published aliases:

```text
:latest
:<git-sha>
```

Neither tag is the experiment identity; the digest is.

## 6. GHCR Environment Evaluation

Workflow:

```text
.github/workflows/ghcr-evaluate.yml
```

Triggers:

- manual dispatch;
- weekly scheduled smoke run;
- successful `GHCR Build and Publish` run on `main`;
- external repository dispatch through `repository-dispatch.yml`.

Manual/repository-dispatch inputs:

```text
target          optional; blank = every Dockerfile-matched source-controlled target
candidate_id    optional; blank = latest candidate in the target Bucket
runtime_variant optional; blank = target/catalog default
evaluation      smoke / parity / full
image_tag       tag to resolve, normally latest
```

The actual evaluation flow is:

```text
HF_TARGETS_JSON
      ↓
repository-defined targets
      ↓
Dockerfile labels + asr-hf target resolution
      ↓
evaluation matrix
      ↓
fetch current revision bundle
      ↓
resolve/fetch candidate from HF Bucket
      ↓
central experiment allocation
      ↓
repository-token GHCR login
      ↓
pull <image>:<tag>
      ↓
freeze RepoDigest
      ↓
verify image labels against target
      ↓
docker run <image>@sha256:...
      ↓
Python ONNX evaluator, CPU lane
      ↓
run-context + samples + metrics + run.parquet
      ↓
Rust run validation
      ↓
HF Bucket runs/<run-id>/
      ↓
benchmarks/<candidate>/ghcr-<package>-cpu/<run-id>.json
```

The repository is bind-mounted at `/workspace`. Project source is loaded with:

```text
PYTHONPATH=/workspace/python/src
```

The evaluation workflow does not pip-install project dependencies into the pulled image at runtime. This preserves the meaning of the recorded GHCR digest as the dependency/runtime environment identity. The image owns the heavyweight NeMo/PyTorch/CUDA/ORT/HF dependency stack; candidate/config/dataset identity continues to come from repository contracts and pinned HF revision documents.

The container runs with the GitHub runner UID/GID so generated run files remain writable by subsequent host-side validation/upload steps.

## 7. GHCR Package Audit

Workflow:

```text
.github/workflows/ghcr-audit.yml
```

Triggers:

- manual dispatch;
- weekly schedule;
- external repository dispatch through `repository-dispatch.yml`.

Checks:

- target/Dockerfile mapping;
- package pull and digest freeze;
- OCI/project labels;
- `org.opencontainers.image.source`;
- GitHub artifact attestation;
- NeMo/PyTorch/ONNX/ORT/HF/datasets/scipy/soundfile import smoke;
- `onnxruntime == 1.28.0`;
- `huggingface_hub == 1.24.0`;
- `pip check`;
- Docker inspect/history evidence upload.

Audit results are retained as GitHub artifacts for 30 days.

## 8. GHCR Contract Validation

Workflow:

```text
.github/workflows/ghcr-contracts.yml
```

This is the fast gate before the heavyweight image build/evaluation lanes. It verifies:

- every participating Dockerfile has required jpapt labels;
- `docker/<environment>/config.json` source identity matches its Dockerfile labels;
- Dockerfile source identity can be matched to a source-controlled HF target;
- the matching `HF_TARGETS_JSON` route agrees with repository routing;
- repository HF target validation succeeds;
- GitHub Action version policy succeeds;
- every workflow is reachable through the repository-dispatch router;
- Rust can parse all current `workflow_dispatch` contracts and resolve a defaulted GHCR evaluation request.

Dispatch reachability and input policy are enforced through `asr-workflow-dispatch`, not through a second hand-maintained workflow catalog.

## 9. Repository dispatch

Every workflow is externally reachable through:

```text
event_type = jpapt.workflow
```

The router accepts the target workflow filename/alias, target ref, and the same input object used by that workflow's `workflow_dispatch` contract. Rust reads the workflow YAML and applies required/default/type/choice validation before the router calls the GitHub workflow-dispatch API.

See [repository-dispatch.md](./repository-dispatch.md) and [github-actions-ux.md](./github-actions-ux.md).

This keeps repository-dispatch parsing centralized rather than duplicating `client_payload` handling across all workflow YAML files.

## 10. Provider lane separation

GHCR Linux containers do not replace native provider lanes.

```text
GHCR Linux environment
├── CPU        supported by ghcr-evaluate.yml
├── CUDA       future self-hosted/GPU lane
└── TensorRT   future dedicated lane

native Windows
└── DirectML   existing rust-eval/provider-strict workflows

native macOS
└── CoreML     existing rust-eval/provider-strict workflows
```

DirectML and CoreML must not be claimed as validated merely because the Linux GHCR image builds or its CPU run passes.

## 11. Current image contract

`docker/nemo-speech-26.07.00/Dockerfile` derives from:

```text
nvcr.io/nvidia/nemo-speech:26.07.00
```

It keeps NVIDIA's NeMo/PyTorch/CUDA ownership intact and adds only project-side tools needed for reference/evaluation integration. Project ORT/HF identities are pinned:

```text
onnxruntime == 1.28.0
huggingface_hub == 1.24.0
```

The final Docker build step imports the required runtime modules and asserts these pins. The image must not bake `HF_TOKEN`, GHCR credentials, candidate IDs, or mutable HF revisions into a layer.

## 12. Operational failure interpretation

### Matrix discovery fails

Likely causes:

- malformed/missing `HF_TARGETS_JSON`;
- variable routing differs from source-controlled target config;
- Dockerfile missing required labels;
- no Docker source repo/framework matches the requested source-controlled target.

An extra variable-only target is a warning rather than a runtime target.

### Build fails during environment smoke

The base image or project-side package layer does not satisfy the declared NeMo/ONNX/ORT/HF environment contract. This is a build failure, not an evaluator failure.

### GHCR login/pull fails

Verify that the package grants this repository GitHub Actions access and that the job declares the appropriate `packages: read` or `packages: write` permission. GHCR workflows do not fall back to a PAT.

### Image identity fails

The package tag points at an image that was not built from the current Docker contract, or an old package version predates the mandatory labels. Run `GHCR Build and Publish`, then audit/evaluate the newly pushed digest.

### Evaluation fails but image audit passes

This indicates the environment is structurally valid but the candidate/config/dataset/runtime evaluation failed. Use the run artifacts and HF run output; do not classify it as a package-authentication failure.

### Attestation fails

The image was not produced by the attested build workflow or predates attestation support. Rebuild/publish the package through the canonical workflow.

## 13. Change policy

When changing a Docker reference environment:

```text
Dockerfile change
  ↓
PR Buildx smoke (no daemon export)
  ↓
merge
  ↓
GHCR push + digest + attestation
  ↓
registry audit / automatic GHCR CPU evaluation
  ↓
HF Bucket run/benchmark evidence
  ↓
provider-specific native evaluation when required
```

Do not evaluate a locally built image and then separately push a different image as if they were the same experiment artifact.
