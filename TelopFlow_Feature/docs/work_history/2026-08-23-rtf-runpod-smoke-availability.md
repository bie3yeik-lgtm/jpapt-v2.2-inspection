# Work history: RunPod smoke availability boundary

## Objective

Confirm why the RunPod smoke benchmark has no `metrics` artifact, using one
guarded batch only and the same immutable inputs that produced the HF smoke
result.

## Inputs

- provider: `runpod`
- GPU request: `a5000`
- batch size: `1`
- profile: `smoke`
- image: the digest recorded by the completed HF smoke result
- model, dataset, fixture revisions, and manifest SHA: the existing Resolver
  and HF smoke identities

No credentials are recorded here.

## Evidence

Local static/mock checks and no-provider preflight passed before the attempt.
The guarded RunPod invocation used run ID
`rtf-runpod-local-20260823-b1`.

The provider returned immediately during Pod creation:

```text
RUNPOD_NO_INSTANCE_AVAILABLE
failed to create pod: graphql error: There are no longer any instances available with the requested specifications
```

The normalized receipt has `status=blocked`, `job_id=null`, and null
`metrics_uri`, `metrics_sha256`, `result_uri`, and `result_sha256`. A follow-up
exact-name Pod query returned zero Pods. Therefore this attempt did not reach
image pull, runtime readiness, SSH endpoint publication, content probe, model
restore, or inference.

## Conclusion

The current RunPod smoke gap is an infrastructure availability boundary for
the requested A5000, not evidence of a benchmark or result-collection failure.
Retrying repeatedly would only increase control-plane traffic and can create
cost if availability changes mid-retry. Do not start batch 8 or 32 until one
guarded batch 1 reaches `content_available=true` and produces completed
metrics/result receipts.

The local live adapter test now rejects a non-completed receipt and rejects a
completed receipt that lacks both metrics/result URI and SHA-256 identities.
This prevents a provider block from being reported as a successful live test.

## Acceptance boundary for the next retry

Accept RunPod smoke only when all of the following are present:

- Pod creation returns a Pod ID;
- runtime and SSH probe succeed;
- content probe reports `content_available=true`;
- receipt status is `completed`;
- metrics and result URI/SHA-256 are present and identity-matched;
- exact-name cleanup leaves no Pod.

## Verification

- `rtf-local-preflight.sh --provider all`: PASS without provider creation
- `test-rtf-provider-adapters.sh --mode static`: PASS
- `test-rtf-provider-adapters.sh --mode mock`: PASS
- one guarded RunPod A5000 attempt: blocked before Pod creation
- post-attempt exact-name Pod query: zero Pods
