# Candidate protocol cross-repository E2E

`Candidate Protocol E2E` verifies the completion protocol against a real second GitHub repository without launching model evaluation or Hugging Face Jobs. It dispatches `Candidate Package Evaluate V2` with `dry_run=true`, waits for the request lifecycle to reach `acknowledged`, then validates the preserved completion receipt and acknowledgement against the same logical request and execution identity.

## What the test proves

A successful run establishes the following chain across two repositories:

```text
orchestrator V2 dry-run
  -> execution identity created by V2
  -> CandidateCompletionReceiptV1 preserved
  -> jpapt.candidate-completed delivered to external receiver
  -> external receiver validates schema and repository binding
  -> CandidateCompletionAckV1 returned to orchestrator
  -> orchestrator recovers the original receipt
  -> canonical receipt SHA-256 matches
  -> request_execution_id binding matches
  -> ACK binding validation succeeds
  -> lifecycle reaches acknowledged
```

The E2E workflow dispatches V2 directly rather than through Candidate Request Gateway. Therefore the expected execution identity is:

```text
eval-<evaluation_run_id>-<evaluation_run_attempt>
```

The acknowledged lifecycle snapshot, completion receipt, and ACK must all carry that exact identity. A mismatch fails the E2E even if the logical `request_id` and receipt SHA happen to match.

The test does **not** build a candidate package, run ONNX Runtime, launch a GPU, or launch Hugging Face Jobs. `dry_run=true` is asserted again from the final completion receipt before the E2E run can succeed.

## Managed receiver bootstrap

The preferred receiver setup path is:

```text
Actions -> Candidate Receiver Bootstrap -> Run workflow
```

`repository` must name an external `owner/name` repository. The bootstrap installs the reference completion/rejection workflows and their required helper scripts together with:

```text
.jpapt/candidate-receiver.json
```

The canonical list of managed receiver files is source-controlled once in:

```text
config/candidate-receiver-bundle.json
```

`scripts/ci/candidate_receiver_bundle.py` validates that definition and supplies the same path/mapping set to bootstrap, readiness, and E2E preflight. This prevents those workflows from silently drifting to different receiver dependency lists.

The installation manifest is `CandidateReceiverInstallationV1`. It records:

- receiver repository identity;
- orchestrator repository identity;
- exact orchestrator commit used for the installation;
- every managed receiver path and its SHA-256;
- an offset-aware RFC3339 installation timestamp.

The complete receiver bundle, including the manifest, is written as **one Git commit** using the Git Data API and then attached to the target default branch with a non-forced fast-forward ref update. The bootstrap captures the receiver branch head before validating any existing managed files and uses that exact commit as the base tree and parent of the installation commit. If the receiver branch moves after preflight, the non-forced ref update fails rather than rebasing the installation onto unvalidated state. A concurrent change is therefore handled by a safe rerun instead of being silently overwritten.

For an existing managed installation, bootstrap treats the current manifest as an ownership record before changing anything. Every existing managed path is compared with the SHA-256 recorded in that manifest. A missing managed path is repairable; a present path whose bytes differ is treated as possible human or out-of-band modification and bootstrap fails closed rather than overwriting it. This protection applies before stale-bundle convergence.

An older owned manifest that no longer matches the canonical bundle is treated as stale and is converged to the current bundle only after the old managed paths pass the ownership/hash check. Newly required files are added, missing files are repaired, and paths that were managed by the old manifest but were intentionally removed from the canonical bundle are deleted in the same atomic Git tree update. An obsolete path that is already absent is simply treated as already converged.

If no manifest exists, already-present canonical managed files are compared byte-for-byte with the current source. Exact matches are treated as a recoverable prior/partial installation; differing files require explicit `adopt_existing=true` after review.

Receiver Actions variables and secrets are intentionally not mutated by bootstrap. Capability/trust configuration remains an explicit repository-owner operation.

## Receiver repository contract

The current canonical receiver bundle is:

```text
.github/workflows/candidate-completion-receipt.yml
.github/workflows/candidate-request-rejection.yml
scripts/ci/candidate_protocol_common.py
scripts/ci/build-candidate-completion-receipt.py
scripts/ci/build-candidate-completion-ack.py
scripts/ci/build-candidate-request-rejection.py
scripts/ci/validate-candidate-protocol-binding.py
scripts/ci/repository-dispatch-with-retry.sh
```

The managed installation also writes:

```text
.jpapt/candidate-receiver.json
```

During E2E preflight, a managed receiver's manifest is validated, its managed-path set must exactly match the current canonical bundle, and every managed file is fetched from the receiver default branch and checked against the SHA-256 recorded in the manifest. Repository/orchestrator binding must also match the current E2E target and orchestrator. A stale or incomplete manifest fails before V2 is dispatched and directs the operator to rerun `Candidate Receiver Bootstrap`.

