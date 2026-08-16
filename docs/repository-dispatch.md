# Repository Dispatch

## Purpose

Every GitHub Actions workflow in this repository can be started from an external system through one repository-level contract.

The canonical entrypoint is:

```text
.github/workflows/repository-dispatch.yml
```

It listens for:

```text
event_type = jpapt.workflow
```

and routes the request to the selected workflow through GitHub's `workflow_dispatch` API.

The workflow YAML remains the source of truth for manual inputs. Rust reads those YAML input definitions directly; there is no second JSON catalog to maintain.

## GitHub platform constraints

`repository_dispatch` and `workflow_dispatch` are GitHub platform events, so two upstream rules matter operationally:

1. the workflow that receives `repository_dispatch` must exist on the repository default branch;
2. a workflow must expose `workflow_dispatch` to be started through the downstream workflow-dispatch API / Run workflow UI.

Therefore this router becomes an external integration endpoint after the router workflow exists on `main`. A branch cannot introduce a brand-new router and expect GitHub to receive `repository_dispatch` through that branch before merge.

GitHub currently limits `workflow_dispatch` to 25 top-level inputs and 65,535 characters of input payload. This repository intentionally keeps workflow inputs far below those limits and derives candidate IDs, runtime defaults, Bucket routing and artifact identity rather than exposing them all as manual fields.

## Rust implementation

The canonical resolver is:

```text
rust/crates/asr-contracts/src/bin/asr-workflow-dispatch.rs
```

Commands:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-workflow-dispatch -- list
cargo run --quiet --locked -p asr-contracts --bin asr-workflow-dispatch -- describe ghcr-evaluate
cargo run --quiet --locked -p asr-contracts --bin asr-workflow-dispatch -- validate
cargo run --quiet --locked -p asr-contracts --bin asr-workflow-dispatch -- \
  resolve --workflow ghcr-evaluate --ref main --inputs-json '{}'
```

Equivalent mise helpers are available:

```bash
mise run actions-list
mise run actions-validate
mise run actions-ghcr
```

The resolver performs:

- workflow filename/alias resolution;
- `workflow_dispatch` presence validation;
- YAML-defined required input validation;
- YAML-defined default completion;
- `choice` option validation;
- boolean type validation;
- unknown-input rejection;
- unsafe Git ref rejection;
- final GitHub workflow-dispatch API body generation.

This moves dispatch policy out of shell/jq while retaining GitHub workflow YAML as the authoritative UI/input contract.

The parser intentionally accepts the workflow-input YAML forms currently used by this repository. `ghcr-contracts.yml` runs the parser against every workflow, so introducing a new YAML input form that the Rust policy layer does not understand fails the fast contract gate rather than silently bypassing validation.

## Request shape

A minimal request is:

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-evaluate"
  }
}
```

`workflow` accepts either:

```text
ghcr-evaluate
ghcr-evaluate.yml
```

The filename stem is the canonical short alias.

A fully specified request can be:

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-evaluate",
    "ref": "main",
    "inputs": {
      "target": "parakeet-tdt_ctc-0.6b-ja",
      "candidate_id": "",
      "runtime_variant": "ctc",
      "evaluation": "smoke",
      "image_tag": "latest"
    }
  }
}
```

Fields:

| field | required | meaning |
|---|---:|---|
| `workflow` | yes | workflow filename or filename-stem alias |
| `ref` | no | downstream `workflow_dispatch` ref; default `main` |
| `inputs` | no | JSON object; omitted values are completed from workflow YAML defaults |

`inputs: null` and omitted `inputs` are normalized to `{}` before Rust validation.

## Validation behavior

The router rejects:

- unknown workflow aliases/files;
- self-dispatch to `repository-dispatch.yml`;
- workflows without `workflow_dispatch`;
- unknown input keys;
- missing required inputs without defaults;
- values outside a `choice` list;
- non-boolean values for boolean inputs;
- unsafe or malformed Git refs.

The router does not reproduce defaults or option lists in shell. These are parsed from the selected workflow's own `workflow_dispatch.inputs` block.

For normal automation, prefer `ref: main`. A non-default ref is syntactically validated by the router, but the external integration should treat branch-specific workflow-schema changes carefully: the router policy itself runs from the default-branch workflow contract, while the downstream workflow executes at the requested ref.

## Example API call

```bash
curl -L \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/bie3yeik-lgtm/jpapt-v2.2-inspection/dispatches \
  -d '{
    "event_type":"jpapt.workflow",
    "client_payload":{
      "workflow":"cpu-full-eval",
      "inputs":{
        "hf_target":"parakeet-tdt_ctc-0.6b-ja"
      }
    }
  }'
```

The external caller token must be allowed to create repository dispatch events for this repository.

## Supported workflows

The router is generic. Every workflow other than the router itself exposes `workflow_dispatch` and is checked by the Rust `validate` command.

Do not maintain a handwritten workflow list here. Use:

```bash
mise run actions-list
```

This avoids docs becoming stale when workflows are added or renamed.

## Security model

The router has only:

```yaml
permissions:
  contents: read
  actions: write
```

It does not forward arbitrary secrets. Downstream workflows resolve their own repository secrets, variables, permissions, and environments in the normal GitHub Actions execution context.

The requested workflow must already exist in `.github/workflows/`; repository dispatch cannot inject arbitrary YAML or arbitrary shell commands.

## Relationship to direct workflow_dispatch

The two paths intentionally converge on the same workflow input contract:

```text
external system
  -> repository_dispatch jpapt.workflow
  -> Repository Dispatch Router
  -> Rust validation/default completion
  -> workflow_dispatch
  -> target workflow
```

and:

```text
operator / GitHub UI / GitHub API
  -> workflow_dispatch
  -> target workflow
```

Therefore:

```text
workflow_dispatch.inputs = canonical workflow-level input schema
repository_dispatch       = repository-level integration transport
Rust resolver              = validation/default/normalization layer
```

No separate dispatch schema should be introduced unless GitHub's workflow YAML can no longer express a required constraint.
