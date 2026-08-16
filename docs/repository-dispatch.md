# Repository Dispatch

## Purpose

Every GitHub Actions workflow in this repository can be started from an external system through a single `repository_dispatch` contract.

The canonical entrypoint is:

```text
.github/workflows/repository-dispatch.yml
```

It listens for:

```text
event_type = jpapt.workflow
```

and routes the request to the requested workflow through GitHub's `workflow_dispatch` API.

This avoids copying `client_payload` parsing, validation, defaulting, and security policy into every workflow file.

## Request shape

Send:

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-evaluate.yml",
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
| `workflow` | yes | file name under `.github/workflows/` |
| `ref` | no | target ref for the downstream `workflow_dispatch`; default `main` |
| `inputs` | no | JSON object containing the downstream workflow's normal manual inputs |

The router rejects:

- paths instead of workflow filenames;
- unknown workflow files;
- self-dispatch to `repository-dispatch.yml`;
- non-object `inputs`;
- workflows that do not expose `workflow_dispatch`.

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
      "workflow":"cpu-full-eval.yml",
      "ref":"main",
      "inputs":{
        "hf_target":"parakeet-tdt_ctc-0.6b-ja",
        "candidate_id":"",
        "runtime_variant":"ctc"
      }
    }
  }'
```

The token used by the external caller must be allowed to create repository dispatch events for this repository.

## Supported workflows

The router is intentionally generic. All workflow files other than the router itself expose `workflow_dispatch`, including normal CI workflows that were previously path-trigger-only.

Current routable workflows include:

```text
capsule-interop.yml
cpu-full-eval.yml
cross-platform-parity.yml
ghcr-audit.yml
ghcr-build-publish.yml
ghcr-contracts.yml
ghcr-evaluate.yml
hf-central-allocator.yml
provider-strict-probes.yml
public-model-e2e.yml
python-unit.yml
rust-ci.yml
rust-eval.yml
rust-release.yml
validate-hf-layout.yml
```

When a workflow adds or renames manual inputs, the repository-dispatch API does not need a new parser. The caller sends the same keys through `client_payload.inputs`.

## Security model

The router has:

```yaml
permissions:
  contents: read
  actions: write
```

It does not receive or forward arbitrary secrets. Downstream workflows resolve their own repository secrets, variables, permissions, and environments in the normal GitHub Actions execution context.

The requested workflow must already exist in `.github/workflows/`; repository dispatch cannot inject arbitrary YAML or shell commands.

## Relationship to direct workflow_dispatch

These two operations are equivalent in intent:

```text
external system
  -> repository_dispatch jpapt.workflow
  -> Repository Dispatch Router
  -> workflow_dispatch
  -> target workflow
```

and:

```text
operator / GitHub API
  -> workflow_dispatch
  -> target workflow
```

Therefore `workflow_dispatch` remains the workflow-level input contract, while `repository_dispatch` is the repository-level external integration contract.
