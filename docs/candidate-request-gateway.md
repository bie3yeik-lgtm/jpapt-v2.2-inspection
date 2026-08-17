# Candidate Request Gateway

`Candidate Request Gateway` is the preferred entry point for external candidate evaluation requests.

It separates request planning from execution:

1. normalize the incoming manual or `repository_dispatch` request;
2. read `.jpapt/hf-bucket.yml` from the source repository when available;
3. resolve and validate the request with the Rust `asr-candidate-request` contract;
4. estimate runtime from completed GitHub Actions history and evaluation provenance;
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
- candidate evaluation artifact names;
- `evaluation-provenance.json` from the matching artifact when available.

For GitHub execution, artifact names identify the requested `suite/environment` pair. The estimator sums the durations of:

- `Resolve request`;
- `Build digest-pinned candidate package`;
- the selected execution job.

Historical samples are then segmented into cohorts. The preferred cohort is the same source repository and dataset identity. When at least three such samples do not exist, the estimator falls back to the same source repository, then to the global `suite/environment` history. This prevents unrelated external repositories or datasets from dominating the estimate while still allowing sparse projects to benefit from shared history.

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
        +-- source .jpapt/hf-bucket.yml
        +-- Rust request normalization
        +-- provenance-cohort p50/p90 estimate
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
                +-- provenance v2 size evidence
                `-- GitHub runner or HF Jobs
```

## Compatibility

`candidate-package-evaluate.yml` continues to expose its existing direct `workflow_dispatch` and `jpapt.candidate-evaluate` interfaces for compatibility. New integrations should prefer `jpapt.candidate-request` through the gateway because the gateway makes Rust normalization and runtime estimation mandatory before execution.

## CI protection

`External Candidate Workflow Contracts` checks:

- `candidate-request-gateway.yml` with actionlint;
- `estimate-candidate-runtime.py` with `py_compile`;
- `run-candidate-package-evaluation.sh` with `bash -n`;
- `asr-candidate-request` with `cargo test --locked`;
- the existing generic evaluator, Bucket workflow, candidate workflow, and Dockerfile contract checks.

Changes to request semantics, provenance, or estimator cohorts should update the associated contract checks and this document together.
