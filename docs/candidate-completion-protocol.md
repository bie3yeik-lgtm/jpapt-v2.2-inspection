# Candidate completion protocol

Candidate evaluation uses explicit request, rejection, completion, acknowledgement, and derived lifecycle contracts. A successful `repository_dispatch` HTTP response proves only that GitHub accepted the event; it does not prove that the receiver validated it.

## Event types

Accepted execution terminates with:

```text
jpapt.candidate-completed
```

A request that fails normalization/resolution before accepted execution emits:

```text
jpapt.candidate-rejected
```

After a receiver validates a completion receipt it returns:

```text
jpapt.candidate-completion-ack
```

The source-controlled contracts are:

```text
contracts/candidate-completion-receipt.schema.json
contracts/candidate-completion-ack.schema.json
contracts/candidate-request-rejection.schema.json
contracts/candidate-request-lifecycle.schema.json
contracts/candidate-request-timeline.schema.json
```

## Trust boundary

Schema validity is not sufficient for cross-repository delivery.

The completion receiver requires:

```text
receipt.receipt_repository == github.repository
```

For an external orchestrator, the receiver also requires the orchestrator repository to be listed in the repository variable:

```text
JPAPT_ORCHESTRATOR_REPOSITORIES
```

The variable is a comma-separated owner/name allowlist. Self-orchestration (`orchestrator_repository == github.repository`) is allowed without the variable. An external orchestrator is rejected when the allowlist is empty or does not contain it.

The ACK receiver recovers the original completion receipt from the evaluation run and validates both canonical receipt SHA-256 and protocol bindings. It requires the ACK orchestrator to be the current repository and requires request, request execution identity when present, receipt repository, evaluation run ID/attempt, and receiver repository to match the preserved receipt.

The rejection reference receiver applies the same destination/orchestrator trust model: the rejection must name the current repository as `receipt_repository`, and an external orchestrator must be allowlisted.

## Delivery states

Completion delivery distinguishes these boundaries:

```text
execution terminal
  -> receipt artifact preserved by orchestrator
  -> completion repository_dispatch accepted by GitHub API
  -> receiver validates schema + repository binding
  -> receiver preserves receipt + acknowledgement artifact
  -> acknowledgement repository_dispatch accepted by GitHub API
  -> orchestrator validates ACK + preserved receipt binding
```

`jpapt.candidate-completion-ack` is therefore the end-to-end evidence that the reference receiver reached the validation boundary.

## Receipt identity and duplicate delivery

`CandidateCompletionReceiptV1` is canonical completion evidence. Duplicate identity is derived from the complete receipt using sorted-key compact JSON and SHA-256:

```text
SHA-256(canonical receipt JSON)
```

The resulting 64-hex value is returned as `CandidateCompletionAckV1.receipt_sha256`. Re-serializing the same JSON object with another key order produces the same identity. Consumers MUST treat matching `receipt_sha256` values as the same completion evidence.

The protocol deliberately separates three identities:

```text
request_id            logical caller correlation identity
request_execution_id  one Gateway/V2 execution identity
receipt_sha256         canonical completion content identity
```

A caller may reuse `request_id` for another execution. Gateway owns `gw-<run_id>-<attempt>` execution IDs and direct V2 invocation owns `eval-<run_id>-<attempt>` IDs. A repository-dispatch caller cannot select a trusted Gateway execution identity: normalization replaces it with the current Gateway execution identity.

`request_execution_id` remains optional in schema version 1 so historical evidence is valid. New Gateway/V2 evidence propagates it through rejection, receipt, ACK, and lifecycle snapshots. A future mandatory execution identity requires a new schema version instead of silently tightening v1.

See `docs/request-execution-identity.md` for the full compatibility and query contract.

## Request rejection

`CandidateRequestRejectionV1` is intentionally separate from completion receipts. It is used when the Gateway cannot reach the accepted execution boundary.

The current stable reason code is:

```text
REQUEST_NORMALIZATION_OR_RESOLUTION_FAILED
```

Detailed failure information remains in `gateway_run_url` rather than being copied into the callback payload. This prevents logs, secrets, or unstable exception text from becoming protocol data.

Rejection evidence is persisted by the orchestrator before callback delivery. If external callback authentication fails, the rejected lifecycle artifact still remains available in the orchestrator repository.

A malformed request whose source/receipt routing itself is not a valid `owner/name` cannot receive a callback because no trustworthy destination exists; the failed Gateway run remains the evidence for that case.

## Request lifecycle snapshots

The lifecycle is generated evidence, not a new runtime authority. Canonical evidence remains the resolved request, rejection, completion receipt, and acknowledgement.

Supported states are:

```text
planned
dispatched
running
rejected
completed
acknowledged
```

