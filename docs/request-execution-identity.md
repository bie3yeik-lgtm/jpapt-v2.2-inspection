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

This means an older acknowledged execution cannot hide a newer retry, while a caller can still query the older execution explicitly.

## Timeline query semantics

`Candidate Request Timeline` uses the same optional selector.

Without `request_execution_id`, it returns the combined history for the logical `request_id`.

With `request_execution_id`, it returns only observations for that execution. Persistent history is read from the execution-specific Bucket partition and GitHub lifecycle artifacts are filtered by payload identity.

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
```

They cover orchestrator-owned generation, spoof rejection, evidence propagation, ACK binding, legacy v1 compatibility, execution-scoped storage, reducer filtering, and cross-execution materialized-state rejection.
