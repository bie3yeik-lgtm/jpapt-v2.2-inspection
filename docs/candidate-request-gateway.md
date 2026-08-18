# Candidate Request Gateway

`Candidate Request Gateway` is the preferred entry point for external candidate evaluation requests.

It separates request planning from execution:

1. normalize the incoming manual or `repository_dispatch` request;
2. assign the current Gateway execution identity;
3. read `.jpapt/hf-bucket.yml` from the source repository when available;
4. resolve and validate the request with the Rust `asr-candidate-request` contract;
5. estimate runtime from completed GitHub Actions history and evaluation provenance;
6. stop after planning by default;
7. dispatch `Candidate Package Evaluate V2` only when `execute=true`;
8. preserve correlated lifecycle/completion evidence after execution terminates.

The protocol distinguishes a caller-visible logical request from one execution attempt. This is required because a caller may intentionally reuse the same `request_id` for a retry.

## Request and execution identity

The external correlation ID is:

```text
request_id
```

The Gateway execution identity is:

```text
request_execution_id = gw-<github.run_id>-<github.run_attempt>
```

These fields have different semantics:

```text
request_id            logical request / retry group
request_execution_id  exactly one Gateway/V2 execution
```

`request_id` is optional. When omitted, normal request normalization generates a correlation ID. When supplied, the caller value is preserved so multiple executions can be grouped deliberately.

`request_execution_id` is **not** caller authority for `repository_dispatch`. Gateway normalization replaces any caller-provided value with the identity of the current Gateway run. When `execute=true`, that `gw-*` value is forwarded to V2 and must remain unchanged through running/completed/acknowledged lifecycle evidence, completion receipt, and ACK.

A direct V2 invocation that is not forwarded by Gateway instead creates:

```text
request_execution_id = eval-<V2 github.run_id>-<V2 github.run_attempt>
```

See `docs/request-execution-identity.md` for storage/query semantics.

## Request event contract

Use event type `jpapt.candidate-request`:

```json
{
  "event_type": "jpapt.candidate-request",
  "client_payload": {
    "request_id": "caller-job-000123",
    "source_repository": "owner/repository",
    "receipt_repository": "owner/repository",
    "candidate_id": "",
    "dataset_source": "auto",
    "suite": "smoke",
    "executor": "github",
    "environment": "linux-cpu",
    "execute": false
  }
}
```

Do not send a trusted execution identity in this payload. The Gateway owns it.

`receipt_repository` is optional. When omitted, it resolves to `source_repository`. It names the repository that receives completion/rejection callback events.

`execute=false` is the recommended first call. It performs request resolution and runtime estimation without candidate download, Docker build, package publication, model evaluation, or HF Jobs compute.

After inspecting the plan, a caller may submit the same logical `request_id` with `execute=true`. This is a **new Gateway execution** and therefore receives a new `request_execution_id`. Logical correlation is preserved without collapsing two executions into one evidence stream.

## Rust request contract

`rust/crates/asr-contracts/src/bin/asr-candidate-request.rs` owns candidate request semantics that previously lived primarily in workflow Bash.

It validates/resolves:

- `request_id` correlation identity;
- `request_execution_id` execution correlation when present;
- `source_repository` as `owner/name`;
- `receipt_repository` as `owner/name`, defaulting to source repository;
- explicit Bucket, source-repository Bucket config, then `<repo>-bucket` convention;
- `candidate-NNNNNN`, repository candidate default, or latest;
- GHCR package naming;
- dataset routing (`auto`, `bucket`, `repository`, `custom`);
- required dataset IDs;
- `smoke`, `parity`, and `probe` suites;
- GitHub or HF Jobs execution;
- Linux CPU/CUDA, macOS CoreML, and Windows DirectML environments;
- environment-to-Execution-Provider mapping;
- environment-to-Python-ORT-package mapping;
- the restriction that HF Jobs execution is Linux-only.

The binary writes normalized values directly to `GITHUB_OUTPUT`, so later orchestration does not repeat these policy decisions.

## Lifecycle boundaries

