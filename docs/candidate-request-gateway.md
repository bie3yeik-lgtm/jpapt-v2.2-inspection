# Candidate Request Gateway

`Candidate Request Gateway` is the preferred entry point for external candidate evaluation requests.

It separates request planning from execution:

1. normalize the incoming manual or `repository_dispatch` request;
2. read `.jpapt/hf-bucket.yml` from the source repository when available;
3. resolve and validate the request with the Rust `asr-candidate-request` contract;
4. estimate runtime from completed GitHub Actions history;
5. stop after planning by default;
6. dispatch `Candidate Package Evaluate` only when `execute=true`.

This keeps dry-run and execution on the same normalized request instead of maintaining separate interpretations in shell code.

## Dispatch contract

Use event type `jpapt.candidate-request`:

```json
{
  "event_type": "jpapt.candidate-request",
  "client_payload": {
    "source_repository": "owner/repository",
    "candidate_id": "",
    "dataset_source": "auto",
    "suite": "smoke",
    "executor": "github",
    "environment": "linux-cpu",
    "execute": false
  }
}
```

`execute=false` is the recommended first call. It performs request resolution and runtime estimation without candidate download, Docker build, package publication, or model evaluation.

After inspecting the plan, submit the same request with `execute=true`. The gateway sends only normalized inputs to `candidate-package-evaluate.yml` through `workflow_dispatch`.

## Rust request contract

`rust/crates/asr-contracts/src/bin/asr-candidate-request.rs` owns candidate request semantics that previously lived primarily in workflow Bash.

It validates and resolves:

- `source_repository` as `owner/name`;
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

## Empirical runtime estimator

`scripts/ci/estimate-candidate-runtime.py` replaces fixed-duration assumptions when enough history exists.

For successful historical `candidate-package-evaluate.yml` runs it reads:

- workflow runs;
- executed job durations;
- candidate evaluation artifact names.

For GitHub execution, artifact names identify the requested `suite/environment` pair. The estimator sums the durations of:

- `Resolve request`;
- `Build digest-pinned candidate package`;
- the selected execution job.

It then reports sample count, p50, p90, and uses the observed p90 rounded upward as the planning estimate. p90 is intentionally used instead of the mean because CI planning should be conservative in the presence of cache misses and runner variance.

For HF Jobs, the estimator uses successful `Hugging Face Jobs` execution history when available. If no usable historical samples exist, it falls back to the previous conservative suite/environment heuristic and marks the method as `fallback`.

The estimate excludes unpredictable external queue delays when GitHub does not expose them as job execution duration.

## Recommended external flow

```text
arbitrary GitHub repository
        |
        | repository_dispatch: jpapt.candidate-request
        v
Candidate Request Gateway
        |
        +-- source .jpapt/hf-bucket.yml
        +-- Rust request normalization
        +-- historical p50/p90 estimate
        |
        +-- execute=false --> plan only
        |
        `-- execute=true
                |
                v
       Candidate Package Evaluate
                |
                +-- candidate resolution
                +-- digest-pinned OCI package
                +-- smoke/parity/probe
                `-- GitHub runner or HF Jobs
```

## Compatibility

`candidate-package-evaluate.yml` continues to expose its existing direct `workflow_dispatch` and `jpapt.candidate-evaluate` interfaces for compatibility. New integrations should prefer `jpapt.candidate-request` through the gateway because the gateway makes Rust normalization and runtime estimation mandatory before execution.

## CI protection

`External Candidate Workflow Contracts` now checks:

- `candidate-request-gateway.yml` with actionlint;
- `estimate-candidate-runtime.py` with `py_compile`;
- `asr-candidate-request` with `cargo test --locked`;
- the existing generic evaluator, Bash helper, Bucket workflow, candidate workflow, and Dockerfile contract checks.

Changes to request semantics should update the Rust resolver tests and this document together.
