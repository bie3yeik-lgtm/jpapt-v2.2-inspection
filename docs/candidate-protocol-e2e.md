# Candidate protocol cross-repository E2E

`Candidate Protocol E2E` verifies the completion protocol against a real second GitHub repository without launching model evaluation or Hugging Face Jobs. It dispatches `Candidate Package Evaluate V2` with `dry_run=true`, waits for the request lifecycle to reach `acknowledged`, then validates the preserved completion receipt and acknowledgement against the same request.

## What the test proves

A successful run establishes the following chain across two repositories:

```text
orchestrator V2 dry-run
  -> CandidateCompletionReceiptV1 preserved
  -> jpapt.candidate-completed delivered to external receiver
  -> external receiver validates schema and repository binding
  -> CandidateCompletionAckV1 returned to orchestrator
  -> orchestrator recovers the original receipt
  -> canonical receipt SHA-256 matches
  -> ACK binding validation succeeds
  -> lifecycle reaches acknowledged
```

The test does **not** build a candidate package, run ONNX Runtime, launch a GPU, or launch Hugging Face Jobs. `dry_run=true` is asserted again from the final completion receipt before the E2E run can succeed.

## Receiver repository contract

The external receiver must be a repository different from the orchestrator and must contain these files on its default branch:

```text
.github/workflows/candidate-completion-receipt.yml
scripts/ci/build-candidate-completion-receipt.py
scripts/ci/build-candidate-completion-ack.py
scripts/ci/validate-candidate-protocol-binding.py
scripts/ci/repository-dispatch-with-retry.sh
```

The receiver workflow should use the reference implementation from this repository unless it intentionally implements the same protocol independently.

The receiver repository variable must allow this orchestrator:

```text
JPAPT_ORCHESTRATOR_REPOSITORIES=bie3yeik-lgtm/jpapt-v2.2-inspection
```

For acknowledgement back to the orchestrator, the receiver must provide a secret named:

```text
JPAPT_ACK_TOKEN
```

The token must be capable of creating `repository_dispatch` events in the orchestrator repository.

The orchestrator must provide:

```text
SOURCE_REPO_TOKEN
```

The token is used both by the synthetic E2E preflight and by `Candidate Package Evaluate V2` when it delivers the completion event to the external receiver.

Secrets are capabilities; `JPAPT_ORCHESTRATOR_REPOSITORIES` is the receiver-side trust policy. Both must be configured.

## Running the E2E workflow

Run:

```text
Actions -> Candidate Protocol E2E -> Run workflow
```

Required inputs:

- `receipt_repository`: external receiver repository, `owner/name`.
- `hf_bucket`: an existing `namespace/name` Bucket accepted by the normal request resolver. The E2E run does not download a candidate from it because evaluation is a dry-run.

Optional inputs:

- `source_repository`: defaults to the orchestrator repository.
- `timeout_seconds`: defaults to 600 and is bounded to 60..1200.

The request ID is generated deterministically from the E2E workflow run:

```text
e2e-<github.run_id>-<github.run_attempt>
```

The workflow derives the 24-character request artifact key using the same SHA-256 rule as normal lifecycle handling, then observes these artifacts:

```text
candidate-lifecycle-<request-key>-running
candidate-lifecycle-<request-key>-completed
candidate-lifecycle-<request-key>-acknowledged
```

The workflow does not need to guess the evaluation run ID. Once `acknowledged` appears, the lifecycle snapshot supplies the exact evaluation run ID, run attempt, receipt SHA-256, and receiver identity used to recover and revalidate canonical evidence.

## Failure interpretation

A failure before dispatch normally indicates configuration or receiver installation problems. A timeout after dispatch means the synthetic request did not reach end-to-end acknowledgement. Inspect the most advanced lifecycle artifact for the request:

```text
running
completed
acknowledged
```

- only `running`: V2 started but no valid completion receipt was observed;
- `completed` without `acknowledged`: the orchestrator has canonical completion evidence but the receiver/ACK path did not complete;
- no `running`: V2 request normalization/resolution failed before the running lifecycle boundary.

Normal completion reconciliation remains active, so temporary completion dispatch loss may recover during the same E2E window.

## Safety and cost

`Candidate Protocol E2E` is manual-only. It refuses a receiver equal to the orchestrator repository, so success necessarily exercises cross-repository delivery. The dispatch body hard-codes:

```json
{
  "suite": "probe",
  "executor": "github",
  "environment": "linux-cpu",
  "dry_run": true
}
```

The final receipt is also required to contain `dry_run=true` and `conclusion=success`; otherwise the E2E workflow fails.
