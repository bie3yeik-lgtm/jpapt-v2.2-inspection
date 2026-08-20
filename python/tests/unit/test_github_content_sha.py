from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts" / "ci" / "github-content-sha.py"
WORKFLOW = ROOT / ".github" / "workflows" / "external-bucket-bootstrap.yml"
RECEIVER_WORKFLOW = ROOT / ".github" / "workflows" / "candidate-receiver-bootstrap.yml"
SPEC = importlib.util.spec_from_file_location("github_content_sha", HELPER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, status: int, payload: object):
        self.status = status
        self._raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._raw


def opener_for(status: int, payload: object, *, expected_suffix: str | None = None):
    def opener(request, timeout=0):
        suffix = expected_suffix or "/repos/owner/repo/contents/.jpapt/hf-bucket.yml"
        assert request.full_url.endswith(suffix)
        assert timeout == 20
        assert request.headers["Authorization"] == "Bearer token"
        return FakeResponse(status, payload)

    return opener


def test_success_returns_canonical_existing_sha():
    sha = "a" * 40
    assert (
        MODULE.fetch_content_sha(
            "owner/repo",
            ".jpapt/hf-bucket.yml",
            "token",
            opener=opener_for(200, {"sha": sha}),
        )
        == sha
    )


def test_immutable_ref_is_encoded_into_contents_lookup():
    sha = "b" * 40
    ref = "c" * 40
    assert (
        MODULE.fetch_content_sha(
            "owner/repo",
            ".jpapt/hf-bucket.yml",
            "token",
            ref=ref,
            opener=opener_for(
                200,
                {"sha": sha},
                expected_suffix=f"/repos/owner/repo/contents/.jpapt/hf-bucket.yml?ref={ref}",
            ),
        )
        == sha
    )


@pytest.mark.parametrize("ref", ["main", "A" * 40, "a" * 39, "../main"])
def test_rejects_non_immutable_ref_before_network(ref: str):
    called = False

    def opener(request, timeout=0):
        nonlocal called
        called = True
        return FakeResponse(200, {"sha": "a" * 40})

    with pytest.raises(ValueError, match="immutable lowercase 40-hex"):
        MODULE.fetch_content_sha(
            "owner/repo",
            ".jpapt/hf-bucket.yml",
            "token",
            ref=ref,
            opener=opener,
        )
    assert not called


def test_only_http_404_is_treated_as_missing():
    def opener(request, timeout=0):
        raise HTTPError(request.full_url, 404, "Not Found", None, io.BytesIO(b"{}"))

    assert MODULE.fetch_content_sha("owner/repo", ".jpapt/hf-bucket.yml", "token", opener=opener) is None


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_http_errors_other_than_404_fail_closed(status: int):
    def opener(request, timeout=0):
        raise HTTPError(request.full_url, status, "error", None, io.BytesIO(b"{}"))

    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        MODULE.fetch_content_sha("owner/repo", ".jpapt/hf-bucket.yml", "token", opener=opener)


def test_transport_failure_fails_closed():
    def opener(request, timeout=0):
        raise URLError("offline")

    with pytest.raises(RuntimeError, match="transport failure"):
        MODULE.fetch_content_sha("owner/repo", ".jpapt/hf-bucket.yml", "token", opener=opener)


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        [],
        {},
        {"sha": "A" * 40},
        {"sha": "a" * 39},
        {"sha": 123},
    ],
)
def test_malformed_success_response_fails_closed(payload: object):
    with pytest.raises(RuntimeError):
        MODULE.fetch_content_sha(
            "owner/repo",
            ".jpapt/hf-bucket.yml",
            "token",
            opener=opener_for(200, payload),
        )


def test_unexpected_non_error_status_fails_closed():
    with pytest.raises(RuntimeError, match="unexpected HTTP 204"):
        MODULE.fetch_content_sha(
            "owner/repo",
            ".jpapt/hf-bucket.yml",
            "token",
            opener=opener_for(204, {}),
        )


@pytest.mark.parametrize("repository", ["./repo", "owner/..", "owner/repo/extra", "bad repo"])
def test_rejects_unsafe_repository_before_network(repository: str):
    called = False

    def opener(request, timeout=0):
        nonlocal called
        called = True
        return FakeResponse(200, {"sha": "a" * 40})

    with pytest.raises(ValueError):
        MODULE.fetch_content_sha(repository, ".jpapt/hf-bucket.yml", "token", opener=opener)
    assert not called


@pytest.mark.parametrize("path", ["", "/absolute", "trailing/", "a//b", "a/../b", "a/./b", "bad path"])
def test_rejects_unsafe_content_path_before_network(path: str):
    called = False

    def opener(request, timeout=0):
        nonlocal called
        called = True
        return FakeResponse(200, {"sha": "a" * 40})

    with pytest.raises(ValueError):
        MODULE.fetch_content_sha("owner/repo", path, "token", opener=opener)
    assert not called


def test_requires_token_before_network():
    with pytest.raises(ValueError, match="GH_TOKEN is required"):
        MODULE.fetch_content_sha("owner/repo", ".jpapt/hf-bucket.yml", "")


def test_bootstrap_workflow_uses_fail_closed_reader_before_put():
    text = WORKFLOW.read_text(encoding="utf-8")
    write_start = text.index("      - name: Write config to source repository\n")
    summary_start = text.index("      - name: Summary\n")
    block = text[write_start:summary_start]
    reader = "python scripts/ci/github-content-sha.py"
    put = "--method PUT"
    assert reader in block
    assert "2>/dev/null || true" not in block
    assert block.index(reader) < block.index(put)
    assert 'if [[ "$existing" == "missing" ]]' in block


def test_receiver_bootstrap_uses_pinned_fail_closed_content_reads():
    text = RECEIVER_WORKFLOW.read_text(encoding="utf-8")
    assert "2>/dev/null || true" not in text
    assert text.count("python scripts/ci/github-content-sha.py") >= 3
    assert '--ref "$validated_head_sha"' in text
    assert '--ref "$head_sha"' in text
    assert '--ref "$TARGET_COMMIT"' in text
    assert "TARGET_COMMIT: ${{ steps.install.outputs.target_commit }}" in text
    assert '?ref=$TARGET_COMMIT" --jq .content' in text
    assert "repository must not contain dot-only path segments" in text
