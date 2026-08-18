# Request execution identity

Candidate protocol has three distinct identities. They are intentionally not interchangeable.

## Identity roles

| identity | meaning | stability |
|---|---|---|
| `request_id` | caller-visible logical correlation ID | may be reused for another execution |
| `request_execution_id` | one orchestrator/evaluator execution instance | unique per Gateway/V2 execution |
| `receipt_sha256` | canonical completion evidence content identity | identical only for identical receipt JSON |

`request_id` is useful for grouping retries. It is not sufficient to distinguish concurrent or later executions of the same logical request.

## Generation ownership

Execution identity is orchestration-owned.

Gateway executions generate:

```text
gw-<github.run_id>-<github.run_attempt>
```

Direct `Candidate Package Evaluate V2` executions generate:

```text
eval-<github.run_id>-<github.run_attempt>
```

A `repository_dispatch` caller cannot choose a trusted Gateway execution identity. Gateway normalization replaces caller-provided `request_execution_id` with its own `gw-*` identity. Gateway then forwards that value to V2.

V2 preserves a forwarded execution identity. When V2 is invoked directly without one, it creates its own `eval-*` identity.

## Protocol propagation

New protocol evidence propagates `request_execution_id` through:

```text
Gateway normalized request
  -> planned lifecycle
  -> V2 workflow dispatch
  -> dispatched lifecycle
  -> running lifecycle
  -> CandidateCompletionReceiptV1
  -> CandidateCompletionAckV1
  -> completed / acknowledged lifecycle
```

Gateway rejection evidence also carries the Gateway execution identity.

The field is optional in schema version 1 for backward compatibility. Historical v1 evidence without `request_execution_id` remains valid. New Gateway/V2 evidence should include it.

ACK binding validates execution identity whenever the receipt contains it. A mismatched ACK is rejected.

## Persistent lifecycle layout

The lifecycle Bucket keeps two views.

Request-level aggregate view:

```text
requests/<request-key>/
├── events/
├── evidence/
└── states/
```

Execution-isolated view for new evidence:

```text
requests/<request-key>/executions/<execution-key>/
├── events/
├── evidence/
└── states/
```

Keys are deterministic:

```text
request-key   = first 24 hex chars of SHA-256(request_id)
execution-key = first 24 hex chars of SHA-256(request_execution_id)
```

The request-level view remains for backward compatibility and for answering "what is the newest observation across all executions?". Its `states/<state>.json` files may therefore move between execution identities according to `updated_at`.

The execution-level view is isolated. `compare-candidate-lifecycle-state.py --require-execution-match` prevents one execution from overwriting another execution's materialized state.

Immutable `events/` remain recovery evidence. `states/` are materialized views, not canonical history.

## Status query semantics

`Candidate Request Status` accepts:

```text
request_id                  required
request_execution_id        optional
```

When only `request_id` is supplied, status considers all available executions and selects the lifecycle observation with the newest `updated_at`. State rank is only a tie-breaker.

When `request_execution_id` is supplied, Status reads the execution-specific Bucket partition and filters GitHub artifact fallback evidence to the same execution. The reducer independently enforces the same execution ID.

GitHub artifact fallback is paginated rather than capped at the first 100 matching artifacts. This matters when the persistent Bucket is temporarily unavailable and an older execution must still be recovered from unexpired Actions evidence.

This means an older acknowledged execution cannot hide a newer retry, while a caller can still query the older execution explicitly.

## Timeline query semantics

`Candidate Request Timeline` uses the same optional selector.

Without `request_execution_id`, it returns the combined history for the logical `request_id`. The generated `CandidateRequestTimelineV1` does not add an execution-scope field in this mode.

With `request_execution_id`, it returns only observations for that execution. Persistent history is read from the execution-specific Bucket partition and GitHub lifecycle artifacts are filtered by payload identity. The generated timeline includes top-level:

```json
{
  "request_execution_id": "gw-123-1"
}
```

and every `events[].snapshot.request_execution_id` must match it. The builder/validator rejects cross-execution contamination.

## Remote lifecycle storage smoke

Repository contract tests validate path construction and filtering without mutating Hugging Face storage. They are not equivalent to proving that the configured account/token can perform a real Bucket write/read.

`.github/workflows/candidate-lifecycle-storage-smoke.yml` provides that operational proof without model compute. It is intentionally **manual-only** and requires:

```text
confirm_write = true
HF_TOKEN      = configured
```

It creates a unique synthetic request/execution identity from the workflow run, writes the lifecycle snapshot through the canonical `persist-candidate-lifecycle.sh`, and reads back all four storage views:

```text
request-level event
request-level running state
execution-level event
execution-level running state
```

Each readback is schema-validated and its canonical observation SHA-256 must equal the source snapshot.

The smoke does not run ONNX Runtime, Docker builds, GPU jobs, model inference, or HF Jobs. It intentionally leaves the uniquely keyed synthetic lifecycle evidence in the private lifecycle Bucket so the remote write/read proof remains auditable rather than becoming an ephemeral test.

This workflow has not proven a particular Bucket until a manual run succeeds. Static/contract CI alone must not be reported as real remote storage verification.

## Compatibility rule

Do not make `request_execution_id` required in schema version 1. Doing so would invalidate historical receipt/ACK/rejection/lifecycle evidence.

If a future protocol requires execution identity unconditionally, introduce a new schema version and an explicit migration/compatibility policy instead of silently tightening v1.

## Contract coverage

The relevant focused suites are:

```text
Candidate Request Execution Contracts
Candidate Lifecycle Execution Storage Contracts
Candidate Lifecycle Persist Contracts
Candidate Request Timeline Contracts
Candidate Protocol Synthetic E2E
```

They cover orchestrator-owned generation, spoof rejection, evidence propagation, ACK binding, legacy v1 compatibility, execution-scoped storage, reducer filtering, scoped timelines, and cross-execution materialized-state rejection. `Candidate Lifecycle Storage Smoke` is the separate manual remote-storage proof.
