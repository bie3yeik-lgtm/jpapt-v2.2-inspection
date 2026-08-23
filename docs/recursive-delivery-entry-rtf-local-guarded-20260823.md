# RTF local guarded verification entry — 2026-08-23

## Objective

Run the RTF score GitHub Actions execution path locally against the pulled
NeMo Speech base image, using the smallest guarded/content-probe boundary
available before spending GPU time on the full benchmark. Continue to HF Jobs
and RunPod only after the local image and guarded contract are executable.

## Scope and non-goals

In scope:

- `docker/rtf-benchmark/Dockerfile` build from the pinned local
  `nvcr.io/nvidia/nemo-speech:26.07.00` image;
- image import, entrypoint, Python package, and guarded DataLoader contract;
- local GPU availability and the boundary between local evidence and provider
  evidence.

Out of scope for this entry:

- a local full smoke benchmark or ranking result;
- unpinned model/dataset downloads;
- HF/RunPod mutation or cost-bearing provider execution before the local guard
  is runnable.

## Current implementation authority

- Runner: `docker/rtf-benchmark/benchmark-runner/benchmark_runner/`.
- Provider entrypoint: `docker/rtf-benchmark/entrypoint.sh`.
- Image definition: `docker/rtf-benchmark/Dockerfile`.
- DataLoader safety boundary: `transcribe_compat.py`, which constrains
  constructor kwargs before NeMo creates a DataLoader and does not mutate
  guarded attributes after initialization.

## Evidence collected

### Source and host contract

- Worktree was clean at entry on
  `codex/fix-hf-cuda-illegal-access-20260821`.
- Existing `parakeet-rtf-benchmark:local-test` is stale: it does not contain
  `benchmark_runner/transcribe_compat.py` and cannot prove the current fix.
- Host NVIDIA driver sees an RTX 3060 with 12 GiB VRAM via `nvidia-smi`.
- Host Python guarded tests pass: 5 tests, including a hard-coded NeMo
  DataLoader constructor regression fixture.

### Docker build and runtime

- Base image is present locally as
  `nvcr.io/nvidia/nemo-speech:26.07.00`.
- The current Dockerfile build reached the base image, build context, and the
  apt layer, but was canceled after the Docker engine stopped responding while
  `shared-mime-info` was being configured.
- Subsequent `docker run`, `docker info`, and `docker version` calls did not
  return a usable Linux engine.
- Docker Desktop status remained `starting`.
- Docker Desktop logs identify the runtime failure as:

  ```text
  DockerDesktop/Wsl/CommandTimedOut
  Docker Desktop is unable to communicate with the Windows Subsystem for Linux
  ```

- `wsl --terminate docker-desktop` and Docker Desktop restart were attempted;
  the engine remained unavailable. This is an environment/runtime blocker,
  not evidence that the RTF runner passed or failed inside NeMo.

## Recovery and successful guarded evidence

Docker Desktop/WSL was recovered without deleting images, volumes, or
distributions. The current Dockerfile was built as
`parakeet-rtf-benchmark:local-20260823` from
`nvcr.io/nvidia/nemo-speech:26.07.00`.

Observed evidence:

- Docker build completed and produced image manifest
  `sha256:32937f535479b92b7dd809b9047c47c175c6a90a8e39b3fe77528e4ea01ad25a`.
- The image contains the current `benchmark_runner.transcribe_compat` module.
- Container unit tests passed: 5 tests, 0 failures.
- `docker run --gpus all` reported CUDA available on an NVIDIA GeForce RTX 3060.
- Fixture download passed at immutable revision
  `8d2c866ee315bdbed468b2e92e4587d85b6a5cc8`.
- Pinned model restore and one-sample CUDA content probe passed with
  `content_available=true`.
- The probe emitted
  `RTF_DATALOADER_POLICY={"num_workers":0,"pin_memory":false,"use_lhotse":false}`
  and did not reproduce either prior provider error.
- With the Actions-equivalent canonical override, the receipt retained
  manifest SHA-256 `9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694`.

The locally materialized manifest has a different SHA (`885010f...`) because
its `audio_path` values point to `/workspace/benchmark-audio/...`. This is
expected: the resolver/fixture canonical hash is computed before materializing
local paths, and `RTF_FIXTURE_MANIFEST_SHA256` binds that canonical identity in
the provider receipt.

## External image boundary

The public GHCR latest manifest was also pulled for comparison:

- reference digest:
  `sha256:bb22a03d9530a0ac3aace6290071f3e88932f277e8350988490b616d6193eaa0`
- image label revision: `326ce619ca8b6a0bd96af376cdec1b9d336ecafd`
- image label runner version: `rtf-benchmark-v1`
- `transcribe_compat.py` was present, but did not contain the current
  `DataLoader.__init__` constructor patch.

The local `.env` is only a developer-machine credential boundary. GitHub
Actions must use repository secrets and the existing workflow convention:

- `HF_TOKEN: ${{ secrets.HF_TOKEN }}` is exposed only in the resolve and
  provider-execution step environments;
- `RUNPOD_TOKEN: ${{ secrets.RUNPOD_TOKEN }}` is exposed only to the RunPod
  configuration step;
- GHCR build/publish uses the workflow-scoped `${{ github.token }}` with the
  declared `packages: write` permission, not a PAT copied from `.env`.

`CR_PAT` was verified locally as a package-capable token and a manually tagged
push succeeded, but it is not part of the canonical Actions credential path.
The subsequent GHCR workflow dispatch was intentionally cancelled after the
local gate to avoid unnecessary external work. Consequently, HF Jobs/RunPod
runtime acceptance remains unverified and must be a later, explicitly guarded
provider experiment.

## Acceptance boundary

The local guarded gate is not accepted until all of the following are observed
from a newly built image:

1. Dockerfile build completes from the pinned NeMo base.
2. Image contains the current `transcribe_compat.py` and executable entrypoint.
3. Container Python unit tests pass inside the image.
4. A guarded content probe reaches the model/DataLoader boundary without
   `persistent_workers` mutation or `NeMo transcription DataLoader policy was
   not applied`.
5. Only after 1–4 pass may an external HF/RunPod run be used as provider
   evidence.

## Blocker and recovery

Current blocker: Docker Desktop's WSL2 backend is unresponsive. No destructive
Docker volume, image, or repository cleanup was performed.

Recovery evidence after this entry was created: Docker Desktop was launched
again, but `docker desktop status` remained `starting`; `wsl --shutdown` also
did not return and the Docker/WSL processes remained present. The host GPU is
available, but the container runtime is not currently usable.

Next safe action: recover or reboot the Docker/WSL runtime, confirm
`docker desktop status` is `running`, then rerun the pinned Dockerfile build
and the guarded container checks. Preserve the existing local images until the
new image is verified.

## Rollback

No repository rollback is needed. The existing source branch remains intact;
the stale local image is retained only as historical comparison evidence.
