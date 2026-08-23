# Work history: RTF RunPod environment transfer boundary

## Objective

Ensure that the RunPod benchmark receives its complete runtime contract without
placing `HF_TOKEN` or benchmark values in Pod metadata. The change is limited
to the provider adapter boundary and does not claim external provider success.

## Finding

The previous guarded RunPod attempt reached `running` and passed the SSH
readiness probe, but the remote benchmark exited with `RTF_DATASET_ID is
required`. The image entrypoint therefore did not receive the Pod-create
`--env` payload in the live path, even though the local command construction
was valid. The failed Pod was deleted and no result was accepted.

## Remediation

- Remove `--env` from `runpodctl pod create`.
- Transfer an allowlisted environment file over the authenticated SSH channel
  after readiness has been established.
- Write the file as `/run/rtf-benchmark.env` with mode `0600`.
- Source the file only for the explicit benchmark entrypoint invocation.
- Keep `HF_TOKEN` out of RunPod control-plane metadata.
- Add static assertions that the old `--env "$env_json"` path is absent and
  that the SSH transfer function remains present.

## Local evidence

- `test-rtf-provider-adapters.sh --mode static`: PASS.
- `test-rtf-provider-adapters.sh --mode mock`: PASS for HF and RunPod,
  including no-instance, timeout, and CUDA-failure receipt cases.
- No HF Job, RunPod Pod, GHCR push, or paid external action was performed for
  this change.

## Inputs still required for a guarded external retry

The retry must use a newly published digest and fixed model, dataset, fixture,
and manifest identities. The local `.env` currently contains only credential
keys; it does not contain the required launch identities. `RUNPOD_API` remains
a local alias, while `RUNPOD_TOKEN` is the canonical name used by Actions.

## Unverified items and rollback

- The SSH-delivered environment has not yet been verified on a newly published
  image in RunPod.
- Existing accepted artifacts and fixture pointers are unchanged.
- Rollback is the previous adapter commit; do not reuse its image digest as
  acceptance evidence.

## Next safe unit

Run the repository GHCR build and Resolver workflow, capture the new immutable
image digest, then perform exactly one guarded RunPod batch-1 retry. Accept the
provider only if content probe, metrics, result receipt, and identity bindings
are all complete.
