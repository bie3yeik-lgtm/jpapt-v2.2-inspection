# Candidate Request Gateway

`Candidate Request Gateway` is the preferred entry point for external candidate evaluation requests.

It separates request planning from execution:

1. normalize the incoming manual or `repository_dispatch` request;
2. read `.jpapt/hf-bucket.yml` from the source repository when available;
3. resolve and validate the request with the Rust `asr-candidate-request` contract;
4. estimate runtime from completed GitHub Actions history and evaluation provenance;
5. stop after planning by default;
6. dispatch `Candidate Package Evaluate V2` only when `execute=true`;
7. emit a correlated completion receipt after execution terminates.

This keeps dry-run, execution, and completion on one normalized request identity instead of maintaining separate interpretations in workflow shell code.

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

`request_id` is optional. When omitted, the gateway generates `gh-<run-id>-<attempt>`. It is preserved unchanged through V2 execution and the completion receipt.

`receipt_repository` is optional. When omitted, it resolves to `source_repository`. It names the repository that receives the completion `repository_dispatch` event.

`execute=false` is the recommended first call. It performs request resolution and runtime estimation without candidate download, Docker build, package publication, or model evaluation.

After inspecting the plan, submit the same request with `execute=true`. The gateway sends only normalized inputs to `candidate-package-evaluate-v2.yml` through `workflow_dispatch`.

## Rust request contract

`rust/crates/asr-contracts/src/bin/asr-candidate-request.rs` owns candidate request semantics that previously lived primarily in workflow Bash.

It validates and resolves:

- `request_id` correlation identity;
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
- the environment-to-Execution-Provider mapping;
- the environment-to-Python-ORT-package mapping;
- the restriction that HF Jobs execution is Linux-only.

The binary writes normalized values directly to `GITHUB_OUTPUT`, so later orchestration does not repeat these policy decisions.

## Completion event contract

Canonical completion transport:

```text
event_type = jpapt.candidate-completed
```

The event is emitted by the final `completion` job in `candidate-package-evaluate-v2.yml` after all possible execution jobs have reached a terminal state.

The exact `client_payload` schema is source-controlled at:

```text
contracts/candidate-completion-receipt.schema.json
```

and is built/validated by:

```text
scripts/ci/build-candidate-completion-receipt.py
```

Example receipt:

```json
{
  "schema_version": 1,
  "request_id": "caller-job-000123",
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
  "requested_candidate_id": "latest",
  "resolved_candidate_id": "candidate-000123",
  "image_ref": "ghcr.io/bie3yeik-lgtm/repository@sha256:...",
  "image_digest": "sha256:...",
  "result_artifact": "candidate-package-candidate-000123-linux-cpu-smoke",
  "result_uri": null,
  "failed_jobs": [],
  "completed_at": "2026-08-17T00:00:00Z"
}
```

`conclusion` is one of `success`, `failure`, or `cancelled`. A successful non-dry evaluation must carry a resolved candidate ID, immutable image reference/digest, and result artifact name. Failure receipts may contain null artifact fields because the failure can occur before candidate/package resolution completes.

For HF Jobs, `result_uri` points to the persistent Bucket result. For GitHub-runner execution, the GitHub artifact name is authoritative and `result_uri` may be null.

The receipt is persisted as a GitHub artifact **before** callback delivery. Therefore callback authentication or receiver failure cannot erase the completion evidence. Callback delivery failure still fails the final completion job, making integration breakage visible.

External callback delivery uses `SOURCE_REPO_TOKEN`. If the receipt target is the orchestrator repository itself, the workflow can fall back to its `GITHUB_TOKEN` with job-level `contents: write` permission.

This repository also contains a reference receiver:

```text
.github/workflows/candidate-completion-receipt.yml
```

It listens for `jpapt.candidate-completed`, validates the payload, and preserves the received receipt as an artifact. External repositories can implement the same event type and schema without copying any execution logic.

## Empirical runtime estimator

`scripts/ci/estimate-candidate-runtime.py` replaces fixed-duration assumptions when enough history exists.

For successful historical `candidate-package-evaluate-v2.yml` runs it reads:

- workflow runs;
- executed job durations;
- candidate evaluation artifact names;
- `evaluation-provenance.json` from the matching artifact when available.

For GitHub execution, artifact names identify the requested `suite/environment` pair. The estimator sums the durations of:

- `Resolve request`;
- `Build digest-pinned candidate package`;
- the selected execution job.

Historical samples are segmented into cohorts. The preferred cohort is the same source repository and dataset identity. When at least three such samples do not exist, the estimator falls back to the same source repository, then to the global `suite/environment` history. This prevents unrelated external repositories or datasets from dominating the estimate while still allowing sparse projects to benefit from shared history.

The estimator reports selected sample count, available sample count, cohort, p50, and p90, and uses the observed p90 rounded upward as the planning estimate. p90 is intentionally used instead of the mean because CI planning should be conservative in the presence of cache misses and runner variance.

Evaluation provenance schema version 2 also records workload-size evidence for future prediction refinement:

- `dataset_bytes` and `dataset_files` for every GitHub evaluation;
- `package_bytes` for Linux OCI evaluation;
- `candidate_bytes` and `candidate_files` for native macOS/Windows evaluation.

The gateway surfaces cohort median size evidence when historical artifacts contain it. These fields are evidence, not yet a linear runtime scaling factor: they are retained so later estimators can introduce size-aware regression without changing the artifact contract again.

For HF Jobs, the estimator uses successful `Hugging Face Jobs` execution history when available. If no usable historical samples exist, it falls back to the conservative suite/environment heuristic and marks the method as `fallback`.

The estimate excludes unpredictable external queue delays when GitHub does not expose them as job execution duration.

## Recommended external flow

```text
arbitrary GitHub repository
        |
        | repository_dispatch: jpapt.candidate-request
        v
Candidate Request Gateway
        |
        +-- request_id / receipt_repository
        +-- source .jpapt/hf-bucket.yml
        +-- Rust request normalization
        +-- provenance-cohort p50/p90 estimate
        |
        +-- execute=false --> plan only
        |
        `-- execute=true
                |
                v
       Candidate Package Evaluate V2
                |
                +-- candidate resolution
                +-- digest-pinned OCI package
                +-- smoke/parity/probe
                +-- provenance v2 size evidence
                +-- GitHub runner or HF Jobs
                |
                v
       CandidateCompletionReceiptV1 artifact
                |
                `-- repository_dispatch: jpapt.candidate-completed
                            |
                            v
                    receipt_repository
```

## Compatibility

`candidate-package-evaluate.yml` remains as a compatibility path for existing direct callers. New integrations should use `jpapt.candidate-request` through the gateway and `candidate-package-evaluate-v2.yml` because the V2 path makes Rust normalization, runtime estimation, request correlation, and completion receipts mandatory.

## CI protection

`External Candidate Workflow Contracts` checks:

- the gateway, V2 evaluation workflow, completion receiver, Bucket workflow, and compatibility workflow with actionlint;
- all candidate Python helpers with `py_compile`;
- `run-candidate-package-evaluation.sh` with `bash -n`;
- the completion receipt JSON Schema as parseable JSON;
- a complete success receipt build/validate/dispatch-envelope round trip;
- `asr-candidate-request` with `cargo test --locked`;
- the candidate Dockerfile with `docker buildx build --check`.

Changes to request semantics, receipt semantics, provenance, or estimator cohorts should update the associated contract checks and this document together.