Semantics:

- `planned`: Gateway Rust normalization/resolution produced a valid plan.
- `dispatched`: Gateway successfully submitted `candidate-package-evaluate-v2.yml`. The evaluation workflow may still be queued and evaluation run identity is not required.
- `running`: the V2 evaluation workflow itself completed Rust request resolution and emitted a snapshot containing its actual `github.run_id` and `github.run_attempt`.
- `rejected`: Gateway failed before accepted execution and produced a validated `CandidateRequestRejectionV1`.
- `completed`: a validated completion receipt exists; evaluation run identity and canonical receipt hash are mandatory.
- `acknowledged`: a validated ACK exists and matches the preserved completion receipt.

The distinction is intentional: GitHub accepting a workflow dispatch is not proof that the dispatched evaluation run reached its own request-resolution boundary.

`updated_at` is an offset-aware RFC3339 timestamp. Lifecycle builders, ordering helpers, and JSON Schema reject naive timestamps without `Z` or an explicit `+/-HH:MM` offset.

Artifact lookup uses the first 24 hex characters of `SHA-256(request_id)` as `<request-key>`:

```text
candidate-lifecycle-<request-key>-planned
candidate-lifecycle-<request-key>-dispatched
candidate-lifecycle-<request-key>-running
candidate-lifecycle-<request-key>-rejected
candidate-lifecycle-<request-key>-completed
candidate-lifecycle-<request-key>-acknowledged
```

Lifecycle snapshots MUST NOT replace evaluation result, promotion, receipt, rejection, or ACK contracts. They are only a query/index layer over canonical evidence.

## Retry-aware current status

A caller may intentionally reuse a `request_id` for another execution attempt. Therefore current status MUST NOT be selected by a fixed state-precedence order. An old `acknowledged` observation is not necessarily current if a newer retry is `running`.

`Candidate Request Status` accepts required `request_id` and optional `request_execution_id`.

Without an execution selector it collects observations across all executions from three independent evidence paths:

1. persistent request-level `states/<state>.json` materialized views;
2. persistent request-level immutable `events/*.lifecycle.json` history;
3. GitHub lifecycle artifacts.

`scripts/ci/reduce-candidate-lifecycle.py` selects the observation with the newest lifecycle `updated_at`. State rank is used only as a deterministic tie-breaker when timestamps are equal.

When `request_execution_id` is supplied, Status instead reads `executions/<execution-key>/states/` and `executions/<execution-key>/events/`, and inspects GitHub artifact payloads until it finds evidence carrying the same execution identity. The reducer independently validates the requested execution ID before selecting a state.

This provides both retry-aware latest status and deterministic historical execution status. It also provides recovery when persistence appends an immutable event but fails before updating the materialized state view: the event itself remains eligible for reduction.

## Request timeline

`CandidateRequestTimelineV1` is the machine-readable history view for one `request_id`. It is generated by `scripts/ci/build-candidate-request-timeline.py` and exposed through `.github/workflows/candidate-request-timeline.yml`.

A timeline contains:

```text
schema_version
request_id
request_key
current_state
event_count
events[]
  observation_sha256
  sources[]
  snapshot
```

Observations are deduplicated by SHA-256 of canonical sorted-key compact lifecycle JSON. If the same snapshot exists in GitHub artifacts and the lifecycle Bucket, the timeline contains one event with both source labels.

Timeline events are ordered by:

1. `snapshot.updated_at`;
2. lifecycle state rank only for equal timestamps;
3. canonical observation hash as a deterministic final tie-breaker.

`current_state` is the state of the final event, so the timeline and current-status reducer use the same retry-aware time ordering.

`Candidate Request Timeline` accepts the same optional `request_execution_id` selector as Status. Without it, the workflow combines all executions for the logical request. With it, GitHub artifact payloads are filtered by execution identity and persistent history is read from the execution-specific Bucket partition.

Both Status and Timeline use `scripts/ci/collect-candidate-lifecycle-bucket-events.py` for persistent event enumeration and download. This keeps Hugging Face Storage Buckets filtering, deterministic ordering, execution-prefix selection, and manifest generation in one implementation.

## Persistent lifecycle storage

GitHub Actions artifacts are short-lived operational evidence. `Candidate Lifecycle Persist` copies lifecycle evidence to a dedicated private Hugging Face Bucket after the Gateway, V2 evaluation workflow, lifecycle observer, or ACK receiver completes.

The Bucket defaults to:

```text
<HF_DEFAULT_NAMESPACE>/<orchestrator-repository-name>-lifecycle
```

and can be overridden with the repository variable:

```text
HF_LIFECYCLE_BUCKET
```

