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

`HF_TARGETS_JSON` retains its historical routing shape:

```json
{
  "parakeet-tdt_ctc-0.6b-ja": {
    "HF_BUCKET": "gawohok7/jpapt-v2.2-dev-bucket",
    "HF_MODEL_REPO": "gawohok7/jpapt-v2.2-dev"
  }
}
```

The variable is not allowed to silently override source-controlled routing. For every target, the resolver checks that its `HF_BUCKET` and `HF_MODEL_REPO` exactly match `asr-hf resolve-target`. It then matches Dockerfile `source.repo_id` and `source.framework` to the resolved target.

Therefore:

```text
HF_TARGETS_JSON
  = selection/routing snapshot checked by CI

config/hf-targets + config/models + asr-catalog
  = canonical repository contract
```

## 4. Authentication

### Preferred

Packages connected to this repository use the workflow `GITHUB_TOKEN`:

```yaml
permissions:
  contents: read
  packages: read
```

Build/publish jobs elevate only their own package permission:

```yaml
permissions:
  contents: read
  packages: write
  attestations: write
  id-token: write
```

### PAT fallback

If a package is not readable through the repository's `GITHUB_TOKEN`, create an Actions **secret** named:

```text
GHCR_PAT
```

with the minimum required package scope. Workflows use:

```text
GHCR_PAT if present
otherwise GITHUB_TOKEN
```

A PAT must not be stored in a repository variable. In particular, `vars.SUPERSECRET` is intentionally not consumed by these workflows. Repository variables are configuration, not secret storage. If that value is a PAT, migrate it to `secrets.GHCR_PAT` and delete the variable.

## 5. GHCR Build and Publish

Workflow:

```text
.github/workflows/ghcr-build-publish.yml
```

Triggers:

- pull request changing `docker/**` or the workflow itself;
- push to `main` changing `docker/**`;
- manual dispatch.

Behavior:

```text
scan docker/*/Dockerfile
    ↓
read io.jpapt.ghcr.package label
    ↓
Buildx build
    ↓
PR: build/load only
main/manual: push GHCR tags
    ↓
resolve image digest
    ↓
label/import smoke
    ↓
GitHub artifact attestation
    ↓
14-day build provenance artifact
```

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
- successful `GHCR Build and Publish` run on `main`.

Manual inputs:

```text
target          optional; blank = every Dockerfile-matched HF target
candidate_id    optional; blank = latest candidate in the target Bucket
runtime_variant optional; blank = Docker/target default
assessment      smoke / parity / full
image_tag       tag to resolve, normally latest
```

The actual evaluation flow is:

```text
HF_TARGETS_JSON
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
GHCR login
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

The repository is bind-mounted at `/workspace`; the project package is installed with `--no-deps`. The Docker image owns the heavyweight NeMo/PyTorch/CUDA environment, while candidate/config/dataset identity continues to come from the repository and HF revision locks.

## 7. GHCR Package Audit

Workflow:

```text
.github/workflows/ghcr-audit.yml
```

Triggers:

- manual dispatch;
- weekly schedule.

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

## 8. Provider lane separation

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

## 9. Current image contract

`docker/nemo-speech-26.07.00/Dockerfile` derives from:

```text
nvcr.io/nvidia/nemo-speech:26.07.00
```

It keeps NVIDIA's NeMo/PyTorch/CUDA ownership intact and adds the repository-side tools needed for reference/evaluation integration. Project ORT/HF identities are pinned:

```text
onnxruntime == 1.28.0
huggingface_hub == 1.24.0
```

The image must not bake `HF_TOKEN`, GHCR credentials, candidate IDs, or mutable HF revisions into a layer.

## 10. Operational failure interpretation

### Matrix discovery fails

Likely causes:

- malformed/missing `HF_TARGETS_JSON`;
- variable routing differs from source-controlled target config;
- Dockerfile missing required labels;
- no Docker source repo/framework matches the requested target.

### GHCR login/pull fails

First verify that the package grants this repository Actions access. If cross-repository access is required, configure `secrets.GHCR_PAT`; do not use a repository variable for the PAT.

### Image identity fails

The package tag points at an image that was not built from the current Docker contract, or an old package version predates the mandatory labels. Run `GHCR Build and Publish`, then evaluate the newly pushed digest.

### Evaluation fails but image audit passes

This indicates the environment is structurally valid but the candidate/config/dataset/runtime evaluation failed. Use the run artifacts and HF run output; do not classify it as a package-authentication failure.

### Attestation fails

The image was not produced by the attested build workflow or predates attestation support. Rebuild/publish the package through the canonical workflow.

## 11. Change policy

When changing a Docker reference environment:

```text
Dockerfile change
  ↓
PR build smoke
  ↓
merge
  ↓
GHCR push + digest + attestation
  ↓
automatic GHCR CPU evaluation
  ↓
HF Bucket run/benchmark evidence
  ↓
provider-specific native evaluation when required
```

Do not evaluate a locally built image and then separately push a different image as if they were the same experiment artifact.
