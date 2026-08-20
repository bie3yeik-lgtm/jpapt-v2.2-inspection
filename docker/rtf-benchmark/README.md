# Common RTF benchmark image

This image is the shared runtime boundary for HF Inference Endpoint and RunPod
Pod measurements. It is based on `nvcr.io/nvidia/nemo-speech:26.07.00` and must
be referenced by a GHCR digest, never by `latest`.

The runner validates a resolved manifest and performs model-side inference via
NeMo `ASRModel.from_pretrained`. Provider adapters must pass the immutable
image digest, materialized fixed manifest, and model/dataset revisions.

The locked Common Voice benchmark materializes deterministic composite samples:
each sample is 30 seconds to 10 minutes, with 20--50 samples and approximately
1.5 hours total audio. Short Common Voice clips are concatenated before timing;
they are not treated as independent benchmark samples.

This profile is labeled `lough inspection`. The separate `precise inspection`
profile is 30 seconds to 30 minutes, 50--150 samples, and 5--10 hours total
audio. The current RTF Phase 1 workflow accepts only `lough inspection`.

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

When `RTF_RESULT_REPO_ID` is set, the entrypoint uploads the completed
`RTF_OUTPUT` to the revision-pinned Hugging Face Dataset repository under
`RTF_RESULT_PATH` and prints a machine-readable `RTF_RESULT_RECEIPT` line.
The current canonical result repository is
`gawohok7/rtf-benchmark-fixtures`; the upload uses the runtime `HF_TOKEN`
secret and never stores it in the image.

Example invocation:

```bash
docker run --rm --gpus all \
  -v "$PWD/benchmark-v1.jsonl:/input/benchmark-v1.jsonl:ro" \
  -v "$PWD/results:/output" \
  ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@sha256:<digest> \
  --manifest /input/benchmark-v1.jsonl --output /output/metrics.json \
  --run-id <run-id> --model-id nvidia/parakeet-tdt_ctc-0.6b-ja \
  --model-revision <model-commit> \
  --dataset-id japanese-asr/ja_asr.common_voice_8_0 \
  --dataset-revision bf8819e8d9a5feb51b0c718686bd20ea67a3c729 \
  --decoder tdt --batch-size 1 --precision float16 \
  --provider cuda --service-id runpod-pod --gpu l4
```

Provider launch forms are also supported. Set the `RTF_*` variables shown in
the explicit invocation above as provider job/pod environment variables. HF
Jobs may invoke the image as:

```bash
hf jobs run --flavor a10g-small \
  ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@sha256:<digest> \
  /opt/rtf-benchmark/entrypoint.sh
```

RunPod may start the same image without a command:

```bash
runpodctl pod create --name parakeet-bench \
  --image ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@sha256:<digest> \
  --gpu-id "NVIDIA RTX A5000"
```

The entrypoint converts both forms to the same `benchmark_runner` invocation.
RunPod automation uses `runpodctl ssh info` and SSH after the Pod becomes
reachable; the deprecated `runpodctl exec` command is not used.
Missing runtime variables fail closed; credentials are not image defaults.

GitHub Actions and local automation should use the lifecycle wrapper:

```bash
./scripts/run-benchmark.sh --provider hf --image "$IMAGE"
./scripts/run-benchmark.sh --provider runpod --image "$IMAGE"
```

The HF branch submits one Job. The RunPod branch creates one Pod with
`sleep infinity`, executes the complete benchmark once, collects the result,
deletes the Pod immediately, and retains an EXIT-trap/orphan-name cleanup
path. RunPod also receives an absolute UTC deadline four hours in the future
through `--terminate-after` as a safety limit so a runner or network failure
cannot leave a benchmark Pod running indefinitely.

`RTF Resolver` writes the uploaded fixture repository and immutable commit SHA
to `rtf-scores/benchmark/benchmark-v1.fixture.json`. `RTF Benchmark Run` reads that
pointer automatically when its fixture inputs are empty.

`evaluation/manifests/rtf-benchmark-v1.json` is the Common Voice dataset
revision lock. The resolved audio manifest and its SHA-256 are runtime inputs
and must be returned with the metrics.