Persistent layout retains a backward-compatible request aggregate and adds execution-isolated partitions for new evidence:

```text
requests/<request-key>/
├── events/
│   └── <evidence-key>.lifecycle.json
├── evidence/
│   └── <sha256>-<canonical-filename>.json
├── states/
│   ├── planned.json
│   ├── dispatched.json
│   ├── running.json
│   ├── rejected.json
│   ├── completed.json
│   └── acknowledged.json
└── executions/
    └── <execution-key>/
        ├── events/
        │   └── <evidence-key>.lifecycle.json
        ├── evidence/
        │   └── <sha256>-<canonical-filename>.json
        └── states/
            ├── planned.json
            ├── dispatched.json
            ├── running.json
            ├── rejected.json
            ├── completed.json
            └── acknowledged.json
```

Keys are:

```text
<request-key>   = first 24 hex chars of SHA-256(request_id)
<execution-key> = first 24 hex chars of SHA-256(request_execution_id)
```

Historical lifecycle snapshots without `request_execution_id` remain request-level only. New evidence with execution identity is written to both the request aggregate and its execution partition.

Roles are intentionally different:

- request-level `events/` is append-only history across all executions for the logical request;
- execution-level `events/` is append-only history for exactly one execution;
- `evidence/` stores canonical rejection, completion receipt, and acknowledgement objects when available, mirrored into the execution partition when execution identity exists;
- request-level `states/` is a newest-observation materialized view across executions, so a newer retry may replace the state view previously associated with another execution;
- execution-level `states/` is isolated and `compare-candidate-lifecycle-state.py --require-execution-match` rejects cross-execution replacement;
- GitHub lifecycle artifacts remain the short-term fallback and make persistence failures independent of the evaluation protocol itself.

Persistence runs through `.github/workflows/candidate-lifecycle-persist.yml`, which is triggered by `workflow_run` rather than being embedded in completion/ACK delivery jobs. Therefore a Bucket outage cannot change an already-established evaluation or acknowledgement result. The workflow also supports manual `source_run_id` input for backfill.

Persistence workflow runs are serialized at repository scope. In addition, `compare-candidate-lifecycle-state.py` enforces monotonic per-state materialized updates, so delayed backfills cannot overwrite a newer state observation with an older one. Execution-scoped views additionally require matching execution identity.

## Retry policy

Both protocol ingress and protocol egress use bounded retries and fail-fast structural validation.

Workflow dispatch delivery uses `scripts/ci/workflow-dispatch-with-retry.sh`. Before any GitHub API call, it requires a valid JSON object with a non-empty string `ref` and, when present, an object-valued `inputs`. The Candidate Request Gateway and legacy compatibility wrapper both use this helper to submit the canonical V2 evaluator. Structurally invalid dispatch bodies are rejected immediately and are never retried.

Repository dispatch delivery uses `scripts/ci/repository-dispatch-with-retry.sh`. Before any GitHub API call, it requires a valid JSON object with a 1..100 character `event_type` and an object-valued `client_payload`. The direct V2 completion callback, request rejection callback, completion ACK callback, and reconciliation redispatch all use this helper.

Both helpers use a bounded three-attempt retry by default and never retry indefinitely. Retries are reserved for transport/API failure after local validation succeeds. Duplicate repository event delivery is expected protocol behavior; completion consumers are idempotent by `receipt_sha256`.

`candidate-completion-reconcile.yml` recovers a preserved receipt after the evaluation workflow terminates. If a matching ACK artifact is absent, it rebuilds the completion envelope and performs bounded redispatch.

## Legacy compatibility entrypoint

`.github/workflows/candidate-package-evaluate.yml` is compatibility-only. It preserves the legacy `jpapt.candidate-evaluate` repository dispatch and manual workflow input surface, but it contains no candidate package build, provider evaluation, HF Jobs execution, or completion implementation.

The wrapper supplies a correlation ID when the legacy caller omitted one, defaults `receipt_repository` to `source_repository`, and forwards the request to `.github/workflows/candidate-package-evaluate-v2.yml` through GitHub workflow dispatch. New integrations should use `Candidate Request Gateway` or V2 directly.

This is deliberate: there is exactly one evaluator implementation and therefore one completion/lifecycle path.

## Dry-run semantics

Gateway API and manual `workflow_dispatch` inputs both preserve `dry_run` through normalization, Rust resolution, and V2 dispatch.

For `dry_run=true`:

- package build and evaluation compute are skipped;
- completion protocol still runs after successful request resolution;
- a successful dry-run receipt may have null resolved candidate, image reference/digest, result artifact, and result URI;
- real orchestration failures still produce a failure conclusion.

For a non-dry request, a terminal execution with no executed evaluation job is not treated as success; the receipt records `evaluation:missing-terminal-result`.

