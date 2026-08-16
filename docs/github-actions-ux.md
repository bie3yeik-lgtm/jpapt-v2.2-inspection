# GitHub Actions Usability and Dispatch Design

## 1. Goal

GitHub Actions in this repository must be usable in three modes without introducing separate runtime policy:

1. automatic PR/push CI;
2. a human operator using the GitHub Actions UI;
3. an external system using `repository_dispatch`.

All three modes should converge on the same source-controlled model/HF/runtime contracts.

## 2. Implemented usability improvements

### One external entrypoint

External callers only need to know:

```text
event_type = jpapt.workflow
workflow   = <workflow filename or alias>
inputs     = normal workflow_dispatch inputs
```

They do not need one repository-dispatch event type per workflow.

### Short workflow aliases

The Rust resolver accepts both:

```text
ghcr-evaluate
ghcr-evaluate.yml
```

The alias is derived from the filename and therefore requires no catalog.

### Defaults are completed automatically

External callers may omit values that already have YAML defaults. For example, a GHCR smoke evaluation can normally omit candidate ID, evaluation mode and image tag.

Candidate omission has a second level of defaulting in the evaluation workflow: the latest compatible candidate is resolved from the target Bucket.

### Invalid requests fail before expensive work

The Rust dispatch resolver rejects:

- unknown workflow names;
- unknown inputs;
- missing required inputs;
- invalid choice values;
- invalid boolean values;
- unsafe refs.

This occurs in the lightweight router before Docker pull, model download or evaluation.

### Introspection is available locally

```bash
mise run actions-list
mise run actions-validate
mise run actions-ghcr
```

These commands make the repository itself discoverable without opening every workflow YAML manually.

### Router runs are identifiable

The repository-dispatch router uses a dynamic `run-name` containing the requested workflow/ref and writes the Rust-normalized request into `GITHUB_STEP_SUMMARY`. External automation failures can therefore be diagnosed from the Actions run without reconstructing the original payload manually.

### Heavy work is separated from routing

The repository uses fast contract jobs before expensive jobs wherever practical:

```text
dispatch validation
HF/Docker routing validation
        ↓
Docker/model/dataset work
        ↓
run validation
        ↓
publish
```

This reduces wasted GitHub-hosted runner time.

### Repeated PR Docker builds are suppressed

GitHub's `pull_request.paths` filter evaluates the PR change set, so once a PR contains a Docker change a later docs-only commit can still create another workflow run. `GHCR Build and Publish` therefore adds a second gate for `pull_request/synchronize` events and compares the previous PR head with the new head.

Only changes under:

```text
docker/**
.github/workflows/ghcr-build-publish.yml
```

cause another expensive image rebuild. Other synchronize commits finish at the lightweight gate.

Concurrency is also scoped to the actual image-build job instead of the whole workflow. This prevents a docs-only synchronize run from canceling an in-flight build before the gate can skip, while still allowing a newer real image build for the same package to replace an obsolete one.

### Immutable execution identity

GHCR evaluations resolve human-friendly tags to an OCI digest before execution. The digest, not `latest`, is recorded as the environment identity.

### Automatic identity allocation

Candidate/experiment/config sequence IDs are allocated centrally rather than entered by an operator. Candidate IDs are also auto-selected when omitted.

## 3. Recommended operator flows

### Ordinary code change

Do nothing manually. PR/push CI is the normal interface.

### Validate repository contracts manually

Use:

```text
GHCR Contract Validation
Validate HF Layout
```

before starting expensive model evaluation when changing routing/configuration.

### Evaluate the latest candidate in GHCR

Use `GHCR Environment Evaluation` and normally set only the target when the defaults are appropriate.

Equivalent external request:

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-evaluate",
    "inputs": {
      "target": "parakeet-tdt_ctc-0.6b-ja"
    }
  }
}
```

### Inspect available inputs before automation

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-workflow-dispatch -- \
  describe rust-eval
```

