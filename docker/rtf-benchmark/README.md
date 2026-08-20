# Common RTF benchmark image

This image is the shared runtime boundary for HF Inference Endpoint and RunPod
Pod measurements. It is based on `nvcr.io/nvidia/nemo-speech:26.07.00` and must
be referenced by a GHCR digest, never by `latest`.

The current runner validates a resolved manifest and emits an explicit
`BLOCKED` result until model-specific inference is connected. Contract
validation must not be reported as a successful benchmark.

```bash
docker build \
  --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" \
  --build-arg RUNNER_VERSION=rtf-benchmark-v1 \
  -f docker/rtf-benchmark/Dockerfile \
  -t parakeet-rtf-benchmark:local \
  .
```

`HF_TOKEN` and `RUNPOD_TOKEN` are supplied only by provider Workflow
environments. They must never be copied into this image or its output.