## Authentication

The orchestrator uses `SOURCE_REPO_TOKEN` when completion or rejection must be delivered to an external receipt repository. Same-repository delivery can fall back to its `GITHUB_TOKEN`.

The receipt repository uses `JPAPT_ACK_TOKEN` to send `jpapt.candidate-completion-ack` to an external orchestrator. Same-repository acknowledgement can fall back to its local `GITHUB_TOKEN`.

`JPAPT_ORCHESTRATOR_REPOSITORIES` controls trust; tokens control capability. A repository must pass both checks before an external acknowledgement is emitted.

Persistent lifecycle storage uses `HF_TOKEN`. The lifecycle Bucket is private by default and contains protocol evidence, not model credentials or GitHub tokens.

No model or evaluation secrets are embedded in protocol payloads.

## Reference workflows

```text
.github/workflows/candidate-request-gateway.yml
.github/workflows/candidate-request-rejection.yml
.github/workflows/candidate-package-evaluate.yml              # legacy forwarding shim
.github/workflows/candidate-package-evaluate-v2.yml           # canonical evaluator
.github/workflows/candidate-completion-receipt.yml
.github/workflows/candidate-completion-ack.yml
.github/workflows/candidate-completion-reconcile.yml
.github/workflows/candidate-request-lifecycle-observer.yml
.github/workflows/candidate-lifecycle-persist.yml
.github/workflows/candidate-request-status.yml
.github/workflows/candidate-request-timeline.yml
```

## Failure interpretation

Do not collapse these conditions into one boolean:

1. request rejection: normalization/resolution did not reach accepted execution;
2. dispatch accepted but evaluation not running: `dispatched` exists but no evaluation-owned `running` snapshot exists yet;
3. evaluation failure: represented by `CandidateCompletionReceiptV1.conclusion=failure`;
4. completion dispatch failure: orchestrator has its receipt artifact but no receiver evidence;
5. receipt schema/binding failure: receiver MUST NOT emit an ACK;
6. ACK dispatch/validation failure: receiver accepted the receipt but orchestrator lacks validated acknowledgement evidence;
7. lifecycle persistence failure: canonical GitHub evidence may still exist, but the long-lived Bucket copy is incomplete;
8. materialized-state lag: immutable Bucket event or GitHub artifact may be newer than `states/<state>.json`, so status reduction considers all available evidence rather than trusting only the view;
9. execution selection mismatch: a requested `request_execution_id` has no matching persistent/artifact evidence, which is distinct from having no history for the logical `request_id`.

Each condition has a different recovery action. Lifecycle persistence can be backfilled from a source workflow run while its GitHub artifacts still exist.

## Contract CI

`External Candidate Workflow Contracts` verifies the core completion/rejection/ACK/lifecycle protocol, Rust request contract, workflow lint, dispatch helper syntax, and candidate Dockerfile parsing.

Additional focused contract suites verify behavior that should not be hidden inside the broad protocol suite:

- `Candidate Request Execution Contracts`: orchestrator-owned execution identity, spoof resistance, receipt/ACK/rejection/lifecycle propagation, ACK binding, and legacy v1 compatibility.
- `Candidate Lifecycle Execution Storage Contracts`: execution-scoped persistence path semantics, execution-aware status reducer, and cross-execution materialized-state rejection.
- `Candidate Dispatch Retry Contracts`: repository-dispatch bounded retry success/exhaustion plus fail-fast rejection of malformed repository, JSON, event type, and payload bodies.
- `Candidate Workflow Dispatch Retry Contracts`: workflow-dispatch bounded retry success/exhaustion, Gateway/legacy helper integration, and fail-fast rejection of malformed JSON/ref/input bodies.
- `Candidate Dispatch Body Contracts`: Gateway `dry_run` normalization and downstream propagation.
- `Candidate Dry Run Contracts`: no-compute completion semantics and missing-terminal-result behavior.
- `Candidate Lifecycle Persist Contracts`: actionlint, shared state ordering, canonical immutable event identity, monotonic materialized-state writes, retry-aware current-state reduction, and persistence path conventions.
- `Candidate Lifecycle Collector Contracts`: shared HF Bucket event filtering/download manifest behavior, workflow reuse, malformed identity rejection, and timezone-aware lifecycle validation.
- `Candidate Request Timeline Contracts`: actionlint, shared state ordering, retry-aware timeline reduction, duplicate observation merging, cross-request isolation, timezone-aware nested lifecycle validation, and Draft 2020-12 schema validation.
- `Candidate Package Evaluate Legacy Contracts`: guarantees the legacy entrypoint only forwards to V2 and rejects reintroduction of duplicated evaluator implementation.
