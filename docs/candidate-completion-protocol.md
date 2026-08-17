# Candidate completion protocol

Candidate evaluation uses a two-message terminal protocol instead of treating a successful `repository_dispatch` HTTP response as proof that the receiver processed the result.

## Event types

Request execution terminates with:

```text
jpapt.candidate-completed
```

After a receiver validates that receipt it returns:

```text
jpapt.candidate-completion-ack
```

The contracts are source-controlled at:

```text
contracts/candidate-completion-receipt.schema.json
contracts/candidate-completion-ack.schema.json
```

## Delivery states

These states are intentionally distinct:

```text
execution terminal
  -> receipt artifact preserved by orchestrator
  -> completion repository_dispatch accepted by GitHub API
  -> receipt receiver workflow validates CandidateCompletionReceiptV1
  -> receiver preserves receipt + acknowledgement artifact
  -> acknowledgement repository_dispatch accepted by GitHub API
  -> orchestrator validates CandidateCompletionAckV1
```

A `204`/successful repository dispatch means only that GitHub accepted the event. It is not equivalent to receiver validation. `jpapt.candidate-completion-ack` is the end-to-end evidence that the reference receiver reached the validation boundary.

## Receipt identity and duplicate delivery

`CandidateCompletionReceiptV1` remains unchanged. Duplicate identity is derived rather than copied into the receipt.

The receiver canonicalizes the complete receipt as JSON using sorted keys and compact separators, then computes:

```text
SHA-256(canonical receipt JSON)
```

The resulting 64-hex value is returned as:

```text
CandidateCompletionAckV1.receipt_sha256
```

This means reserializing the same JSON object with another key order produces the same receipt identity. Retries may create more than one receiver run or acknowledgement, but consumers MUST treat matching `receipt_sha256` values as the same completion evidence.

`request_id` is correlation identity; `receipt_sha256` is content identity. A single request may be retried as a new evaluation run, so consumers should not use `request_id` alone as receipt deduplication identity.

## CandidateCompletionAckV1

Example:

```json
{
  "schema_version": 1,
  "request_id": "caller-job-000123",
  "receipt_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "receipt_repository": "owner/source",
  "orchestrator_repository": "bie3yeik-lgtm/jpapt-v2.2-inspection",
  "evaluation_run_id": 123456789,
  "evaluation_run_attempt": 1,
  "receiver_repository": "owner/source",
  "receiver_run_id": 987654321,
  "receiver_run_attempt": 1,
  "receiver_run_url": "https://github.com/owner/source/actions/runs/987654321",
  "accepted_at": "2026-08-17T00:00:01Z"
}
```

The acknowledgement deliberately does not repeat candidate, image, dataset, result, or conclusion fields. Those belong to the receipt whose canonical hash is acknowledged. This avoids a second derived source of truth.

## Retry policy

The reference receiver dispatches acknowledgement events through:

```text
scripts/ci/repository-dispatch-with-retry.sh
```

The helper performs a bounded three-attempt retry by default for transient GitHub API delivery failures. It never retries indefinitely.

Duplicate event delivery is therefore expected protocol behavior. Consumers MUST be idempotent by `receipt_sha256`.

The completion receipt is preserved before callback delivery, so callback failure does not destroy terminal execution evidence.

## Authentication

The orchestrator sends `jpapt.candidate-completed` using `SOURCE_REPO_TOKEN` for an external receipt repository.

The reference receipt repository sends `jpapt.candidate-completion-ack` using:

```text
JPAPT_ACK_TOKEN
```

The token must be able to create repository dispatch events in the orchestrator repository. When receiver and orchestrator are the same repository, the reference workflow can use its local `GITHUB_TOKEN` fallback.

No model or evaluation secrets are embedded in either protocol payload.

## Reference workflows

Emitter:

```text
.github/workflows/candidate-package-evaluate-v2.yml
```

Receipt receiver / ACK emitter:

```text
.github/workflows/candidate-completion-receipt.yml
```

ACK receiver:

```text
.github/workflows/candidate-completion-ack.yml
```

The ACK receiver serializes identical `receipt_sha256` groups with GitHub Actions concurrency and preserves the acknowledgement as an artifact named by the receipt hash when the event supplies it.

## Failure interpretation

There are four materially different failures:

1. evaluation failure: represented by `CandidateCompletionReceiptV1.conclusion=failure`;
2. completion dispatch failure: orchestrator has its receipt artifact, but no receiver evidence;
3. receipt validation failure: receiver workflow fails and MUST NOT emit an ACK;
4. ACK dispatch/validation failure: receiver accepted the receipt but orchestrator lacks validated acknowledgement evidence.

These conditions should not be collapsed into one boolean because they have different recovery actions.

## Contract CI

`External Candidate Workflow Contracts` verifies:

- receipt and ACK schemas are parseable JSON;
- receipt and ACK builders compile;
- receipt generation and validation;
- completion dispatch envelope event type;
- ACK generation and validation;
- ACK dispatch envelope event type;
- request ID preservation;
- canonical receipt SHA stability across JSON key reordering;
- workflow actionlint;
- bounded-dispatch helper Bash syntax;
- Rust request contract tests;
- candidate Dockerfile parsing.