Gateway/V2 lifecycle states are deliberately not synonyms:

```text
planned
  -> dispatched
  -> running
  -> completed
  -> acknowledged
```

with rejection as the pre-execution failure path:

```text
planned/resolution failure -> rejected
```

Meaning:

- `planned`: Gateway normalization/Rust resolution succeeded;
- `dispatched`: GitHub accepted the V2 workflow dispatch;
- `running`: the actual V2 workflow exists and completed its own Rust request-resolution boundary, with concrete evaluation run ID/attempt;
- `completed`: canonical completion receipt exists;
- `acknowledged`: receiver ACK was validated against the preserved receipt;
- `rejected`: Gateway did not reach accepted execution.

GitHub accepting a workflow dispatch is therefore not treated as proof that evaluation is running.

## Completion event contract

Canonical completion transport is:

```text
event_type = jpapt.candidate-completed
```

The final `completion` job in `candidate-package-evaluate-v2.yml` emits the event after all possible execution jobs reach a terminal state.

The schema is:

```text
contracts/candidate-completion-receipt.schema.json
```

The orchestrator production builder and validator are Rust authorities:

```text
rust/crates/asr-contracts/src/bin/asr-candidate-protocol-build.rs
  receipt

rust/crates/asr-contracts/src/bin/asr-candidate-protocol.rs
  receipt-validate
  receipt-sha
```

`scripts/ci/build-candidate-completion-receipt.py` remains a portable compatibility/parity implementation for receiver bundles and cross-language contract tests; it is not the V2 production completion builder. See `docs/candidate-protocol-runtime-boundary.md` for the full runtime boundary.

A current receipt includes both logical and execution correlation when generated by Gateway/V2:

```json
{
  "schema_version": 1,
  "request_id": "caller-job-000123",
  "request_execution_id": "gw-987654321-1",
  "source_repository": "owner/repository",
  "receipt_repository": "owner/repository",
  "conclusion": "success",
  "dry_run": false,
  "suite": "smoke",
  "executor": "github",
  "environment": "linux-cpu",
  "provider": "CPUExecutionProvider",
  "orchestrator_repository": "bie3yeik-lgtm/jpapt-v2.2-inspection",
  "workflow_file": "candidate-package-evaluate-v2.yml",
  "run_id": 123456789,
  "run_attempt": 1,
  "run_url": "https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/123456789",
  "commit_sha": "0123456789012345678901234567890123456789",
  "requested_candidate_id": "candidate-000123",
  "resolved_candidate_id": "candidate-000123",
  "image_ref": "ghcr.io/bie3yeik-lgtm/repository@sha256:...",
  "image_digest": "sha256:...",
  "result_artifact": "candidate-package-candidate-000123-linux-cpu-smoke",
  "result_uri": null,
  "failed_jobs": [],
  "completed_at": "2026-08-17T00:00:00Z"
}
```

`request_execution_id` remains optional in schema version 1 only for historical compatibility. New Gateway/V2 evidence should contain it. Do not make it mandatory in v1; introduce a new schema version if mandatory execution identity is required later.

`conclusion` is `success`, `failure`, or `cancelled`. A successful non-dry evaluation must carry a resolved candidate ID, immutable image reference/digest, and result artifact name. Failure receipts may contain null artifact fields because failure can occur before candidate/package resolution completes.

For HF Jobs, `result_uri` points to the persistent Bucket result. For GitHub-runner execution, the GitHub artifact name is authoritative and `result_uri` may be null.

The receipt is persisted as a GitHub artifact **before** callback delivery. Callback authentication/receiver failure therefore cannot erase canonical completion evidence.

External callback delivery uses `SOURCE_REPO_TOKEN`. Same-repository delivery may fall back to the workflow `GITHUB_TOKEN` when permissions allow it.

The reference receiver is:

```text
.github/workflows/candidate-completion-receipt.yml
```

