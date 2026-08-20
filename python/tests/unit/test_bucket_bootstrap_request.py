from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts" / "ci" / "normalize-bucket-bootstrap-request.py"
WORKFLOW = ROOT / ".github" / "workflows" / "external-bucket-bootstrap.yml"
SPEC = importlib.util.spec_from_file_location("normalize_bucket_bootstrap_request", HELPER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def resolve_dispatch(payload: str, *, default_namespace: str = ""):
    return MODULE.resolve_request(
        event_name="repository_dispatch",
        payload_json=payload,
        repository_input="",
        namespace_input="",
        private_input="",
        write_input="",
        default_namespace=default_namespace,
    )


def resolve_workflow(
    *,
    repository: str = "owner/repo",
    namespace: str = "ns",
    private: object = "true",
    write: object = "true",
    default_namespace: str = "",
):
    return MODULE.resolve_request(
        event_name="workflow_dispatch",
        payload_json="{}",
        repository_input=repository,
        namespace_input=namespace,
        private_input=private,
        write_input=write,
        default_namespace=default_namespace,
    )


def test_repository_dispatch_defaults_missing_booleans_to_true():
    value = resolve_dispatch('{"repository":"owner/repo","hf_namespace":"ns"}')
    assert value == {
        "repository": "owner/repo",
        "namespace": "ns",
        "private_bucket": True,
        "write_repo_config": True,
    }


def test_repository_dispatch_null_booleans_default_to_true():
    value = resolve_dispatch(
        '{"repository":"owner/repo","hf_namespace":"ns","private_bucket":null,"write_repo_config":null}'
    )
    assert value["private_bucket"] is True
    assert value["write_repo_config"] is True


@pytest.mark.parametrize("field", ["private_bucket", "write_repo_config"])
@pytest.mark.parametrize("bad", ['"yes"', '"1"', "1", "[]", "{}"])
def test_repository_dispatch_rejects_non_boolean_mutation_flags(field: str, bad: str):
    payload = '{"repository":"owner/repo","hf_namespace":"ns","' + field + '":' + bad + "}"
    with pytest.raises(ValueError, match=f"{field} must be true or false"):
        resolve_dispatch(payload)


def test_repository_dispatch_accepts_explicit_false():
    value = resolve_dispatch(
        '{"repository":"owner/repo","hf_namespace":"ns","private_bucket":false,"write_repo_config":false}'
    )
    assert value["private_bucket"] is False
    assert value["write_repo_config"] is False


def test_workflow_dispatch_accepts_typed_string_booleans():
    value = resolve_workflow(private="false", write="false")
    assert value["private_bucket"] is False
    assert value["write_repo_config"] is False


@pytest.mark.parametrize(
    "repository",
    ["./repo", "../repo", "owner/.", "owner/..", "owner/repo/extra", "owner/bad repo"],
)
def test_rejects_ambiguous_repository_identities(repository: str):
    with pytest.raises(ValueError):
        resolve_workflow(repository=repository)


def test_allows_dot_prefixed_repository_segments():
    assert resolve_workflow(repository=".owner/repo")["repository"] == ".owner/repo"
    assert resolve_workflow(repository="owner/.repo")["repository"] == "owner/.repo"


@pytest.mark.parametrize("namespace", [".", "..", "ns/name", "bad ns", ""])
def test_explicit_or_default_namespace_must_be_single_safe_segment(namespace: str):
    if namespace == "":
        with pytest.raises(ValueError):
            resolve_workflow(namespace="", default_namespace="bad ns")
    else:
        with pytest.raises(ValueError):
            resolve_workflow(namespace=namespace)


def test_allows_dot_prefixed_namespace():
    assert resolve_workflow(namespace=".namespace")["namespace"] == ".namespace"


def test_uses_valid_default_namespace_when_explicit_namespace_is_blank():
    value = resolve_workflow(namespace="", default_namespace="default-ns")
    assert value["namespace"] == "default-ns"


def test_repository_dispatch_can_leave_namespace_blank_for_authenticated_inference():
    value = resolve_dispatch('{"repository":"owner/repo"}')
    assert value["namespace"] == ""


def test_rejects_non_string_repository_or_namespace():
    with pytest.raises(ValueError, match="repository and hf_namespace must be strings"):
        resolve_dispatch('{"repository":123,"hf_namespace":"ns"}')
    with pytest.raises(ValueError, match="repository and hf_namespace must be strings"):
        resolve_dispatch('{"repository":"owner/repo","hf_namespace":123}')


def test_rejects_non_object_payload_and_unsupported_event():
    with pytest.raises(ValueError, match="JSON object"):
        resolve_dispatch("[]")
    with pytest.raises(ValueError, match="unsupported bootstrap event"):
        MODULE.resolve_request(
            event_name="push",
            payload_json="{}",
            repository_input="owner/repo",
            namespace_input="ns",
            private_input="true",
            write_input="true",
            default_namespace="",
        )


def test_workflow_uses_normalized_mutation_flags_only_after_resolution():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python scripts/ci/normalize-bucket-bootstrap-request.py resolve" in text
    assert "python scripts/ci/normalize-bucket-bootstrap-request.py namespace" in text
    assert "PRIVATE_BUCKET: ${{ steps.resolve.outputs.private_bucket }}" in text
    assert "WRITE_REPO_CONFIG: ${{ steps.resolve.outputs.write_repo_config }}" in text

    create_start = text.index("      - name: Create or reuse Bucket\n")
    generate_start = text.index("      - name: Generate Bucket and repository metadata\n")
    create_block = text[create_start:generate_start]
    assert "PAYLOAD:" not in create_block
    assert "inputs.private_bucket" not in create_block
    assert "jq -r '.private_bucket" not in create_block
    assert '[[ "$PRIVATE_BUCKET" == "true" || "$PRIVATE_BUCKET" == "false" ]]' in create_block

    write_start = text.index("      - name: Write config to source repository\n")
    summary_start = text.index("      - name: Summary\n")
    write_block = text[write_start:summary_start]
    assert "PAYLOAD:" not in write_block
    assert "inputs.write_repo_config" not in write_block
    assert "jq -r '.write_repo_config" not in write_block
    assert '[[ "$WRITE_REPO_CONFIG" == "true" || "$WRITE_REPO_CONFIG" == "false" ]]' in write_block
