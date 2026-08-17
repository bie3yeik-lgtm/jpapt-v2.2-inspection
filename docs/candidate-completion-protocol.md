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

The ACK receiver recovers the original completion receipt from the evaluation run and validates both canonical receipt SHA-256 and protocol bindings. It requires the ACK orchestrator to be the current repository and requires request, receipt repository, evaluation run ID/attempt, and receiver repository to match the preserved receipt.

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

`request_id` is correlation identity; `receipt_sha256` is content identity. A request may be retried as a new evaluation run, so `request_id` alone is not a receipt deduplication identity.

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
running
rejected
completed
acknowledged
```

Semantics:

- `planned`: Gateway Rust normalization/resolution produced a valid plan.
- `running`: Gateway successfully submitted `candidate-package-evaluate-v2.yml`; GitHub may not yet expose the evaluation run ID.
- `rejected`: Gateway failed before accepted execution and produced a validated `CandidateRequestRejectionV1`.
- `completed`: a validated completion receipt exists; evaluation run identity and canonical receipt hash are mandatory.
- `acknowledged`: a validated ACK exists and matches the preserved completion receipt.

Artifact lookup uses the first 24 hex characters of `SHA-256(request_id)` as `<request-key>`:

```text
candidate-lifecycle-<request-key>-planned
candidate-lifecycle-<request-key>-running
candidate-lifecycle-<request-key>-rejected
candidate-lifecycle-<request-key>-completed
candidate-lifecycle-<request-key>-acknowledged
```

Lifecycle snapshots MUST NOT replace evaluation result, promotion, receipt, rejection, or ACK contracts. They are only a query/index layer over canonical evidence.

## Persistent lifecycle storage

GitHub Actions artifacts are short-lived operational evidence. `Candidate Lifecycle Persist` copies lifecycle evidence to a dedicated private Hugging Face Bucket after the Gateway, lifecycle observer, or ACK receiver completes.

The Bucket defaults to:

```text
<HF_DEFAULT_NAMESPACE>/<orchestrator-repository-name>-lifecycle
```

and can be overridden with the repository variable:

```text
HF_LIFECYCLE_BUCKET
```

Persistent layout is keyed by the same `<request-key>` used for GitHub artifacts:

```text
requests/<request-key>/
├── events/
│   └── <evidence-key>.lifecycle.json
├── evidence/
│   └── <sha256>-<canonical-filename>.json
└── states/
    ├── planned.json
    ├── running.json
    ├── rejected.json
    ├── completed.json
    └── acknowledged.json
```

Roles are intentionally different:

- `events/` is append-only lifecycle evidence. Event names are derived from Gateway, evaluation, and receiver run identities.
- `evidence/` stores canonical rejection, completion receipt, and acknowledgement objects when they are available.
- `states/` is a materialized lookup view. It may be overwritten by another observation of the same state and MUST NOT be treated as canonical history.
- GitHub lifecycle artifacts remain the short-term fallback and make persistence failures independent of the evaluation protocol itself.

Persistence runs through `.github/workflows/candidate-lifecycle-persist.yml`, which is triggered by `workflow_run` rather than being embedded in evaluation/ACK jobs. Therefore a Bucket outage cannot change an already-established evaluation or acknowledgement result. The workflow also supports manual `source_run_id` input for backfill.

`Candidate Request Status` resolves the most advanced available state in this order:

```text
acknowledged -> completed -> rejected -> running -> planned
```

It first checks `states/` in the persistent lifecycle Bucket and falls back to GitHub Actions artifacts when persistent evidence is unavailable. The downloaded snapshot is revalidated and its original `request_id` must match the requested correlation ID.

## Retry policy

Repository dispatch delivery uses `scripts/ci/repository-dispatch-with-retry.sh` with a bounded three-attempt retry by default. It never retries indefinitely. Duplicate event delivery is expected protocol behavior; completion consumers are idempotent by `receipt_sha256`.

`candidate-completion-reconcile.yml` recovers a preserved receipt after the evaluation workflow terminates. If a matching ACK artifact is absent, it rebuilds the completion envelope and performs bounded redispatch.

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
.github/workflows/candidate-package-evaluate-v2.yml
.github/workflows/candidate-completion-receipt.yml
.github/workflows/candidate-completion-ack.yml
.github/workflows/candidate-completion-reconcile.yml
.github/workflows/candidate-request-lifecycle-observer.yml
.github/workflows/candidate-lifecycle-persist.yml
.github/workflows/candidate-request-status.yml
```

## Failure interpretation

Do not collapse these conditions into one boolean:

1. request rejection: normalization/resolution did not reach accepted execution;
2. evaluation failure: represented by `CandidateCompletionReceiptV1.conclusion=failure`;
3. completion dispatch failure: orchestrator has its receipt artifact but no receiver evidence;
4. receipt schema/binding failure: receiver MUST NOT emit an ACK;
5. ACK dispatch/validation failure: receiver accepted the receipt but orchestrator lacks validated acknowledgement evidence;
6. lifecycle persistence failure: canonical GitHub evidence may still exist, but the long-lived Bucket copy is incomplete.

Each condition has a different recovery action. Lifecycle persistence can be backfilled from a source workflow run while its GitHub artifacts still exist.

## Contract CI

`External Candidate Workflow Contracts` verifies:

- receipt, ACK, rejection, and lifecycle schemas are parseable JSON;
- all protocol builders/validators compile;
- positive and negative receiver-binding behavior;
- receipt generation and validation;
- completion and ACK envelope event types;
- rejection generation, validation, and event type;
- request ID preservation;
- canonical receipt SHA stability across JSON key reordering;
- planned, running, rejected, completed, and acknowledged lifecycle generation/validation;
- stable request artifact-key derivation;
- workflow actionlint;
- bounded-dispatch helper syntax;
- Rust request contract tests;
- candidate Dockerfile parsing.

`Candidate Lifecycle Persist Contracts` separately verifies:

- persistence/status workflow actionlint;
- persistence helper Bash syntax;
- Bucket-disabled local no-op behavior;
- immutable event, canonical evidence, and materialized-state path conventions.
