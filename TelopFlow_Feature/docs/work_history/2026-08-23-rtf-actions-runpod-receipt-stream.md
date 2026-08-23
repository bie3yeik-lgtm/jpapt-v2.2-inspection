# RTF Benchmark Run 32626919319: RunPod receipt stream recovery

## Observation

The second Actions RunPod smoke used the corrected fixture and image identity:

- image digest: `sha256:3ea1bc51ecbab7d5922cffb209f0e0323b9914ec1dedfb40cd82bace658abfc8`
- fixture revision: `0556991b56c5f6e9753402ab2265232ce2577ae1`
- manifest: `9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694`
- RunPod Pod: `qxsthdn7bceq03`

The provider completed transcription for all 21 fixture samples and emitted
both machine-readable `RTF_CONTENT_PROBE` and completed `RTF_RESULT_RECEIPT`
lines. The receipt contained metrics/result SHA
`4894921f16342546b0b0197273f293e638ff3dd555176553edaaff7fa22b4e38`.

## Failure cause

The RunPod wrapper did not persist the remote SSH stdout. After the benchmark
published its result, the follow-up SSH file-copy operations timed out. The
wrapper therefore lost the already emitted receipt, generated a synthetic
`PROVIDER_EXECUTION_FAILED` receipt, and made the Actions benchmark fail even
though provider execution had completed.

This was a result-collection failure, not a stale fixture, GHCR image, CUDA
illegal-access, or OOM failure.

## Remediation

The RunPod wrapper now:

1. tees the remote entrypoint stdout/stderr into `RTF_RUNPOD_LOG`;
2. recovers `RTF_CONTENT_PROBE` and `RTF_RESULT_RECEIPT` from that log;
3. uses SSH file-copy as a fallback rather than the only receipt source; and
4. accepts a valid completed receipt when the SSH channel closes after result
   publication, while still failing closed when no completed receipt exists.

The contract workflow asserts that this recovery path remains present. The
next safe unit is one guarded Actions RunPod smoke after this change is
merged. A score is not accepted until the collect job validates the recovered
receipt and metrics URI/SHA.