It validates schema, receipt destination, external orchestrator allowlist, and then emits an ACK. The receiver intentionally remains portable Python/shell because an arbitrary receipt repository is not required to contain this Rust workspace. ACKs returning to the orchestrator are validated with Rust authority against the preserved receipt, including canonical receipt SHA-256, logical request identity, execution identity when present, receipt repository, and evaluation run ID/attempt.

## Runtime estimator

`scripts/ci/estimate-candidate-runtime.py` replaces fixed-duration assumptions when enough history exists.

For successful historical `candidate-package-evaluate-v2.yml` runs it reads workflow/job timing and matching `evaluation-provenance.json` when available.

For GitHub execution, the estimator considers the durations of:

```text
Resolve request
Build digest-pinned candidate package
target execution job
```

Historical cohorts prefer:

1. same source repository + dataset identity;
2. same source repository;
3. global suite/environment history.

A cohort needs enough samples before it replaces the fallback estimate. The planning estimate uses observed p90 rather than the mean so cache misses and runner variance are not hidden.

Provenance also retains workload-size evidence such as dataset/package/candidate bytes. These are evidence for later size-aware modeling; they are not silently treated as a linear runtime multiplier today.

For HF Jobs, successful HF Jobs history is used when available. External queue delay is not invented when GitHub does not expose it as job duration.

## Recommended external flow

```text
arbitrary GitHub repository
        |
        | repository_dispatch: jpapt.candidate-request
        v
Candidate Request Gateway
        |
        +-- request_id = logical correlation
        +-- request_execution_id = gw-<run>-<attempt>
        +-- source .jpapt/hf-bucket.yml
        +-- Rust request normalization
        +-- provenance-matched runtime estimate
        |
        +-- execute=false --> plan only
        |
        `-- execute=true
                |
                | forwards the same request_execution_id
                v
       Candidate Package Evaluate V2
                |
                +-- running lifecycle with evaluation run identity
                +-- candidate/package/evaluation or dry-run
                |
                v
       CandidateCompletionReceiptV1 artifact
                |
                `-- repository_dispatch: jpapt.candidate-completed
                            |
                            v
                    receipt_repository
                            |
                            `-- ACK -> orchestrator -> acknowledged
```

## Retry and query behavior

Reusing a `request_id` does not overwrite execution history.

Persistent lifecycle storage keeps:

```text
requests/<request-key>/...                       aggregate logical request view
requests/<request-key>/executions/<execution-key>/...  isolated execution view
```

`Candidate Request Status` with only `request_id` chooses the newest lifecycle `updated_at` across executions. Supplying `request_execution_id` restricts the query to exactly one execution.

`Candidate Request Timeline` behaves similarly: no selector returns combined request history; an execution selector produces an execution-scoped `CandidateRequestTimelineV1` whose top-level `request_execution_id` and every event snapshot must agree.

## Compatibility

`candidate-package-evaluate.yml` remains a compatibility entrypoint for existing direct callers. It forwards to V2 and must not reintroduce a second evaluator implementation.

New integrations should use Candidate Request Gateway for external requests. Direct V2 remains useful for controlled/manual orchestration and for the dedicated cross-repository E2E harness.

## CI protection

Protocol protection is distributed across focused suites rather than hidden in one broad workflow:

```text
External Candidate Workflow Contracts
Candidate Request Execution Contracts
Candidate Protocol Production Wiring Contracts
Candidate Dry Run Contracts
Candidate Lifecycle Persist Contracts
Candidate Lifecycle Persist Protocol Authority Contracts
Candidate Lifecycle Execution Storage Contracts
Candidate Request Timeline Contracts
Candidate Protocol Synthetic E2E
Candidate Protocol Surface Contracts
```

The verified `Candidate Request Execution Contracts` run 32032887712 proved orchestrator-owned execution identity, spoof resistance, receipt/ACK/rejection/lifecycle propagation, legacy v1 compatibility, Gateway/V2 wiring, and Rust request tests.

The persistence and synthetic contracts protect the current Rust-authority / portable-receiver boundary. Real Hugging Face lifecycle storage writes and real cross-repository callback routing must not be reported as verified until the manual storage smoke and dedicated external fixture E2E succeed.
