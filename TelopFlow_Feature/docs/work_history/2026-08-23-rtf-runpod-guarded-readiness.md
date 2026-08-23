# RTF RunPod guarded readiness result

Date: 2026-08-23

## Attempt

- Run ID: `rtf-runpod-guarded-20260823-b1`
- Provider: RunPod
- GPU: RTX 3090
- Batch size: 1
- Image: digest-pinned RTF benchmark image
- Model/dataset/fixture: immutable revisions from the tracked benchmark
  receipt

The account preflight reported an available balance before this attempt. One
Pod was created successfully, but it remained in
`desiredStatus=RUNNING` / `runtimeStatus=initializing` for approximately ten
minutes. It never reached runtime availability, SSH readiness, content probe,
model loading, or inference.

To prevent additional idle GPU cost, the guarded attempt was stopped before
the configured readiness timeout. The Pod was then explicitly deleted and a
follow-up `pod get` returned `not_found`. No second Pod was created.

## Result

- result receipt: not produced because the local terminal interruption
  occurred during readiness polling
- content probe: not reached
- metrics/result: not produced
- post-cleanup account state: `currentSpendPerHr=0`
- observed balance change: approximately 0.07 account units during the
  short-lived readiness attempt

This is not evidence of a CUDA, NeMo, dataset, or metrics failure. It is a
RunPod lifecycle/image-readiness failure boundary. The next investigation
must determine why the selected image remains `initializing` (image pull,
registry reachability, or provider capacity) before another paid retry.

## Safety evidence

- Only one Pod was created.
- No batch 8/32 or full-matrix execution was attempted.
- Pod deletion was confirmed after interruption.
- The existing RunPod adapter retains bounded create/readiness timeouts and
  deletion traps; this local terminal interruption required explicit follow-up
  deletion because the outer WSL terminal did not deliver the signal through
  to the child process.

## Next safe unit

Perform a no-Pod image reachability/registry-auth investigation and improve
the local process wrapper so an interrupted WSL command cannot orphan a Pod.
Do not retry the benchmark until that boundary is understood.
