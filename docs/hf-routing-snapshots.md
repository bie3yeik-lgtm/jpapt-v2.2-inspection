# Hugging Face Routing Snapshots

This document defines the temporal semantics of `HF_TARGETS_JSON`.

## Current-state rule

`HF_TARGETS_JSON` is a **current operational routing snapshot**, not a permanent
model identity registry.

Within one snapshot:

- every target key is unique;
- every `HF_BUCKET` value is unique;
- every target has one current `HF_BUCKET` and one current `HF_MODEL_REPO`;
- therefore a Bucket can be reverse-resolved to exactly one target at execution
  time.

Example current snapshot:

```json
{
  "model-a": {
    "HF_BUCKET": "example/bucket-a",
    "HF_MODEL_REPO": "example/model-a-dev"
  },
  "model-b": {
    "HF_BUCKET": "example/bucket-b",
    "HF_MODEL_REPO": "example/model-b-dev"
  }
}
```

A snapshot that assigns `example/bucket-a` to both targets is invalid.

## Historical reassignment is allowed

The uniqueness rule applies only **inside the same snapshot**.

Assignments may change later because of storage capacity, lifecycle, project
organization, migration, or operational policy.

For example, this is valid over time:

```text
Snapshot T1
model-a -> bucket-a
model-b -> bucket-b

Snapshot T2
model-a -> bucket-c
model-b -> bucket-a
```

`bucket-a` is unique in each snapshot even though its associated target changed
between T1 and T2.

A target may likewise move from `bucket-a` to `bucket-c` without changing the
target's logical identity.

## Why Bucket is not stored in `reference.json`

`reference.json` records model provenance:

```text
development_artifact
upstream
tokenizer
reference implementation
decoder contract
```

`HF_BUCKET` is an operational storage location, not a model provenance identity.
Embedding it in `reference.json` would incorrectly make a mutable routing choice
part of the immutable model contract.

Therefore:

```text
reference.json
  = model/config provenance

HF_TARGETS_JSON
  = current routing

run-context.json
  = execution-time routing snapshot
```

## Execution-time snapshot

Because the current Repository Variable may change after a run, every evaluation
records the routing actually used at execution time:

```text
run-context.json.metadata.hf_target_id
run-context.json.metadata.hf_bucket
run-context.json.metadata.hf_model_repo
```

Python and Rust evaluators both capture these values from the resolved workflow
environment.

The allocation README written under `candidates/` or `experiments/` also records
the Bucket and target seen at allocation time. That relationship is explicitly a
snapshot, not a permanent association.

## Reproducing an old run

Do not use the current `HF_TARGETS_JSON` to infer where an old run lived.

Use the run itself:

```text
metadata.hf_bucket
  -> historical Bucket used for the run

revisions.config_version
  -> immutable configuration set inside that Bucket

artifact.candidate_id
  -> exact candidate artifact selected

metadata.experiment_id
  -> logical experiment grouping
```

Reproduction flow:

```bash
export HF_BUCKET="<run-context.metadata.hf_bucket>"
export HF_CONFIG_VERSION="<run-context.revisions.config_version>"

bash scripts/hf/hf-fetch-revisions.sh
bash scripts/hf/hf-fetch-candidate.sh "<run-context.artifact.candidate_id>"
```

Then compare the stored artifact SHA-256 and revision bundle SHA-256 before
accepting the reproduction.

## Current resolver behavior

`scripts/ci/resolve-hf-target.py` validates the supplied `HF_TARGETS_JSON` as one
snapshot.

It rejects:

- malformed target entries;
- missing `HF_BUCKET` or `HF_MODEL_REPO`;
- duplicate `HF_BUCKET` values in the same snapshot;
- Bucket values not present in the current snapshot.

It does **not** compare the current mapping with an older mapping and does not
reject a target because its Bucket changed historically.

This means changing a Repository Variable from:

```json
"model-a": {"HF_BUCKET": "example/bucket-a", ...}
```

to:

```json
"model-a": {"HF_BUCKET": "example/bucket-c", ...}
```

is a valid routing update.

## Sequential ID implications

Candidate and experiment numeric sequences are scoped to a Bucket collection:

```text
<bucket>/candidates/
<bucket>/experiments/
```

If a target moves to another Bucket, new allocations continue from the maximum
sequence already present in the **destination Bucket collection**, not from the
old target's previous Bucket.

This is intentional. The sequence identifies an object within the physical
Bucket lifecycle; it is not a globally unique target counter.

Historical objects remain addressable by the Bucket snapshot recorded in their
run/allocation metadata.

## Operational invariants

1. `HF_BUCKET` values are unique within the current `HF_TARGETS_JSON` snapshot.
2. Bucket assignments may change between snapshots.
3. Bucket identity is never treated as permanent target identity.
4. `reference.json` does not contain `HF_BUCKET`.
5. every run records the actual Bucket used at execution time.
6. historical reproduction uses the run's stored Bucket, not the current
   Repository Variable.
7. sequential IDs continue from the destination Bucket's existing maximum after
   a routing move.
