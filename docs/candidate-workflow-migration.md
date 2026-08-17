# Candidate workflow migration policy

The canonical candidate orchestration path is:

```text
Candidate Request Gateway
  -> Candidate Package Evaluate V2
  -> completion / rejection protocol
  -> acknowledgement
  -> lifecycle persistence
```

`.github/workflows/candidate-package-evaluate.yml` remains only as a frozen compatibility entrypoint for existing callers of `jpapt.candidate-evaluate` and the original manual workflow inputs.

## Policy

New protocol or orchestration features MUST be implemented in the Gateway/V2 path. The legacy workflow must not gain independent versions of lifecycle, completion, acknowledgement, persistence, or receiver-bootstrap behavior.

The following common manual inputs are contract-frozen between legacy and V2:

```text
source_repository
hf_bucket
candidate_id
package_name
dataset_source
dataset_id
suite
executor
environment
hf_flavor
hf_jobs_image
dry_run
```

V2 additionally owns protocol correlation inputs:

```text
request_id
receipt_repository
```

`Candidate Legacy Compatibility` runs `scripts/ci/check-candidate-workflow-compatibility.py` and fails when the common input type, required flag, default, or choice options drift between the two workflow files. It also verifies that the legacy repository-dispatch event `jpapt.candidate-evaluate` remains present while compatibility is supported.

## Why the legacy implementation is not immediately replaced

The legacy workflow historically represents an entire synchronous evaluation run. Replacing it with a one-shot dispatcher would preserve the filename and inputs but change the meaning of the workflow run conclusion: a successful wrapper run would prove only that another workflow was dispatched, not that evaluation completed.

Until callers are migrated or V2 is made safely reusable without changing that run-level semantic, the legacy implementation remains frozen rather than silently changing behavior.

## Migration target

Callers should move to:

```text
jpapt.candidate-request
```

through `Candidate Request Gateway`, or invoke `Candidate Package Evaluate V2` directly when they intentionally do not need Gateway planning.

The Gateway/V2 path provides request IDs, explicit receipt destinations, rejection semantics, completion receipts, ACK validation, lifecycle snapshots, persistence, receiver bootstrap/readiness, and cross-repository synthetic E2E coverage.

Once no external caller depends on the legacy run-level semantics, the old workflow can be replaced by a compatibility adapter or removed in a versioned breaking change.