For compatibility, an independently installed receiver without `.jpapt/candidate-receiver.json` can still pass existence-based preflight, but every path in the **current** canonical bundle must exist. New installations should use the managed bootstrap.

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
HF_TOKEN
```

`SOURCE_REPO_TOKEN` is used by bootstrap, synthetic E2E preflight, and `Candidate Package Evaluate V2` when delivering completion/rejection events to external repositories. Installing workflow files also requires that this credential has the corresponding repository capability; bootstrap fails rather than silently degrading when GitHub rejects the atomic branch update.

`HF_TOKEN` is used by request resolution and by the readiness audit to prove that the exact Bucket intended for E2E is reachable. Secrets are capabilities; `JPAPT_ORCHESTRATOR_REPOSITORIES` is the receiver-side trust policy. All required capabilities and trust configuration must be present.

## Readiness audit

Before running E2E, run:

```text
Actions -> Candidate Protocol Readiness -> Run workflow
```

Use the same `receipt_repository` and `hf_bucket` that will be passed to `Candidate Protocol E2E`. `Candidate Protocol Readiness` audits the target repository and the request-resolution prerequisite without mutating either GitHub repository or the HF Bucket.

It verifies:

- orchestrator `SOURCE_REPO_TOKEN` and `HF_TOKEN` are configured;
- `hf_bucket` uses `namespace/name` form;
- `hf://buckets/<hf_bucket>/candidates` is listable with `HF_TOKEN`;
- at least one canonical `candidate-NNNNNN` identifier is visible under the candidate collection;
- receiver workflow is reachable;
- a managed installation manifest is structurally valid when present;
- the managed path set exactly matches the current canonical receiver bundle;
- every recorded managed-file hash matches the receiver default branch;
- an unmanaged compatibility receiver contains every current canonical bundle path when unmanaged mode is explicitly allowed;
- receiver `JPAPT_ORCHESTRATOR_REPOSITORIES` contains the current orchestrator;
- receiver secret metadata includes `JPAPT_ACK_TOKEN`.

The HF check is intentionally metadata-only: readiness lists the candidate collection and does not download candidate/model payload bytes. This catches a missing, inaccessible, or empty candidate collection before a synthetic V2 request is dispatched while preserving the dry-run cost boundary.

The audit never reads secret values. A failure to read required metadata is treated as inability to prove readiness. A stale managed receiver fails readiness and should be updated with `Candidate Receiver Bootstrap` before E2E.

## Running the E2E workflow

After receiver bootstrap, receiver-side trust/token configuration, and a successful readiness audit, run:

```text
Actions -> Candidate Protocol E2E -> Run workflow
```

Required inputs:

- `receipt_repository`: external receiver repository, `owner/name`.
- `hf_bucket`: the same existing `namespace/name` Bucket that passed readiness. The E2E run does not download a candidate from it because evaluation is a dry-run, but normal request resolution must still be able to identify a candidate.

Optional inputs:

- `source_repository`: defaults to the orchestrator repository.
- `timeout_seconds`: defaults to 600 and is bounded to 60..1200.

The logical request ID is generated from the outer E2E workflow run:

```text
e2e-<github.run_id>-<github.run_attempt>
```

This is deliberately different from execution identity. V2 is dispatched without a caller-selected execution ID, so the V2 run creates:

```text
eval-<V2 github.run_id>-<V2 github.run_attempt>
```

The V2 submission uses the same bounded `scripts/ci/workflow-dispatch-with-retry.sh` ingress helper as normal Gateway/legacy forwarding. Malformed workflow-dispatch bodies fail before the GitHub API call; transient API failures receive bounded retries.

The workflow derives the 24-character request artifact key using the same SHA-256 rule as normal lifecycle handling, then observes these artifacts:

```text
candidate-lifecycle-<request-key>-running
candidate-lifecycle-<request-key>-completed
candidate-lifecycle-<request-key>-acknowledged
```

The workflow does not guess the evaluation run ID or execution ID. Once `acknowledged` appears, the lifecycle snapshot supplies the exact evaluation run ID, run attempt, receipt SHA-256, receiver identity, and `request_execution_id` used to recover and revalidate canonical evidence.

Final evidence validation requires:

```text
lifecycle.request_id == receipt.request_id == ack.request_id
lifecycle.request_execution_id == receipt.request_execution_id == ack.request_execution_id
request_execution_id == eval-<evaluation_run_id>-<evaluation_run_attempt>
receipt.receipt_repository == requested external receiver
ack.receipt_sha256 == SHA-256(canonical receipt JSON)
receipt.dry_run == true
receipt.conclusion == success
```

## Failure interpretation

A readiness failure on the HF Bucket means the E2E request prerequisite is not usable: the Bucket is malformed, inaccessible with the configured token, or exposes no canonical candidate ID. Fix that before dispatching E2E.

A failure after readiness but before E2E dispatch normally indicates configuration, bootstrap drift, stale receiver installation, or receiver trust/capability problems. A timeout after dispatch means the synthetic request did not reach end-to-end acknowledgement. Inspect the most advanced lifecycle artifact for the request:

```text
running
completed
acknowledged
```

- only `running`: V2 started but no valid completion receipt was observed;
- `completed` without `acknowledged`: the orchestrator has canonical completion evidence but the receiver/ACK path did not complete;
- no `running`: V2 request normalization/resolution failed before the running lifecycle boundary.

An execution-identity mismatch is a protocol binding failure even if the logical `request_id` is the same. Do not merge evidence from separate retries merely because they share `request_id`.

Normal completion reconciliation remains active, so temporary completion dispatch loss may recover during the same E2E window.

## Safety and cost

`Candidate Protocol Readiness` only lists HF Bucket metadata and reads GitHub repository/action metadata. It does not sync candidate payloads, build packages, run ONNX Runtime, or launch Hugging Face Jobs.

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

## Current external blocker

The orchestrator-side harness is implemented. A real success still requires a dedicated second repository with the receiver bundle, allowlist, minimally scoped ACK token, orchestrator delivery capability, and an accessible candidate Bucket. This provisioning is tracked in GitHub Issue #70.

Until that fixture exists, `Candidate Protocol Synthetic E2E` is the zero-network safety net for receipt/ACK/lifecycle/execution-identity bindings. It is not a substitute for proving cross-repository token scopes and callback routing.