An external integration should discover or validate against this contract during development instead of copying assumptions into its own code.

## 4. GitHub Actions UI limitations that cannot be solved inside workflow YAML

The following are platform limitations rather than repository implementation gaps.

### Dynamic dropdowns

`workflow_dispatch` choice options are static YAML. GitHub does not dynamically populate a choice list from:

- `config/hf-targets/*.toml`;
- an HF Bucket candidate listing;
- GHCR package tags/digests;
- another workflow input.

Therefore `hf_target`, candidate and similar dynamically changing values should remain strings when duplication would otherwise create a second source of truth.

The repository mitigates this with defaults, Bucket auto-resolution and Rust introspection rather than maintaining duplicated static dropdowns.

### Dependent/conditional form fields

The native Run workflow form cannot express a wizard such as:

```text
choose target
  -> dynamically list runtime variants
  -> dynamically list candidates
  -> dynamically restrict evaluation suites
```

A custom GitHub App/web UI could implement this, but it would be a separate product surface and is not introduced here.

### Grouping the Actions sidebar

GitHub controls workflow presentation in the Actions UI. Repository YAML cannot create arbitrary folders/groups in the sidebar.

Naming remains the available organization mechanism.

### Runtime-generated defaults in the UI

A workflow YAML default cannot be calculated from a Bucket or registry at form-render time. Therefore values such as "latest compatible candidate" are represented by a blank input and resolved after the workflow starts.

### Rich input validation before clicking Run workflow

GitHub validates basic input types/choices but not repository-specific formats such as `candidate-NNNNNN` or cross-field constraints. The repository performs those checks immediately after start, primarily in Rust/source-controlled resolvers.

## 5. Improvements intentionally not implemented

### A second dispatch catalog JSON

Rejected because it would duplicate `workflow_dispatch.inputs` and eventually drift from the GitHub UI.

### Static target/candidate choice lists

Rejected because target and Bucket state are dynamic and already have canonical sources elsewhere.

### One giant evaluation workflow

A single UI workflow with every possible provider/evaluator option would reduce the workflow count but create many irrelevant or conditionally incompatible fields. The current separation between GHCR, Python parity, Rust evaluation and provider proof preserves clearer failure semantics.

A future front-end may call the common repository-dispatch API without changing these underlying workflows.

## 6. Further improvements worth considering

These are feasible but should be added only when their operational value justifies additional complexity.

### Reusable workflow extraction

Common evaluation preparation can move to `workflow_call` reusable workflows if duplication between CPU full, parity, Rust and GHCR lanes grows materially. Do not extract merely to reduce YAML line count; provider/runtime boundaries must remain visible.

### GitHub Environments for promotion/release

If production promotion gains human approval requirements, use GitHub Environments and required reviewers around the promotion/release job rather than adding ad-hoc confirmation strings.

### GPU self-hosted evaluation

A CUDA/TensorRT lane can use a labeled self-hosted runner and the same GHCR digest/HF contracts. It should be separate from the current CPU-hosted GHCR lane so runner capability is explicit evidence.

### Custom dispatch UI

If operators need dynamic target/variant/candidate dropdowns, build a thin UI or GitHub App that queries the repository/Bucket and submits the existing `jpapt.workflow` contract. The backend workflow contract does not need to change.

## 7. Design rule for new workflows

A new workflow should:

1. expose `workflow_dispatch` unless it is the repository dispatch router itself;
2. keep user inputs minimal and derive values from source-controlled config/Bucket state where possible;
3. use YAML defaults for stable defaults;
4. validate model-independent policy in Rust rather than shell/Python;
5. avoid reproducing routing tables or candidate mappings in workflow YAML;
6. fail before expensive work when the request is invalid;
7. upload diagnostic artifacts on failure when they materially help diagnosis;
8. use immutable identities for artifacts/environments that can otherwise move;
9. remain reachable through the common repository-dispatch router;
10. update docs when a GitHub platform limitation affects operator behavior.
